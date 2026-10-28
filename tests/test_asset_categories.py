from test_platform import app, login
from it_platform.models import Asset, Assignment, db


def test_inventory_groups_legacy_types_and_combines_search(app):
    with app.app_context():
        db.session.add_all([
            Asset(code="LAP-2", alias="Oficina", category="Laptop"),
            Asset(code="TAB-3", category="Tablet"),
            Asset(code="PRINT-4", category="Impresora"),
            Asset(code="NET-5", category="Red"),
            Asset(code="SCREEN-6", category="Monitor"),
            Asset(code="CUSTOM-7", category="Legacy"),
        ])
        db.session.commit()
    client = app.test_client()
    login(client)
    page = client.get("/assets?group=computing").get_data(as_text=True)
    assert all(code in page for code in ("PC-001", "LAP-2", "TAB-3"))
    assert all(code not in page for code in ("PRINT-4", "NET-5", "SCREEN-6"))
    page = client.get("/assets?group=computing&q=Oficina").get_data(as_text=True)
    assert "LAP-2" in page and "PC-001" not in page
    for group, code in [("printers", "PRINT-4"), ("communication", "NET-5"),
                        ("peripherals", "SCREEN-6"), ("other", "CUSTOM-7")]:
        page = client.get("/assets", query_string={"group": group}).get_data(as_text=True)
        assert code in page and "LAP-2" not in page
    assert client.get("/assets?group=invalid").status_code == 400
    assert "PRINT-4" in client.get("/assets").get_data(as_text=True)


def test_group_form_validates_pair_and_preserves_existing_type(app):
    client = app.test_client()
    login(client)
    page = client.get("/assets/1/edit").get_data(as_text=True)
    assert 'value="computing" selected' in page and 'value="Computadora" data-group="computing" selected' in page
    for group, kind in [("printers", "Laptop"), ("invalid", "Laptop")]:
        response = client.post("/assets/1/edit", data={
            "code": "PC-001", "asset_group": group, "category": kind})
        assert response.status_code == 200
        with app.app_context():
            assert db.session.get(Asset, 1).category == "Computadora"
    response = client.post("/assets/1/edit", data={
        "code": "PC-001", "asset_group": "communication", "category": "Red"})
    assert response.status_code == 302
    assert "PC-001" in client.get("/assets?group=communication").get_data(as_text=True)
    assert "PC-001" not in client.get("/assets?group=computing").get_data(as_text=True)
    assert client.post("/assets/new", data={"asset_group": "printers", "category": "Impresora"}).status_code == 302


def test_group_filter_preserves_requester_scope(app):
    with app.app_context():
        db.session.add(Asset(code="PRIVATE", category="Laptop"))
        db.session.add(Assignment(asset_id=1, employee_no="123", employee_name="Test", assigned_by=1))
        db.session.commit()
    client = app.test_client()
    login(client, "leader")
    page = client.get("/assets?group=computing").get_data(as_text=True)
    assert "PC-001" in page and "PRIVATE" not in page
    assert "PC-001" not in client.get("/assets?group=printers").get_data(as_text=True)
