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
from collections import OrderedDict

from nucleo.estadistica import ajuste_zipf
from nucleo.texto import clave_consulta

LARGO_MAX_CONSULTA = 64


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
        return True

    def aplicar_bloqueo(self):
        """Quita lo ya guardado que la moderación actual rechazaría (la lista pudo cambiar)."""
        malas = [c for c in self.almacen.consultas_distintas() if self.moderador.sensible(c, c)]
        quitados = self.almacen.eliminar_consultas(malas)
        if quitados:
            self._cache.clear()
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
