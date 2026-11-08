"""Herramientas de administración: reiniciar señales y generar datos de prueba.

Protegidas por ADMIN_TOKEN (cabecera X-Admin-Token). Sin ADMIN_TOKEN quedan apagadas (403) y la
página no muestra el panel. Usa un token largo y, fuera de tu máquina, HTTPS: viaja en una cabecera.

  GET  /api/admin/estado     eventos guardados por tipo
  POST /api/admin/reiniciar  {"alcance": "todo" | ["reacciones", "clics", "consultas"]}
  POST /api/admin/simular    {"consultas": 200, "reacciones": 300, "semilla": null,
                              "perfil_local": false, "reemplazar": false}
                             reemplazar=true borra todas las señales antes de generar.
"""
import hmac

from flask import Blueprint, current_app, jsonify, request

from api import servicio_buscador, servicio_senales
from api.validacion import entero, objeto_json
from senales import poblar
from senales.servicio import ALCANCES

bp_admin = Blueprint("admin", __name__)

MAX_CONSULTAS = 2_000
MAX_REACCIONES = 5_000
CONSULTAS_DEFECTO = 200
REACCIONES_DEFECTO = 300


def _token():
    return getattr(current_app.extensions.get("config"), "admin_token", None)


@bp_admin.app_context_processor
def _contexto():
    """La plantilla solo dibuja el panel si hay token configurado."""
    return {"admin_habilitado": bool(_token())}


@bp_admin.before_request
def _proteger():
    esperado = _token()
    if not esperado:
        return jsonify({"error": "administración apagada: define la variable ADMIN_TOKEN"}), 403
    enviado = request.headers.get("X-Admin-Token", "")
    if not hmac.compare_digest(enviado.encode(), esperado.encode()):
        return jsonify({"error": "token inválido"}), 401
    return None


def _limitado(valor, defecto, maximo):
    n = entero(valor)
    return defecto if n is None else max(0, min(n, maximo))


@bp_admin.get("/api/admin/estado")
def estado():
    return jsonify({"eventos": servicio_senales().estadisticas()["eventos"]})


@bp_admin.post("/api/admin/reiniciar")
def reiniciar():
    datos = objeto_json()
    if datos is None:
        return jsonify({"error": "se esperaba un objeto JSON"}), 400
    alcance = datos.get("alcance", "todo")
    if alcance == "todo":
        alcances = None
    elif isinstance(alcance, list) and alcance and all(isinstance(a, str) for a in alcance):
        alcances = alcance
    else:
        return jsonify({"error": "alcance inválido", "validos": ["todo", *ALCANCES]}), 400
    senales = servicio_senales()
    try:
        borrados = senales.reiniciar(alcances)
    except ValueError as error:
        return jsonify({"error": str(error), "validos": ["todo", *ALCANCES]}), 400
    return jsonify({"borrados": borrados, "eventos": senales.estadisticas()["eventos"]})


@bp_admin.post("/api/admin/simular")
def simular():
    datos = objeto_json()
    if datos is None:
        return jsonify({"error": "se esperaba un objeto JSON"}), 400
    senales = servicio_senales()
    borrados = senales.reiniciar() if datos.get("reemplazar") is True else None
    muestra = poblar.generar(
        servicio_buscador(), senales,
        consultas=_limitado(datos.get("consultas"), CONSULTAS_DEFECTO, MAX_CONSULTAS),
        reacciones=_limitado(datos.get("reacciones"), REACCIONES_DEFECTO, MAX_REACCIONES),
        semilla=entero(datos.get("semilla")),
    )
    senales.cargar_eventos(muestra.filas)
    respuesta = {
        "semilla": muestra.semilla,
        "insertados": muestra.resumen,
        "eventos": senales.estadisticas()["eventos"],
    }
    if borrados is not None:
        respuesta["borrados"] = borrados
    if datos.get("perfil_local") is True:
        respuesta["perfil_local"] = muestra.perfil_local
    return jsonify(respuesta)
