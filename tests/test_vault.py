import time
import pytest
from cryptography.fernet import Fernet
from test_platform import app, login
from it_platform.models import Credential, CredentialVersion, VaultAccess, User, Audit, db
from it_platform.vault_crypto import encrypt


@pytest.fixture
def vault_app(app, tmp_path, monkeypatch):
    key = tmp_path / "vault.key"
    key.write_bytes(Fernet.generate_key())
    app.config["VAULT_KEY_FILE"] = str(key)
    monkeypatch.setattr("it_platform.vault.lookup", lambda number, **kwargs: [{"employee_no": number, "name": "Prueba"}])
    return app


def prepare_access(app, username, it_access=False):
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == username))
        row = VaultAccess(user_id=user.id, it_access=it_access)
        db.session.add(row)
        db.session.commit()


def unlock(client):
    return client.post("/vault/unlock", data={"password": "A-long-test-password"})


def create(client, **overrides):
    data = {"title": "Correo de prueba", "kind": "Microsoft 365 / Office", "url": "",
            "username": "login-secret", "password": "Password-never-in-logs", "pin": "098765",
            "code": "RECOVERY-SECRET", "notes": "Nota protegida"}
    data.update(overrides)
    return client.post("/vault/new", data=data)


def test_encryption_scope_history_restore_and_notes(vault_app):
    app = vault_app
    prepare_access(app, "leader")
    prepare_access(app, "other")
    prepare_access(app, "admin", True)
    client = app.test_client()
    login(client, "leader")
    assert unlock(client).status_code == 302
    assert create(client).status_code == 302
    assert client.get("/vault").status_code == 200
    assert client.get("/vault/1/edit").status_code == 200
    assert b"Password-never-in-logs" not in client.get("/vault/1").data
    assert b"Password-never-in-logs" in client.post("/vault/1/reveal/1").data
    assert b"login-secret" not in client.get("/vault/1/edit").data
    with app.app_context():
        original = db.session.get(CredentialVersion, 1).ciphertext
        assert "Password-never-in-logs" not in original and "RECOVERY-SECRET" not in original
        assert not any("Password-never-in-logs" in row.target for row in db.session.scalars(db.select(Audit)))
    assert client.post("/vault/1/edit", data={"title": "Actualizado", "kind": "Portal", "version": "1", "password": "New-Password"}).status_code == 302
    # Blank username and PIN preserve their values.
    response = client.post("/vault/1/reveal/2")
    assert b"New-Password" in response.data and b"098765" in response.data
    assert client.post("/vault/1/reveal/1").status_code == 403
    assert client.post("/vault/1/restore/1", data={"version": "2"}).status_code == 403
    assert client.delete("/vault/1").status_code == 405
    client.post("/logout")
    login(client, "other")
    unlock(client)
    assert b"Actualizado" not in client.get("/vault").data
    assert client.get("/vault/1").status_code == 404
    assert client.post("/vault/1/reveal/2").status_code == 404
    client.post("/logout")
    login(client)
    unlock(client)
    assert client.get("/vault/1").status_code == 200
    assert b"Password-never-in-logs" in client.post("/vault/1/reveal/1").data
    assert client.post("/vault/1/restore/1", data={"version": "2"}).status_code == 302
    with app.app_context():
        credential = db.session.get(Credential, 1)
        assert credential.current_version == 3 and credential.title == "Correo de prueba"
        assert db.session.get(CredentialVersion, 1).ciphertext == original
        assert db.session.scalar(db.select(db.func.count()).select_from(CredentialVersion)) == 3
    client.post("/vault/1/archive")
    assert client.get("/vault/1/edit").status_code == 403
    assert b"Correo de prueba" not in client.get("/vault").data
    assert b"Correo de prueba" in client.get("/vault?archived=1").data


def test_role_alone_does_not_grant_vault(vault_app):
    prepare_access(vault_app, "leader")
    prepare_access(vault_app, "admin")
    client = vault_app.test_client()
    login(client, "leader")
    unlock(client)
    create(client)
    client.post("/logout")
    login(client)
    unlock(client)
    assert client.get("/vault/1").status_code == 404


def test_password_verification_expiry_and_failure_lock(vault_app, monkeypatch):
    clock = [1800000000.0]
    monkeypatch.setattr("time.time", lambda: clock[0])
    client = vault_app.test_client()
    login(client, "leader")
    assert client.get("/vault").location.endswith("/vault/unlock")
    assert unlock(client).status_code == 302
    assert client.get("/vault").status_code == 200
    client.post("/vault/lock")
    assert unlock(client).status_code == 302  # password only, no authenticator
    clock[0] += 301
    assert client.get("/vault").location.endswith("/vault/unlock")
    for _ in range(5):
        client.post("/vault/unlock", data={"password": "bad"})
    assert unlock(client).status_code == 429


def test_missing_key_and_ciphertext_tamper(vault_app):
    prepare_access(vault_app, "leader")
    client = vault_app.test_client()
    login(client, "leader")
    unlock(client)
    create(client)
    with vault_app.app_context():
        db.session.get(CredentialVersion, 1).ciphertext = "invalid-token"
        db.session.commit()
    assert client.post("/vault/1/reveal/1").status_code == 503
    vault_app.config["VAULT_KEY_FILE"] = ""
    assert client.get("/vault").status_code == 503


def test_no_enrollment_and_password_change_invalidates_unlock(vault_app):
    from werkzeug.security import generate_password_hash
    client = vault_app.test_client()
    login(client, "leader")
    assert client.get("/vault").location.endswith("/vault/unlock")
    assert client.get("/vault/setup").location.endswith("/vault/unlock")
    assert b'one-time-code' not in client.get("/vault/unlock").data
    assert unlock(client).status_code == 302
    assert client.get("/vault").status_code == 200
    with vault_app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == "leader"))
        user.password_hash = generate_password_hash("Changed-test-password")
        db.session.commit()
    assert client.get("/vault").location.endswith("/vault/unlock")


def test_stale_edit_csrf_and_no_delete(vault_app):
    prepare_access(vault_app, "admin", True)
    client = vault_app.test_client()
    login(client)
    unlock(client)
    create(client)
    payload = {"version": "1", "title": "Nuevo título", "kind": "Portal", "clear_pin": "1"}
    client.post("/vault/1/edit", data=payload)
    client.post("/vault/1/edit", data=payload)
    with vault_app.app_context():
        assert db.session.get(Credential, 1).current_version == 2
    assert b"098765" not in client.post("/vault/1/reveal/2").data
    assert client.delete("/vault/1").status_code == 405
    vault_app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/vault/1/reveal/2").status_code == 400


def test_old_totp_configuration_does_not_block_access(vault_app):
    prepare_access(vault_app, "leader")
    with vault_app.app_context():
        row = db.session.scalar(db.select(VaultAccess))
        row.totp_secret = "old-encrypted-value-not-used"
        row.last_counter = 99999999999
        db.session.commit()
    client = vault_app.test_client()
    login(client, "leader")
    assert unlock(client).status_code == 302
    assert client.get("/vault").status_code == 200


def test_key_generation_never_overwrites(vault_app, tmp_path):
    key = tmp_path / "new.key"
    runner = vault_app.test_cli_runner()
    assert runner.invoke(args=["vault-init-key", "--path", str(key)]).exit_code == 0
    original = key.read_bytes()
    assert runner.invoke(args=["vault-init-key", "--path", str(key)]).exit_code != 0
    assert key.read_bytes() == original


def test_revocation_applies_to_existing_session(vault_app):
    prepare_access(vault_app, "leader")
    prepare_access(vault_app, "admin", True)
    client = vault_app.test_client()
    login(client, "leader")
    unlock(client)
    create(client)
    client.post("/logout")
    login(client)
    unlock(client)
    assert client.get("/vault/1").status_code == 200
    result = vault_app.test_cli_runner().invoke(args=["vault-grant-it", "--username", "admin", "--revoke"])
    assert result.exit_code == 0
    assert client.get("/vault/1").status_code == 404


def test_ciphertext_substitution_and_key_restore(vault_app, tmp_path):
    prepare_access(vault_app, "admin", True)
    client = vault_app.test_client()
    login(client)
    unlock(client)
    create(client)
    create(client, title="Otra cuenta")
    with vault_app.app_context():
        first = db.session.get(CredentialVersion, 1)
        original = first.ciphertext
        first.ciphertext = db.session.get(CredentialVersion, 2).ciphertext
        db.session.commit()
    assert client.post("/vault/1/reveal/1").status_code == 503
    with vault_app.app_context():
        db.session.get(CredentialVersion, 1).ciphertext = original
        db.session.commit()
    key_path = vault_app.config["VAULT_KEY_FILE"]
    wrong = tmp_path / "wrong.key"
    wrong.write_bytes(Fernet.generate_key())
    vault_app.config["VAULT_KEY_FILE"] = str(wrong)
    assert client.post("/vault/1/reveal/1").status_code == 503
    vault_app.config["VAULT_KEY_FILE"] = key_path
    assert b"Password-never-in-logs" in client.post("/vault/1/reveal/1").data


def test_forged_owner_and_assets_are_rejected(vault_app):
    prepare_access(vault_app, "leader")
    client = vault_app.test_client()
    login(client, "leader")
    unlock(client)
    assert create(client, asset_ids="1").status_code == 403
    assert create(client, owner_employee_no="456").status_code == 302
    with vault_app.app_context():
        assert db.session.get(Credential, 1).owner_employee_no == "123"


def test_owner_can_inactivate_only_own_without_deletion(vault_app):
    prepare_access(vault_app, "leader")
    prepare_access(vault_app, "other")
    prepare_access(vault_app, "admin", True)
    client = vault_app.test_client()
    login(client, "leader")
    unlock(client)
    create(client)
    assert b'Inactivar credencial' in client.get("/vault/1").data
    assert client.post("/vault/1/archive").status_code == 302
    assert client.get("/vault/1/edit").status_code == 403
    assert client.post("/vault/1/archive").status_code == 403
    assert b'Correo de prueba' in client.get("/vault?archived=1").data
    assert b'Password-never-in-logs' in client.post("/vault/1/reveal/1").data
    with vault_app.app_context():
        assert db.session.get(Credential, 1).archived
        assert db.session.scalar(db.select(db.func.count()).select_from(CredentialVersion)) == 1
    client.post("/logout")
    login(client, "other")
    unlock(client)
    assert client.post("/vault/1/archive").status_code == 404
    client.post("/logout")
    login(client)
    unlock(client)
    assert client.post("/vault/1/archive").status_code == 302
    with vault_app.app_context():
        assert not db.session.get(Credential, 1).archived
