"""Fachada del motor: lo único que usa la capa web.

No sabe de Flask ni de dónde vienen los datos: recibe un `RepositorioCatalogo` (ver
datos/repositorio.py) y, opcionalmente, un objeto de señales con

    senales.pesos(consulta, ids) -> {id: (peso_reacciones, factor_aprendizaje)}
    senales.conteos(id)          -> {"me_gusta": n, "no_me_gusta": n, "me_encanta": n}

recomendar() no usa las señales globales: recibe el perfil de la persona ya ponderado.

Con una fuente SQL el catálogo puede cambiar mientras la app corre: `recargar()`
reconstruye el índice y lo intercambia de forma atómica (las consultas en curso siguen
con el anterior).

buscar() es una tubería de pasos pequeños:
    analizar -> puntuar -> aplicar señales -> ordenar -> serializar
"""
import logging
import threading
import time
from collections import Counter

from busqueda import parametros as P
from busqueda import ranking, recomendador
from busqueda.consulta import analizar
from busqueda.indice import construir_indice

log = logging.getLogger(__name__)

NEUTRO = (1.0, 1.0)


class Buscador:
    def __init__(self, repositorio, recarga_segundos=0, senales=None):
        """recarga_segundos > 0: relee la fuente (y reindexa) si el índice tiene más de esa
        antigüedad, al llegar la siguiente consulta."""
        self.repositorio = repositorio
        self.recarga_segundos = recarga_segundos
        self.senales = senales
        self._lock = threading.Lock()
        self._indice = None
        self._cargado_en = 0.0
        self.recargar()

    # --- índice ---------------------------------------------------------
    def recargar(self):
        indice = construir_indice(self.repositorio.listar())
        self._indice = indice  # asignación atómica
        self._cargado_en = time.monotonic()
        log.info("Índice listo: %d documentos", len(indice.catalogo))

    def _vencido(self):
        return self.recarga_segundos > 0 and time.monotonic() - self._cargado_en > self.recarga_segundos

    @property
    def indice(self):
        if self._vencido():
            with self._lock:
                if self._vencido():  # otro hilo pudo recargar mientras esperábamos
                    try:
                        self.recargar()
                    except Exception:
                        # Si la base falla seguimos sirviendo el índice anterior.
                        log.exception("No se pudo recargar el catálogo")
                        self._cargado_en = time.monotonic()
        return self._indice

    def existe(self, doc_id):
        """¿Hay un documento con ese id? (la API lo usa para no registrar señales de ids falsos)"""
        return doc_id in self.indice.ids

    def resumen(self):
        """Datos para la página principal: total de documentos y totales por idioma."""
        indice = self.indice
        por_idioma = Counter(doc["idioma"] for doc in indice.catalogo)
        idiomas = [
            {
                "codigo": i,
                "nombre": P.NOMBRE_IDIOMA[i],
                "bandera": P.BANDERA_IDIOMA[i],
                "total": por_idioma[i],
            }
            for i in P.IDIOMAS
        ]
        return len(indice.catalogo), idiomas

    # --- señales (solo sobre los documentos que hace falta) --------------
    def _pesos(self, consulta, docs):
        if self.senales is None:
            return {}
        return self.senales.pesos(consulta, [d["id"] for d in docs])

    def _conteos(self, doc_id):
        return self.senales.conteos(doc_id) if self.senales is not None else None

    # --- búsqueda -------------------------------------------------------
    def buscar(self, consulta, dominante):
        indice = self.indice
        if not consulta:
            return self._listado_completo(indice, dominante)

        analisis = analizar(consulta, indice)
        base = {
            "consulta": consulta,
            "consulta_simplificada": analisis.interpretacion.simplificada if analisis.interpretacion else "",
            "abreviaturas": analisis.interpretacion.abreviaturas if analisis.interpretacion else {},
            "emojis": analisis.emojis,
            "modo": analisis.modo,
            "idioma_dominante": dominante,
        }
        if analisis.vacio:
            return {**base, "terminos_expandidos": [], "total_coincidencias": 0, "resultados": []}

        puntajes = ranking.puntuar(indice, analisis, dominante)
        pesos = self._pesos(consulta, [p.doc for p in puntajes])
        ordenados = ranking.ordenar(puntajes, pesos)

        resultados = []
        for p in ordenados[: P.LIMITE_RESULTADOS]:
            reacciones, aprendizaje = pesos.get(p.doc["id"], NEUTRO)
            resultados.append(ranking.decorar(
                p.doc, p.score, p.coincide_emoji, reacciones * aprendizaje,
                self._conteos(p.doc["id"]), ranking.explicar(p, reacciones, aprendizaje),
            ))
        ranking.marcar_homografos(resultados)

        return {
            **base,
            "terminos_expandidos": analisis.vector.terminos,
            "total_coincidencias": len(puntajes),
            "resultados": resultados,
        }

    def recomendar(self, consultas, reacciones, dominante, limite=P.REC_LIMITE):
        """Sugerencias personales a partir de evidencia ya ponderada (ver recomendador.py).

        consultas: [(texto, peso)]   reacciones: [(doc_id, peso con signo)]
        Vacío mientras haya menos de REC_MIN_SENALES huellas. No guarda nada de lo recibido."""
        if len(consultas) + len(reacciones) < P.REC_MIN_SENALES:
            return {"elementos": []}
        return recomendador.recomendar(self.indice, consultas, reacciones, dominante, limite)

    def _listado_completo(self, indice, dominante):
        """Sin texto: el orden lo dan las reacciones (peso) y, a igualdad, el nombre."""
        catalogo = indice.catalogo
        pesos = self._pesos("", catalogo)

        def peso_de(doc):
            reacciones, aprendizaje = pesos.get(doc["id"], NEUTRO)
            return reacciones * aprendizaje

        ordenados = sorted(catalogo, key=lambda d: (d["idioma"] != dominante, -peso_de(d), d["nombre"]))
        return {
            "consulta": "",
            "consulta_simplificada": "",
            "abreviaturas": {},
            "emojis": [],
            "modo": "nombre",
            "idioma_dominante": dominante,
            "terminos_expandidos": [],
            "total_coincidencias": len(catalogo),
            "resultados": [
                ranking.decorar(
                    doc, None, peso=peso_de(doc), reacciones=self._conteos(doc["id"]),
                    explicacion=ranking.explicacion_sin_consulta(peso_de(doc)),
                )
                for doc in ordenados
            ],
        }


