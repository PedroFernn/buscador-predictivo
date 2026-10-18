"""Parámetros de recuperación y ranking: el único lugar con constantes ajustables.

El resto del paquete las lee como `parametros.NOMBRE` en el momento de usarlas, así que
scripts/calibrar.py puede cambiarlas temporalmente. Las que afectan al índice (CAMPOS,
CAMPOS_SINOPSIS) obligan a reindexar.
"""

# --- Idiomas -------------------------------------------------------------------
IDIOMAS = ("es", "en", "pt")
NOMBRE_IDIOMA = {"es": "Español", "en": "Inglés", "pt": "Portugués"}
BANDERA_IDIOMA = {"es": "🇲🇽", "en": "🇬🇧", "pt": "🇧🇷"}
IDIOMA_POR_DEFECTO = "es"

# --- Pesos por campo -----------------------------------------------------------
CAMPOS = (
    ("nombre", 0.60),
    ("categoria", 0.15),
    ("descripcion", 0.25),
)

# Pesos alternos: "modo sinopsis" prioriza la descripción para entender lo que el
# usuario describe (p. ej. "ct" -> caro -> "muy expensive").
CAMPOS_SINOPSIS = (
    ("nombre", 0.25),
    ("categoria", 0.10),
    ("descripcion", 0.65),
)
CAMPOS_POR_MODO = {"nombre": CAMPOS, "sinopsis": CAMPOS_SINOPSIS}

# --- Prior de idioma -----------------------------------------------------------
# Documento del idioma seleccionado mantiene el 100% (o boost) de su score.
# Documentos de otros idiomas sufren una penalización sobre su score coseno.
BOOST_IDIOMA_DOMINANTE = 1.10
FACTOR_IDIOMA_SECUNDARIO = 0.35
# El emoji es evidencia explícita: un documento que coincide con él no sufre la
# penalización completa de idioma (si no, "pie 🥧" daría Pie (es) antes que Pie (en)
# solo por el selector). Sigue por debajo del idioma dominante.
FACTOR_IDIOMA_CON_EMOJI = 0.85

# --- Interpretación de la consulta ---------------------------------------------
# Los sinónimos pesan menos que lo escrito literalmente por el usuario.
FACTOR_SINONIMO = 0.70
# Si el usuario escribió una palabra conocida completa ("caro"), sus prefijos solo
# cuentan si cubren al menos este % del término (evita "caroco").
COBERTURA_MIN_CONCEPTO = 0.70
# Consultas descriptivas largas también activan el modo sinopsis.
MIN_TERMINOS_SINOPSIS = 3

# --- Emojis en la consulta -----------------------------------------------------
# Un documento cuyo `emoji` coincide con el escrito recibe m = 1. Si hay coincidencia:
#     base = (1 - W) * coseno_texto + W * m
# W es mayor cuando el usuario solo escribió emojis (no hay texto que pesar).
PESO_EMOJI_SOLO = 0.85
PESO_EMOJI_CON_TEXTO = 0.50

# --- Salida --------------------------------------------------------------------
LIMITE_RESULTADOS = 12

# --- Sugerencias personales (ver recomendador.py) ------------------------------
REC_MIN_SENALES = 3         # búsquedas distintas + reacciones antes de sugerir nada
REC_LIMITE = 6              # elementos que se devuelven por defecto
REC_LIMITE_MAX = 12
REC_MAX_TERMINOS = 40       # el perfil se poda a sus términos más pesados
REC_PESO_NEGATIVO = 0.7     # cuánto resta parecerse a lo que no gustó
REC_AFINIDAD_MIN = 0.03     # por debajo no se sugiere (ruido de términos sueltos)
REC_MAX_MOTIVOS = 3         # términos del perfil que se muestran como "por qué"
