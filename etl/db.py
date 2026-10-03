"""Accès PostgreSQL : connexion psycopg (COPY) et moteur SQLAlchemy (pandas)."""
from __future__ import annotations

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL

from .config import PG


def connexion() -> psycopg.Connection:
    return psycopg.connect(**PG)


def moteur() -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=PG["user"],
        password=PG["password"],
        host=PG["host"],
        port=PG["port"],
        database=PG["dbname"],
    )
    return create_engine(url)
