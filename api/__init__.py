"""Capa web: blueprints delgados. Las dependencias llegan por `app.extensions` (ver app.py)."""
from flask import current_app


def servicio_buscador():
    return current_app.extensions["buscador"]


def servicio_senales():
    return current_app.extensions["senales"]


def registrar_blueprints(app):
    from api.buscar import bp_buscar
    from api.recomendaciones import bp_recomendaciones
    from api.senales import bp_senales
    from api.sugerencias import bp_sugerencias

    for bp in (bp_buscar, bp_senales, bp_sugerencias, bp_recomendaciones):
        app.register_blueprint(bp)


