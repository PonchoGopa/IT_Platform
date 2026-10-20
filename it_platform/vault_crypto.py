"""Authenticated encryption for vault data. No secrets in logs."""
import json
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


class VaultError(Exception):
    pass


def cipher():
    try:
        path = current_app.config.get("VAULT_KEY_FILE")
        if not path:
            raise ValueError()
        return Fernet(Path(path).read_bytes().strip())
    except (OSError, ValueError):
        raise VaultError("La bóveda no está disponible. IT debe revisar su clave de cifrado.") from None


def encrypt(data):
    return cipher().encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()


def decrypt(token):
    try:
        return json.loads(cipher().decrypt(token.encode()).decode())
    except (InvalidToken, ValueError, UnicodeError, TypeError):
        raise VaultError("No fue posible descifrar el registro. Revisa la clave y el respaldo.") from None

