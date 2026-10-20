from test_platform import app, login
from it_platform.models import Asset, Assignment, Ticket, TicketComment, TicketEvent, User, db


def create_ticket(client, **overrides):
    fields = {"subject": "Sin acceso al ERP", "description": "El portal no permite ingresar.",
              "category": "ERP", "priority": "normal", "asset_id": ""}
    fields.update(overrides)
    return client.post("/tickets/new", data=fields)


def management_data(app, **overrides):
    with app.app_context():
        t = db.session.get(Ticket, 1)
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        fields = {"revision": str(t.revision), "assigned_to_id": str(admin.id),
                  "status": t.status, "priority": t.priority, "solution": t.solution}
    fields.update(overrides)
    return fields


def test_requester_scope_and_private_notes(app):
    client = app.test_client()
    login(client, "leader")
    assert create_ticket(client).status_code == 302
    assert client.get("/tickets/1").status_code == 200
    assert client.get("/tickets/new").status_code == 200
    assert client.post("/tickets/1/manage", data={}).status_code == 403
    assert client.post("/tickets/1/comments", data={"body": "Oculta", "internal": "1"}).status_code == 403
    client.post("/logout")
    login(client, "other")
    assert b"Sin acceso al ERP" not in client.get("/tickets").data
    assert client.get("/tickets/1").status_code == 404
    assert client.post("/tickets/1/comments", data={"body": "Intrusion"}).status_code == 404
    client.post("/logout")
    login(client)
    assert client.post("/tickets/1/comments", data={"body": "NOTA_PRIVADA", "internal": "1"}).status_code == 302
    assert b"NOTA_PRIVADA" in client.get("/tickets/1").data
    assert client.get("/tickets").status_code == 200
    client.post("/logout")
    login(client, "leader")
    assert b"NOTA_PRIVADA" not in client.get("/tickets/1").data
    assert client.post("/tickets/1/comments", data={"body": "Ya reinicie"}).status_code == 302


def test_ticket_status_solution_closure_and_reopen(app):
    client = app.test_client()
    login(client)
    create_ticket(client)
    # Cannot jump directly from new to closed or resolve without a solution.
    client.post("/tickets/1/manage", data=management_data(app, status="closed", solution="Hecho"))
    with app.app_context():
        assert db.session.get(Ticket, 1).status == "new"
    client.post("/tickets/1/manage", data=management_data(app, status="working"))
    client.post("/tickets/1/manage", data=management_data(app, status="resolved"))
    with app.app_context():
        assert db.session.get(Ticket, 1).status == "working"
    client.post("/tickets/1/manage", data=management_data(app, status="resolved", solution="Acceso restablecido"))
    client.post("/tickets/1/manage", data=management_data(app, status="closed"))
    with app.app_context():
        ticket = db.session.get(Ticket, 1)
        assert ticket.closed_at and ticket.resolved_at
        assert ticket.folio == "IT-000001"
    client.post("/tickets/1/comments", data={"body": "Comentario cerrado"})
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(TicketComment)) == 0
    client.post("/tickets/1/manage", data=management_data(app, status="working"))
    with app.app_context():
        ticket = db.session.get(Ticket, 1)
        assert ticket.status == "working"
        assert ticket.closed_at is None and ticket.resolved_at is None
        assert db.session.scalar(db.select(db.func.count()).select_from(TicketEvent)) >= 6


def test_ticket_asset_scope_and_validation(app):
    client = app.test_client()
    login(client, "leader")
    assert create_ticket(client, asset_id="1").status_code == 403
    assert create_ticket(client, subject="").status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Ticket)) == 0
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        db.session.add(Assignment(asset_id=1, employee_no="123", employee_name="Prueba", assigned_by=admin.id))
        db.session.commit()
    assert create_ticket(client, asset_id="1").status_code == 302
    with app.app_context():
        assert db.session.get(Ticket, 1).asset_id == 1


def test_invalid_assignee_and_stale_edit_are_atomic(app):
    client = app.test_client()
    login(client)
    create_ticket(client)
    with app.app_context():
        requester = db.session.scalar(db.select(User).where(User.username == "leader"))
        requester_id = requester.id
    client.post("/tickets/1/manage", data=management_data(app, assigned_to_id=str(requester_id), priority="urgent"))
    with app.app_context():
        assert db.session.get(Ticket, 1).priority == "normal"
    stale = management_data(app, priority="urgent")
    client.post("/tickets/1/comments", data={"body": "Nuevo dato"})
    client.post("/tickets/1/manage", data=stale)
    with app.app_context():
        assert db.session.get(Ticket, 1).priority == "normal"


def test_ticket_filters_and_csrf(app):
    client = app.test_client()
    login(client, "leader")
    create_ticket(client)
    assert b"Sin acceso al ERP" in client.get("/tickets?q=IT-000001&status=new").data
    assert b"Sin acceso al ERP" not in client.get("/tickets?status=closed").data
    app.config["WTF_CSRF_ENABLED"] = True
    assert create_ticket(client).status_code == 400
    assert client.post("/tickets/1/comments", data={"body": "Sin token"}).status_code == 400
