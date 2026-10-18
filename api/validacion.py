"""Validación de entradas JSON, en un solo lugar para todos los blueprints."""
from flask import request

MAX_POSICION = 50


def objeto_json():
    """El cuerpo como dict, o None si no es un objeto JSON."""
    datos = request.get_json(silent=True)
    return datos if isinstance(datos, dict) else None


def entero(valor):
    """int (no bool) o string de dígitos ASCII -> int; si no, None."""
    if isinstance(valor, str) and valor.isascii() and valor.isdigit():
        return int(valor)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    return None


def posicion(valor):
    """Posición de un resultado (1..MAX_POSICION), o None si falta o no es válida."""
    n = entero(valor)
    return n if n is not None and 1 <= n <= MAX_POSICION else None


def segundos(valor_ms):
    """Marca de tiempo en milisegundos (int/float, no bool) -> segundos; si no es válida, None."""
    if isinstance(valor_ms, bool) or not isinstance(valor_ms, (int, float)):
        return None
    return valor_ms / 1000 if 0 <= valor_ms < 1e14 else None
