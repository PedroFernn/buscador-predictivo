"""Índice: IDF, vectores tf-idf normalizados por campo y listas de postings por modo.

Se construye una vez por carga del catálogo. Cada posting guarda el peso del término
en el documento, de modo que la consulta suma `peso_q × peso_d` por término sin
recorrer el vector de cada documento (O(postings tocados), no O(candidatos × |q|)).

Ojo con los dos tipos de identificador: `posicion` es el lugar del documento dentro de
`Indice.catalogo` (interno al motor) y `doc["id"]` es el id del repositorio (el que ven
la API y las señales).
"""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from busqueda import parametros as P
from nucleo.emojis import extraer_emojis, normalizar_emoji
from nucleo.texto import tokenizar


@dataclass(frozen=True)
class Indice:
    """Todo lo que se calcula una vez por carga del catálogo."""
    catalogo: list      # documentos saneados; la posición en la lista es la posición interna
    ids: frozenset      # ids de repositorio presentes
    posicion_por_id: dict  # id de repositorio -> posición interna
    idf: dict
    vocabulario: list   # ordenado: permite bisect para expandir prefijos
    postings: dict      # modo -> {término: [(posicion, peso)]}
    normas: dict        # modo -> [norma del vector por posición]
    vectores: dict      # modo -> [{término: peso}] por posición (perfil de gustos, ver recomendador.py)
    emoji_a_docs: dict  # clave de emoji normalizada -> [posicion]


def sanear(documento):
    idioma = documento.get("idioma") or P.IDIOMA_POR_DEFECTO
    if idioma not in P.IDIOMAS:
        idioma = P.IDIOMA_POR_DEFECTO
    # `or ""` cubre NULL de la base de datos (categoría sin asignar, etc.)
    return {
        **documento,
        "nombre": documento.get("nombre") or "",
        "categoria": documento.get("categoria") or "",
        "descripcion": documento.get("descripcion") or "",
        "emoji": documento.get("emoji") or "📄",
        "idioma": idioma,
    }


def normalizar_vector(vector):
    norma = math.sqrt(sum(peso * peso for peso in vector.values()))
    if norma == 0:
        return {}
    return {termino: peso / norma for termino, peso in vector.items()}


def construir_indice(documentos):
    pares = [(crudo, sanear(crudo)) for crudo in documentos]
    pares = [(c, d) for c, d in pares if d["nombre"] or d["descripcion"]]
    catalogo = [d for _, d in pares]
    n = len(catalogo)
    campos = P.CAMPOS
    tokens_por_doc = [{campo: tokenizar(doc[campo]) for campo, _ in campos} for doc in catalogo]

    df = defaultdict(int)
    for por_campo in tokens_por_doc:
        presentes = set()
        for tokens in por_campo.values():
            presentes.update(tokens)
        for termino in presentes:
            df[termino] += 1

    idf = {termino: math.log10(1 + n / frecuencia) for termino, frecuencia in df.items()}
    vocabulario = sorted(idf)

    postings = {modo: defaultdict(list) for modo in P.CAMPOS_POR_MODO}
    normas = {modo: [] for modo in P.CAMPOS_POR_MODO}
    vectores = {modo: [] for modo in P.CAMPOS_POR_MODO}

    for posicion, tokens_campo in enumerate(tokens_por_doc):
        # Vector tf-idf normalizado por campo (se reutiliza en cada modo)
        por_campo = {}
        for campo, _ in campos:
            tf = Counter(tokens_campo[campo])
            por_campo[campo] = normalizar_vector({t: freq * idf[t] for t, freq in tf.items()})

        for modo, pesos_campo in P.CAMPOS_POR_MODO.items():
            vector = defaultdict(float)
            for campo, peso_campo in pesos_campo:
                for termino, peso in por_campo[campo].items():
                    vector[termino] += peso_campo * peso
            normas[modo].append(math.sqrt(sum(p * p for p in vector.values())))
            vectores[modo].append(dict(vector))
            for termino, peso in vector.items():
                postings[modo][termino].append((posicion, peso))

    # Índice de emojis. Se lee del dato crudo: sanear() rellena 📄 en los documentos
    # sin emoji y eso no debe contar como coincidencia.
    emoji_a_docs = defaultdict(list)
    for posicion, (crudo, _) in enumerate(pares):
        emojis_doc, _ = extraer_emojis(crudo.get("emoji") or "")
        for clave in {normalizar_emoji(e) for e in emojis_doc}:
            emoji_a_docs[clave].append(posicion)

    return Indice(
        catalogo=catalogo,
        ids=frozenset(d["id"] for d in catalogo if "id" in d),
        posicion_por_id={d["id"]: i for i, d in enumerate(catalogo) if "id" in d},
        idf=idf,
        vocabulario=vocabulario,
        postings={modo: dict(p) for modo, p in postings.items()},
        normas=normas,
        vectores=vectores,
        emoji_a_docs=dict(emoji_a_docs),
    )


