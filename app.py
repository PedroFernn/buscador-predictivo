"""Ensamblado de la aplicación. Toda la lógica vive en los paquetes; aquí solo se cablea.

    python app.py                       # desarrollo: http://localhost:5000
    gunicorn "app:create_app()"         # producción (SENALES_DB en archivo: varios workers comparten señales)
"""
from flask import Flask

from api import registrar_blueprints
from busqueda import Buscador
from config import Config
from datos.repositorio import crear_repositorio
from senales import Senales


def create_app(config=None, repositorio=None, senales=None):
    """Fábrica de la app. `repositorio` y `senales` se pueden inyectar (pruebas)."""
    config = config or Config.desde_entorno()
    senales = senales or Senales.desde_config(config)
    repositorio = repositorio or crear_repositorio(config.database_url)

    app = Flask(__name__)
    app.extensions["senales"] = senales
    app.extensions["buscador"] = Buscador(
        repositorio, recarga_segundos=config.recarga_segundos, senales=senales,
    )
    registrar_blueprints(app)
    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
