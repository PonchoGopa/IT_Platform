from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from .models import User, audit, db

bp = Blueprint("auth", __name__)
DUMMY_HASH = generate_password_hash("unused-dummy-password")


def require_roles(*roles):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for("auth.login"))
            if roles and g.user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorate


@bp.before_app_request
def load_user():
    g.user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    if g.user and not g.user.active:
        session.clear()
        g.user = None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(User).where(User.username == username))
        valid = check_password_hash(user.password_hash if user else DUMMY_HASH, password)
        locked = user and user.locked_until and user.locked_until > datetime.utcnow()
        if user and user.active and valid and not locked:
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            g.user = user
            user.failed_attempts = 0
            user.locked_until = None
            audit("login", user.id)
            db.session.commit()
            return redirect(url_for("main.home"))
        if user and not locked:
            user.failed_attempts += 1
            if user.failed_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                user.failed_attempts = 0
            db.session.commit()
        flash("Acceso no válido o temporalmente bloqueado.", "error")
    return render_template("login.html")


@bp.post("/logout")
@require_roles()
def logout():
    audit("logout", g.user.id)
    db.session.commit()
    session.clear()
    return redirect(url_for("auth.login"))
