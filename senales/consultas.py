"""Sugerencias por frecuencia real de las consultas (Zipf), sobre una tabla y una ventana.

Sustituye al antiguo registro en memoria (puerta de admisión LRU, cubos de tiempo, cabeza/cola
y desalojo por lotes) por una consulta SQL sobre la tabla de eventos:

  - Ventana deslizante exacta: solo cuentan las apariciones de los últimos `ventana_s`;
    lo anterior se purga (ver Senales), así la tabla no crece sin límite (Heaps).
  - Prefijo: rango sobre el índice (tipo, consulta, ts), sin recorrer todo.
  - Umbral público: una consulta solo se sugiere si alcanzó `min_frecuencia` en la ventana
    (se cuenta desde la primera vez; el umbral reemplaza a la puerta de admisión).
  - Moderación: no se cuentan datos personales ni términos bloqueados.
  - Cache de prefijos (LRU con TTL) para los prefijos populares, que se repiten mucho.

Orden: mayor frecuencia, luego la más reciente, luego alfabético.
"""
from collections import Counter, OrderedDict

from nucleo.estadistica import ajuste_potencia, ajuste_zipf, curva_heaps, rango_frecuencia
from nucleo.texto import clave_consulta

LARGO_MAX_CONSULTA = 64
USO_TTL_S = 2.0            # uso() se recalcula a lo más cada tanto (la página de analítica lo consulta seguido)
USO_MAX_EVENTOS = 200_000  # uso() mide sobre las últimas consultas de la ventana, no sobre todas
USO_TOP = 10


class HistorialConsultas:
    def __init__(self, almacen, reloj, moderador, ventana_s, min_frecuencia=1,
                 cache_ttl_s=30.0, max_cache=2_048, largo_max=LARGO_MAX_CONSULTA):
        self.almacen = almacen
        self._reloj = reloj
        self.moderador = moderador
        self.ventana_s = float(ventana_s)
        self.min_frecuencia = max(1, int(min_frecuencia))
        self.cache_ttl_s = float(cache_ttl_s)
        self.max_cache = max(1, int(max_cache))
        self.largo_max = largo_max
        self.moderadas = 0
        self._cache = OrderedDict()  # (prefijo, k) -> (hora, filas)
        self._uso = None             # (hora, resultado de uso())

    # --- escritura ------------------------------------------------------
    def registrar(self, texto):
        """Cuenta una consulta ya confirmada. True si se guardó, False si se descartó."""
        texto = (texto or "")[: self.largo_max * 4]
        clave = clave_consulta(texto)
        if not clave or len(clave) > self.largo_max:
            return False
        if self.moderador.sensible(texto, clave):
            self.moderadas += 1
            return False
        forma = " ".join(texto.split())[: self.largo_max * 2]
        self.almacen.agregar("consulta", self._reloj(), consulta=clave, texto=forma if forma != clave else None)
        self._cache.clear()
        self._uso = None
        return True

    def vaciar_cache(self):
        """Olvida los prefijos ya resueltos (tras borrar o cargar eventos sin pasar por registrar())."""
        self._cache.clear()
        self._uso = None

    def aplicar_bloqueo(self):
        """Quita lo ya guardado que la moderación actual rechazaría (la lista pudo cambiar)."""
        malas = [c for c in self.almacen.consultas_distintas() if self.moderador.sensible(c, c)]
        quitados = self.almacen.eliminar_consultas(malas)
        if quitados:
            self._cache.clear()
            self._uso = None
        return quitados

    # --- lectura --------------------------------------------------------
    def sugerir(self, prefijo, k=8):
        """Las k consultas más frecuentes (en la ventana) que empiezan con `prefijo`.

        origen = "cache": resuelto antes para ese prefijo. "tabla": consultado ahora."""
        k = max(1, min(int(k), 50))
        p = clave_consulta(prefijo, parcial=True)
        ahora = self._reloj()
        guardada = self._cache.get((p, k))
        if guardada is not None and ahora - guardada[0] < self.cache_ttl_s:
            self._cache.move_to_end((p, k))
            return self._respuesta(p, guardada[1], "cache")
        filas = self.almacen.consultas_frecuentes(ahora - self.ventana_s, p, self.min_frecuencia, k)
        self._cache[(p, k)] = (ahora, filas)
        if len(self._cache) > self.max_cache:
            self._cache.popitem(last=False)
        return self._respuesta(p, filas, "tabla")

    @staticmethod
    def _respuesta(prefijo, filas, origen):
        return {
            "prefijo": prefijo,
            "origen": origen,
            "sugerencias": [
                {"consulta": texto or consulta, "frecuencia": n} for consulta, n, _, texto in filas
            ],
        }

    def estadisticas(self):
        frecuencias = self.almacen.frecuencias_consultas(self._reloj() - self.ventana_s)
        return {
            "consultas_vivas": len(frecuencias),
            "ocurrencias_en_ventana": sum(frecuencias),
            "ventana_segundos": self.ventana_s,
            "min_frecuencia_publica": self.min_frecuencia,
            "prefijos_en_cache": len(self._cache),
            "descartadas_por_moderacion": self.moderadas,
            "zipf": ajuste_zipf(sorted(frecuencias, reverse=True)),
        }

    def uso(self):
        """Zipf y Heaps medidos sobre el tráfico real que hay hoy en la ventana (para graficar).

        Heaps solo ve lo que la ventana conserva: lo anterior se purgó, así que la curva es la del
        tramo vivo, no la de toda la historia."""
        ahora = self._reloj()
        if self._uso is not None and ahora - self._uso[0] < USO_TTL_S:
            return self._uso[1]
        consultas = self.almacen.consultas_en_orden(ahora - self.ventana_s, USO_MAX_EVENTOS)
        conteo = Counter(consultas)
        frecuencias = sorted(conteo.values(), reverse=True)
        m = min(len(frecuencias), 1000)
        zipf = ajuste_potencia(range(1, m + 1), frecuencias[:m]) if m >= 10 else None
        # Cuántas consultas distintas / términos distintos van apareciendo conforme llegan consultas
        curva = curva_heaps([[c] for c in consultas])
        curva_terminos = curva_heaps([c.split(" ") for c in consultas])
        resultado = {
            "eventos": len(consultas),
            "distintas": len(conteo),
            "ventana_segundos": self.ventana_s,
            "min_frecuencia_publica": self.min_frecuencia,
            "zipf": {
                "puntos": rango_frecuencia(frecuencias),
                "ajuste": None if zipf is None else {
                    "exponente": round(-zipf["exponente"], 3), "constante": round(zipf["constante"], 3),
                    "r2": round(zipf["r2"], 3), "puntos": m,
                },
                # Solo lo que ya es público (alcanzó el umbral): no se exponen consultas sueltas
                "top": [{"consulta": c, "frecuencia": n} for c, n in conteo.most_common(USO_TOP)
                        if n >= self.min_frecuencia],
            },
            "heaps": {
                "consultas": _serie_heaps([(i, v) for i, _, v in curva]),
                "terminos": _serie_heaps([(i, v) for i, _, v in curva_terminos]),
            },
        }
        self._uso = (ahora, resultado)
        return resultado


def _serie_heaps(curva):
    """{puntos, ajuste} de una curva [(x, V)]; el ajuste ignora el arranque (x < 10) si hay de sobra."""
    ajustables = [(x, v) for x, v in curva if x >= 10]
    ajuste = ajuste_potencia(*zip(*(ajustables if len(ajustables) >= 3 else curva))) if len(curva) >= 3 else None
    return {
        "puntos": [list(par) for par in curva],
        "ajuste": None if ajuste is None else {
            "beta": round(ajuste["exponente"], 3), "k": round(ajuste["constante"], 3),
            "r2": round(ajuste["r2"], 3), "puntos": ajuste["puntos"],
        },
    }

