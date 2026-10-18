"""Sugerencias por frecuencia: GET /api/sugerencias, POST /api/consultas, GET /api/historial/estadisticas."""
from flask import Blueprint, jsonify, request

from api import servicio_buscador, servicio_senales
from api.validacion import entero, objeto_json

bp_sugerencias = Blueprint("sugerencias", __name__)


@bp_sugerencias.get("/api/sugerencias")
def sugerencias():
    """GET /api/sugerencias?q=<prefijo>&limite=8 -> las más frecuentes con ese prefijo."""
    try:
        limite = max(1, min(int(request.args.get("limite", 8)), 20))
    except ValueError:
        limite = 8
    respuesta = jsonify(servicio_senales().sugerir(request.args.get("q", "")[:200], limite))
    # Los prefijos populares se repiten mucho (Zipf): que el navegador los reutilice un rato.
    respuesta.headers["Cache-Control"] = "public, max-age=15"
    return respuesta


@bp_sugerencias.post("/api/consultas")
def registrar():
    """POST /api/consultas {"q": "...", "mostrados": [id, ...]}

    Cuenta una consulta ya confirmada por la persona. `mostrados` (opcional) son los ids de
    los resultados que se le mostraron, en orden: sus impresiones (posición = lugar en la lista).
    """
    datos = objeto_json() or {}
    texto = datos.get("q", "")
    if not isinstance(texto, str):
        texto = ""
    mostrados = datos.get("mostrados")
    ids = []
    if isinstance(mostrados, list):
        for valor in mostrados[:50]:
            doc_id = entero(valor)
            if doc_id is not None and doc_id not in ids and servicio_buscador().existe(doc_id):
                ids.append(doc_id)
    return jsonify({"registrada": servicio_senales().registrar_consulta(texto, ids)})


@bp_sugerencias.get("/api/historial/estadisticas")
def estadisticas():
    """Tamaño de la ventana, eventos por tipo, descartes por moderación y exponente de Zipf medido."""
    return jsonify(servicio_senales().estadisticas())
