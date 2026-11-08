"""Página /analitica y los datos de sus gráficas: el índice invertido, Zipf, Heaps y los árboles B.

  GET /analitica                  la página (gráficas dinámicas; static/js/analitica.js)
  GET /api/analitica/corpus       lo que depende del catálogo: índice invertido, Zipf, Heaps, árboles
  GET /api/analitica/uso          Zipf y Heaps del tráfico real de consultas (ventana deslizante)
  GET /api/analitica/sondeo?q=    qué toca una consulta: términos, postings y nodos del vocabulario
  GET /api/analitica/cache        tasa de aciertos del cache de prefijos por rango de prefijo
  GET /api/analitica/retencion    sin política frente a la ventana (simulación con la misma ley)
  GET /api/analitica/arbol-demo   árbol B pequeño con sus claves y el recorrido de la consulta

Son datos agregados y ya moderados (las consultas sueltas solo salen si alcanzaron el umbral público),
así que no piden ADMIN_TOKEN.
"""
from flask import Blueprint, jsonify, render_template, request

from api import servicio_buscador, servicio_senales
from senales.retencion import VENTANA_DEFECTO_S, medir

bp_analitica = Blueprint("analitica", __name__)

LARGO_MAX_SONDEO = 200
RETENCION_MIN, RETENCION_MAX, RETENCION_DEFECTO = 1_000, 200_000, 60_000
_retencion = {}  # eventos -> medición; la simulación es cara, se hace una vez por tamaño


@bp_analitica.get("/analitica")
def pagina():
    return render_template("analitica.html")


@bp_analitica.get("/api/analitica/corpus")
def corpus():
    return jsonify(servicio_buscador().analitica.corpus())


@bp_analitica.get("/api/analitica/uso")
def uso():
    respuesta = jsonify(servicio_senales().uso())
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@bp_analitica.get("/api/analitica/sondeo")
def sondeo():
    consulta = request.args.get("q", "").strip()[:LARGO_MAX_SONDEO]
    return jsonify(servicio_buscador().analitica.sondeo(consulta))



@bp_analitica.get("/api/analitica/cache")
def cache():
    respuesta = jsonify(servicio_senales().aciertos_cache())
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@bp_analitica.get("/api/analitica/retencion")
def retencion():
    try:
        eventos = int(request.args.get("eventos", RETENCION_DEFECTO))
    except ValueError:
        eventos = RETENCION_DEFECTO
    eventos = min(max(eventos, RETENCION_MIN), RETENCION_MAX)
    if eventos not in _retencion:
        if len(_retencion) >= 4:
            _retencion.pop(next(iter(_retencion)))
        _retencion[eventos] = medir(eventos, ventana=VENTANA_DEFECTO_S)
    return jsonify(_retencion[eventos])


@bp_analitica.get("/api/analitica/arbol-demo")
def arbol_demo():
    try:
        grado = min(max(int(request.args.get("grado", 2)), 2), 3)
        n = min(max(int(request.args.get("n", 22)), 6), 40)
    except ValueError:
        grado, n = 2, 22
    consulta = request.args.get("q", "").strip()[:LARGO_MAX_SONDEO]
    return jsonify(servicio_buscador().analitica.arbol_demo(grado, n, consulta))
