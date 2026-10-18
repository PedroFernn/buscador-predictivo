"""Normalización de texto: única copia para el motor, las señales y los scripts.

Minúsculas y sin diacríticos, salvo la ñ: es otra letra, no una n acentuada
(así "año" y "ano" no colisionan).
"""
import re
import unicodedata

LETRA_ENE = "\u00f1"  # ñ
TOPE_PREFIJO = "\U0010ffff"  # mayor code point: delimita el rango de un prefijo

_RE_TOKEN = re.compile(r"[a-z0-9\u00f1]+")
# Para claves de consulta los emojis también cuentan como token
_RE_TOKEN_CON_EMOJI = re.compile(r"[a-z0-9\u00f1]+|[\U0001F000-\U0001FAFF\u2600-\u27BF]")
_RE_TONOS_PIEL = re.compile("[\U0001F3FB-\U0001F3FF]")


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower()).replace("n\u0303", LETRA_ENE)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def tokenizar(texto):
    return _RE_TOKEN.findall(normalizar(texto))


def clave_consulta(texto, parcial=False):
    """Forma canónica de una consulta: tokens normalizados unidos por un espacio.

    Con parcial=True (un prefijo que se está escribiendo) conserva un espacio final,
    para que "pan " no se confunda con "pan".
    """
    bruto = texto or ""
    tokens = _RE_TOKEN_CON_EMOJI.findall(_RE_TONOS_PIEL.sub("", normalizar(bruto)))
    if not tokens:
        return ""
    clave = " ".join(tokens)
    if parcial and bruto[-1:].isspace():
        clave += " "
    return clave
