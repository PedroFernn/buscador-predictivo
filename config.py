"""Configuración: el único módulo que lee variables de entorno (todas opcionales)."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

RAIZ = Path(__file__).resolve().parent


def _entero(nombre, defecto, minimo=1):
    try:
        return max(minimo, int(os.environ.get(nombre, defecto)))
    except ValueError:
        return defecto


@dataclass(frozen=True)
class Config:
    database_url: Optional[str] = None       # sin definir: catalogo.json
    recarga_segundos: int = 0                # >0: reindexa el catálogo cuando tiene esa antigüedad
    senales_db: str = str(RAIZ / "senales.db")  # SQLite con reacciones, clics y consultas
    ventana_dias: int = 7                    # ventana de las sugerencias por frecuencia
    min_frecuencia: int = 3                  # una consulta se sugiere si se repitió al menos así
    bloqueados: Tuple[str, ...] = ()         # términos que nunca se cuentan ni se sugieren
    retencion_dias: int = 90                 # cuánto se conservan clics e impresiones

    @classmethod
    def desde_entorno(cls):
        env = os.environ
        return cls(
            database_url=env.get("DATABASE_URL") or None,
            recarga_segundos=_entero("RECARGA_SEGUNDOS", 0, minimo=0),
            senales_db=env.get("SENALES_DB") or cls.senales_db,
            ventana_dias=_entero("HISTORIAL_VENTANA_DIAS", 7),
            min_frecuencia=_entero("HISTORIAL_MIN_FRECUENCIA", 3),
            bloqueados=tuple(t for t in env.get("HISTORIAL_BLOQUEADOS", "").split(",") if t.strip()),
            retencion_dias=_entero("SENALES_RETENCION_DIAS", 90),
        )
