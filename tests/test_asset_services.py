from test_platform import app, login
from it_platform.models import Asset, AssetService, Assignment, Audit, User, db


def payload(**overrides):
    data = dict(performed_on="2026-01-01", service_type="full", responsible="IT",
                description="Documentos del usuario", result="success", location="NAS/PC-001",
                restoration="verified", next_due_on="2026-02-01")
    data.update(overrides)
    return data


def test_histories_and_audit(app):
    client = app.test_client()
    login(client)
    assert client.get("/assets/1/services/backup/new").status_code == 200
    assert client.post("/assets/1/services/backup/new", data=payload()).status_code == 302
    assert client.post("/assets/1/services/maintenance/new", data=payload(
        service_type="preventive", description="Limpieza y revisión")).status_code == 302
    with app.app_context():
        rows = db.session.scalars(db.select(AssetService).order_by(AssetService.id)).all()
        assert len(rows) == 2
        assert rows[0].restoration == "verified"
        assert rows[1].location == ""
        assert rows[0].author.username == "admin"
        assert db.session.scalar(db.select(db.func.count()).select_from(Audit).where(
            Audit.action.in_(["asset.backup.create", "asset.maintenance.create"]))) == 2
        db.session.add(Asset(code="OTHER", category="Laptop"))
        db.session.commit()
    page = client.get("/assets/1").data
    assert b"NAS/PC-001" in page and "Limpieza y revisión".encode() in page
    assert b"NAS/PC-001" not in client.get("/assets/2").data


def test_invalid_records_do_not_write(app):
    client = app.test_client()
    login(client)
    for changes in [dict(performed_on="bad"), dict(performed_on="2999-01-01"),
                    dict(next_due_on="2025-01-01"), dict(responsible=" "),
                    dict(description=""), dict(description="a" * 5001),
                    dict(service_type="preventive"), dict(result="invalid"),
                    dict(location=""), dict(location="a" * 501), dict(restoration="invalid")]:
        response = client.post("/assets/1/services/backup/new", data=payload(**changes))
        assert response.status_code == 200
        assert b"Revisa los campos" in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(AssetService)) == 0
    assert client.post("/assets/999/services/backup/new", data=payload()).status_code == 404
    assert client.get("/assets/1/services/invalid/new").status_code == 404


def test_permissions_and_csrf(app):
    client = app.test_client()
    assert client.get("/assets/1/services/backup/new").status_code == 302
    login(client, "leader")
    for kind in ("maintenance", "backup"):
        assert client.get(f"/assets/1/services/{kind}/new").status_code == 403
        assert client.post(f"/assets/1/services/{kind}/new", data=payload()).status_code == 403
    client.post("/logout")
    login(client)
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/assets/1/services/backup/new", data=payload()).status_code == 400


def test_requester_cannot_see_backup_locations(app):
    client = app.test_client()
    login(client)
    client.post("/assets/1/services/backup/new", data=payload())
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        db.session.add(Assignment(asset_id=1, employee_no="123", employee_name="Prueba", assigned_by=admin.id))
        db.session.commit()
    client.post("/logout")
    login(client, "leader")
    response = client.get("/assets/1")
    assert response.status_code == 200
    assert b"NAS/PC-001" not in response.data
