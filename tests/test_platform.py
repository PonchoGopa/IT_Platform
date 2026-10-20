import pytest
from werkzeug.security import generate_password_hash
from it_platform import create_app
from it_platform.models import Asset, Assignment, User, db


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-key-" * 8,
                      "SQLALCHEMY_DATABASE_URI": "sqlite://",
                      "WTF_CSRF_ENABLED": False, "SESSION_COOKIE_SECURE": False,
                      "RH_DATABASE_URL": "", "RH_NAME_COLUMNS": ""})
    with app.app_context():
        db.create_all()
        for username, role, employee in [("admin", "admin", None), ("leader", "requester", "123"), ("other", "requester", "456")]:
            db.session.add(User(username=username, role=role, employee_no=employee,
                                password_hash=generate_password_hash("A-long-test-password")))
        db.session.add(Asset(code="PC-001", category="Computadora"))
        db.session.commit()
    yield app


def login(client, username="admin", password="A-long-test-password"):
    return client.post("/login", data={"username": username, "password": password})


def test_permissions_and_csrf(app):
    client = app.test_client()
    assert client.get("/assets").status_code == 302
    login(client, "leader")
    for path in ["/employees", "/audit", "/assets/new", "/assets/1"]:
        assert client.get(path).status_code == 403
    assert client.post("/assets/1/status", data={"status": "retired"}).status_code == 403
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/logout").status_code == 400


def test_assignment_history_and_owner_scope(app, monkeypatch):
    monkeypatch.setattr("it_platform.routes.lookup", lambda *a, **k: [{"employee_no": "123", "name": "Persona Prueba"}])
    client = app.test_client()
    login(client)
    assert client.post("/assets/1/assign", data={"employee_no": "123"}).status_code == 302
    client.post("/assets/1/assign", data={"employee_no": "123"})
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Assignment)) == 1
    client.post("/logout")
    login(client, "leader")
    assert client.get("/assets/1").status_code == 200
    client.post("/logout")
    login(client, "other")
    assert client.get("/assets/1").status_code == 403
    assert b"PC-001" not in client.get("/assets").data
    client.post("/logout")
    login(client)
    client.post("/assets/1/return")
    client.post("/assets/1/assign", data={"employee_no": "123"})
    with app.app_context():
        history = db.session.scalars(db.select(Assignment).order_by(Assignment.id)).all()
        assert len(history) == 2
        assert history[0].ended_at is not None
        assert history[1].ended_at is None


def test_duplicate_serial_and_templates(app):
    client = app.test_client()
    login(client)
    for path in ["/", "/assets", "/assets/1", "/assets/new", "/employees", "/audit"]:
        assert client.get(path).status_code == 200
    payload = {"code": "PC-002", "serial": "ABC", "category": "Laptop"}
    assert client.post("/assets/new", data=payload).status_code == 302
    payload["code"] = "PC-003"
    assert client.post("/assets/new", data=payload).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Asset)) == 2


def test_lockout(app):
    client = app.test_client()
    for _ in range(5):
        assert login(client, password="bad").status_code == 200
    assert login(client).status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_directory_failure_prevents_assignment(app):
    client = app.test_client()
    login(client)
    client.post("/assets/1/assign", data={"employee_no": "123"})
    with app.app_context():
        assert db.session.get(Asset, 1).status == "available"
        assert db.session.scalar(db.select(db.func.count()).select_from(Assignment)) == 0


def test_identifier_validation():
    from it_platform.employees import identifier
    with pytest.raises(ValueError):
        identifier("employee_ki; DROP TABLE user")


def test_reject_rh_as_platform_database():
    with pytest.raises(RuntimeError, match="distinta de kimexrh"):
        create_app({"TESTING": True, "SECRET_KEY": "test-key-" * 8,
                    "SQLALCHEMY_DATABASE_URI": "mysql+pymysql://user:pass@localhost/kimexrh"})


@pytest.mark.parametrize("uri", [None, "sqlite:///it_platform.db"])
def test_runtime_requires_mysql(uri):
    with pytest.raises(RuntimeError, match="MySQL"):
        create_app({"SECRET_KEY": "test-key-" * 8,
                    "SQLALCHEMY_DATABASE_URI": uri})


@pytest.mark.parametrize("search,exact,expected", [
    ("", False, ["1"]), ("Persona", False, ["1"]),
    ("2", False, []), ("1", True, ["1"]), ("2", True, []),
])
def test_directory_only_active(app, search, exact, expected):
    from sqlalchemy import create_engine, event, text
    from it_platform.employees import lookup
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def mysql_concat(connection, record):
        connection.create_function("CONCAT_WS", -1,
            lambda sep, *values: sep.join(str(v) for v in values if v is not None))

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE employee_ki (Employee_No INT, Employee_Name TEXT, Active INT)"))
        conn.execute(text("INSERT INTO employee_ki VALUES (1, 'Persona activa', 1), (2, 'Persona baja', 0)"))
    app.config.update(RH_DATABASE_URL="configured", RH_NAME_COLUMNS="Employee_Name",
                      RH_DEPARTMENT_COLUMN="")
    app.extensions["rh_engine"] = engine
    try:
        with app.app_context():
            assert [r["employee_no"] for r in lookup(search, exact)] == expected
    finally:
        engine.dispose()
