"""Puntuación, ordenación y serialización de resultados. Funciones puras.

    score  = (aporte_coseno + aporte_emoji) × factor_idioma        (similitud: la insignia de la UI)
    orden  = score × peso, con peso = reacciones × aprendizaje      (el orden real)

`peso` viene de las señales de uso (ver senales/): aquí solo se multiplica.
"""
from collections import Counter
from dataclasses import dataclass

from busqueda import parametros as P
from busqueda.consulta import Analisis
from busqueda.indice import Indice

SIN_REACCIONES = {"me_gusta": 0, "no_me_gusta": 0, "me_encanta": 0}


@dataclass(frozen=True)
class Puntaje:
    doc: dict
    coseno: float          # (1 - W) × coseno de términos
    emoji: float           # W × m
    coincide_emoji: bool
    factor_idioma: float

    @property
    def score(self):
        return (self.coseno + self.emoji) * self.factor_idioma


def peso_emoji(analisis: Analisis):
    """W de la mezcla coseno/emoji: 0 sin coincidencia de emoji; mayor si solo hay emojis."""
    if not analisis.coinciden:
        return 0.0
    return P.PESO_EMOJI_CON_TEXTO if analisis.tiene_texto else P.PESO_EMOJI_SOLO


def factor_idioma(idioma_doc, dominante, coincide_emoji):
    if idioma_doc == dominante:
        return P.BOOST_IDIOMA_DOMINANTE
    if coincide_emoji:
        return P.FACTOR_IDIOMA_CON_EMOJI
    return P.FACTOR_IDIOMA_SECUNDARIO


def acumular_productos(vector, postings):
    """Producto punto consulta·documento por posición, sumando por término."""
    productos = {}
    for termino, peso_q in vector.pesos.items():
        for posicion, peso_d in postings.get(termino, ()):
            productos[posicion] = productos.get(posicion, 0.0) + peso_q * peso_d
    return productos


def puntuar(indice: Indice, analisis: Analisis, dominante):
    """Candidatos con score > 0: los que comparten algún término expandido o el emoji."""
    modo = analisis.modo
    w = peso_emoji(analisis)
    productos = acumular_productos(analisis.vector, indice.postings[modo])
    normas = indice.normas[modo]
    norma_q = analisis.vector.norma

    puntajes = []
    for posicion in sorted(set(productos) | set(analisis.coinciden)):  # orden determinista
        doc = indice.catalogo[posicion]
        m = analisis.coinciden.get(posicion, 0.0)
        norma_d = normas[posicion]
        # Similitud coseno estrictamente de TÉRMINOS
        coseno = productos.get(posicion, 0.0) / (norma_q * norma_d) if norma_q and norma_d else 0.0
        puntaje = Puntaje(
            doc=doc,
            coseno=(1 - w) * coseno,
            emoji=w * m,
            coincide_emoji=bool(m),
            factor_idioma=factor_idioma(doc["idioma"], dominante, m),
        )
        if puntaje.score > 0:
            puntajes.append(puntaje)
    return puntajes


def ordenar(puntajes, pesos):
    """Orden por score × peso; desempate por nombre (un emoji compartido por 17 documentos
    da scores casi idénticos y el orden no debe depender del azar).

    `pesos`: id de documento -> (reacciones, aprendizaje)."""
    def clave(p):
        reacciones, aprendizaje = pesos.get(p.doc["id"], (1.0, 1.0))
        return (-(p.score * reacciones * aprendizaje), p.doc["nombre"])

    return sorted(puntajes, key=clave)


def explicar(puntaje: Puntaje, reacciones, aprendizaje):
    """Desglose del score por componente (tooltip de la UI)."""
    return {
        "coseno": round(puntaje.coseno, 4),
        "emoji": round(puntaje.emoji, 4),
        "factor_idioma": puntaje.factor_idioma,
        "score": round(puntaje.score, 4),
        "reacciones": round(reacciones, 4),
        "aprendizaje": round(aprendizaje, 4),
        "orden": round(puntaje.score * reacciones * aprendizaje, 4),
    }


def explicacion_sin_consulta(peso):
    """Lista sin texto: solo cuentan las reacciones (no hay score)."""
    return {
        "coseno": None, "emoji": None, "factor_idioma": None, "score": None,
        "reacciones": round(peso, 4), "aprendizaje": 1.0, "orden": round(peso, 4),
    }


def decorar(doc, score, emoji_coincide=False, peso=1.0, reacciones=None, explicacion=None):
    idioma = doc["idioma"]
    return dict(
        doc,
        score=None if score is None else round(score, 4),
        idioma_nombre=P.NOMBRE_IDIOMA[idioma],
        bandera=P.BANDERA_IDIOMA[idioma],
        homografo=False,
        emoji_coincide=emoji_coincide,
        peso=round(peso, 4),
        reacciones=reacciones or dict(SIN_REACCIONES),
        explicacion=explicacion,
    )


def marcar_homografos(resultados):
    conteo = Counter(r["nombre"].lower() for r in resultados)
    for resultado in resultados:
        if conteo[resultado["nombre"].lower()] > 1:
            resultado["homografo"] = True
