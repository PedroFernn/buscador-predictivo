"""Retención de consultas: sin política (Heaps) frente a la tabla con ventana deslizante.

Flujo sintético con ley Zipf sobre el vocabulario: cada consulta escoge sus palabras con una zeta
(sin tope). Se mide cuántas consultas y términos distintos acumularía una tabla sin política, y cuántas
filas tiene la tabla real (senales/almacen.py + purga) cuando se le aplica la ventana.

Lo usan scripts/simular.py (consola) y /api/analitica/retencion (la página). Es una simulación: el
tráfico real no tiene historia sin política que medir, por eso la comparación es con el flujo sintético.
"""
import random
import time
from collections import Counter

from nucleo.estadistica import ajuste_loglog
from senales.almacen import AlmacenEventos
from senales.consultas import HistorialConsultas
from senales.moderacion import Moderador

S_PALABRAS = 1.3          # exponente Zipf del vocabulario (soporte infinito: Heaps no satura)
PURGA_CADA = 10_000
VENTANA_DEFECTO_S = 8 * 3600


def zeta(s, rng):
    """Muestra de una distribución zeta (Zipf sin tope), algoritmo de Devroye."""
    b = 2 ** (s - 1)
    while True:
        u = 1.0 - rng.random()
        v = rng.random()
        x = min(int(u ** (-1.0 / (s - 1))), 10**9)
        t = (1.0 + 1.0 / x) ** (s - 1)
        if v * x * (t - 1.0) / (b - 1.0) <= t / b:
            return x


def consulta(rng):
    n = 1 if rng.random() < 0.55 else 2
    return " ".join(f"t{zeta(S_PALABRAS, rng)}" for _ in range(n))


def puntos_de_control(n):
    base = [1_000, 3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000]
    return [p for p in base if p <= n] + ([n] if n not in base else [])


def medir(eventos, semilla=1, ventana=VENTANA_DEFECTO_S):
    """Serie [{n, consultas, terminos, filas, vivas}] en los puntos de control, más el Zipf final."""
    rng = random.Random(semilla)
    reloj = [0.0]
    almacen = AlmacenEventos(":memory:")
    # moderar=False: los tokens sintéticos (t12345678) no son datos personales y alterarían la medición
    historial = HistorialConsultas(almacen, lambda: reloj[0], Moderador(activo=False), ventana)

    sin_politica_q, sin_politica_t = Counter(), set()
    puntos = set(puntos_de_control(eventos))
    serie, lote = [], []
    inicio = time.perf_counter()
    for i in range(1, eventos + 1):
        reloj[0] += 1.0
        q = consulta(rng)
        sin_politica_q[q] += 1
        sin_politica_t.update(q.split(" "))
        lote.append(("consulta", None, q, None, None, reloj[0]))
        if i % PURGA_CADA == 0 or i in puntos:
            almacen.agregar_muchos(lote)
            lote = []
            almacen.purgar(("consulta",), reloj[0] - ventana)
        if i in puntos:
            serie.append({
                "n": i,
                "consultas": len(sin_politica_q),
                "terminos": len(sin_politica_t),
                "filas": sum(almacen.conteo_por_tipo().values()),
                "vivas": len(almacen.frecuencias_consultas(reloj[0] - ventana)),
            })
    ns = [p["n"] for p in serie if p["n"] >= 1_000]
    ajuste = ajuste_loglog(ns, [p["consultas"] for p in serie if p["n"] >= 1_000]) if len(ns) >= 3 else None
    almacen.cerrar()
    return {
        "eventos": eventos,
        "ventana_segundos": ventana,
        "segundos": round(time.perf_counter() - inicio, 2),
        "puntos": serie,
        "heaps_consultas": None if ajuste is None else {"beta": round(ajuste[0], 3), "r2": round(ajuste[2], 4)},
    }
