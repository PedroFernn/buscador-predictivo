"""Sugerencias personales: del rastro de una persona a documentos del catálogo.

Entrada: evidencia ya ponderada (ver senales/perfil.py), con signo.
    consultas   [(texto, peso)]      lo que buscó (peso > 0)
    reacciones  [(doc_id, peso)]     lo que valoró (peso > 0 gustó, peso < 0 no gustó)

Es relevancia por retroalimentación (Rocchio) sobre el mismo espacio vectorial del buscador:

  1. Perfil. Dos vectores de términos, uno positivo y otro negativo. Cada búsqueda aporta su
     vector de consulta (el mismo que usa buscar(): prefijos, sinónimos y significado de los
     emojis) y cada reacción el vector tf-idf del documento, ambos normalizados a longitud 1 y
     multiplicados por su peso. Como los vectores ya llevan idf, los términos que aparecen en
     casi todo el catálogo (cola de la ley de Zipf) casi no pesan en el perfil.
  2. Poda. El perfil conserva solo sus REC_MAX_TERMINOS términos más pesados: su tamaño no
     crece con el uso (el vocabulario sí crece, ley de Heaps) y cada petición cuesta lo mismo.
  3. Candidatos por el índice inverso. Solo se tocan los postings de los términos del perfil:
     un documento sin ningún término en común nunca se puntúa.
  4. Afinidad = coseno(perfil+, doc) − REC_PESO_NEGATIVO · coseno(perfil−, doc), por el prior
     de idioma de ranking.py. Quedan fuera lo que la persona ya valoró y los documentos cuyo
     nombre contiene todo lo que buscó (esos ya los mostró su búsqueda).
  5. Puentes. Si la afinidad directa no alcanza para llenar la lista y la persona terminó una
     categoría (todo lo suyo ya lo vio, o la buscó por su nombre y cabía entera en los
     resultados), el árbol de esa categoría la lleva a la rama más cercana de otro árbol
     (ver categorias.py) y de ahí salen las sugerencias que faltan, marcadas con `puente`.

Sin estado: nada de lo recibido se guarda en el servidor. Funciones puras, sin Flask.
"""
import math
from collections import defaultdict

from busqueda import categorias as C
from busqueda import parametros as P
from busqueda import ranking
from busqueda.categorias import MODO
from busqueda.consulta import VectorConsulta, analizar
from nucleo.lexico import STOPWORDS
from nucleo.texto import normalizar, tokenizar



def _podar(perfil):
    """Los REC_MAX_TERMINOS términos más pesados (solo pesos positivos)."""
    pesados = sorted(((t, p) for t, p in perfil.items() if p > 0), key=lambda tp: (-tp[1], tp[0]))
    return dict(pesados[: P.REC_MAX_TERMINOS])


def construir_perfil(indice, consultas, reacciones):
    """(positivo, negativo): vectores {término: peso} ya podados."""
    positivo, negativo = defaultdict(float), defaultdict(float)

    for texto, peso in consultas:
        vector = analizar(texto, indice).vector
        if vector.norma:
            for termino, p in vector.pesos.items():
                positivo[termino] += peso * p / vector.norma

    vectores, normas = indice.vectores[MODO], indice.normas[MODO]
    for doc_id, peso in reacciones:
        posicion = indice.posicion_por_id.get(doc_id)
        if posicion is None or not normas[posicion] or not peso:
            continue
        destino = positivo if peso > 0 else negativo
        for termino, p in vectores[posicion].items():
            if termino not in STOPWORDS:
                destino[termino] += abs(peso) * p / normas[posicion]

    return _podar(positivo), _podar(negativo)


def _norma(perfil):
    return math.sqrt(sum(p * p for p in perfil.values()))


def _productos(indice, perfil, norma):
    """Producto punto perfil·documento por posición, recorriendo solo los postings tocados."""
    if not norma:
        return {}
    return ranking.acumular_productos(VectorConsulta(perfil, sorted(perfil), norma), indice.postings[MODO])


def _motivos(indice, posicion, positivo):
    """Los términos del perfil que más pesan en este documento (el \"por qué\")."""
    aportes = sorted(
        ((positivo[t] * p, t) for t, p in indice.vectores[MODO][posicion].items()
         if t in positivo and t not in STOPWORDS),
        key=lambda ap: (-ap[0], ap[1]),
    )
    return [t for _, t in aportes[: P.REC_MAX_MOTIVOS]]


def _ya_buscado(doc, buscados):
    """¿El nombre del documento contiene todos los términos de alguna búsqueda?"""
    nombre = set(tokenizar(doc["nombre"]))
    return any(terminos <= nombre for terminos in buscados)


def _identidad(doc):
    """Nombre e idioma: el catálogo repite entradas (mismo nombre, otra categoría)."""
    return normalizar(doc["nombre"]), doc["idioma"]


def _elemento(doc, afinidad, motivos, puente=None):
    idioma = doc["idioma"]
    elemento = {
        "id": doc["id"],
        "nombre": doc["nombre"],
        "categoria": doc["categoria"],
        "descripcion": doc["descripcion"],
        "emoji": doc["emoji"],
        "idioma": idioma,
        "idioma_nombre": P.NOMBRE_IDIOMA[idioma],
        "bandera": P.BANDERA_IDIOMA[idioma],
        "afinidad": round(afinidad, 4),
        "motivos": motivos,
    }
    if puente:
        elemento["puente"] = puente  # {"desde": categoría terminada, "hacia": rama a la que lleva}
    return elemento


def _coseno_centroide(indice, posicion, centroide):
    norma = indice.normas[MODO][posicion]
    if not norma:
        return 0.0
    vector = indice.vectores[MODO][posicion]
    return sum(peso * vector.get(termino, 0.0) for termino, peso in centroide.items()) / norma


def _por_puentes(indice, textos, tocadas, dominante, visto, vistos, neg, norma_neg, faltan):
    """Sugerencias que salen de la rama más cercana a una categoría terminada.

    afinidad = REC_PESO_PUENTE · similitud acumulada · (PISO + (1 − PISO) · coseno con el padre),
    menos lo que se parezca a lo que no gustó. `vistos` son las identidades ya sugeridas."""
    def omitir(posicion):
        return visto(posicion) or _identidad(indice.catalogo[posicion]) in vistos

    rutas = C.puentes(indice.categorias, tocadas, textos, dominante, visto, omitir, faltan)
    normas = indice.normas[MODO]
    candidatos = []
    for similitud, origen, padre, destino, posiciones in rutas:
        for posicion in posiciones:
            doc = indice.catalogo[posicion]
            if not normas[posicion]:
                continue
            cercania = _coseno_centroide(indice, posicion, padre.centroide)
            afinidad = P.REC_PESO_PUENTE * similitud * (P.REC_PUENTE_PISO + (1 - P.REC_PUENTE_PISO) * cercania)
            if neg:
                resta = P.REC_PESO_NEGATIVO * neg.get(posicion, 0.0) / (norma_neg * normas[posicion])
                if resta and afinidad - resta <= 0:
                    continue
                afinidad -= resta
            afinidad *= ranking.factor_idioma(doc["idioma"], dominante, False)
            candidatos.append((-afinidad, doc["nombre"], posicion, padre, origen, destino))

    candidatos.sort(key=lambda c: c[:3])
    elementos = []
    for menos, _, posicion, padre, origen, destino in candidatos:
        doc = indice.catalogo[posicion]
        if _identidad(doc) in vistos:
            continue
        vistos.add(_identidad(doc))
        elementos.append(_elemento(
            doc, -menos, _motivos(indice, posicion, padre.centroide),
            {"desde": origen.nombre, "hacia": destino.nombre},
        ))
        if len(elementos) == faltan:
            break
    return elementos


def recomendar(indice, consultas, reacciones, dominante, limite=P.REC_LIMITE):
    """{"elementos": [...]}; vacío si no hay nada positivo de qué partir."""
    positivo, negativo = construir_perfil(indice, consultas, reacciones)
    norma_pos = _norma(positivo)
    if not norma_pos:
        return {"elementos": []}
    norma_neg = _norma(negativo)
    pos = _productos(indice, positivo, norma_pos)
    neg = _productos(indice, negativo, norma_neg)

    valorados = {doc_id for doc_id, _ in reacciones}
    conocidos = {
        _identidad(indice.catalogo[indice.posicion_por_id[doc_id]])
        for doc_id in valorados if doc_id in indice.posicion_por_id
    }
    buscados = [terminos for terminos in (set(tokenizar(texto)) for texto, _ in consultas) if terminos]
    normas = indice.normas[MODO]

    def visto(posicion):
        doc = indice.catalogo[posicion]
        return _identidad(doc) in conocidos or _ya_buscado(doc, buscados)

    tocadas = {  # categorías donde la persona ya valoró algo
        C.clave_categoria(indice.catalogo[indice.posicion_por_id[doc_id]])
        for doc_id in valorados if doc_id in indice.posicion_por_id
    }
    candidatos = []
    for posicion, producto in pos.items():
        doc = indice.catalogo[posicion]
        if not normas[posicion]:
            continue
        # `conocidos` incluye al propio documento valorado y a sus duplicados de nombre e idioma
        if _identidad(doc) in conocidos or _ya_buscado(doc, buscados):
            tocadas.add(C.clave_categoria(doc))
            continue
        afinidad = producto / (norma_pos * normas[posicion])
        if neg:
            afinidad -= P.REC_PESO_NEGATIVO * neg.get(posicion, 0.0) / (norma_neg * normas[posicion])
        afinidad *= ranking.factor_idioma(doc["idioma"], dominante, False)
        if afinidad >= P.REC_AFINIDAD_MIN:
            candidatos.append((-afinidad, doc["nombre"], posicion))

    candidatos.sort()  # mayor afinidad; a igualdad, por nombre (orden determinista)
    limite = max(1, min(int(limite), P.REC_LIMITE_MAX))
    elementos, vistos = [], set()
    for menos, _, posicion in candidatos:
        doc = indice.catalogo[posicion]
        if _identidad(doc) in vistos:
            continue
        vistos.add(_identidad(doc))
        elementos.append(_elemento(doc, -menos, _motivos(indice, posicion, positivo)))
        if len(elementos) == limite:
            break
    if len(elementos) < limite:
        elementos.extend(_por_puentes(
            indice, [texto for texto, _ in consultas], tocadas, dominante, visto, vistos,
            neg, norma_neg, limite - len(elementos),
        ))
    return {"elementos": elementos}


