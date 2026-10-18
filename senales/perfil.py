"""Del rastro personal (historial y reacciones que guarda el navegador) a evidencia con peso.

El perfil de una persona vive en su navegador y viaja en cada petición: el servidor no lo
guarda (a diferencia de reacciones, clics y consultas globales, que sí forman el almacén).
Aquí solo se decide cuánto vale cada huella; qué hacer con ella lo decide busqueda/recomendador.py.

    reacción:  PUNTOS[tipo] × decaimiento(edad)           (los mismos puntos y vida media que reacciones.py)
    búsqueda:  PESO_CONSULTA × (1 + ln veces) × decaimiento(edad)

La repetición cuenta de forma sublineal: la frecuencia de uso es una distribución de cola larga
(Zipf) y 20 repeticiones de una sola consulta no deben tapar el resto de los intereses.
"""
import math

from senales.reacciones import PUNTOS, VIDA_MEDIA_S

PESO_CONSULTA = 0.5      # buscar es una señal más débil que reaccionar de forma explícita
MAX_REPETICIONES = 1_000


def decaimiento(edad_s, vida_media_s=VIDA_MEDIA_S):
    """1.0 ahora; la mitad tras una vida media. Una hora en el futuro cuenta como ahora."""
    if vida_media_s <= 0:
        return 1.0
    return 0.5 ** (max(0.0, edad_s) / vida_media_s)


def peso_consulta(veces, edad_s, vida_media_s=VIDA_MEDIA_S):
    veces = max(1, min(int(veces), MAX_REPETICIONES))
    return PESO_CONSULTA * (1 + math.log(veces)) * decaimiento(edad_s, vida_media_s)


def peso_reaccion(tipo, edad_s, vida_media_s=VIDA_MEDIA_S):
    """Con signo: positivo si gustó, negativo si no gustó."""
    return PUNTOS[tipo] * decaimiento(edad_s, vida_media_s)
