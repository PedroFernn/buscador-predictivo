"""Senales: la fachada única de todo lo que aprende el sistema del uso.

Reúne en un solo objeto, respaldado por un solo almacén de eventos persistente:
  - reacciones   (me gusta / me encanta / no me gusta)      -> factor por documento
  - clics        (qué eligió la gente, y en qué posición)    -> factor por (consulta, documento)
  - impresiones  (qué se mostró y en qué posición)           -> denominador del CTR
  - consultas    (frecuencia real)                           -> sugerencias

Una sola función de puntuación: `pesos(consulta, ids)` devuelve, por documento, el par
(peso_reacciones, factor_aprendizaje); su producto es el `peso` que multiplica al score.

Persistencia y varios procesos: los eventos viven en SQLite (con archivo y WAL los comparten
todos los workers). Los agregados se mantienen en memoria y se reconstruyen desde el log al
arrancar y cada vez que otro proceso escribe (se detecta con PRAGMA data_version, a lo más
cada `sync_s` segundos), así que los demás workers ven una escritura con un retraso de unos
segundos, no al reiniciar.
"""
import threading
import time

from nucleo.texto import clave_consulta
from senales.almacen import AlmacenEventos
from senales.clics import MAX_CLAVES, Clics
from senales.consultas import LARGO_MAX_CONSULTA, HistorialConsultas
from senales import perfil
from senales.moderacion import Moderador
from senales.reacciones import TIPOS, VIDA_MEDIA_S, Reacciones

DIA_S = 86_400
MAX_IMPRESIONES = 50   # ids por lote de impresiones
PURGA_CADA = 500       # escrituras entre purgas


class Senales:
    def __init__(self, ruta=":memory:", *, reloj=time.time, vida_media_s=VIDA_MEDIA_S,
                 retencion_s=90 * DIA_S, ventana_s=7 * DIA_S, min_frecuencia=1,
                 bloqueados=(), moderar=True, max_claves=MAX_CLAVES, sync_s=5.0):
        self._reloj = reloj
        self._vida_media_s = vida_media_s
        self._retencion_s = float(retencion_s)
        self._max_claves = max_claves
        self._sync_s = sync_s
        self._lock = threading.RLock()
        self._escrituras = 0
        self._ultima_sync = time.monotonic()

        self.almacen = AlmacenEventos(ruta)
        self.historial = HistorialConsultas(
            self.almacen, reloj, Moderador(bloqueados, moderar), ventana_s, min_frecuencia,
        )
        self.reacciones = Reacciones(vida_media_s)
        self.clics = Clics(max_claves)
        self.historial.aplicar_bloqueo()
        self._purgar()
        self._recargar()

    @classmethod
    def desde_config(cls, config):
        return cls(
            config.senales_db,
            ventana_s=config.ventana_dias * DIA_S,
            retencion_s=config.retencion_dias * DIA_S,
            min_frecuencia=config.min_frecuencia,
            bloqueados=config.bloqueados,
        )

    # --- puntuación (lo que usa el motor) ---------------------------------
    def pesos(self, consulta, ids):
        """{doc_id: (peso_reacciones, factor_aprendizaje)}; (1.0, 1.0) sin señales."""
        ids = list(ids)
        clave = clave_consulta(consulta) if consulta else ""
        with self._lock:
            self._sincronizar()
            ahora = self._reloj()
            aprendizaje = self.clics.factores(clave, ids)
            return {i: (self.reacciones.peso(i, ahora), aprendizaje.get(i, 1.0)) for i in ids}

    def conteos(self, doc_id):
        with self._lock:
            self._sincronizar()
            return self.reacciones.conteos(doc_id)

    def puntos(self, doc_id):
        with self._lock:
            self._sincronizar()
            return self.reacciones.puntos(doc_id)

    # --- escritura --------------------------------------------------------
    def reaccionar(self, doc_id, tipo):
        """Registra una reacción. Devuelve los conteos actualizados del documento."""
        if tipo not in TIPOS:
            raise ValueError(f"reacción desconocida: {tipo}")
        ahora = self._reloj()
        with self._lock:
            self.almacen.agregar(tipo, ahora, doc_id=doc_id)
            conteo = self.reacciones.registrar(doc_id, tipo, ahora)
            self._escrito()
            return conteo

    def registrar_clic(self, consulta, doc_id, posicion=None):
        """Registra que, para `consulta`, la persona eligió `doc_id` (en el lugar `posicion`)."""
        clave = self._clave_registrable(consulta)
        if not clave:
            return False
        ahora = self._reloj()
        with self._lock:
            self.almacen.agregar("clic", ahora, doc_id=doc_id, consulta=clave, posicion=posicion)
            self.clics.clic(clave, doc_id, posicion)
            self._escrito()
        return True

    def registrar_impresiones(self, consulta, ids):
        """Registra los documentos mostrados para `consulta`, en orden (posición = índice + 1)."""
        clave = self._clave_registrable(consulta)
        ids = list(ids)[:MAX_IMPRESIONES]
        if not clave or not ids:
            return False
        ahora = self._reloj()
        filas = [("impresion", i, clave, pos, None, ahora) for pos, i in enumerate(ids, start=1)]
        with self._lock:
            self.almacen.agregar_muchos(filas)
            for i in ids:
                self.clics.impresion(clave, i)
            self._escrito(len(filas))
        return True

    def registrar_consulta(self, texto, mostrados=()):
        """Cuenta una consulta confirmada y, si se dan, los ids mostrados (sus impresiones)."""
        with self._lock:
            registrada = self.historial.registrar(texto)
            if registrada:
                self._escrito()
        if registrada and mostrados:
            self.registrar_impresiones(texto, mostrados)
        return registrada

    def _clave_registrable(self, consulta):
        """Clave canónica, o None si no debe guardarse (vacía, larga o con datos personales)."""
        consulta = (consulta or "")[: LARGO_MAX_CONSULTA * 4]
        clave = clave_consulta(consulta)
        if not clave or len(clave) > LARGO_MAX_CONSULTA:
            return None
        return None if self.historial.moderador.sensible(consulta, clave) else clave

    # --- perfil personal (sin estado: no se guarda nada) ------------------
    def ponderar_perfil(self, consultas, reacciones):
        """Evidencia personal con peso, lista para el recomendador.

        consultas:  [(texto, veces, hora_s)]     reacciones: [(doc_id, tipo, hora_s)]
        `hora_s` (segundos desde la época) puede ser None: cuenta como reciente.
        Devuelve ([(texto, peso)], [(doc_id, peso)]); el peso de una reacción lleva signo."""
        ahora = self._reloj()

        def edad(hora):
            return 0.0 if hora is None else ahora - hora

        vida = self._vida_media_s
        return (
            [(t, perfil.peso_consulta(n, edad(h), vida)) for t, n, h in consultas],
            [(i, perfil.peso_reaccion(tipo, edad(h), vida)) for i, tipo, h in reacciones],
        )

    # --- sugerencias y estadísticas ---------------------------------------
    def sugerir(self, prefijo, k=8):
        with self._lock:
            return self.historial.sugerir(prefijo, k)

    def estadisticas(self):
        with self._lock:
            return {
                **self.historial.estadisticas(),
                "eventos": self.almacen.conteo_por_tipo(),
                "aprendizaje": self.clics.estadisticas(),
                "max_claves": self._max_claves,
            }

    # --- mantenimiento ----------------------------------------------------
    def _escrito(self, n=1):
        self._escrituras += n
        if self._escrituras >= PURGA_CADA:
            self._escrituras = 0
            self._purgar()

    def _purgar(self):
        """Fuera lo que salió de su ventana (consultas) o de su retención (clics e impresiones)."""
        ahora = self._reloj()
        self.almacen.purgar(("consulta",), ahora - self.historial.ventana_s)
        self.almacen.purgar(("clic", "impresion"), ahora - self._retencion_s)

    def _recargar(self):
        """Reconstruye los agregados en memoria desde el log de eventos."""
        ahora = self._reloj()
        reacciones = Reacciones(self._vida_media_s)
        for tipo, doc_id, _, _, ts in self.almacen.leer(TIPOS):
            reacciones.registrar(doc_id, tipo, ts)
        clics = Clics(self._max_claves)
        for tipo, doc_id, consulta, posicion, _ in self.almacen.leer(("clic", "impresion"), ahora - self._retencion_s):
            if tipo == "clic":
                clics.clic(consulta, doc_id, posicion)
            else:
                clics.impresion(consulta, doc_id)
        self.reacciones, self.clics = reacciones, clics
        self._version_datos = self.almacen.data_version()

    def _sincronizar(self):
        """Si OTRO proceso escribió desde la última lectura, reconstruye (a lo más cada sync_s)."""
        if not self._sync_s:
            return
        ahora = time.monotonic()
        if ahora - self._ultima_sync < self._sync_s:
            return
        self._ultima_sync = ahora
        if self.almacen.data_version() != self._version_datos:
            self._recargar()

    def cerrar(self):
        self.almacen.cerrar()


