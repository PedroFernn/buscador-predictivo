"""GET / (página) y GET /api/buscar."""
from flask import Blueprint, jsonify, render_template, request

from api import servicio_buscador
from busqueda.parametros import IDIOMA_POR_DEFECTO, IDIOMAS

bp_buscar = Blueprint("buscar", __name__)


@bp_buscar.get("/")
def index():
    total, idiomas = servicio_buscador().resumen()
    return render_template("index.html", total=total, idiomas=idiomas, idioma_defecto=IDIOMA_POR_DEFECTO)


@bp_buscar.get("/api/buscar")
def buscar():
    """GET /api/buscar?q=<texto>&idioma=es|en|pt (idioma inválido o ausente cae a es)."""
    consulta = request.args.get("q", "").strip()
    dominante = request.args.get("idioma", IDIOMA_POR_DEFECTO)
    if dominante not in IDIOMAS:
        dominante = IDIOMA_POR_DEFECTO
    return jsonify(servicio_buscador().buscar(consulta, dominante))
