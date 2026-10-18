"""Reacciones (me gusta / me encanta / no me gusta) y su efecto en el ranking.

Cada documento acumula evidencia positiva y negativa. Con ella se calcula un factor
acotado y con confianza: valoración suavizada con un prior Beta(a, b),

    factor = 1 + A · (2v − 1),   v = (positivos + a) / (positivos + negativos + a + b)

que vale exactamente 1.0 sin reacciones, queda en (1 − A, 1 + A) y converge a la proporción
real con más evidencia (2 reacciones no igualan a 200). La evidencia decae de forma
exponencial (vida media de unas semanas): una reacción vieja pesa menos que una reciente.
Los conteos brutos (los que muestra la interfaz) no decaen.

Sin prior Zipf: el factor de un documento depende solo de su propia evidencia, así que se
calcula por documento y solo para los que hace falta. Sin Flask y sin SQL; el estado se
reconstruye desde el almacén de eventos (ver servicio.py).
"""

TIPOS = ("me_gusta", "no_me_gusta", "me_encanta")
# Cuánto aporta cada reacción (los negativos restan a la evidencia en contra)
PUNTOS = {"me_gusta": 1.0, "me_encanta": 2.0, "no_me_gusta": -1.5}

AMPLITUD_REACCION = 0.5        # el factor queda en (0.5, 1.5)
PRIOR_A = 2.0                  # Beta(a, b): pseudo-puntos a favor y en contra
PRIOR_B = 2.0                  #   (0.5 sin datos: factor exactamente 1.0)
VIDA_MEDIA_S = 21 * 86_400     # la evidencia pierde la mitad de su peso cada 3 semanas


def valoracion_suavizada(positivos, negativos, a=PRIOR_A, b=PRIOR_B):
    """Beta(a, b) como prior: a/(a+b) sin datos; converge a la proporción real con más reacciones."""
    return (positivos + a) / (positivos + negativos + a + b)


def factor_reaccion(positivos, negativos):
    """Factor multiplicativo en (1 - A, 1 + A); exactamente 1.0 sin evidencia (con a == b)."""
    return 1 + AMPLITUD_REACCION * (2 * valoracion_suavizada(positivos, negativos) - 1)


class Reacciones:
    """Agregados en memoria. No es segura entre hilos por sí sola: la protege Senales."""

    def __init__(self, vida_media_s=VIDA_MEDIA_S):
        self.vida_media_s = float(vida_media_s)
        self._conteos = {}      # doc_id -> {tipo: veces} (brutos, para mostrar)
        self._evidencia = {}    # doc_id -> [positiva, negativa, hora] ya decaídas a `hora`

    def registrar(self, doc_id, tipo, ahora):
        """Suma una reacción. Devuelve los conteos actualizados del documento."""
        if tipo not in TIPOS:
            raise ValueError(f"reacción desconocida: {tipo}")
        conteo = self._conteos.setdefault(doc_id, dict.fromkeys(TIPOS, 0))
        conteo[tipo] += 1

        positiva, negativa = self._decaida(doc_id, ahora)
        puntos = PUNTOS[tipo]
        if puntos >= 0:
            positiva += puntos
        else:
            negativa -= puntos
        self._evidencia[doc_id] = [positiva, negativa, ahora]
        return dict(conteo)

    def conteos(self, doc_id):
        conteo = self._conteos.get(doc_id)
        return dict(conteo) if conteo else dict.fromkeys(TIPOS, 0)

    def puntos(self, doc_id):
        """Puntos brutos (sin decaimiento): suma de PUNTOS por reacción."""
        conteo = self._conteos.get(doc_id)
        if not conteo:
            return 0.0
        return sum(PUNTOS[t] * veces for t, veces in conteo.items())

    def _decaida(self, doc_id, ahora):
        """(evidencia positiva, evidencia negativa) del documento decaídas hasta `ahora`."""
        registro = self._evidencia.get(doc_id)
        if registro is None:
            return 0.0, 0.0
        positiva, negativa, hora = registro
        if self.vida_media_s > 0:
            decaimiento = 0.5 ** (max(0.0, ahora - hora) / self.vida_media_s)
            positiva *= decaimiento
            negativa *= decaimiento
        return positiva, negativa

    def peso(self, doc_id, ahora):
        """Factor de ranking del documento: 1.0 si nadie ha reaccionado."""
        if doc_id not in self._evidencia:
            return 1.0
        return factor_reaccion(*self._decaida(doc_id, ahora))
