from pathlib import Path
import click
from cryptography.fernet import Fernet
from .models import Audit, User, VaultAccess, db


def register(app):
    @app.cli.command("vault-init-key")
    @click.option("--path", "key_path", required=True, type=click.Path(dir_okay=False))
    def init_key(key_path):
        """Generate a new key file; never replace an existing key."""
        target = Path(key_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(Fernet.generate_key() + b"\n")
        except FileExistsError:
            raise click.ClickException("Ya existe una clave en esa ruta. No se reemplazó.") from None
        click.echo("Clave creada. Configura VAULT_KEY_FILE, restringe sus permisos y respáldala por separado.")

    @app.cli.command("vault-grant-it")
    @click.option("--username", required=True)
    @click.option("--revoke", is_flag=True, help="Retirar acceso global; conserva el acceso propio.")
    def grant(username, revoke):
        user = db.session.scalar(db.select(User).where(User.username == username.strip().lower()))
        if not user or user.role not in ("admin", "technician") or not user.active:
            raise click.ClickException("Selecciona un administrador o técnico activo.")
        access = db.session.get(VaultAccess, user.id)
        if not access:
            access = VaultAccess(user_id=user.id)
            db.session.add(access)
        access.it_access = not revoke
        db.session.add(Audit(action="vault.it_revoked" if revoke else "vault.it_granted", target=str(user.id)))
        db.session.commit()
        click.echo("Permiso de bóveda actualizado.")

