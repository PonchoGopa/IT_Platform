from test_platform import app, login
from test_vault import vault_app, prepare_access, unlock, create


ROWS = [{"employee_no": "123", "name": "Ana Pérez"},
        {"employee_no": "456", "name": "Luis Gómez"}]


def test_asset_employee_dropdown(app, monkeypatch):
    monkeypatch.setattr("it_platform.routes.employee_options", lambda: (ROWS, None))
    client = app.test_client()
    login(client)
    response = client.get("/assets/1")
    assert response.status_code == 200
    assert b'<select name="employee_no"' in response.data
    assert '123 — Ana Pérez'.encode() in response.data
    assert '456 — Luis Gómez'.encode() in response.data
    assert b'<input name="employee_no"' not in response.data


def test_vault_owner_dropdown_preserves_selection_and_permissions(vault_app, monkeypatch):
    monkeypatch.setattr("it_platform.vault.employee_options", lambda: (ROWS, None))
    prepare_access(vault_app, "admin", True)
    prepare_access(vault_app, "leader")
    client = vault_app.test_client()
    login(client)
    unlock(client)
    response = client.get("/vault/new")
    assert b'<select name="owner_employee_no"' in response.data
    assert '456 — Luis Gómez'.encode() in response.data
    create(client, owner_employee_no="456")
    response = client.get("/vault/1/edit")
    assert b'value="456" selected' in response.data
    client.post("/logout")
    login(client, "leader")
    unlock(client)
    response = client.get("/vault/new")
    assert b'owner_employee_no' not in response.data
    assert 'Luis Gómez'.encode() not in response.data


def test_directory_error_preserves_owner_and_disables_assignment(vault_app, monkeypatch):
    monkeypatch.setattr("it_platform.vault.employee_options", lambda: ([], "RH no disponible"))
    monkeypatch.setattr("it_platform.routes.employee_options", lambda: ([], "RH no disponible"))
    prepare_access(vault_app, "admin", True)
    client = vault_app.test_client()
    login(client)
    unlock(client)
    create(client, owner_employee_no="123")
    response = client.get("/vault/1/edit")
    assert response.status_code == 200
    assert b'name="owner_employee_no" value="123"' in response.data
    response = client.get("/assets/1")
    assert b'disabled' in response.data and b'RH no disponible' in response.data


def test_options_include_more_than_one_hundred_active_employees(app):
    from sqlalchemy import create_engine, event, text
    from it_platform.employees import employee_options, lookup
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def concat(conn, record):
        conn.create_function("CONCAT_WS", -1, lambda sep, *parts: sep.join(str(p) for p in parts if p is not None))

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE employee_ki (Employee_No INT, Employee_Name TEXT, Active INT)"))
        conn.execute(text("INSERT INTO employee_ki VALUES (:id, :name, :active)"),
                     [{"id": n, "name": f"Empleado {n:03}", "active": 1} for n in range(1, 106)] +
                     [{"id": 999, "name": "Baja", "active": 0}])
    app.config.update(RH_DATABASE_URL="configured", RH_NAME_COLUMNS="Employee_Name", RH_DEPARTMENT_COLUMN="")
    app.extensions["rh_engine"] = engine
    try:
        with app.app_context():
            assert len(lookup()) == 100
            rows, error = employee_options()
            assert error is None and len(rows) == 105
            assert rows[-1]["employee_no"] == "105"
            assert all(row["employee_no"] != "999" for row in rows)
    finally:
        engine.dispose()
