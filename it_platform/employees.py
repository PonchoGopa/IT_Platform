"""Isolated read-only adapter. No RH schema creation or writes."""
import re
from flask import current_app
from sqlalchemy import create_engine, text


class DirectoryUnavailable(Exception):
    pass


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Identificador RH inválido")
    return f"`{value}`"


def lookup(search="", exact=False, *, limit=100):
    cfg = current_app.config
    if not cfg.get("RH_DATABASE_URL") or not cfg.get("RH_NAME_COLUMNS"):
        raise DirectoryUnavailable("Falta configurar la conexión y las columnas de RH.")
    try:
        table = identifier(cfg["RH_TABLE"])
        key = identifier(cfg["RH_ID_COLUMN"])
        names = [identifier(c.strip()) for c in cfg["RH_NAME_COLUMNS"].split(",") if c.strip()]
        if not names:
            raise ValueError("Faltan columnas de nombre")
        fullname = "CONCAT_WS(' ', " + ", ".join(names) + ")"
        dept = identifier(cfg["RH_DEPARTMENT_COLUMN"]) if cfg.get("RH_DEPARTMENT_COLUMN") else "''"
        predicate = f"CAST({key} AS CHAR) = :query" if exact else f"(CAST({key} AS CHAR) LIKE :query OR {fullname} LIKE :query)"
        engine = current_app.extensions.get("rh_engine")
        if engine is None:
            engine = create_engine(cfg["RH_DATABASE_URL"], pool_pre_ping=True,
                                   pool_size=2, max_overflow=0, connect_args={"connect_timeout": 5})
            current_app.extensions["rh_engine"] = engine
        with engine.connect() as conn:
            suffix = "" if limit is None else " LIMIT :row_limit"
            params = {"active": 1, "query": search if exact else f"%{search}%"}
            if limit is not None:
                params["row_limit"] = limit
            rows = conn.execute(text(f"SELECT CAST({key} AS CHAR) AS employee_no, {fullname} AS name, {dept} AS department FROM {table} WHERE `Active` = :active AND {predicate} ORDER BY {key}{suffix}"), params).mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        current_app.logger.warning("Directorio RH no disponible (%s)", type(exc).__name__)
        raise DirectoryUnavailable("No fue posible consultar RH. Revisa la configuración y la conexión.") from None


def employee_options():
    """All active employees for selectors; the directory page keeps its limit."""
    try:
        rows = lookup(limit=None)
        return sorted(rows, key=lambda row: ((row["name"] or "").casefold(), row["employee_no"])), None
    except DirectoryUnavailable as exc:
        return [], str(exc)
