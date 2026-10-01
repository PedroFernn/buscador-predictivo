"""Crea las tablas e importa catalogo.json a la base de datos.

    python migrar.py                      # usa DATABASE_URL, o sqlite:///catalogo.db
    python migrar.py --url postgresql://usuario:clave@host/base
    python migrar.py --reemplazar         # vacía documentos y categorías antes
"""
import argparse
import json
import os
import sys

from sqlalchemy import delete, func, insert, select

from repositorio import CATALOGO_JSON, categorias, crear_engine, documentos, metadata

URL_POR_DEFECTO = "sqlite:///catalogo.db"


def importar(engine, ruta_json, reemplazar=False):
    metadata.create_all(engine)

    with open(ruta_json, encoding="utf-8") as f:
        crudo = json.load(f)

    with engine.begin() as conexion:  # una sola transacción: todo o nada
        existentes = conexion.scalar(select(func.count()).select_from(documentos))
        if existentes and not reemplazar:
            raise SystemExit(
                f"La tabla documentos ya tiene {existentes} filas. "
                "Usa --reemplazar para vaciarla e importar de nuevo."
            )
        if reemplazar:
            conexion.execute(delete(documentos))
            conexion.execute(delete(categorias))

        nombres = sorted({d.get("categoria", "").strip() for d in crudo} - {""})
        if nombres:
            conexion.execute(insert(categorias), [{"nombre": n} for n in nombres])
        ids = dict(conexion.execute(select(categorias.c.nombre, categorias.c.id)).all())

        filas = [
            {
                "nombre": d.get("nombre", ""),
                "descripcion": d.get("descripcion", ""),
                "emoji": d.get("emoji", "📄"),
                "idioma": d.get("idioma", "es"),
                "categoria_id": ids.get(d.get("categoria", "").strip()),
            }
            for d in crudo
        ]
        if filas:
            conexion.execute(insert(documentos), filas)

    return len(filas), len(nombres)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL", URL_POR_DEFECTO))
    parser.add_argument("--json", default=str(CATALOGO_JSON))
    parser.add_argument("--reemplazar", action="store_true")
    args = parser.parse_args()

    n_docs, n_cats = importar(crear_engine(args.url), args.json, args.reemplazar)
    print(f"Listo: {n_docs} documentos y {n_cats} categorías en {args.url}")
    print(f"Para usarla:  DATABASE_URL={args.url} python app.py", file=sys.stderr)


if __name__ == "__main__":
    main()
