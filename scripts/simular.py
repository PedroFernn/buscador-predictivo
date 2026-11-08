"""simular.py — Zipf + Heaps sobre un flujo sintético de consultas.

Muestra, con números medidos y no supuestos:
  1. Sin política de retención, consultas y términos distintos crecen como K·n^β (Heaps).
  2. Con la ventana de senales/consultas.py (y su purga) la tabla de eventos se aplana.
  3. Las sugerencias populares se repiten (Zipf): el cache de prefijos las resuelve sin consultar.

Uso:  python -m scripts.simular [--eventos 200000] [--semilla 1] [--ventana 28800]
"""
import argparse
import math
import random
import statistics
import time
from collections import Counter

from nucleo.estadistica import ajuste_loglog, ajuste_zipf
from senales.retencion import PURGA_CADA, consulta, puntos_de_control
from senales.almacen import AlmacenEventos
from senales.consultas import HistorialConsultas
from senales.moderacion import Moderador

# Flujo sintético y su generador: senales/retencion.py (compartido con la página /analitica)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--eventos", type=int, default=200_000)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--ventana", type=int, default=8 * 3600, help="ventana en segundos simulados (1 evento/s)")
    a = ap.parse_args()

    rng = random.Random(a.semilla)
    reloj = [0.0]
    almacen = AlmacenEventos(":memory:")
    # moderar=False: los tokens sintéticos (t12345678) no son datos personales y alterarían la medición
    historial = HistorialConsultas(almacen, lambda: reloj[0], Moderador(activo=False), a.ventana)

    sin_politica_q, sin_politica_t = Counter(), set()
    puntos = set(puntos_de_control(a.eventos))
    serie, lote = {}, []
    t0 = time.perf_counter()
    for i in range(1, a.eventos + 1):
        reloj[0] += 1.0
        q = consulta(rng)
        sin_politica_q[q] += 1
        sin_politica_t.update(q.split(" "))
        lote.append(("consulta", None, q, None, None, reloj[0]))
        if i % PURGA_CADA == 0 or i in puntos:
            almacen.agregar_muchos(lote)
            lote = []
            almacen.purgar(("consulta",), reloj[0] - a.ventana)
        if i in puntos:
            serie[i] = (len(sin_politica_q), len(sin_politica_t),
                        sum(almacen.conteo_por_tipo().values()), len(almacen.frecuencias_consultas(reloj[0] - a.ventana)))
    print(f"  {a.eventos:,} eventos en {time.perf_counter() - t0:.1f} s\n")

    print(f"Sin política (consultas / términos distintos)  vs  tabla con ventana de {a.ventana:,} s (filas / consultas vivas)\n")
    cab = f"{'n':>9} | {'consultas':>10} {'términos':>9} | {'filas':>8} {'vivas':>8}"
    print(cab)
    print("-" * len(cab))
    for n in sorted(serie):
        q, t, filas, vivas = serie[n]
        print(f"{n:>9,} | {q:>10,} {t:>9,} | {filas:>8,} {vivas:>8,}")

    # --- Heaps sobre la referencia sin política ---
    ns = [n for n in sorted(serie) if n >= 1_000]
    for etiqueta, idx in (("términos", 1), ("consultas", 0)):
        ajuste = ajuste_loglog(ns, [serie[n][idx] for n in ns])
        if ajuste:
            beta, lnK, r2 = ajuste
            print(f"\nHeaps ({etiqueta} distintos): V(n) ≈ {math.exp(lnK):.2f}·n^{beta:.3f}   (R²={r2:.4f})")
    ajuste = ajuste_loglog(ns, [serie[n][1] for n in ns])
    if ajuste:
        beta, lnK, _ = ajuste
        n_futuro = 10**9
        print(f"Extrapolación (no medida): con n = {n_futuro:,} eventos habría ≈ {math.exp(lnK) * n_futuro ** beta:,.0f} "
              "términos distintos sin política de retención.")

    # --- Zipf ---
    z = ajuste_zipf(sorted(sin_politica_q.values(), reverse=True), max_puntos=300)
    print(f"Zipf (frecuencia de consultas, 300 primeras posiciones): {z}")
    top = sum(c for _, c in sin_politica_q.most_common(500))
    print(f"Las 500 consultas más frecuentes cubren {100 * top / a.eventos:.1f}% del tráfico "
          f"(de {len(sin_politica_q):,} distintas).")

    # --- Latencia de sugerir(): tabla vs cache ---
    rng = random.Random(a.semilla + 99)
    pruebas = []
    for _ in range(2_000):
        q = consulta(rng)
        pruebas.append(q[: rng.randint(1, len(q))])
    historial._cache.clear()
    frio, tibio = [], []
    for p in pruebas:
        t0 = time.perf_counter_ns()
        origen = historial.sugerir(p, 8)["origen"]
        (frio if origen == "tabla" else tibio).append((time.perf_counter_ns() - t0) / 1000)
    for p in pruebas:  # segunda pasada: los prefijos repetidos salen del cache
        t0 = time.perf_counter_ns()
        origen = historial.sugerir(p, 8)["origen"]
        (frio if origen == "tabla" else tibio).append((time.perf_counter_ns() - t0) / 1000)
    print(f"\nLatencia de sugerir() sobre {2 * len(pruebas):,} peticiones (prefijos con el mismo tráfico Zipf):")
    for nombre, v in (("tabla", frio), ("cache", tibio)):
        if v:
            v.sort()
            print(f"  {nombre:<6} {len(v):>5,} peticiones | mediana {statistics.median(v):9.1f} µs | "
                  f"p99 {v[int(0.99 * (len(v) - 1))]:9.1f} µs")
    print("\nEstadísticas finales de la ventana:")
    for k, v in historial.estadisticas().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

