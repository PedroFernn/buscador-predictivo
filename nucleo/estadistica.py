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
