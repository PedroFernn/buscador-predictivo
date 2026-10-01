"""Emojis: detectarlos en la consulta, normalizarlos y entender qué significan.

Sin dependencias externas (solo `unicodedata`). No usar el nombre `emoji.py`:
chocaría con el paquete de PyPI del mismo nombre.

Tres formas de "entender" un emoji (las combina sri.py):
  1. Coincidencia directa con el campo `emoji` de los documentos del catálogo.
  2. Significado curado: EMOJI_CONCEPTOS (abajo; extiéndelo a gusto).
  3. Respaldo: palabras del nombre Unicode del emoji (🦄 -> "unicorn").
"""
import re
import unicodedata

ZWJ = "\u200d"
VS15, VS16 = "\ufe0e", "\ufe0f"
KEYCAP = "\u20e3"


# =============================================================================
# DETECCIÓN
# =============================================================================
def _es_tono(c):
    return 0x1F3FB <= ord(c) <= 0x1F3FF


def _es_regional(c):
    return 0x1F1E6 <= ord(c) <= 0x1F1FF


def _es_etiqueta(c):
    return 0xE0020 <= ord(c) <= 0xE007F  # banderas de subdivisión (🏴󠁧󠁢󠁥󠁮󠁧󠁿)


def _es_base(t, i):
    """¿El carácter t[i] puede iniciar un emoji?"""
    c = t[i]
    cp = ord(c)
    if _es_regional(c) or _es_tono(c):
        return True
    if cp >= 0x2190 and unicodedata.category(c) == "So":
        return True  # pictogramas y símbolos: 🐙 ☕ ⚡ ✈ ...
    sig = t[i + 1] if i + 1 < len(t) else ""
    if c in "0123456789#*":  # keycaps: 1️⃣ #️⃣
        return t[i + 1:i + 3] in (KEYCAP, VS16 + KEYCAP)
    # Símbolos que solo son emoji con selector de variación: ↔️ ❤️ ©️
    return sig == VS16 and cp >= 0xA9 and not c.isalnum()


def _fin_cluster(t, i):
    """Índice donde termina el emoji que empieza en t[i] (maneja ZWJ,
    tonos de piel, selectores, banderas y keycaps)."""
    n, j = len(t), i + 1
    if _es_regional(t[i]) and j < n and _es_regional(t[j]):
        j += 1  # bandera = dos indicadores regionales
    while True:
        while j < n and (
            t[j] in (VS15, VS16, KEYCAP) or _es_tono(t[j]) or _es_etiqueta(t[j])
        ):
            j += 1
        if j + 1 < n and t[j] == ZWJ and _es_base(t, j + 1):
            j += 2  # 👨‍🏫 = 👨 + ZWJ + 🏫
            continue
        return j


def extraer_emojis(texto):
    """-> (lista de emojis tal como se escribieron, texto sin emojis)."""
    emojis, resto, i = [], [], 0
    while i < len(texto):
        if _es_base(texto, i):
            j = _fin_cluster(texto, i)
            emojis.append(texto[i:j])
            resto.append(" ")
            i = j
        else:
            resto.append(texto[i])
            i += 1
    return emojis, "".join(resto)


def normalizar_emoji(emoji):
    """Clave de comparación: ignora selectores de variación y tonos de piel,
    así ⚖ == ⚖️ y 👍🏽 == 👍."""
    return "".join(
        c for c in emoji if c not in (VS15, VS16) and not _es_tono(c)
    )


# =============================================================================
# SIGNIFICADO
# =============================================================================
# Cada línea: "emojis separados por espacio" -> "palabras ancla".
# Las anclas deberían ser palabras de GRUPOS_SEMANTICOS (sri.py): así el emoji
# hereda también sus equivalentes en inglés y portugués ("😢" -> triste -> sad).
CONCEPTOS_EMOJI = [
    ("💰 💵 💸 💲 🤑 🪙 💳 🏦", "dinero"),
    ("💎 👑 💍", "caro"),
    ("😀 😃 😄 😁 😆 😊 🙂 😉 🥳 🤩 🥰 😂 🤣", "feliz"),
    ("😢 😭 😞 😔 ☹️ 🙁 🥺 😿", "triste"),
    ("😡 😠 🤬 👿 😤", "enojo"),
    ("😨 😱 😰 😧 😬", "miedo"),
    ("🤒 🤢 🤮 🤧 😷 🤕 🥴", "enfermo"),
    ("🩺 💊 💉 🏥 🚑", "medico"),
    ("🥶 🧊 ❄️ ☃️ ⛄", "frio"),
    ("🥵 🔥 ☀️ 🌡️", "calor"),
    ("🐌 🐢 🦥", "lento"),
    ("⚡ 🏎️ 💨 🚀 🏃", "rapido"),
    ("🍔 🍕 🌮 🍟 🍝 🍽️ 🥗 🍱", "comida"),
    ("🥤 🍺 🍷 🍹 🧃 🍸 🥂", "bebida"),
    ("🏠 🏡", "casa"),
    ("🚗 🚕 🚙 🚘", "coche"),
    ("🏫 🎓 🎒", "escuela"),
    ("👴 👵 🧓", "viejo"),
    ("💼 👷", "trabajo"),
]


def _construir_conceptos():
    mapa = {}
    for emojis, palabras in CONCEPTOS_EMOJI:
        for emoji in emojis.split():
            clave = normalizar_emoji(emoji)
            mapa.setdefault(clave, [])
            for p in palabras.split():
                if p not in mapa[clave]:
                    mapa[clave].append(p)
    return mapa


EMOJI_CONCEPTOS = _construir_conceptos()

# Palabras de nombres Unicode que no aportan significado.
_GENERICAS = frozenset("""
    face with and the for symbol sign button mark person people large small
    medium heavy light dark squared circled white black top left right up
    down arrow over under
""".split())


def conceptos_curados(clave):
    return EMOJI_CONCEPTOS.get(clave, [])


def palabras_nombre(emoji):
    """Palabras (en inglés) del nombre Unicode: 🦄 -> ["unicorn"]."""
    palabras = []
    for c in emoji:
        if c in (ZWJ, VS15, VS16, KEYCAP) or _es_tono(c) or _es_regional(c):
            continue
        if _es_etiqueta(c):
            continue
        nombre = unicodedata.name(c, "").lower()
        for p in re.findall(r"[a-z]+", nombre):
            if len(p) >= 3 and p not in _GENERICAS and p not in palabras:
                palabras.append(p)
    return palabras
