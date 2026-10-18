"""calibrar.py — búsqueda en rejilla de las constantes de ranking contra un conjunto de oro.

    python -m scripts.calibrar                         # evaluacion/oro.csv y el catálogo por defecto
    python -m scripts.calibrar --oro otro.csv --k 10 --mostrar 10
    python -m scripts.calibrar --url sqlite:///catalogo.db

El formato del CSV y las métricas están en busqueda/evaluacion.py. El archivo de constantes
no se edita: al final se imprime el bloque a copiar en busqueda/parametros.py.
"""
import argparse
import sys
from pathlib import Path

from busqueda import Buscador, parametros
from busqueda.evaluacion import REJILLA, cargar_oro, evaluar, rejilla
from datos.repositorio import RepositorioSQL, crear_engine, crear_repositorio

RUTA_ORO = Path(__file__).resolve().parent.parent / "evaluacion" / "oro.csv"


def _linea(valores, metricas, k):
    ndcg, mrr, exito = metricas
    texto = "  ".join(f"{v:g}" for v in valores.values())
    return f"nDCG@{k}={ndcg:.4f}  MRR={mrr:.4f}  Éxito@3={exito:.4f}  |  {texto}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--oro", default=str(RUTA_ORO), help="CSV del conjunto de oro")
    ap.add_argument("--url", default=None, help="DATABASE_URL (sin definir: catalogo.json)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--mostrar", type=int, default=5, help="cuántas combinaciones imprimir")
    args = ap.parse_args()

    if not Path(args.oro).exists():
        sys.exit(
            f"No existe {args.oro}. Crea el conjunto de oro (consulta,idioma,doc_id,relevancia)"
            " con consultas reales; ver el encabezado de busqueda/evaluacion.py."
        )
    oro = cargar_oro(args.oro)
    if not oro:
        sys.exit(f"{args.oro} no tiene filas.")

    repo = RepositorioSQL(crear_engine(args.url)) if args.url else crear_repositorio()
    buscador = Buscador(repo)  # sin señales: recuperación pura

    actuales = {n: getattr(parametros, n) for n in REJILLA}
    base = evaluar(buscador, oro, args.k)
    filas = rejilla(buscador, oro, args.k)

    print(f"{len(oro)} consultas de oro · {len(filas)} combinaciones\n")
    print("Orden de columnas de las constantes:", ", ".join(REJILLA))
    print("Actuales    ", _linea(actuales, base, args.k))
    for i, (valores, metricas) in enumerate(filas[: args.mostrar], start=1):
        print(f"Mejor #{i:<2}   ", _linea(valores, metricas, args.k))

    mejor, metricas = filas[0]
    if metricas[0] > base[0] + 1e-9:
        print(f"\nMejora nDCG@{args.k}: {base[0]:.4f} -> {metricas[0]:.4f}. Constantes a copiar en busqueda/parametros.py:\n")
        for nombre, valor in mejor.items():
            print(f"{nombre} = {valor}")
    else:
        print("\nLas constantes actuales ya son las mejores de la rejilla.")


if __name__ == "__main__":
    main()
