"""Almacén de eventos en SQLite: una sola tabla para todas las señales de uso.

    eventos(tipo, doc_id, consulta, posicion, texto, ts)

    tipo       doc_id  consulta  posicion  texto
    ---------  ------  --------  --------  -----------------------------------
    me_gusta     x
    me_encanta   x
    no_me_gusta  x
    clic         x       clave     x       (posición del resultado elegido)
    impresion    x       clave     x       (posición en que se mostró)
    consulta             clave             forma original, si difiere de la clave

`consulta` es siempre la clave canónica (nucleo.texto.clave_consulta). Es un registro de
solo-agregar: los conteos, pesos y sugerencias se derivan de él, y se purga lo que sale de
su ventana de retención. En archivo (WAL) lo comparten varios procesos.
"""
import sqlite3
import threading

from nucleo.texto import TOPE_PREFIJO

ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id       INTEGER PRIMARY KEY,
    tipo     TEXT NOT NULL,
    doc_id   INTEGER,
    consulta TEXT,
    posicion INTEGER,
    texto    TEXT,
    ts       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eventos_tipo_consulta_ts ON eventos (tipo, consulta, ts);
CREATE INDEX IF NOT EXISTS ix_eventos_tipo_ts ON eventos (tipo, ts);
"""

_INSERTAR = "INSERT INTO eventos (tipo, doc_id, consulta, posicion, texto, ts) VALUES (?, ?, ?, ?, ?, ?)"


def _marcas(n):
    return ",".join("?" * n)


class AlmacenEventos:
    def __init__(self, ruta=":memory:"):
        self.ruta = str(ruta)
        self._lock = threading.RLock()
        # Una conexión por proceso, protegida por un candado; autocommit (cada escritura es atómica)
        self._con = sqlite3.connect(self.ruta, check_same_thread=False, isolation_level=None, timeout=5.0)
        with self._lock:
            if self.ruta != ":memory:":
                self._con.execute("PRAGMA journal_mode=WAL")  # lectores y escritor no se bloquean
            self._con.execute("PRAGMA synchronous=NORMAL")
            self._con.executescript(ESQUEMA)

    # --- escritura ------------------------------------------------------
    def agregar(self, tipo, ts, doc_id=None, consulta=None, posicion=None, texto=None):
        with self._lock:
            self._con.execute(_INSERTAR, (tipo, doc_id, consulta, posicion, texto, ts))

    def agregar_muchos(self, filas):
        """filas: tuplas (tipo, doc_id, consulta, posicion, texto, ts), en una transacción."""
        with self._lock:
            self._con.execute("BEGIN")
            try:
                self._con.executemany(_INSERTAR, filas)
                self._con.execute("COMMIT")
            except BaseException:
                self._con.execute("ROLLBACK")
                raise

    def purgar(self, tipos, antes_de):
        """Borra los eventos de esos tipos anteriores a `antes_de`. Devuelve cuántos."""
        tipos = tuple(tipos)
        with self._lock:
            return self._con.execute(
                f"DELETE FROM eventos WHERE tipo IN ({_marcas(len(tipos))}) AND ts < ?",
                (*tipos, antes_de),
            ).rowcount

    def eliminar_consultas(self, claves):
        claves = list(claves)
        if not claves:
            return 0
        with self._lock:
            total = 0
            for i in range(0, len(claves), 500):
                lote = claves[i:i + 500]
                total += self._con.execute(
                    f"DELETE FROM eventos WHERE tipo = 'consulta' AND consulta IN ({_marcas(len(lote))})",
                    lote,
                ).rowcount
            return total

    # --- lectura --------------------------------------------------------
    def leer(self, tipos, desde=None):
        """[(tipo, doc_id, consulta, posicion, ts)] en orden cronológico."""
        tipos = tuple(tipos)
        sql = f"SELECT tipo, doc_id, consulta, posicion, ts FROM eventos WHERE tipo IN ({_marcas(len(tipos))})"
        params = list(tipos)
        if desde is not None:
            sql += " AND ts >= ?"
            params.append(desde)
        with self._lock:
            return self._con.execute(sql + " ORDER BY ts, id", params).fetchall()

    def consultas_distintas(self):
        with self._lock:
            return [f[0] for f in self._con.execute(
                "SELECT DISTINCT consulta FROM eventos WHERE tipo = 'consulta'")]

    def consultas_frecuentes(self, desde, prefijo, minimo, k):
        """Las k consultas con más apariciones desde `desde` cuya clave empieza con `prefijo`.

        Orden: mayor frecuencia, luego la más reciente, luego alfabético. La forma original
        sale de la fila más reciente por inserción (SQLite: columna desnuda junto a un único MAX)."""
        with self._lock:
            return self._con.execute(
                """
                SELECT consulta, COUNT(*) AS n, MAX(id) AS ultima, texto
                FROM eventos
                WHERE tipo = 'consulta' AND ts >= ? AND consulta >= ? AND consulta < ?
                GROUP BY consulta
                HAVING n >= ?
                ORDER BY n DESC, ultima DESC, consulta ASC
                LIMIT ?
                """,
                (desde, prefijo, prefijo + TOPE_PREFIJO, minimo, k),
            ).fetchall()

    def frecuencias_consultas(self, desde):
        """Lista con el número de apariciones de cada consulta distinta desde `desde`."""
        with self._lock:
            return [f[0] for f in self._con.execute(
                "SELECT COUNT(*) FROM eventos WHERE tipo = 'consulta' AND ts >= ? GROUP BY consulta",
                (desde,))]

    def conteo_por_tipo(self):
        with self._lock:
            return dict(self._con.execute("SELECT tipo, COUNT(*) FROM eventos GROUP BY tipo").fetchall())

    def data_version(self):
        """Cambia cuando OTRA conexión confirma escrituras (no con las propias)."""
        with self._lock:
            return self._con.execute("PRAGMA data_version").fetchone()[0]

    def cerrar(self):
        with self._lock:
            self._con.close()
