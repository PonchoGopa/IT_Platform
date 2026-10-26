from datetime import date, timedelta

from test_platform import app, login
from it_platform.models import Asset, AssetService, User, db


def add_service(asset_id, performed_on, description, **changes):
    values = dict(asset_id=asset_id, kind="maintenance",
                  performed_on=performed_on, service_type="preventive",
                  responsible="IT", description=description, result="success",
                  created_by=1)
    values.update(changes)
    db.session.add(AssetService(**values))


def test_report_latest_is_by_performed_date_and_id_not_insertion_or_backup(app):
    today = date.today()
    with app.app_context():
        db.session.add(Asset(code="0002", alias="Sin registro", category="Laptop"))
        add_service(1, today - timedelta(days=2), "old_same_day")
        add_service(1, today - timedelta(days=2), "latest_same_day", result="partial")
        add_service(1, today - timedelta(days=30), "late_capture_old")
        add_service(1, today, "backup_excluded", kind="backup", service_type="full")
        db.session.commit()
    client = app.test_client()
    login(client)
    page = client.get("/reports/maintenance").get_data(as_text=True)
    assert "latest_same_day" in page
    assert all(value not in page for value in ("old_same_day", "late_capture_old", "backup_excluded"))
    assert "Sin registro" in page and "Sin mantenimiento registrado" in page
    assert "Parcial" in page
    assert page.count('/assets/1"') == 1


def test_report_filters_latest_due_date_and_search(app):
    today = date.today()
    with app.app_context():
        for code in ["OVERDUE", "SCHEDULED", "UNSCHEDULED", "BACKUPONLY"]:
            db.session.add(Asset(code=code, category="Laptop"))
        db.session.flush()
        assets = {a.code: a.id for a in db.session.scalars(db.select(Asset))}
        add_service(assets["OVERDUE"], today-timedelta(days=4), "old",
                    next_due_on=today+timedelta(days=40))
        add_service(assets["OVERDUE"], today-timedelta(days=2), "due_old",
                    next_due_on=today-timedelta(days=1))
        add_service(assets["SCHEDULED"], today-timedelta(days=2), "due_today",
                    next_due_on=today)
        add_service(assets["UNSCHEDULED"], today, "no_due")
        add_service(assets["BACKUPONLY"], today, "backup",
                    kind="backup", service_type="full")
        db.session.commit()
    client = app.test_client()
    login(client)
    for status, included, excluded in [
        ("overdue", "due_old", "due_today"),
        ("scheduled", "due_today", "due_old"),
        ("unscheduled", "no_due", "due_old"),
        ("missing", "BACKUPONLY", "due_today"),
    ]:
        page = client.get("/reports/maintenance", query_string={"status": status}).get_data(as_text=True)
        assert included in page and excluded not in page
    page = client.get("/reports/maintenance?q=OVERDUE").get_data(as_text=True)
    assert "due_old" in page and "due_today" not in page
    assert client.get("/reports/maintenance?q=%25").status_code == 200
    assert client.get("/reports/maintenance?status=invalid").status_code == 400


def test_reports_permissions_and_navigation(app):
    client = app.test_client()
    for path in ["/reports", "/reports/maintenance"]:
        assert client.get(path).status_code == 302
    login(client, "leader")
    assert b">Reportes</a>" not in client.get("/").data
    for path in ["/reports", "/reports/maintenance"]:
        assert client.get(path).status_code == 403
    client.post("/logout")
    login(client)
    assert client.get("/reports").status_code == 200
    assert b">Reportes</a>" in client.get("/").data
    with app.app_context():
        db.session.add(User(username="tech", role="technician", password_hash="unused"))
        db.session.commit()
        tech_id = db.session.scalar(db.select(User.id).where(User.username == "tech"))
    with client.session_transaction() as session:
        session["user_id"] = tech_id
    assert client.get("/reports/maintenance").status_code == 200


def test_report_pagination_empty_and_escaped_description(app):
    client = app.test_client()
    login(client)
    assert "No hay equipos".encode() in client.get("/reports/maintenance?q=absent").data
    with app.app_context():
        db.session.add_all(Asset(code=f"P-{i:03}", category="Laptop") for i in range(51))
        add_service(1, date.today(), "<script>alert(1)</script>")
        db.session.commit()
    first = client.get("/reports/maintenance").get_data(as_text=True)
    second = client.get("/reports/maintenance?page=2").get_data(as_text=True)
    assert "Siguiente" in first and "Anterior" in second
    assert first.count('class="badge badge-neutral">Sin mantenimiento registrado') == 50
    assert "&lt;script&gt;" in second and "<script>" not in second
    assert client.get("/reports/maintenance?page=bad").status_code == 200
    assert client.get("/reports/maintenance?page=999").status_code == 200
