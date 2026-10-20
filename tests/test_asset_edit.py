from test_platform import app, login
from it_platform.models import Asset, Assignment, Audit, User, db


def test_edit_asset_preserves_assignment_and_audits(app):
    client = app.test_client()
    login(client)
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        db.session.get(Asset, 1).status = "assigned"
        db.session.add(Assignment(asset_id=1, employee_no="123", employee_name="Prueba", assigned_by=admin.id))
        db.session.commit()
    response = client.get("/assets/1/edit")
    assert response.status_code == 200 and b'PC-001' in response.data
    payload = {"code": "PC-001", "serial": "SERIE-123", "category": "Laptop", "brand": "HP",
               "model": "ProBook", "location": "IT", "specs": "16 GB RAM", "status": "retired"}
    assert client.post("/assets/1/edit", data=payload).status_code == 302
    with app.app_context():
        asset = db.session.get(Asset, 1)
        assert asset.serial == "SERIE-123" and asset.model == "ProBook"
        assert asset.status == "assigned"
        assert db.session.get(Assignment, 1).ended_at is None
        assert db.session.scalar(db.select(Audit).where(Audit.action == "asset.update.model"))
    assert b'ProBook' in client.get("/assets/1/edit").data


def test_edit_rejects_duplicates_and_invalid_fields(app):
    client = app.test_client()
    login(client)
    with app.app_context():
        db.session.add(Asset(code="PC-002", serial="EXISTENTE", category="Monitor"))
        db.session.commit()
    payload = {"code": "PC-001", "serial": "EXISTENTE", "category": "Laptop", "brand": "Cambio"}
    response = client.post("/assets/1/edit", data=payload)
    assert response.status_code == 200 and b'EXISTENTE' in response.data
    with app.app_context():
        assert db.session.get(Asset, 1).brand == ""
        assert db.session.get(Asset, 1).serial is None
    payload.update(serial="", code="")
    assert client.post("/assets/1/edit", data=payload).status_code == 200
    with app.app_context():
        assert db.session.get(Asset, 1).code == "PC-001"


def test_edit_permissions_and_csrf(app):
    client = app.test_client()
    login(client, "leader")
    assert client.get("/assets/1/edit").status_code == 403
    assert client.post("/assets/1/edit", data={}).status_code == 403
    client.post("/logout")
    login(client)
    assert client.get("/assets/999/edit").status_code == 404
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/assets/1/edit", data={}).status_code == 400
