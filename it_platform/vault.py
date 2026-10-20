from datetime import datetime, timedelta
from functools import wraps
import hashlib
import time
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import or_
from werkzeug.security import check_password_hash
from .auth import require_roles
from .employees import DirectoryUnavailable, employee_options, lookup
from .models import (Asset, Assignment, Credential, CredentialVersion, User, VaultAccess,
                     audit, db)
from .vault_crypto import VaultError, cipher, decrypt, encrypt

bp = Blueprint("vault", __name__, url_prefix="/vault")
KINDS = ["Portal", "Microsoft 365 / Office", "Configuración / activación", "Inicio de sesión",
         "Administrador local", "PIN de equipo", "Recuperación / BitLocker", "Servicio", "Compartida", "Otra"]
SECRET_FIELDS = {"username": "Usuario / correo", "password": "Contraseña", "pin": "PIN", "code": "Código / clave de recuperación", "notes": "Notas protegidas"}


def access_record(lock=False):
    stmt = db.select(VaultAccess).where(VaultAccess.user_id == g.user.id)
    return db.session.scalar(stmt.with_for_update() if lock else stmt)


def privileged():
    access = access_record()
    return bool(g.user.role in ("admin", "technician") and access and access.it_access)


def stamp():
    return hashlib.sha256(("password-only-v1:" + g.user.password_hash).encode()).hexdigest()


def verified(fn):
    @wraps(fn)
    @require_roles()
    def wrapped(*args, **kwargs):
        cipher()
        verified_at = session.get("vault_verified_at", 0)
        if (not isinstance(verified_at, (int, float)) or not 0 <= time.time() - verified_at < 300
                or session.get("vault_stamp") != stamp()):
            if request.method == "GET":
                session["vault_next"] = request.full_path.rstrip("?")
            return redirect(url_for("vault.unlock"))
        return fn(*args, **kwargs)
    return wrapped


def return_to_vault():
    target = session.pop("vault_next", "")
    if not (target == "/vault" or target.startswith("/vault/") or target.startswith("/vault?")):
        target = url_for("vault.index")
    return redirect(target)


@bp.errorhandler(VaultError)
def unavailable(error):
    db.session.rollback()
    return render_template("vault/unavailable.html", message=str(error)), 503


@bp.app_context_processor
def context():
    return {"credential_kinds": KINDS, "secret_fields": SECRET_FIELDS}


def credential_scope():
    stmt = db.select(Credential)
    if not privileged():
        terms = [Credential.owner_user_id == g.user.id]
        if g.user.employee_no:
            terms.append(Credential.owner_employee_no == g.user.employee_no)
        stmt = stmt.where(or_(*terms))
    return stmt


def get_credential(credential_id, lock=False):
    stmt = credential_scope().where(Credential.id == credential_id)
    result = db.session.scalar(stmt.with_for_update() if lock else stmt)
    if result is None:
        abort(404)
    return result


def read_version(credential, number):
    version = db.session.scalar(db.select(CredentialVersion).where(
        CredentialVersion.credential_id == credential.id, CredentialVersion.number == number))
    if not version:
        abort(404)
    data = decrypt(version.ciphertext)
    if data.get("credential_id") != credential.id or data.get("number") != number:
        raise VaultError("No fue posible validar la versión solicitada.")
    return data, version


def save_version(credential, payload, restored_from=None):
    data = {"credential_id": credential.id, "number": credential.current_version,
            "metadata": {"title": credential.title, "kind": credential.kind, "url": credential.url,
                         "owner_employee_no": credential.owner_employee_no,
                         "owner_user_id": credential.owner_user_id,
                         "asset_ids": [asset.id for asset in credential.assets]}, "secrets": payload}
    db.session.add(CredentialVersion(credential_id=credential.id, number=credential.current_version,
        ciphertext=encrypt(data), author_id=g.user.id, restored_from=restored_from))


def failed_verification(access):
    access.failures += 1
    if access.failures >= 5:
        access.locked_until = datetime.utcnow() + timedelta(minutes=15)
        access.failures = 0
    audit("vault.verify_failed", g.user.id)
    db.session.commit()


def blocked(access):
    return access.locked_until and access.locked_until > datetime.utcnow()


@bp.route("/setup", methods=["GET", "POST"])
@require_roles()
def setup():
    # Compatibility for bookmarks from the former authenticator flow.
    session.pop("vault_pending", None)
    return redirect(url_for("vault.unlock"))


@bp.route("/unlock", methods=["GET", "POST"])
@require_roles()
def unlock():
    cipher()
    if request.method == "POST":
        access = access_record(lock=True)
        if access is None:
            access = VaultAccess(user_id=g.user.id)
            db.session.add(access)
            db.session.flush()
        if blocked(access):
            db.session.rollback()
            flash("Verificación temporalmente bloqueada. Intenta después de 15 minutos.", "error")
            return render_template("vault/unlock.html"), 429
        if check_password_hash(g.user.password_hash, request.form.get("password", "")):
            access.failures = 0
            access.locked_until = None
            session.pop("vault_pending", None)
            session["vault_verified_at"] = time.time()
            session["vault_stamp"] = stamp()
            audit("vault.unlock", g.user.id)
            db.session.commit()
            return return_to_vault()
        failed_verification(access)
        flash("Contraseña no válida.", "error")
    return render_template("vault/unlock.html")


@bp.post("/lock")
@require_roles()
def lock():
    session.pop("vault_verified_at", None)
    session.pop("vault_stamp", None)
    session.pop("vault_pending", None)
    session.pop("vault_next", None)
    return redirect(url_for("main.home"))


@bp.get("")
@verified
def index():
    query = request.args.get("q", "").strip()[:160]
    archived = request.args.get("archived") == "1"
    stmt = credential_scope().where(Credential.archived.is_(archived))
    asset_id = request.args.get("asset_id", type=int)
    if asset_id is not None:
        stmt = stmt.where(Credential.assets.any(Asset.id == asset_id))
    if query:
        stmt = stmt.where(Credential.title.contains(query, autoescape=True))
    rows = db.session.scalars(stmt.order_by(Credential.title).limit(200)).all()
    return render_template("vault/index.html", rows=rows, query=query, archived=archived,
                           vault_it=privileged(), asset_id=asset_id)


def available_assets():
    stmt = db.select(Asset)
    if not privileged():
        if not g.user.employee_no:
            return []
        stmt = stmt.join(Assignment).where(Assignment.employee_no == g.user.employee_no, Assignment.ended_at.is_(None))
    return db.session.scalars(stmt.order_by(Asset.code)).all()


@bp.route("/new", methods=["GET", "POST"])
@verified
def new():
    return credential_form()


@bp.route("/<int:credential_id>/edit", methods=["GET", "POST"])
@verified
def edit(credential_id):
    credential = get_credential(credential_id, lock=request.method == "POST")
    if credential.archived:
        abort(403)
    return credential_form(credential)


def credential_form(credential=None):
    vault_it = privileged()
    assets = available_assets()
    if request.method == "POST":
        if credential and request.form.get("version") != str(credential.current_version):
            db.session.rollback()
            flash("La credencial cambió. Abre nuevamente la edición antes de guardar.", "error")
            return redirect(url_for("vault.detail", credential_id=credential.id))
        title = request.form.get("title", "").strip()
        kind = request.form.get("kind", "")
        url = request.form.get("url", "").strip()
        payload = {key: request.form.get(key, "") for key in SECRET_FIELDS}
        owner = request.form.get("owner_employee_no", "").strip() if vault_it else g.user.employee_no
        selected = request.form.getlist("asset_ids")
        by_id = {str(a.id): a for a in assets}
        errors = []
        if not title or len(title) > 160 or kind not in KINDS or len(url) > 500:
            errors.append("Revisa el nombre, tipo y dirección del servicio.")
        if any(len(value) > (10000 if key == "notes" else 2000) for key, value in payload.items()):
            errors.append("Los valores protegidos exceden la longitud permitida.")
        if any(item not in by_id for item in selected):
            abort(403)
        if credential:
            previous, _ = read_version(credential, credential.current_version)
            # Blank secret fields preserve the value unless explicitly cleared.
            for key in SECRET_FIELDS:
                if request.form.get("clear_" + key) == "1":
                    payload[key] = ""
                elif payload[key] == "":
                    payload[key] = previous["secrets"].get(key, "")
        if not any(payload.values()):
            errors.append("Ingresa al menos un dato protegido.")
        if owner and (not credential or owner != credential.owner_employee_no):
            try:
                if not lookup(owner, exact=True):
                    errors.append("El empleado debe estar activo en RH.")
            except DirectoryUnavailable as exc:
                errors.append(str(exc))
        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, "error")
        else:
            creating = credential is None
            if creating:
                credential = Credential(title=title, kind=kind)
                db.session.add(credential)
                db.session.flush()
            else:
                credential.current_version += 1
            credential.title, credential.kind, credential.url = title, kind, url
            credential.owner_employee_no = owner or None
            credential.owner_user_id = None if owner else (credential.owner_user_id or g.user.id)
            credential.assets = [by_id[key] for key in dict.fromkeys(selected)]
            save_version(credential, payload)
            audit("vault.create" if creating else "vault.update", credential.id)
            db.session.commit()
            return redirect(url_for("vault.detail", credential_id=credential.id))
    employees, employee_error = employee_options() if vault_it else ([], None)
    return render_template("vault/form.html", credential=credential, assets=assets, vault_it=vault_it,
                           employees=employees, employee_error=employee_error)


@bp.get("/<int:credential_id>")
@verified
def detail(credential_id):
    credential = get_credential(credential_id)
    versions = db.session.scalars(db.select(CredentialVersion).where(CredentialVersion.credential_id == credential.id).order_by(CredentialVersion.number.desc())).all() if privileged() else []
    return render_template("vault/detail.html", credential=credential, versions=versions, vault_it=privileged())


@bp.post("/<int:credential_id>/reveal/<int:number>")
@verified
def reveal(credential_id, number):
    credential = get_credential(credential_id, lock=True)
    if number != credential.current_version and not privileged():
        abort(403)
    data, version = read_version(credential, number)
    audit("vault.reveal", f"credential:{credential.id}:v{number}")
    db.session.commit()
    return render_template("vault/reveal.html", credential=credential, data=data, version=version)


@bp.post("/<int:credential_id>/restore/<int:number>")
@verified
def restore(credential_id, number):
    if not privileged():
        abort(403)
    credential = get_credential(credential_id, lock=True)
    if request.form.get("version") != str(credential.current_version):
        db.session.rollback()
        flash("La credencial cambió. Revisa el historial antes de recuperar.", "error")
    else:
        data, _ = read_version(credential, number)
        meta = data["metadata"]
        for key in ("title", "kind", "url", "owner_employee_no", "owner_user_id"):
            setattr(credential, key, meta[key])
        credential.assets = db.session.scalars(db.select(Asset).where(Asset.id.in_(meta["asset_ids"]))).all()
        credential.current_version += 1
        save_version(credential, data["secrets"], restored_from=number)
        audit("vault.restore", f"credential:{credential.id}:from{number}")
        db.session.commit()
        flash("Versión recuperada. La contraseña del servicio externo no se modifica.")
    return redirect(url_for("vault.detail", credential_id=credential_id))


@bp.post("/<int:credential_id>/archive")
@verified
def archive(credential_id):
    credential = get_credential(credential_id, lock=True)
    # Owners can inactivate; only authorized IT can reactivate.
    if credential.archived and not privileged():
        abort(403)
    credential.archived = not credential.archived
    audit("vault.archive" if credential.archived else "vault.reactivate", credential.id)
    db.session.commit()
    return redirect(url_for("vault.detail", credential_id=credential_id))
