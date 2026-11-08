"""Página /analitica y los datos de sus gráficas: el índice invertido, Zipf, Heaps y los árboles B.

  GET /analitica                  la página (gráficas dinámicas; static/js/analitica.js)
  GET /api/analitica/corpus       lo que depende del catálogo: índice invertido, Zipf, Heaps, árboles
  GET /api/analitica/uso          Zipf y Heaps del tráfico real de consultas (ventana deslizante)
  GET /api/analitica/sondeo?q=    qué toca una consulta: términos, postings y nodos del vocabulario

Son datos agregados y ya moderados (las consultas sueltas solo salen si alcanzaron el umbral público),
así que no piden ADMIN_TOKEN.
"""
from flask import Blueprint, jsonify, render_template, request

from api import servicio_buscador, servicio_senales

bp_analitica = Blueprint("analitica", __name__)

LARGO_MAX_SONDEO = 200


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
