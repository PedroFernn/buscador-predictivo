"""Ajustes log-log: Zipf y Heaps son leyes potenciales (rectas en log-log)."""
import math


def ajuste_loglog(xs, ys):
    """Mínimos cuadrados de log(y) sobre log(x). Devuelve (pendiente, intercepto, r2) o None."""
    pares = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    n = len(pares)
    if n < 3:
        return None
    mx = sum(p[0] for p in pares) / n
    my = sum(p[1] for p in pares) / n
    sxx = sum((p[0] - mx) ** 2 for p in pares)
    if sxx == 0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pares)
    syy = sum((p[1] - my) ** 2 for p in pares)
    pendiente = sxy / sxx
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 1.0
    return pendiente, my - pendiente * mx, r2


def ajuste_zipf(frecuencias_desc, max_puntos=1000):
    """Exponente s de f(r) ~ C / r^s sobre las primeras `max_puntos` posiciones del ranking."""
    m = min(len(frecuencias_desc), max_puntos)
    if m < 10:
        return None
    ajuste = ajuste_loglog(range(1, m + 1), frecuencias_desc[:m])
    if ajuste is None:
        return None
    pendiente, _, r2 = ajuste
    return {"exponente": round(-pendiente, 3), "r2": round(r2, 3), "puntos": m}


def ajuste_potencia(xs, ys):
    """y ≈ constante · x^exponente (recta en log-log). Devuelve un dict o None.

    Es lo que se dibuja sobre Zipf (f ≈ C / r^s, exponente = -s) y Heaps (V ≈ K · n^β, exponente = β)."""
    xs, ys = list(xs), list(ys)
    ajuste = ajuste_loglog(xs, ys)
    if ajuste is None:
        return None
    pendiente, intercepto, r2 = ajuste
    return {
        "exponente": pendiente,
        "constante": math.exp(intercepto),
        "r2": r2,
        "puntos": sum(1 for x, y in zip(xs, ys) if x > 0 and y > 0),
    }


def puntos_log(n, max_puntos=120):
    """Posiciones enteras de 1 a n, espaciadas en escala log (incluye 1 y n, sin repetir).

    Sirve para graficar sin mandar millones de puntos: en log-log 120 bastan para ver la recta."""
    if n <= 0:
        return []
    if n <= max_puntos:
        return list(range(1, n + 1))
    paso = math.log(n) / (max_puntos - 1)
    return sorted({min(n, max(1, round(math.exp(paso * i)))) for i in range(max_puntos)} | {1, n})


def rango_frecuencia(frecuencias_desc, max_puntos=160):
    """[(rango, frecuencia)] de una lista ya ordenada de mayor a menor, submuestreada en log."""
    return [(r, frecuencias_desc[r - 1]) for r in puntos_log(len(frecuencias_desc), max_puntos)]


def curva_heaps(secuencias, max_puntos=120):
    """Crecimiento del vocabulario: [(secuencias leídas, elementos leídos, distintos vistos)].

    `secuencias` es una lista de listas (un documento = sus tokens; una consulta = sus términos).
    Se mide al terminar ~max_puntos de ellas, en escala log; los puntos sin elementos nuevos
    en x se omiten."""
    secuencias = list(secuencias)
    marcas = set(puntos_log(len(secuencias), max_puntos))
    vistos, leidos, curva = set(), 0, []
    for i, secuencia in enumerate(secuencias, 1):
        leidos += len(secuencia)
        vistos.update(secuencia)
        if i in marcas and leidos > 0 and (not curva or leidos > curva[-1][1]):
            curva.append((i, leidos, len(vistos)))
    return curva

