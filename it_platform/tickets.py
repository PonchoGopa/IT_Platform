from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import or_
from .auth import require_roles
from .models import Asset, Assignment, Ticket, TicketComment, TicketEvent, User, audit, db, now

bp = Blueprint("tickets", __name__, url_prefix="/tickets")
CATEGORIES = ["Hardware", "Software", "Red", "Correo", "ERP", "Accesos", "Otros"]
PRIORITIES = {"low": "Baja", "normal": "Normal", "high": "Alta", "urgent": "Urgente"}
STATUSES = {"new": "Nuevo", "review": "En revisión", "working": "En atención",
            "waiting": "En espera", "resolved": "Resuelto", "closed": "Cerrado"}
TRANSITIONS = {
    "new": {"review", "working"},
    "review": {"working", "waiting"},
    "working": {"waiting", "resolved"},
    "waiting": {"review", "working", "resolved"},
    "resolved": {"working", "closed"},
    "closed": {"working"},
}


def is_it():
    return g.user.role in ("admin", "technician")


def scoped():
    stmt = db.select(Ticket)
    return stmt if is_it() else stmt.where(Ticket.requester_id == g.user.id)


def get_ticket(ticket_id, lock=False):
    stmt = scoped().where(Ticket.id == ticket_id)
    ticket = db.session.scalar(stmt.with_for_update() if lock else stmt)
    if ticket is None:
        abort(404)
    return ticket


def record(ticket, message, action):
    db.session.add(TicketEvent(ticket_id=ticket.id, actor_id=g.user.id, message=message))
    audit(action, f"ticket:{ticket.id}")


def eligible_assets():
    stmt = db.select(Asset)
    if not is_it():
        if not g.user.employee_no:
            return []
        stmt = stmt.join(Assignment).where(Assignment.employee_no == g.user.employee_no,
                                          Assignment.ended_at.is_(None))
    return db.session.scalars(stmt.order_by(Asset.code)).all()


@bp.app_context_processor
def context():
    return {"ticket_statuses": STATUSES, "ticket_priorities": PRIORITIES,
            "ticket_categories": CATEGORIES}


@bp.get("")
@require_roles()
def index():
    status = request.args.get("status", "")
    query = request.args.get("q", "").strip()[:160]
    stmt = scoped()
    if status in STATUSES:
        stmt = stmt.where(Ticket.status == status)
    if query:
        conditions = [Ticket.subject.contains(query, autoescape=True)]
        number = query.upper().removeprefix("IT-")
        if number.isascii() and number.isdigit() and len(number) <= 10:
            conditions.append(Ticket.id == int(number))
        stmt = stmt.where(or_(*conditions))
    rows = db.session.scalars(stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc()).limit(200)).all()
    return render_template("tickets/index.html", rows=rows, status=status, query=query)


@bp.route("/new", methods=["GET", "POST"])
@require_roles()
def new():
    assets = eligible_assets()
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "")
        priority = request.form.get("priority", "normal")
        asset_id = request.form.get("asset_id", "")
        asset = next((a for a in assets if str(a.id) == asset_id), None)
        if not subject or len(subject) > 160 or not description or len(description) > 10000:
            flash("Ingresa un asunto de hasta 160 caracteres y una descripción de hasta 10,000.", "error")
        elif category not in CATEGORIES or priority not in PRIORITIES:
            flash("Selecciona una categoría y prioridad válidas.", "error")
        elif asset_id and not asset:
            abort(403)
        else:
            ticket = Ticket(requester_id=g.user.id, subject=subject, description=description,
                            category=category, priority=priority, asset_id=asset.id if asset else None)
            db.session.add(ticket)
            db.session.flush()
            record(ticket, "Solicitud creada", "ticket.create")
            db.session.commit()
            return redirect(url_for("tickets.detail", ticket_id=ticket.id))
    return render_template("tickets/new.html", assets=assets)


@bp.get("/<int:ticket_id>")
@require_roles()
def detail(ticket_id):
    ticket = get_ticket(ticket_id)
    comments = db.select(TicketComment).where(TicketComment.ticket_id == ticket.id)
    if not is_it():
        comments = comments.where(TicketComment.internal.is_(False))
    comments = db.session.scalars(comments.order_by(TicketComment.id)).all()
    events = db.session.scalars(db.select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id)).all()
    technicians = db.session.scalars(db.select(User).where(User.active.is_(True), User.role.in_(["admin", "technician"])).order_by(User.username)).all() if is_it() else []
    allowed_statuses = [key for key in STATUSES if key == ticket.status or key in TRANSITIONS[ticket.status]]
    return render_template("tickets/detail.html", ticket=ticket, comments=comments,
                           events=events, technicians=technicians, allowed_statuses=allowed_statuses)


@bp.post("/<int:ticket_id>/comments")
@require_roles()
def comment(ticket_id):
    ticket = get_ticket(ticket_id, lock=True)
    body = request.form.get("body", "").strip()
    internal = request.form.get("internal") == "1"
    if internal and not is_it():
        abort(403)
    if ticket.status == "closed":
        flash("El ticket está cerrado. IT debe reabrirlo para continuar.", "error")
    elif not body or len(body) > 10000:
        flash("Escribe un comentario de hasta 10,000 caracteres.", "error")
    else:
        db.session.add(TicketComment(ticket_id=ticket.id, author_id=g.user.id, body=body, internal=internal))
        ticket.updated_at = now()
        ticket.revision += 1
        audit("ticket.note" if internal else "ticket.comment", f"ticket:{ticket.id}")
        db.session.commit()
        return redirect(url_for("tickets.detail", ticket_id=ticket_id))
    db.session.rollback()
    return redirect(url_for("tickets.detail", ticket_id=ticket_id))


@bp.post("/<int:ticket_id>/manage")
@require_roles("admin", "technician")
def manage(ticket_id):
    ticket = get_ticket(ticket_id, lock=True)
    # Reject stale edits before applying any part of the update.
    if request.form.get("revision") != str(ticket.revision):
        db.session.rollback()
        flash("El ticket cambió. Revisa la información actual antes de guardar.", "error")
        return redirect(url_for("tickets.detail", ticket_id=ticket_id))
    status = request.form.get("status", "")
    priority = request.form.get("priority", "")
    assigned_id = request.form.get("assigned_to_id", "")
    solution = request.form.get("solution", "").strip()
    technician = db.session.scalar(db.select(User).where(User.id == int(assigned_id), User.active.is_(True), User.role.in_(["admin", "technician"]))) if assigned_id.isascii() and assigned_id.isdigit() and len(assigned_id) <= 10 else None
    errors = []
    if status not in STATUSES or (status != ticket.status and status not in TRANSITIONS[ticket.status]):
        errors.append("Cambio de estado no permitido.")
    if priority not in PRIORITIES:
        errors.append("Prioridad no válida.")
    if assigned_id and not technician:
        errors.append("Selecciona un técnico activo.")
    if len(solution) > 10000 or (status in ("resolved", "closed") and not solution):
        errors.append("Para resolver o cerrar debes registrar una solución de hasta 10,000 caracteres.")
    if status in ("working", "resolved", "closed") and not technician:
        errors.append("Asigna un responsable de IT para atender, resolver o cerrar.")
    if errors:
        db.session.rollback()
        for error in errors:
            flash(error, "error")
        return redirect(url_for("tickets.detail", ticket_id=ticket_id))
    changes = False
    if (technician and technician.id != ticket.assigned_to_id) or (not technician and ticket.assigned_to_id):
        ticket.assigned_to_id = technician.id if technician else None
        record(ticket, "Responsable: " + (technician.username if technician else "Sin asignar"), "ticket.assign")
        changes = True
    if priority != ticket.priority:
        record(ticket, f"Prioridad: {PRIORITIES[ticket.priority]} → {PRIORITIES[priority]}", "ticket.priority")
        ticket.priority = priority
        changes = True
    if solution != ticket.solution:
        ticket.solution = solution
        record(ticket, "Solución actualizada", "ticket.solution")
        changes = True
    if status != ticket.status:
        record(ticket, f"Estado: {STATUSES[ticket.status]} → {STATUSES[status]}", "ticket.status")
        ticket.status = status
        if status == "resolved":
            ticket.resolved_at = now()
        elif status == "working":
            ticket.resolved_at = None
            ticket.closed_at = None
        elif status == "closed":
            ticket.closed_at = now()
        changes = True
    if changes:
        ticket.updated_at = now()
        ticket.revision += 1
    db.session.commit()
    return redirect(url_for("tickets.detail", ticket_id=ticket_id))
