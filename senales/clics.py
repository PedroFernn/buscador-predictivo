"""Aprendizaje por clics: qué resultado elige la gente para cada consulta.

Dos mapas, ambos con el mismo contenido por documento [clics ponderados, impresiones]:
  - por consulta exacta: clave -> {doc_id: [c, i]}   (peso PESO_EXACTO)
  - por término:         término -> {doc_id: [c, i]}  (peso 1)
Así, elegir "pan dulce" también enseña algo a "pan" (comparten el término "pan").

CTR corregido por posición. Un resultado en el lugar k se clica menos por estar más abajo,
no por ser peor: cada clic se pondera por 1 / P(examinar k) ≈ 1 + log2(k) (con tope). Las
impresiones (qué se mostró y en qué lugar) permiten estimar un CTR suavizado:

    C = Σ peso·clics_ponderados,   I = Σ peso·impresiones
    ctr = (C + α) / (I + α + β)                      prior Beta(α, β): media p0 = α/(α+β)
    factor = 1 + A · tanh((ctr − p0) / ESCALA)

Sin datos de la consulta no hay factor (1.0). Con datos, un documento muy elegido sube y
uno mostrado una y otra vez sin que nadie lo elija baja un poco (señal negativa débil: el
factor queda en [1 − A·tanh(p0/ESCALA), 1 + A) ≈ [0.85, 1.4)). Se descartó el prior Zipf
sobre rangos: premiaba al que ya estaba arriba (círculo de popularidad).

Memoria acotada (Heaps: el vocabulario crece sin límite): al superar MAX_CLAVES por mapa se
desalojan las claves con menos interacciones. Sin Flask ni SQL; no es segura entre hilos
por sí sola (la protege Senales).
"""
import heapq
import math

from nucleo.lexico import STOPWORDS

PESO_EXACTO = 2.0
AMPLITUD_APRENDIZAJE = 0.4
ALFA_CTR = 1.0
BETA_CTR = 9.0                  # p0 = 0.1: un resultado "normal" se clica ~1 de cada 10 veces
ESCALA_CTR = 0.25
PESO_POSICION_MAX = 4.0
MAX_CLAVES = 5_000
FRACCION_DESALOJO = 0.10

_P0 = ALFA_CTR / (ALFA_CTR + BETA_CTR)


def terminos_de(clave):
    """Términos de una consulta, sin relleno (si solo hay relleno, todos)."""
    tokens = clave.split()
    return [t for t in tokens if t not in STOPWORDS] or tokens


def peso_posicion(posicion):
    """1 / P(examinar la posición k) ≈ 1 + log2(k), acotado. Sin posición: 1."""
    if not posicion or posicion < 1:
        return 1.0
    return min(1.0 + math.log2(posicion), PESO_POSICION_MAX)


class _Mapa:
    def __init__(self, tope):
        self.tope = max(1, int(tope))
        self.datos = {}      # clave -> {doc_id: [clics_ponderados, impresiones]}
        self._totales = {}   # clave -> interacciones totales (criterio de desalojo)

    def sumar(self, clave, doc_id, columna, valor):
        fila = self.datos.setdefault(clave, {}).setdefault(doc_id, [0.0, 0])
        fila[columna] += valor
        self._totales[clave] = self._totales.get(clave, 0) + 1

    def desalojar(self):
        if len(self.datos) <= self.tope:
            return
        cuantos = len(self.datos) - self.tope + max(1, int(self.tope * FRACCION_DESALOJO))
        for clave in heapq.nsmallest(cuantos, self._totales, key=self._totales.get):
            self.datos.pop(clave, None)
            self._totales.pop(clave, None)


class Clics:
    def __init__(self, max_claves=MAX_CLAVES):
        self._exactos = _Mapa(max_claves)
        self._terminos = _Mapa(max_claves)

    def _sumar(self, clave, doc_id, columna, valor):
        self._exactos.sumar(clave, doc_id, columna, valor)
        for termino in terminos_de(clave):
            self._terminos.sumar(termino, doc_id, columna, valor)
        self._exactos.desalojar()
        self._terminos.desalojar()

    def clic(self, clave, doc_id, posicion=None):
        self._sumar(clave, doc_id, 0, peso_posicion(posicion))

    def impresion(self, clave, doc_id):
        self._sumar(clave, doc_id, 1, 1)

    def factores(self, clave, ids):
        """doc_id -> factor de ranking. Vacío si no hay datos de esta consulta para esos ids."""
        if not clave:
            return {}
        exactos = self._exactos.datos.get(clave, {})
        por_termino = [self._terminos.datos.get(t, {}) for t in terminos_de(clave)]
        factores, hay_datos = {}, False
        for doc_id in ids:
            c = i = 0.0
            fila = exactos.get(doc_id)
            if fila:
                c += PESO_EXACTO * fila[0]
                i += PESO_EXACTO * fila[1]
            for mapa in por_termino:
                fila = mapa.get(doc_id)
                if fila:
                    c += fila[0]
                    i += fila[1]
            hay_datos = hay_datos or bool(c or i)
            ctr = min(1.0, (c + ALFA_CTR) / (i + ALFA_CTR + BETA_CTR))
            factores[doc_id] = 1 + AMPLITUD_APRENDIZAJE * math.tanh((ctr - _P0) / ESCALA_CTR)
        return factores if hay_datos else {}

    def estadisticas(self):
        return {
            "consultas_con_datos": len(self._exactos.datos),
            "terminos_con_datos": len(self._terminos.datos),
        }
