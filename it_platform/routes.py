from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from .auth import require_roles
from .employees import DirectoryUnavailable, employee_options, lookup
from .models import AssetCodeCounter, Asset, AssetService, Assignment, Audit, Ticket, User, audit, db, now

bp = Blueprint("main", __name__)
CATEGORIES = ["Computadora", "Laptop", "Monitor", "Impresora", "Tablet", "Red", "Otro"]
STATUSES = {"available": "Disponible", "assigned": "Asignado", "repair": "En reparación", "retired": "Dado de baja"}


@bp.app_context_processor
def context():
    return {"statuses": STATUSES, "categories": CATEGORIES,
            "is_it": bool(g.user and g.user.role in ("admin", "technician"))}


@bp.get("/")
@require_roles()
def home():
    counts = None
    if g.user.role in ("admin", "technician"):
        counts = {label: db.session.scalar(db.select(db.func.count()).select_from(Asset).where(Asset.status == state)) for state, label in STATUSES.items()}
    return render_template("home.html", counts=counts)


@bp.get("/employees")
@require_roles("admin", "technician")
def employees():
    rows, error = [], None
    query = request.args.get("q", "").strip()[:100]
    try:
        rows = lookup(query)
    except DirectoryUnavailable as exc:
        error = str(exc)
    return render_template("employees.html", rows=rows, error=error, query=query)


@bp.get("/assets")
@require_roles()
def assets():
    query = request.args.get("q", "").strip()[:100]
    stmt = db.select(Asset)
    if g.user.role == "requester":
        stmt = stmt.join(Assignment).where(Assignment.employee_no == g.user.employee_no,
                                          Assignment.ended_at.is_(None)) if g.user.employee_no else stmt.where(db.false())
    if query:
        stmt = stmt.where(or_(Asset.alias.contains(query), Asset.code.contains(query), Asset.serial.contains(query), Asset.model.contains(query)))
    rows = db.session.scalars(stmt.order_by(Asset.code).limit(200)).all()
    return render_template("assets.html", rows=rows, query=query)


@bp.route("/assets/new", methods=["GET", "POST"])
@require_roles("admin", "technician")
def asset_new():
    return save_asset_form()


@bp.route("/assets/<int:asset_id>/edit", methods=["GET", "POST"])
@require_roles("admin", "technician")
def asset_edit(asset_id):
    return save_asset_form(db.get_or_404(Asset, asset_id))


def next_asset_code():
    # Initialize and lock one shared row, even when the first requests overlap.
    table = AssetCodeCounter.__table__
    if db.session.get_bind().dialect.name == "mysql":
        from sqlalchemy.dialects.mysql import insert
        stmt = insert(table).values(id=1, last_number=0)
        db.session.execute(stmt.on_duplicate_key_update(id=table.c.id))
    else:
        from sqlalchemy.dialects.sqlite import insert
        db.session.execute(insert(table).values(id=1, last_number=0).on_conflict_do_nothing())
    counter = db.session.scalar(db.select(AssetCodeCounter).where(
        AssetCodeCounter.id == 1).with_for_update())
    codes = db.session.scalars(db.select(Asset.code)).all()
    highest = max((int(code) for code in codes if code.isascii() and code.isdecimal()), default=0)
    counter.last_number = max(counter.last_number, highest) + 1
    return f"{counter.last_number:04d}"


def save_asset_form(asset=None):
    if request.method == "POST":
        fields = {k: request.form.get(k, "").strip() for k in ("code", "alias", "serial", "category", "brand", "model", "specs", "location")}
        if asset is None:
            fields["code"] = ""  # New codes are assigned by the server when saving.
        limits = {"alias": 120, "code": 50, "serial": 100, "brand": 80, "model": 100, "specs": 5000, "location": 120}
        if (asset is not None and not fields["code"]) or fields["category"] not in CATEGORIES or any(len(fields[k]) > limit for k, limit in limits.items()):
            flash("Revisa los campos y sus longitudes.", "error")
        else:
            fields["serial"] = fields["serial"] or None
            creating = asset is None
            changed = []
            if not creating:
                changed = [key for key, value in fields.items() if getattr(asset, key) != value]
                for key, value in fields.items():
                    setattr(asset, key, value)
            try:
                if creating:
                    fields["code"] = next_asset_code()
                    asset = Asset(**fields)
                    db.session.add(asset)
                db.session.flush()
                if creating:
                    audit("asset.create", asset.id)
                else:
                    for key in changed:
                        audit("asset.update." + key, asset.id)
                db.session.commit()
                flash("Equipo registrado." if creating else "Datos del equipo actualizados.")
                return redirect(url_for("main.asset_detail", asset_id=asset.id))
            except IntegrityError:
                db.session.rollback()
                if creating:
                    asset = None
                flash("El código o número de serie ya está registrado.", "error")
    return render_template("asset_form.html", asset=asset)


def accessible_asset(asset_id):
    asset = db.get_or_404(Asset, asset_id)
    if g.user.role == "requester":
        assignment = db.session.scalar(db.select(Assignment).where(Assignment.asset_id == asset_id,
            Assignment.employee_no == g.user.employee_no, Assignment.ended_at.is_(None))) if g.user.employee_no else None
        if not assignment:
            abort(403)
    return asset


@bp.get("/assets/<int:asset_id>")
@require_roles()
def asset_detail(asset_id):
    asset = accessible_asset(asset_id)
    history = db.session.scalars(db.select(Assignment).where(Assignment.asset_id == asset.id).order_by(Assignment.id.desc())).all() if g.user.role != "requester" else []
    tickets_query = db.select(Ticket).where(Ticket.asset_id == asset.id)
    if g.user.role == "requester":
        tickets_query = tickets_query.where(Ticket.requester_id == g.user.id)
    related_tickets = db.session.scalars(tickets_query.order_by(Ticket.id.desc()).limit(50)).all()
    services = db.session.scalars(db.select(AssetService).where(AssetService.asset_id == asset.id)
        .order_by(AssetService.performed_on.desc(), AssetService.id.desc())).all() if g.user.role in ("admin", "technician") else []
    employees, employee_error = employee_options() if g.user.role in ("admin", "technician") and asset.status == "available" else ([], None)
    return render_template("asset_detail.html", asset=asset, history=history,
                           related_tickets=related_tickets, employees=employees, employee_error=employee_error,
                           services=services)


@bp.post("/assets/<int:asset_id>/assign")
@require_roles("admin", "technician")
def assign(asset_id):
    employee_no = request.form.get("employee_no", "").strip()
    try:
        employee = lookup(employee_no, exact=True) if employee_no else []
    except DirectoryUnavailable as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.asset_detail", asset_id=asset_id))
    if not employee:
        flash("Selecciona un empleado existente en RH.", "error")
        return redirect(url_for("main.asset_detail", asset_id=asset_id))
    # Lock the asset to serialize assignment and return operations on MySQL.
    asset = db.session.scalar(db.select(Asset).where(Asset.id == asset_id).with_for_update())
    if not asset:
        abort(404)
    if asset.status != "available":
        db.session.rollback()
        flash("El equipo debe estar disponible antes de asignarlo.", "error")
    else:
        db.session.add(Assignment(asset_id=asset.id, employee_no=employee[0]["employee_no"],
            employee_name=employee[0]["name"], assigned_by=g.user.id))
        asset.status = "assigned"
        audit("asset.assign", asset.id)
        db.session.commit()
    return redirect(url_for("main.asset_detail", asset_id=asset_id))


@bp.post("/assets/<int:asset_id>/return")
@require_roles("admin", "technician")
def return_asset(asset_id):
    asset = db.session.scalar(db.select(Asset).where(Asset.id == asset_id).with_for_update())
    if not asset:
        abort(404)
    assignment = db.session.scalar(db.select(Assignment).where(Assignment.asset_id == asset_id, Assignment.ended_at.is_(None)))
    if assignment:
        assignment.ended_at = now()
        asset.status = "available"
        audit("asset.return", asset.id)
        db.session.commit()
    else:
        db.session.rollback()
        flash("El equipo no tiene una asignación activa.", "error")
    return redirect(url_for("main.asset_detail", asset_id=asset_id))


@bp.post("/assets/<int:asset_id>/status")
@require_roles("admin", "technician")
def asset_status(asset_id):
    asset = db.session.scalar(db.select(Asset).where(Asset.id == asset_id).with_for_update())
    if not asset:
        abort(404)
    status = request.form.get("status")
    if status not in ("available", "repair", "retired") or asset.status == "assigned":
        db.session.rollback()
        flash("Devuelve primero el equipo asignado y selecciona un estado válido.", "error")
    else:
        asset.status = status
        audit("asset.status." + status, asset.id)
        db.session.commit()
    return redirect(url_for("main.asset_detail", asset_id=asset_id))


@bp.get("/audit")
@require_roles("admin")
def audit_log():
    rows = db.session.execute(db.select(Audit, User.username).outerjoin(
        User, Audit.actor_id == User.id).order_by(Audit.id.desc()).limit(200)).all()
    return render_template("audit.html", rows=rows)
