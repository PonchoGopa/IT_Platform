from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import require_roles
from .models import Asset, AssetService, audit, db

bp = Blueprint("asset_services", __name__)
KINDS = {"maintenance": "Mantenimiento", "backup": "Respaldo"}
TYPES = {
    "maintenance": {"preventive": "Preventivo", "corrective": "Correctivo"},
    "backup": {"full": "Completo", "incremental": "Incremental", "differential": "Diferencial"},
}
RESULTS = {"success": "Completado", "partial": "Parcial", "failed": "Fallido"}
RESTORATIONS = {"not_tested": "Sin probar", "verified": "Restauración verificada", "failed": "Prueba fallida"}


@bp.app_context_processor
def context():
    return dict(service_kinds=KINDS, service_types=TYPES,
                service_results=RESULTS, service_restorations=RESTORATIONS)


@bp.route("/assets/<int:asset_id>/services/<kind>/new", methods=["GET", "POST"])
@require_roles("admin", "technician")
def new(asset_id, kind):
    from flask import abort
    if kind not in KINDS:
        abort(404)
    asset = db.get_or_404(Asset, asset_id)
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in
                  ("service_type", "responsible", "description", "result", "location", "restoration")}
        try:
            performed = date.fromisoformat(request.form.get("performed_on", ""))
            due = request.form.get("next_due_on", "").strip()
            due = date.fromisoformat(due) if due else None
            if performed > date.today() or (due and due <= performed):
                raise ValueError
            if (values["service_type"] not in TYPES[kind] or values["result"] not in RESULTS
                    or not 1 <= len(values["responsible"]) <= 120
                    or not 1 <= len(values["description"]) <= 5000):
                raise ValueError
            if kind == "backup":
                if not 1 <= len(values["location"]) <= 500 or values["restoration"] not in RESTORATIONS:
                    raise ValueError
            else:
                values.update(location="", restoration="not_tested")
        except ValueError:
            flash("Revisa los campos: fecha realizada hasta hoy, próxima fecha posterior, campos obligatorios y longitudes indicadas.", "error")
        else:
            record = AssetService(asset_id=asset.id, kind=kind, performed_on=performed,
                                  next_due_on=due, created_by=g.user.id, **values)
            db.session.add(record)
            db.session.flush()
            audit("asset." + kind + ".create", f"asset:{asset.id}/service:{record.id}")
            db.session.commit()
            flash(KINDS[kind] + " registrado.")
            return redirect(url_for("main.asset_detail", asset_id=asset.id))
    return render_template("asset_service_form.html", asset=asset, kind=kind, today=date.today().isoformat())
