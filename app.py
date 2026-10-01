import os

from flask import Flask, jsonify, render_template, request

from repositorio import crear_repositorio
from sri import IDIOMA_POR_DEFECTO, IDIOMAS, Buscador

app = Flask(__name__)

# La fuente de datos se elige en repositorio.crear_repositorio() según
# DATABASE_URL (sin definir = catalogo.json). RECARGA_SEGUNDOS=300 hace que el
# índice se reconstruya solo cada 5 min para ver cambios hechos en la base.
buscador = Buscador(
    crear_repositorio(),
    recarga_segundos=int(os.environ.get("RECARGA_SEGUNDOS", "0")),
)


@app.route("/")
def index():
    total, idiomas = buscador.resumen()
    return render_template(
        "index.html",
        total=total,
        idiomas=idiomas,
        idioma_defecto=IDIOMA_POR_DEFECTO,
    )


@app.route("/api/buscar")
def buscar():
    consulta = request.args.get("q", "").strip()
    dominante = request.args.get("idioma", IDIOMA_POR_DEFECTO)
    if dominante not in IDIOMAS:
        dominante = IDIOMA_POR_DEFECTO
    return jsonify(buscador.buscar(consulta, dominante))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
