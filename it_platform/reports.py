from datetime import date

from flask import Blueprint, abort, render_template, request
from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased

from .auth import require_roles
from .models import Asset, AssetService, db

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.get("")
@bp.get("/")
@require_roles("admin", "technician")
def index():
    return render_template("reports/index.html")


@bp.get("/maintenance")
@require_roles("admin", "technician")
def maintenance():
    query = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "")
    if status not in ("", "missing", "overdue", "scheduled", "unscheduled"):
        abort(400)
    page = max(1, request.args.get("page", 1, type=int))
    today = date.today()

    # Select by performed date, then ID so same-day entries remain deterministic.
    newer = aliased(AssetService)
    newer_exists = db.select(newer.id).where(
        newer.asset_id == AssetService.asset_id,
        newer.kind == "maintenance",
        or_(newer.performed_on > AssetService.performed_on,
            and_(newer.performed_on == AssetService.performed_on,
                 newer.id > AssetService.id)),
    ).correlate(AssetService).exists()
    latest = db.select(AssetService).where(
        AssetService.kind == "maintenance", ~newer_exists
    ).subquery()
    service = aliased(AssetService, latest)
    stmt = db.select(Asset, service).outerjoin(service, service.asset_id == Asset.id)
    if query:
        stmt = stmt.where(or_(
            Asset.alias.contains(query, autoescape=True),
            Asset.code.contains(query, autoescape=True),
            Asset.serial.contains(query, autoescape=True),
            Asset.location.contains(query, autoescape=True),
        ))
    conditions = {
        "missing": service.id.is_(None),
        "overdue": service.next_due_on < today,
        "scheduled": service.next_due_on >= today,
        "unscheduled": and_(service.id.is_not(None), service.next_due_on.is_(None)),
    }
    # Totals cover all equipment matching the search, before the status filter.
    summary = {"total": db.session.scalar(db.select(db.func.count()).select_from(stmt.subquery()))}
    for key, condition in conditions.items():
        summary[key] = db.session.scalar(
            db.select(db.func.count()).select_from(stmt.where(condition).subquery()))
    if status:
        stmt = stmt.where(conditions[status])
    total = db.session.scalar(db.select(db.func.count()).select_from(stmt.subquery()))
    per_page = 50
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    rows = db.session.execute(stmt.order_by(
        service.performed_on.is_not(None), service.performed_on.desc(), Asset.code
    ).limit(per_page).offset((page - 1) * per_page)).all()
    return render_template("reports/maintenance.html", rows=rows, query=query,
                           status=status, summary=summary, today=today,
                           page=page, pages=pages, total=total)
