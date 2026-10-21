from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import LONGTEXT

db = SQLAlchemy()


def now():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    employee_no = db.Column(db.String(64), unique=True)
    role = db.Column(db.String(20), nullable=False, default="requester")
    active = db.Column(db.Boolean, nullable=False, default=True)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)


class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    serial = db.Column(db.String(100), unique=True)
    category = db.Column(db.String(40), nullable=False)
    brand = db.Column(db.String(80), default="")
    model = db.Column(db.String(100), default="")
    specs = db.Column(db.Text, default="")
    location = db.Column(db.String(120), default="")
    status = db.Column(db.String(30), nullable=False, default="available")
    created_at = db.Column(db.DateTime, default=now, nullable=False)


class AssetService(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    performed_on = db.Column(db.Date, nullable=False)
    service_type = db.Column(db.String(30), nullable=False)
    responsible = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    result = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(500), nullable=False, default="")
    restoration = db.Column(db.String(20), nullable=False, default="not_tested")
    next_due_on = db.Column(db.Date)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    author = db.relationship(User)


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    employee_no = db.Column(db.String(64), nullable=False)
    employee_name = db.Column(db.String(255), nullable=False)
    started_at = db.Column(db.DateTime, default=now, nullable=False)
    ended_at = db.Column(db.DateTime)
    assigned_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset = db.relationship(Asset)


class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(60), nullable=False)
    target = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    subject = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    solution = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    updated_at = db.Column(db.DateTime, default=now, nullable=False)
    resolved_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    revision = db.Column(db.Integer, nullable=False, default=1)
    requester = db.relationship(User, foreign_keys=[requester_id])
    assigned_to = db.relationship(User, foreign_keys=[assigned_to_id])
    asset = db.relationship(Asset)

    @property
    def folio(self):
        return f"IT-{self.id:06d}"


class TicketComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    internal = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    author = db.relationship(User)


class TicketEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    actor = db.relationship(User)


class VaultAccess(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    it_access = db.Column(db.Boolean, nullable=False, default=False)
    # Legacy columns retained to avoid altering existing installations.
    # The vault now verifies only the platform password; TOTP is not used.
    totp_secret = db.Column(db.Text)
    last_counter = db.Column(db.BigInteger, nullable=False, default=-1)
    failures = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)


credential_assets = db.Table("credential_asset",
    db.Column("credential_id", db.Integer, db.ForeignKey("credential.id"), primary_key=True),
    db.Column("asset_id", db.Integer, db.ForeignKey("asset.id"), primary_key=True))


class Credential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(40), nullable=False)
    url = db.Column(db.String(500), nullable=False, default="")
    owner_employee_no = db.Column(db.String(64), index=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    archived = db.Column(db.Boolean, nullable=False, default=False)
    current_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    assets = db.relationship(Asset, secondary=credential_assets)


class CredentialVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    ciphertext = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    restored_from = db.Column(db.Integer)
    author = db.relationship(User)
    __table_args__ = (db.UniqueConstraint("credential_id", "number"),)


def audit(action, target):
    from flask import g
    db.session.add(Audit(actor_id=g.user.id if g.user else None,
                         action=action, target=str(target)))
