"""POST /api/recomendaciones: sugerencias personales a partir del perfil que envía el navegador."""
from flask import Blueprint, jsonify

from api import servicio_buscador, servicio_senales
from api.validacion import entero, objeto_json, segundos
from busqueda import parametros as P
from senales.reacciones import TIPOS

bp_recomendaciones = Blueprint("recomendaciones", __name__)

MAX_CONSULTAS = 20      # el historial del navegador guarda 10; se acepta algo de holgura
MAX_REACCIONES = 100
LARGO_MAX_TEXTO = 200


def _consultas(valor):
    """[{"q", "n", "ts"}] -> [(texto, veces, hora_s)]; lo inválido se ignora, sin error."""
    salida = []
    for item in valor[:MAX_CONSULTAS] if isinstance(valor, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("q"), str):
            continue
        texto = item["q"].strip()[:LARGO_MAX_TEXTO]
        if texto:
            salida.append((texto, entero(item.get("n")) or 1, segundos(item.get("ts"))))
    return salida


def _reacciones(valor):
    """[{"id", "tipo", "ts"}] -> [(doc_id, tipo, hora_s)], una por documento (la más reciente)."""
    por_documento = {}
    for item in valor[:MAX_REACCIONES] if isinstance(valor, list) else []:
        if not isinstance(item, dict) or item.get("tipo") not in TIPOS:
            continue
        doc_id = entero(item.get("id"))
        if doc_id is None:
            continue
        hora = segundos(item.get("ts"))
        previa = por_documento.get(doc_id)
        if previa is None or (hora or 0) >= (previa[2] or 0):
            por_documento[doc_id] = (doc_id, item["tipo"], hora)
    return list(por_documento.values())


@bp_recomendaciones.post("/api/recomendaciones")
def recomendaciones():
    """POST /api/recomendaciones

    {"consultas":  [{"q": "pan dulce", "n": 3, "ts": <ms>}, ...],     búsquedas (historial local)
     "reacciones": [{"id": 12, "tipo": "me_gusta", "ts": <ms>}, ...],  última reacción por documento
     "idioma": "es", "limite": 6}

    -> {"elementos": [{id, nombre, categoria, emoji, idioma, afinidad, motivos, ...}]}
    Vacío mientras no haya suficientes huellas. El perfil no se guarda en el servidor.
    """
    datos = objeto_json()
    if datos is None:
        return jsonify({"error": "se esperaba un objeto JSON"}), 400
    dominante = datos.get("idioma")
    if dominante not in P.IDIOMAS:
        dominante = P.IDIOMA_POR_DEFECTO
    limite = max(1, min(entero(datos.get("limite")) or P.REC_LIMITE, P.REC_LIMITE_MAX))

    consultas, reacciones = servicio_senales().ponderar_perfil(
        _consultas(datos.get("consultas")), _reacciones(datos.get("reacciones")),
    )
    respuesta = jsonify(servicio_buscador().recomendar(consultas, reacciones, dominante, limite))
    respuesta.headers["Cache-Control"] = "no-store"  # es personal: ningún cache debe reutilizarlo
    return respuesta
