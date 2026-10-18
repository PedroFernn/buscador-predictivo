"""De texto crudo a vector de consulta: emojis, abreviaturas, relleno, sinónimos, prefijos.

Funciones puras (sin estado): reciben el índice y devuelven un `Analisis`.
"""
import bisect
import math
from dataclasses import dataclass, field
from typing import NamedTuple

from busqueda import parametros as P
from nucleo.emojis import conceptos_curados, extraer_emojis, normalizar_emoji, palabras_nombre
from nucleo.lexico import ABREVIATURAS, SINONIMOS, STOPWORDS
from nucleo.texto import tokenizar


@dataclass(frozen=True)
class Interpretacion:
    terminos: list          # [(término, es_exacto)]
    simplificada: str
    abreviaturas: dict
    modo: str               # "nombre" | "sinopsis"
    tiene_texto: bool


class VectorConsulta(NamedTuple):
    pesos: dict
    terminos: list          # términos expandidos, ordenados
    norma: float


VECTOR_VACIO = VectorConsulta({}, [], 0.0)


@dataclass(frozen=True)
class Analisis:
    """Todo lo que se entendió de la consulta, listo para puntuar."""
    consulta: str
    emojis: list                                  # [{"emoji", "coincidencias"}]
    coinciden: dict = field(default_factory=dict)  # posición -> m (coincidencia directa de emoji)
    interpretacion: Interpretacion = None
    vector: VectorConsulta = VECTOR_VACIO

    @property
    def modo(self):
        return self.interpretacion.modo if self.interpretacion else "nombre"

    @property
    def tiene_texto(self):
        return bool(self.interpretacion and self.interpretacion.tiene_texto)

    @property
    def vacio(self):
        """Sin vector de términos ni coincidencias de emoji: no hay nada que recuperar."""
        return not self.vector.pesos and not self.coinciden


def interpretar_consulta(texto, extra=()):
    """Simplifica la consulta: expande abreviaturas, quita relleno y decide si conviene
    buscar en la sinopsis (descripción) además del nombre.

    `texto` es la consulta sin emojis; `extra` son términos (término, exacto) que vienen
    del significado de los emojis."""
    crudos = tokenizar(texto)
    if not crudos and not extra:
        return None

    abreviaturas = {}
    expandidos = []  # (término, es_exacto)
    for token in crudos:
        if token in ABREVIATURAS:
            abreviaturas[token] = ABREVIATURAS[token]
            expandidos.extend((t, True) for t in tokenizar(ABREVIATURAS[token]))
        else:
            expandidos.append((token, False))

    contenido = [(t, e) for t, e in expandidos if t not in STOPWORDS]
    if not contenido and crudos:
        # Solo había relleno ("q", "es la"): búsqueda literal por prefijo.
        contenido = [(t, False) for t in crudos]
        abreviaturas = {}

    vistos, unicos = set(), []
    for par in [*contenido, *extra]:
        if par not in vistos:
            vistos.add(par)
            unicos.append(par)

    hay_sinonimos = any(t in SINONIMOS for t, _ in unicos)
    usa_sinopsis = bool(abreviaturas) or hay_sinonimos or len(unicos) >= P.MIN_TERMINOS_SINOPSIS
    return Interpretacion(
        terminos=unicos,
        simplificada=" ".join(t for t, _ in unicos),
        abreviaturas=abreviaturas,
        modo="sinopsis" if usa_sinopsis else "nombre",
        tiene_texto=bool(crudos),
    )


def vector_consulta(terminos, idf, vocabulario):
    """Cada prefijo escrito se expande a los términos del vocabulario que empiezan con él,
    ponderados por idf y por la fracción ya escrita (cobertura); los sinónimos pesan menos."""
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
                if es_concepto and cobertura < P.COBERTURA_MIN_CONCEPTO:
                    continue
                aporte(termino, idf[termino] * cobertura)

        # Entender lo que busca: términos equivalentes (es/en/pt)
        for sinonimo in SINONIMOS.get(token, ()):
            if sinonimo in idf:
                aporte(sinonimo, idf[sinonimo] * P.FACTOR_SINONIMO)

    vector = {t: p for t, p in pesos.items() if p > 0}
    if not vector:
        return VECTOR_VACIO
    norma = math.sqrt(sum(p * p for p in vector.values()))
    return VectorConsulta(vector, sorted(vector), norma)


def analizar(consulta, indice):
    """Paso 1 y 2 de la búsqueda: separar emojis del texto, entender cada uno y armar el vector."""
    emojis, texto = extraer_emojis(consulta)
    claves, vistas = [], set()
    for emoji in emojis:
        clave = normalizar_emoji(emoji)
        if clave not in vistas:
            vistas.add(clave)
            claves.append((emoji, clave))

    coinciden = {}   # posición -> m
    extra = []       # términos que aporta el significado del emoji
    resumen = []
    for emoji, clave in claves:
        directos = indice.emoji_a_docs.get(clave, [])
        resumen.append({"emoji": emoji, "coincidencias": len(directos)})
        for posicion in directos:
            coinciden[posicion] = 1.0
        extra.extend((p, False) for p in conceptos_curados(clave))
        if not directos:
            # Emoji que el catálogo no usa: se interpreta por su nombre.
            extra.extend((p, False) for p in palabras_nombre(emoji))

    interpretacion = interpretar_consulta(texto, extra)
    vector = (
        vector_consulta(interpretacion.terminos, indice.idf, indice.vocabulario)
        if interpretacion
        else VECTOR_VACIO
    )
    return Analisis(consulta, resumen, coinciden, interpretacion, vector)
