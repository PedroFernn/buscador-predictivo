"""Evaluación del ranking contra un conjunto de oro, y búsqueda en rejilla de constantes.

El conjunto de oro es un CSV con una fila por (consulta, idioma, documento):

    consulta,idioma,doc_id,relevancia
    polvo,es,41,3
    polvo,pt,512,3

relevancia: 0 (nada) a 3 (exacto). Lo que no aparece cuenta como 0. Conviene incluir los
pares homógrafos en ambos idiomas, emojis, abreviaturas y typos.

Se mide la recuperación pura (un Buscador sin señales: reacciones y clics son señales de
uso, no de relevancia) con nDCG@k, MRR y Éxito@3. Las constantes se cambian en
`busqueda.parametros` durante la evaluación y se restauran al terminar. Los pesos por campo
(CAMPOS) no están en la rejilla porque obligan a reindexar en cada combinación.

Sin dependencias fuera del proyecto: lo usan scripts/calibrar.py y las pruebas de regresión.
"""
import csv
import itertools
import math
from contextlib import contextmanager

from busqueda import parametros

UMBRAL_RELEVANTE = 1  # relevancia mínima para contar un documento como acierto (MRR, Éxito@3)

# Constantes de consulta (no requieren reindexar). Edita los valores a probar.
REJILLA = {
    "BOOST_IDIOMA_DOMINANTE": (1.00, 1.10, 1.25),
    "FACTOR_IDIOMA_SECUNDARIO": (0.25, 0.35, 0.50),
    "FACTOR_IDIOMA_CON_EMOJI": (0.70, 0.85, 1.00),
    "PESO_EMOJI_CON_TEXTO": (0.30, 0.50, 0.70),
    "FACTOR_SINONIMO": (0.50, 0.70, 0.90),
}


# --- Métricas ------------------------------------------------------------------
def ndcg_en_k(relevancias_devueltas, relevancias_ideales, k=10):
    def dcg(rels):
        return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))

    ideal = dcg(sorted(relevancias_ideales, reverse=True))
    return dcg(relevancias_devueltas) / ideal if ideal else 0.0


def reciproco_primer_acierto(relevancias_devueltas):
    for posicion, r in enumerate(relevancias_devueltas, start=1):
        if r >= UMBRAL_RELEVANTE:
            return 1 / posicion
    return 0.0


def exito_en_k(relevancias_devueltas, k=3):
    return 1.0 if any(r >= UMBRAL_RELEVANTE for r in relevancias_devueltas[:k]) else 0.0


# --- Conjunto de oro -------------------------------------------------------------
def cargar_oro(ruta):
    """-> {(consulta, idioma): {doc_id: relevancia}}"""
    oro = {}
    with open(ruta, encoding="utf-8", newline="") as f:
        for n, fila in enumerate(csv.DictReader(f), start=2):
            try:
                clave = (fila["consulta"], fila["idioma"].strip() or parametros.IDIOMA_POR_DEFECTO)
                oro.setdefault(clave, {})[int(fila["doc_id"])] = int(fila["relevancia"])
            except (KeyError, ValueError, AttributeError) as error:
                raise ValueError(f"{ruta}, línea {n}: fila inválida ({error!r})") from error
    return oro


def evaluar(buscador, oro, k=10):
    """Promedios sobre todas las consultas: (nDCG@k, MRR, Éxito@3)."""
    if not oro:
        return 0.0, 0.0, 0.0
    ndcg = mrr = exito = 0.0
    for (consulta, idioma), juicios in oro.items():
        ids = [r["id"] for r in buscador.buscar(consulta, idioma)["resultados"][:k]]
        devueltas = [juicios.get(i, 0) for i in ids]
        ndcg += ndcg_en_k(devueltas, list(juicios.values()), k)
        mrr += reciproco_primer_acierto(devueltas)
        exito += exito_en_k(devueltas, 3)
    n = len(oro)
    return ndcg / n, mrr / n, exito / n


@contextmanager
def constantes(valores):
    """Cambia constantes de busqueda.parametros mientras dura el bloque y las restaura al salir."""
    previos = {nombre: getattr(parametros, nombre) for nombre in valores}
    try:
        for nombre, valor in valores.items():
            setattr(parametros, nombre, valor)
        yield
    finally:
        for nombre, valor in previos.items():
            setattr(parametros, nombre, valor)


def rejilla(buscador, oro, k=10, espacio=None):
    """Evalúa todas las combinaciones. -> lista de (valores, (ndcg, mrr, exito)), mejor primero."""
    espacio = espacio or REJILLA
    nombres = list(espacio)
    filas = []
    for combinacion in itertools.product(*(espacio[n] for n in nombres)):
        valores = dict(zip(nombres, combinacion))
        with constantes(valores):
            filas.append((valores, evaluar(buscador, oro, k)))
    filas.sort(key=lambda fila: (-fila[1][0], -fila[1][1]))
    return filas
