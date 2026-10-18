"""POST /api/reaccion y POST /api/seleccion: señales de uso de los resultados."""
from flask import Blueprint, jsonify

from api import servicio_buscador, servicio_senales
from api.validacion import entero, objeto_json, posicion
from senales.reacciones import TIPOS

bp_senales = Blueprint("senales", __name__)

_NO_EXISTE = ({"error": "documento inexistente"}, 404)


@bp_senales.post("/api/reaccion")
def reaccionar():
    """POST /api/reaccion {"id": <doc_id>, "tipo": "me_gusta"|"no_me_gusta"|"me_encanta"}"""
    datos = objeto_json()
    if datos is None:
        return jsonify({"error": "se esperaba un objeto JSON"}), 400
    doc_id, tipo = entero(datos.get("id")), datos.get("tipo")
    if doc_id is None:
        return jsonify({"error": "id inválido"}), 400
    if tipo not in TIPOS:
        return jsonify({"error": "tipo inválido", "tipos": list(TIPOS)}), 400
    if not servicio_buscador().existe(doc_id):
        return jsonify(_NO_EXISTE[0]), _NO_EXISTE[1]

    conteos = servicio_senales().reaccionar(doc_id, tipo)
    return jsonify({"id": doc_id, "conteos": conteos, "puntos": servicio_senales().puntos(doc_id)})


@bp_senales.post("/api/seleccion")
def seleccionar():
    """POST /api/seleccion {"q": "<consulta>", "id": <doc_id>, "pos": <lugar 1..50, opcional>}"""
    datos = objeto_json()
    if datos is None:
        return jsonify({"error": "se esperaba un objeto JSON"}), 400
    consulta = datos.get("q", "")
    if not isinstance(consulta, str) or not consulta.strip()[:200]:
        return jsonify({"registrada": False})
    doc_id = entero(datos.get("id"))
    if doc_id is None:
        return jsonify({"error": "id inválido"}), 400
    if not servicio_buscador().existe(doc_id):
        return jsonify(_NO_EXISTE[0]), _NO_EXISTE[1]

    return jsonify({"registrada": servicio_senales().registrar_clic(consulta[:200], doc_id, posicion(datos.get("pos")))})
