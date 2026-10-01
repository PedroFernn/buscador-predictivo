"""Motor SRI: D, Q, F, R(qk, dj). No sabe de Flask ni de dónde vienen los datos.

Recibe un `RepositorioCatalogo` (ver repositorio.py) y construye el índice a
partir de `repositorio.listar()`. Con una fuente SQL el catálogo puede cambiar
mientras la app corre: `Buscador.recargar()` reconstruye el índice y lo
intercambia de forma atómica (las consultas en curso siguen con el anterior).
"""
import bisect
import logging
import math
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

log = logging.getLogger(__name__)

# =============================================================================
# CONFIGURACIÓN Y CONSTANTES
# =============================================================================
IDIOMAS = ("es", "en", "pt")
NOMBRE_IDIOMA = {"es": "Español", "en": "Inglés", "pt": "Portugués"}
BANDERA_IDIOMA = {"es": "🇲🇽", "en": "🇬🇧", "pt": "🇧🇷"}
IDIOMA_POR_DEFECTO = "es"

CAMPOS = (
    ("nombre", 0.60),
    ("categoria", 0.15),
    ("descripcion", 0.25),
)

# Ajustes del prior de idioma:
# Documento del idioma seleccionado mantiene el 100% (o boost) de su score.
# Documentos de otros idiomas sufren una penalización sobre su score coseno.
BOOST_IDIOMA_DOMINANTE = 1.10
FACTOR_IDIOMA_SECUNDARIO = 0.35

LIMITE_SUGERENCIAS = 12

# Pesos de campo alternos: "modo sinopsis" prioriza la descripción para
# entender lo que el usuario describe (p. ej. "ct" -> caro -> "muy expensive").
CAMPOS_SINOPSIS = (
    ("nombre", 0.25),
    ("categoria", 0.10),
    ("descripcion", 0.65),
)
CAMPOS_POR_MODO = {"nombre": CAMPOS, "sinopsis": CAMPOS_SINOPSIS}

# Los sinónimos pesan menos que lo escrito literalmente por el usuario.
FACTOR_SINONIMO = 0.70
# Si el usuario escribió una palabra conocida completa ("caro"), sus
# prefijos solo cuentan si cubren al menos este % del término (evita "caroco").
COBERTURA_MIN_CONCEPTO = 0.70
# Consultas descriptivas largas también activan el modo sinopsis.
MIN_TERMINOS_SINOPSIS = 3


# =============================================================================
# DICCIONARIOS DE SIMPLIFICACIÓN (extiende aquí: sin acentos y en minúsculas)
# =============================================================================
# Abreviaturas / jerga de chat -> palabra completa
ABREVIATURAS = {
    "ct": "caro",
    "q": "que", "k": "que", "xq": "porque", "pq": "porque", "porq": "porque",
    "tb": "tambien", "tbn": "tambien", "tmb": "tambien", "tbm": "tambem",
    "x": "por", "xa": "para", "d": "de", "bn": "bien", "cmo": "como",
    "dnd": "donde", "qn": "quien", "xfa": "favor", "xfis": "favor",
    "msj": "mensaje", "grax": "gracias", "vc": "voce",
    "pls": "please", "plz": "please", "thx": "thanks",
}

# Palabras de relleno que se eliminan al simplificar la consulta
STOPWORDS = frozenset("""
    el la los las un una unos unas lo al del de en con sin por para y o u e
    que es son ser sea esta este esto esa eso ese hay muy mas menos como
    cual cuales donde cuando quien se su sus mi mis tu tus me te le les
    algo cosa cosas quiero quisiera busco buscar necesito dame dime favor
    the a an of in on at to for and or is are be it this that these those
    something thing things want need looking find show please with from
    um uma uns umas os as do da dos das no na nos nas em com sem pelo pela
    voce isso isto algum alguma quero preciso procuro
    porque tambien tambem gracias thanks because also why
""".split())

# Grupos de conceptos equivalentes (es / en / pt). Buscar uno activa los demás.
GRUPOS_SEMANTICOS = [
    "caro costoso costosa carisimo costly expensive pricey luxury lujo luxo "
    "custoso valioso valuable",
    "barato ganga cheap inexpensive affordable bargain oferta pechincha",
    "dinero plata money cash moneda finanzas dinheiro financiero financial",
    "grande enorme gigante big large huge giant",
    "pequeno chico diminuto small little tiny mini",
    "rapido veloz velocidad fast quick speed velocidade",
    "lento despacio slow devagar",
    "comida alimento food meal refeicao comer eat",
    "bebida beber drink liquido liquid",
    "miedo temor susto fear scared afraid medo",
    "feliz alegre contento happy glad alegria felicidad",
    "triste tristeza sad sorrow",
    "enojo enojado enfado ira anger angry raiva",
    "enfermo enfermedad sick ill disease doente",
    "medico doctor physician medicina medicine",
    "trabajo empleo job work profesion profession emprego trabalho",
    "casa hogar home house vivienda lar",
    "dificil complicado hard difficult tough",
    "facil sencillo simple easy",
    "viejo antiguo old ancient anciano velho",
    "bonito hermoso lindo bello beautiful pretty belo",
    "coche carro auto car automovil vehiculo vehicle",
    "escuela colegio school estudiar study educacion education escola",
    "frio cold helado gelado",
    "calor caliente hot heat quente",
]


# =============================================================================
# NORMALIZACIÓN Y TOKENIZACIÓN
# =============================================================================
def sanear(documento):
    idioma = documento.get("idioma") or IDIOMA_POR_DEFECTO
    if idioma not in IDIOMAS:
        idioma = IDIOMA_POR_DEFECTO
    # `or ""` cubre NULL de la base de datos (categoría sin asignar, etc.)
    return {
        **documento,
        "nombre": documento.get("nombre") or "",
        "categoria": documento.get("categoria") or "",
        "descripcion": documento.get("descripcion") or "",
        "emoji": documento.get("emoji") or "📄",
        "idioma": idioma,
    }


def normalizar(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def tokenizar(texto):
    return re.findall(r"[a-z0-9]+", normalizar(texto))


def normalizar_vector(vector):
    norma = math.sqrt(sum(peso * peso for peso in vector.values()))
    if norma == 0:
        return {}
    return {termino: peso / norma for termino, peso in vector.items()}


def construir_sinonimos():
    mapa = defaultdict(set)
    for grupo in GRUPOS_SEMANTICOS:
        terminos = set(tokenizar(grupo))
        for t in terminos:
            mapa[t] |= terminos
    return {t: grupo - {t} for t, grupo in mapa.items()}


SINONIMOS = construir_sinonimos()


# =============================================================================
# ÍNDICE INVERTIDO Y VECTORES
# =============================================================================
@dataclass(frozen=True)
class Indice:
    """Todo lo que se calcula una vez por carga del catálogo."""
    catalogo: list
    idf: dict
    vocabulario: list
    vectores_por_modo: dict
    indice_invertido: dict


def construir_indice(documentos):
    catalogo = [
        doc for doc in map(sanear, documentos)
        if doc["nombre"] or doc["descripcion"]
    ]
    n = len(catalogo)
    tokens_por_doc = [
        {campo: tokenizar(doc[campo]) for campo, _ in CAMPOS}
        for doc in catalogo
    ]

    df = defaultdict(int)
    for campos in tokens_por_doc:
        presentes = set()
        for tokens in campos.values():
            presentes.update(tokens)
        for termino in presentes:
            df[termino] += 1

    idf = {
        termino: math.log10(1 + n / frecuencia)
        for termino, frecuencia in df.items()
    }
    vocabulario = sorted(idf.keys())

    indice_invertido = defaultdict(list)
    vectores_por_modo = {modo: [] for modo in CAMPOS_POR_MODO}

    for doc_id, campos in enumerate(tokens_por_doc):
        # Vector tf-idf normalizado por campo (se reutiliza en cada modo)
        por_campo = {}
        for campo, _ in CAMPOS:
            tf = Counter(campos[campo])
            bruto = {t: freq * idf[t] for t, freq in tf.items()}
            por_campo[campo] = normalizar_vector(bruto)

        terminos_doc = set()
        for vector_campo in por_campo.values():
            terminos_doc.update(vector_campo.keys())
        for termino in terminos_doc:
            indice_invertido[termino].append(doc_id)

        for modo, pesos_campo in CAMPOS_POR_MODO.items():
            vector = defaultdict(float)
            for campo, peso_campo in pesos_campo:
                for termino, peso in por_campo[campo].items():
                    vector[termino] += peso_campo * peso
            norma_total = math.sqrt(sum(p * p for p in vector.values()))
            vectores_por_modo[modo].append((dict(vector), norma_total))

    return Indice(catalogo, idf, vocabulario, vectores_por_modo, dict(indice_invertido))


# =============================================================================
# CONSULTAS
# =============================================================================
def interpretar_consulta(consulta):
    """Simplifica la consulta: expande abreviaturas, quita relleno y decide
    si conviene buscar en la sinopsis (descripción) además del nombre."""
    crudos = tokenizar(consulta)
    if not crudos:
        return None

    abreviaturas = {}
    expandidos = []  # (termino, es_exacto)
    for token in crudos:
        if token in ABREVIATURAS:
            abreviaturas[token] = ABREVIATURAS[token]
            expandidos.extend((t, True) for t in tokenizar(ABREVIATURAS[token]))
        else:
            expandidos.append((token, False))

    contenido = [(t, e) for t, e in expandidos if t not in STOPWORDS]
    if not contenido:
        # Solo había relleno ("q", "es la"): búsqueda literal por prefijo.
        contenido = [(t, False) for t in crudos]
        abreviaturas = {}

    vistos, unicos = set(), []
    for par in contenido:
        if par not in vistos:
            vistos.add(par)
            unicos.append(par)

    sinonimos = {t for t, _ in unicos if t in SINONIMOS}
    usa_sinopsis = (
        bool(abreviaturas)
        or bool(sinonimos)
        or len(unicos) >= MIN_TERMINOS_SINOPSIS
    )
    return {
        "terminos": unicos,
        "simplificada": " ".join(t for t, _ in unicos),
        "abreviaturas": abreviaturas,
        "modo": "sinopsis" if usa_sinopsis else "nombre",
    }


def vector_consulta(terminos, idf, vocabulario):
    pesos = {}

    def aporte(termino, peso):
        if peso > pesos.get(termino, 0.0):
            pesos[termino] = peso

    for token, exacto in terminos:
        if exacto:
            if token in idf:
                aporte(token, idf[token])
        else:
            es_concepto = token in SINONIMOS
            inicio = bisect.bisect_left(vocabulario, token)
            for i in range(inicio, len(vocabulario)):
                termino = vocabulario[i]
                if not termino.startswith(token):
                    break
                cobertura = len(token) / len(termino)
                if es_concepto and cobertura < COBERTURA_MIN_CONCEPTO:
                    continue
                aporte(termino, idf[termino] * cobertura)

        # Entender lo que busca: términos equivalentes (es/en/pt)
        for sinonimo in SINONIMOS.get(token, ()):
            if sinonimo in idf:
                aporte(sinonimo, idf[sinonimo] * FACTOR_SINONIMO)

    vector = {t: p for t, p in pesos.items() if p > 0}
    if not vector:
        return {}, [], 0.0

    norma_q = math.sqrt(sum(p * p for p in vector.values()))
    return vector, sorted(vector.keys()), norma_q


def decorar(documento, score):
    idioma = documento["idioma"]
    return dict(
        documento,
        score=None if score is None else round(score, 4),
        idioma_nombre=NOMBRE_IDIOMA[idioma],
        bandera=BANDERA_IDIOMA[idioma],
        homografo=False,
    )


def marcar_homografos(resultados):
    conteo = Counter(r["nombre"].lower() for r in resultados)
    for resultado in resultados:
        if conteo[resultado["nombre"].lower()] > 1:
            resultado["homografo"] = True


# =============================================================================
# FACHADA: lo único que usa la capa web
# =============================================================================
class Buscador:
    def __init__(self, repositorio, recarga_segundos=0):
        """recarga_segundos > 0: relee la fuente (y reindexa) si el índice
        tiene más de esa antigüedad, al llegar la siguiente consulta."""
        self.repositorio = repositorio
        self.recarga_segundos = recarga_segundos
        self._lock = threading.Lock()
        self._indice = None
        self._cargado_en = 0.0
        self.recargar()

    def recargar(self):
        indice = construir_indice(self.repositorio.listar())
        self._indice = indice  # asignación atómica
        self._cargado_en = time.monotonic()
        log.info("Índice listo: %d documentos", len(indice.catalogo))

    def _vencido(self):
        return (
            self.recarga_segundos > 0
            and time.monotonic() - self._cargado_en > self.recarga_segundos
        )

    @property
    def indice(self):
        if self._vencido():
            with self._lock:
                if self._vencido():  # otro hilo pudo recargar mientras esperábamos
                    try:
                        self.recargar()
                    except Exception:
                        # Si la base falla seguimos sirviendo el índice anterior.
                        log.exception("No se pudo recargar el catálogo")
                        self._cargado_en = time.monotonic()
        return self._indice

    # --- datos para la página principal ---------------------------------
    def resumen(self):
        indice = self.indice
        por_idioma = Counter(doc["idioma"] for doc in indice.catalogo)
        idiomas = [
            {
                "codigo": i,
                "nombre": NOMBRE_IDIOMA[i],
                "bandera": BANDERA_IDIOMA[i],
                "total": por_idioma[i],
            }
            for i in IDIOMAS
        ]
        return len(indice.catalogo), idiomas

    # --- búsqueda -------------------------------------------------------
    def buscar(self, consulta, dominante):
        indice = self.indice
        total = len(indice.catalogo)

        if not consulta:
            resultados = sorted(
                indice.catalogo,
                key=lambda doc: (doc["idioma"] != dominante, doc["nombre"]),
            )
            return {
                "consulta": "",
                "consulta_simplificada": "",
                "abreviaturas": {},
                "modo": "nombre",
                "idioma_dominante": dominante,
                "terminos_expandidos": [],
                "total_coincidencias": total,
                "resultados": [decorar(doc, None) for doc in resultados],
            }

        interpretacion = interpretar_consulta(consulta)
        vector_q, terminos_expandidos, norma_q = vector_consulta(
            interpretacion["terminos"], indice.idf, indice.vocabulario
        )
        base = {
            "consulta": consulta,
            "consulta_simplificada": interpretacion["simplificada"],
            "abreviaturas": interpretacion["abreviaturas"],
            "modo": interpretacion["modo"],
            "idioma_dominante": dominante,
        }
        if not vector_q or norma_q == 0.0:
            return {
                **base,
                "terminos_expandidos": [],
                "total_coincidencias": 0,
                "resultados": [],
            }

        vectores = indice.vectores_por_modo[interpretacion["modo"]]

        candidatos_ids = set()
        for termino in terminos_expandidos:
            candidatos_ids.update(indice.indice_invertido.get(termino, []))

        puntuados = []
        for doc_id in candidatos_ids:
            doc = indice.catalogo[doc_id]
            vector_doc, norma_doc = vectores[doc_id]

            if norma_doc == 0:
                continue

            # Similitud coseno estrictamente de TÉRMINOS
            producto_punto = sum(
                peso_q * vector_doc.get(termino, 0.0)
                for termino, peso_q in vector_q.items()
            )
            coseno_texto = producto_punto / (norma_q * norma_doc)

            # Factor de ajuste según coincidencia de idioma
            if doc["idioma"] == dominante:
                factor_idioma = BOOST_IDIOMA_DOMINANTE
            else:
                factor_idioma = FACTOR_IDIOMA_SECUNDARIO

            score_final = coseno_texto * factor_idioma

            if score_final > 0:
                puntuados.append((score_final, doc))

        puntuados.sort(key=lambda x: x[0], reverse=True)

        resultados = [
            decorar(doc, score) for score, doc in puntuados[:LIMITE_SUGERENCIAS]
        ]
        marcar_homografos(resultados)

        return {
            **base,
            "terminos_expandidos": terminos_expandidos,
            "total_coincidencias": len(puntuados),
            "resultados": resultados,
        }
