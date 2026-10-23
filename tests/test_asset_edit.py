from pathlib import Path
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


def test_alias_saved_searched_and_shown_in_selectors(app, monkeypatch):
    from test_vault import prepare_access, unlock
    monkeypatch.setattr("it_platform.routes.employee_options", lambda: ([], None))
    client = app.test_client()
    login(client)
    payload = {"code": "PC-001", "alias": "Laptop de recepción", "category": "Laptop"}
    assert client.post("/assets/1/edit", data=payload).status_code == 302
    with app.app_context():
        asset = db.session.get(Asset, 1)
        assert asset.alias == "Laptop de recepción"
        assert asset.display_name == "Laptop de recepción (PC-001)"
        assert db.session.scalar(db.select(Audit).where(Audit.action == "asset.update.alias"))
    for url in ["/assets?q=recepción", "/assets/1", "/assets/1/edit", "/tickets/new"]:
        response = client.get(url)
        assert response.status_code == 200
        assert "Laptop de recepción" in response.get_data(as_text=True)
    prepare_access(app, "admin", True)
    # A key is required for the vault, independent of inventory metadata.
    from cryptography.fernet import Fernet
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(dir=app.instance_path) as directory:
        key = Path(directory) / "vault.key"
        key.write_bytes(Fernet.generate_key())
        app.config["VAULT_KEY_FILE"] = str(key)
        unlock(client)
        response = client.get("/vault/new")
        assert response.status_code == 200
        assert "Laptop de recepción (PC-001)" in response.get_data(as_text=True)


def test_alias_upgrade_preserves_existing_assets_and_is_repeatable(app):
    from sqlalchemy import text, inspect
    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE asset DROP COLUMN alias"))
    runner = app.test_cli_runner()
    assert runner.invoke(args=["upgrade-db"]).exit_code == 0
    assert runner.invoke(args=["upgrade-db"]).exit_code == 0
    with app.app_context():
        assert "alias" in {c["name"] for c in inspect(db.engine).get_columns("asset")}
        asset = db.session.get(Asset, 1)
        assert asset.alias == "" and asset.display_name == asset.code == "PC-001"


def test_new_asset_codes_follow_numeric_history_and_ignore_submitted_code(app):
    client = app.test_client()
    login(client)
    with app.app_context():
        db.session.add(Asset(code="0007", category="Laptop"))
        db.session.commit()
    page = client.get("/assets/new").get_data(as_text=True)
    assert "Automático al guardar" in page and 'name="code"' not in page
    for expected in ["0008", "0009"]:
        response = client.post("/assets/new", data={"category": "Laptop", "code": "9999"})
        assert response.status_code == 302
        with app.app_context():
            assert db.session.scalar(db.select(Asset).where(Asset.code == expected))
    with app.app_context():
        assert not db.session.scalar(db.select(Asset).where(Asset.code == "9999"))
        assert db.session.get(Asset, 1).code == "PC-001"


def test_failed_asset_creation_does_not_consume_code(app):
    client = app.test_client()
    login(client)
    with app.app_context():
        db.session.add(Asset(code="0007", serial="DUPLICATE", category="Laptop"))
        db.session.commit()
    assert client.post("/assets/new", data={"category": "Laptop", "serial": "DUPLICATE"}).status_code == 200
    assert client.post("/assets/new", data={"category": "Laptop"}).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(Asset).where(Asset.code == "0008"))
        assert not db.session.scalar(db.select(Asset).where(Asset.code == "0009"))
