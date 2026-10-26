import os
from datetime import timedelta
import click
from dotenv import load_dotenv
from flask import Flask
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash
from .models import User, db


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        MAX_CONTENT_LENGTH=1024 * 1024,
        RH_DATABASE_URL=os.getenv("RH_DATABASE_URL", ""),
        RH_TABLE=os.getenv("RH_TABLE", "employee_ki"),
        RH_ID_COLUMN=os.getenv("RH_ID_COLUMN", "Employee_No"),
        RH_NAME_COLUMNS=os.getenv("RH_NAME_COLUMNS", ""),
        RH_DEPARTMENT_COLUMN=os.getenv("RH_DEPARTMENT_COLUMN", ""),
        VAULT_KEY_FILE=os.getenv("VAULT_KEY_FILE", ""),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"].startswith("replace-with-"):
        raise RuntimeError("Configura SECRET_KEY con al menos 32 caracteres aleatorios.")
    from sqlalchemy.engine import make_url
    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("Configura DATABASE_URL con la conexión MySQL de IT Platform.")
    platform_url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if not app.testing and (platform_url.drivername != "mysql+pymysql" or not platform_url.database):
        raise RuntimeError("IT Platform requiere una base MySQL mediante mysql+pymysql.")
    if platform_url.database and platform_url.database.lower() == "kimexrh":
        raise RuntimeError("La base de IT Platform debe ser distinta de kimexrh.")
    if os.getenv("APP_ENV") == "production" and not app.testing:
        if not app.config["SESSION_COOKIE_SECURE"] or not app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql+pymysql://"):
            raise RuntimeError("Producción requiere cookies seguras y una base MySQL propia.")
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    CSRFProtect(app)
    from .auth import bp as auth
    from .routes import bp as main
    from .tickets import bp as tickets
    from .vault import bp as vault
    app.register_blueprint(auth)
    app.register_blueprint(main)
    from .asset_services import bp as asset_services
    app.register_blueprint(asset_services)
    app.register_blueprint(tickets)
    app.register_blueprint(vault)
    from .reports import bp as reports
    app.register_blueprint(reports)
    from .vault_cli import register
    register(app)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.cli.command("init-db")
    def init_db():
        """Create only the platform tables, never RH tables."""
        db.create_all()
        click.echo("Tablas de IT Platform creadas.")

    @app.cli.command("upgrade-db")
    def upgrade_db():
        """Apply additive schema updates to existing platform tables."""
        from sqlalchemy import inspect, text
        if not inspect(db.engine).has_table("asset"):
            raise click.ClickException("Primero ejecuta init-db.")
        from .models import AssetCodeCounter
        AssetCodeCounter.__table__.create(db.engine, checkfirst=True)
        columns = {column["name"] for column in inspect(db.engine).get_columns("asset")}
        if "alias" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE asset ADD COLUMN alias VARCHAR(120) NOT NULL DEFAULT ''"))
            click.echo("Campo alias agregado a los equipos.")
        else:
            click.echo("El esquema ya está actualizado.")

    @app.cli.command("create-user")
    @click.option("--username", prompt=True)
    @click.option("--role", type=click.Choice(["admin", "technician", "requester"]), default="requester")
    @click.option("--employee-no", default=None)
    @click.password_option(confirmation_prompt=True)
    def create_user(username, role, employee_no, password):
        username = username.strip().lower()
        if not username or len(username) > 100 or len(password) < 12:
            raise click.ClickException("Usuario inválido o contraseña menor a 12 caracteres.")
        if employee_no:
            from .employees import lookup, DirectoryUnavailable
            try:
                if not lookup(employee_no, exact=True):
                    raise click.ClickException("Empleado inexistente en RH.")
            except DirectoryUnavailable as exc:
                raise click.ClickException(str(exc))
        if db.session.scalar(db.select(User).where(User.username == username)):
            raise click.ClickException("El usuario ya existe.")
        db.session.add(User(username=username, role=role, employee_no=employee_no,
                            password_hash=generate_password_hash(password)))
        from sqlalchemy.exc import IntegrityError
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise click.ClickException("El empleado ya tiene un usuario asociado.") from None
        click.echo("Usuario creado.")
    return app
