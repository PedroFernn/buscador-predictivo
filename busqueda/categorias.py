"""Bosque de categorías: un árbol B por categoría y un árbol B de categorías.

    categorias : ArbolB   clave de categoría (normalizada)  -> Categoria
    Categoria.docs : ArbolB   (idioma, nombre normalizado, posición) -> posición

Como la clave de cada documento empieza por el idioma, los documentos de un idioma son un
tramo contiguo del árbol: `rango()` los saca sin recorrer los demás.

Cada categoría guarda su centroide (suma normalizada de los vectores tf-idf de sus documentos,
podada a CATEGORIA_MAX_TERMINOS) y sus categorías vecinas, ordenadas por similitud coseno entre
centroides. Se calculan una vez por carga del catálogo con un índice inverso de centroides:
O(términos tocados), no O(categorías²).

`puentes()` es la navegación: parte de las categorías terminadas y avanza, de mejor a peor
similitud acumulada (búsqueda de costo uniforme sobre el grafo de vecinas), hacia las ramas de
otros árboles que todavía tienen documentos por ver. Funciones puras, sin Flask.
"""
import heapq
from collections import defaultdict
from dataclasses import dataclass

from busqueda import parametros as P
from nucleo.arbol_b import ArbolB
from nucleo.lexico import STOPWORDS
from nucleo.texto import normalizar, tokenizar

# Se compara en el modo que mira la descripción (el mismo que usa recomendador.py)
MODO = "sinopsis"
_FRACCION_TERMINO_COMUN = 0.5  # con muchas categorías, un término en más de esta fracción no discrimina
_MIN_CATEGORIAS_PARA_PODAR = 20


@dataclass(frozen=True, eq=False)
class Categoria:
    clave: str
    nombre: str
    docs: ArbolB      # (idioma, nombre normalizado, posición) -> posición
    centroide: dict   # término -> peso, norma 1
    vecinas: tuple    # ((clave, similitud), ...) de más a menos cercana


def clave_categoria(doc):
    return normalizar(doc["categoria"]).strip()


def _centroide(vectores, normas, posiciones):
    suma = defaultdict(float)
    for posicion in posiciones:
        if not normas[posicion]:
            continue
        for termino, peso in vectores[posicion].items():
            if termino not in STOPWORDS:
                suma[termino] += peso / normas[posicion]
    pesados = sorted(suma.items(), key=lambda tp: (-tp[1], tp[0]))[: P.CATEGORIA_MAX_TERMINOS]
    norma = sum(p * p for _, p in pesados) ** 0.5
    return {t: p / norma for t, p in pesados} if norma else {}


def _vecinas(centroides):
    """{clave: ((vecina, similitud), ...)} por coseno entre centroides, vía índice inverso."""
    inverso = defaultdict(list)
    for clave, centroide in centroides.items():
        for termino, peso in centroide.items():
            inverso[termino].append((clave, peso))
    if len(centroides) >= _MIN_CATEGORIAS_PARA_PODAR:
        tope = _FRACCION_TERMINO_COMUN * len(centroides)
        inverso = {t: lista for t, lista in inverso.items() if len(lista) <= tope}

    vecinas = {}
    for clave, centroide in centroides.items():
        acumulado = defaultdict(float)
        for termino, peso in centroide.items():
            for otra, otro_peso in inverso.get(termino, ()):
                if otra != clave:
                    acumulado[otra] += peso * otro_peso
        cercanas = sorted(
            ((s, o) for o, s in acumulado.items() if s >= P.CATEGORIA_SIM_MIN),
            key=lambda so: (-so[0], so[1]),
        )
        vecinas[clave] = tuple((o, s) for s, o in cercanas[: P.CATEGORIA_VECINAS])
    return vecinas


def construir(catalogo, vectores, normas):
    """Árbol B de categorías a partir del catálogo saneado y los vectores del modo MODO."""
    grupos, nombres = defaultdict(list), {}
    for posicion, doc in enumerate(catalogo):
        clave = clave_categoria(doc)
        if clave:
            grupos[clave].append(posicion)
            nombres.setdefault(clave, doc["categoria"])

    centroides = {c: _centroide(vectores, normas, posiciones) for c, posiciones in grupos.items()}
    vecinas = _vecinas(centroides)

    arbol = ArbolB(P.ARBOL_B_GRADO)
    for clave, posiciones in grupos.items():
        docs = ArbolB(P.ARBOL_B_GRADO)
        for posicion in posiciones:
            doc = catalogo[posicion]
            docs.insertar((doc["idioma"], normalizar(doc["nombre"]), posicion), posicion)
        arbol.insertar(clave, Categoria(clave, nombres[clave], docs, centroides[clave], vecinas[clave]))
    return arbol


def posiciones(categoria, idioma):
    """Posiciones de los documentos de la categoría en ese idioma (tramo contiguo del árbol)."""
    return [p for _, p in categoria.docs.rango((idioma,), (idioma + "\x00",))]


def nombradas_por(categorias, texto):
    """Categorías que la consulta nombra completas: su nombre empieza con la consulta y todas
    sus palabras están (enteras) en el nombre. Recorre solo ese prefijo del árbol de categorías."""
    palabras = set(tokenizar(texto))
    prefijo = normalizar(texto).strip()
    if not palabras or not prefijo:
        return []
    return [c for _, c in categorias.prefijo(prefijo) if palabras <= set(tokenizar(c.nombre))]


def terminada(categoria, idioma, visto):
    """¿No queda nada por ver en esa categoría (en ese idioma)?"""
    docs = posiciones(categoria, idioma)
    return len(docs) >= P.REC_PUENTE_MIN_DOCS and all(visto(p) for p in docs)


def puentes(categorias, tocadas, textos, idioma, visto, omitir, necesarios):
    """Rutas desde las categorías terminadas hacia ramas de otros árboles con documentos libres.

    tocadas    claves de categorías en las que la persona ya valoró o buscó algo
    textos     consultas de la persona (una que nombra una categoría completa también la termina)
    visto      posición -> ¿ya lo valoró o ya lo buscó? (decide si una categoría está terminada)
    omitir     posición -> ¿no ofrecerlo? (visto, o ya sugerido por otra vía)
    necesarios documentos libres a reunir antes de parar

    Devuelve [(similitud acumulada, origen, padre, destino, [posiciones libres])]: `padre` es la
    categoría desde la que se llegó a `destino`, de mejor a peor similitud acumulada.
    """
    origenes = {}
    for clave in sorted(tocadas):
        categoria = categorias.obtener(clave)
        if categoria is not None and terminada(categoria, idioma, visto):
            origenes[clave] = categoria
    for texto in textos:
        for categoria in nombradas_por(categorias, texto):
            cabe = P.REC_PUENTE_MIN_DOCS <= len(posiciones(categoria, idioma)) <= P.LIMITE_RESULTADOS
            if cabe:  # la búsqueda ya la mostró entera
                origenes.setdefault(categoria.clave, categoria)

    cola = [(-1.0, clave, clave, clave) for clave in sorted(origenes)]  # (-similitud, clave, origen, padre)
    heapq.heapify(cola)
    alcanzadas = set(origenes)
    rutas, reunidos, exploradas = [], 0, 0
    while cola and reunidos < necesarios and exploradas < P.REC_PUENTE_MAX_CATEGORIAS:
        menos, clave, origen, padre = heapq.heappop(cola)
        categoria = categorias.obtener(clave)
        if clave != origen:
            exploradas += 1
            libres = [p for p in posiciones(categoria, idioma) if not omitir(p)]
            if libres:
                rutas.append((-menos, origenes[origen], categorias.obtener(padre), categoria, libres))
                reunidos += len(libres)
        for otra, similitud in categoria.vecinas:
            if otra not in alcanzadas:
                alcanzadas.add(otra)
                heapq.heappush(cola, (menos * similitud, otra, origen, clave))
    return rutas
