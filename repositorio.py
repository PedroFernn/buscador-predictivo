"""Capa de datos del catálogo.

El motor de búsqueda (sri.py) solo conoce `RepositorioCatalogo.listar()`:
una lista de dicts con las claves

    id, nombre, categoria, descripcion, emoji, idioma

No sabe de dónde vienen. Para cambiar de fuente basta con elegirla en
`crear_repositorio()` (variable de entorno DATABASE_URL); el resto no cambia.

    DATABASE_URL sin definir  -> catalogo.json   (comportamiento anterior)
    DATABASE_URL=sqlite:///catalogo.db
    DATABASE_URL=postgresql://usuario:clave@host/base
    DATABASE_URL=mysql+pymysql://usuario:clave@host/base?charset=utf8mb4
"""
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)

CATALOGO_JSON = Path(__file__).parent / "catalogo.json"


# =============================================================================
# ESQUEMA SQL
# =============================================================================
# `categoria` deja de ser texto repetido en cada fila y pasa a ser una tabla.
# Así se pueden renombrar, listar o filtrar categorías sin tocar documentos.
metadata = MetaData()

categorias = Table(
    "categorias",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre", String(80), nullable=False, unique=True),
)

documentos = Table(
    "documentos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre", String(120), nullable=False),
    Column("descripcion", Text, nullable=False, server_default=""),
    Column("emoji", String(16), nullable=False, server_default="📄"),
    Column("idioma", String(5), nullable=False, server_default="es"),
    Column("categoria_id", Integer, ForeignKey("categorias.id"), nullable=True),
    Index("ix_documentos_categoria", "categoria_id"),
    Index("ix_documentos_idioma", "idioma"),
)


# =============================================================================
# INTERFAZ
# =============================================================================
class RepositorioCatalogo(ABC):
    @abstractmethod
    def listar(self) -> list[dict]:
        """Todos los documentos, con `categoria` ya resuelta a su nombre."""


# =============================================================================
# FUENTE: JSON
# =============================================================================
class RepositorioJSON(RepositorioCatalogo):
    def __init__(self, ruta=CATALOGO_JSON):
        self.ruta = Path(ruta)

    def listar(self):
        with open(self.ruta, encoding="utf-8") as f:
            crudo = json.load(f)
        return [{"id": i, **doc} for i, doc in enumerate(crudo, start=1)]


# =============================================================================
# FUENTE: SQL (SQLAlchemy: SQLite, PostgreSQL, MySQL, ...)
# =============================================================================
class RepositorioSQL(RepositorioCatalogo):
    def __init__(self, engine):
        self.engine = engine

    def listar(self):
        consulta = (
            select(
                documentos.c.id,
                documentos.c.nombre,
                categorias.c.nombre.label("categoria"),
                documentos.c.descripcion,
                documentos.c.emoji,
                documentos.c.idioma,
            )
            .select_from(
                documentos.outerjoin(
                    categorias, documentos.c.categoria_id == categorias.c.id
                )
            )
            .order_by(documentos.c.id)
        )
        with self.engine.connect() as conexion:
            return [dict(fila._mapping) for fila in conexion.execute(consulta)]


def crear_engine(url):
    # Heroku/Render entregan "postgres://", que SQLAlchemy ya no acepta.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return create_engine(url, pool_pre_ping=True)


def crear_repositorio(url=None):
    url = url or os.environ.get("DATABASE_URL")
    if url:
        return RepositorioSQL(crear_engine(url))
    return RepositorioJSON()
