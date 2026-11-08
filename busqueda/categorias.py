"""Bosque de categorías: un árbol B por categoría y un árbol B de categorías.

    categorias : ArbolB   clave de categoría (normalizada)  -> Categoria
    Categoria.docs : ArbolB   (idioma, nombre normalizado, posición) -> posición

Como la clave de cada documento empieza por el idioma, los documentos de un idioma son un
tramo contiguo del árbol: `rango()` los saca sin recorrer los demás.

Cada categoría guarda su centroide (suma normalizada de los vectores tf-idf de sus documentos,
podada a CATEGORIA_MAX_TERMINOS) y sus categorías vecinas, ordenadas por similitud coseno entre
centroides. Se calculan una vez por carga del catálogo con un índice inverso de centroides:
O(términos tocados), no O(categorías²).

Llave relacional. Un árbol B solo ordena; para que además relacione, las categorías se
ordenan por cercanía (cada una queda junto a las más parecidas, ver ordenar_por_cercania) y se
guardan en un segundo árbol, `mapa`, con la llave forzada `NN_categoria`:

    00_frutas   01_verduras   02_granos   03_metales
    (bloque)    (la más cercana al terminar 00)          NN = lugar en el orden, con ceros a la izquierda

Terminar el bloque 00_frutas_* es llegar a 01_*: la más cercana es, literalmente, la llave que
sigue (o la que antecede) en el árbol. El árbol por nombre (`categorias`) se conserva para
buscar por prefijo de nombre, que el prefijo numérico de las llaves del mapa impediría.

`puentes()` es la navegación: parte de las categorías terminadas y camina por las llaves del
mapa en ambos sentidos (siguientes/anteriores), de mejor a peor similitud acumulada, hasta
que un eslabón deja de parecerse (corte entre bloques). Funciones puras, sin Flask.
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
    llave: str = ""   # llave forzada del mapa: NN_categoria (NN = lugar en el orden por cercanía)
    eslabones: tuple = (0.0, 0.0)  # similitud con la categoría anterior y con la siguiente en el mapa


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


def _similitudes(vecinas):
    """{(a, b): similitud} simétrico (a < b): la mayor de las dos listas de vecinas."""
    sim = {}
    for a, lista in vecinas.items():
        for b, s in lista:
            par = (a, b) if a < b else (b, a)
            sim[par] = max(sim.get(par, 0.0), s)
    return sim


def ordenar_por_cercania(claves, vecinas):
    """Orden lineal de las categorías en que las contiguas son las más parecidas.

    Heurística de arista voraz (la del viajante): se toman las parejas de mayor similitud y se
    enlaza cada una si ninguna de las dos ya tiene dos enlaces y no se cierra un ciclo. Queda un
    conjunto de cadenas, que se ponen una tras otra (la mayor primero). Determinista.

    Un orden lineal no puede conservar todas las vecindades: cada categoría tiene a lo sumo dos
    contiguas. Por eso se mide cuánto conserva (preservacion) en vez de suponerlo."""
    sim = _similitudes(vecinas)
    raiz = {c: c for c in claves}

    def buscar(x):
        while raiz[x] != x:
            raiz[x] = raiz[raiz[x]]
            x = raiz[x]
        return x

    enlaces = defaultdict(list)
    for (a, b), _ in sorted(sim.items(), key=lambda par_s: (-par_s[1], par_s[0])):
        if len(enlaces[a]) < 2 and len(enlaces[b]) < 2 and buscar(a) != buscar(b):
            enlaces[a].append(b)
            enlaces[b].append(a)
            raiz[buscar(a)] = buscar(b)

    cadenas, visitadas = [], set()
    for inicio in sorted(claves):  # se parte de un extremo (0 o 1 enlaces); el menor alfabético va primero
        if inicio in visitadas or len(enlaces[inicio]) == 2:
            continue
        cadena, previa, actual = [inicio], None, inicio
        visitadas.add(inicio)
        while True:
            siguientes = [x for x in enlaces[actual] if x != previa]
            if not siguientes:
                break
            previa, actual = actual, siguientes[0]
            cadena.append(actual)
            visitadas.add(actual)
        cadenas.append(cadena)
    cadenas.sort(key=lambda cadena: (-len(cadena), cadena[0]))
    return [clave for cadena in cadenas for clave in cadena], sim


def llave_relacional(lugar, ancho, clave):
    """NN_categoria: el prefijo numérico fuerza el orden; el nombre (con _) lo hace legible."""
    return f"{lugar:0{ancho}d}_{clave.replace(' ', '_')}"


def preservacion(orden, vecinas):
    """Fracción de categorías con vecinas cuya vecina más cercana quedó contigua en el orden."""
    lugar = {clave: i for i, clave in enumerate(orden)}
    con_vecinas = [c for c in orden if vecinas.get(c)]
    if not con_vecinas:
        return None
    contiguas = sum(1 for c in con_vecinas if abs(lugar[c] - lugar[vecinas[c][0][0]]) == 1)
    return contiguas / len(con_vecinas)


def construir(catalogo, vectores, normas):
    """(por_nombre, mapa): los dos árboles de categorías, a partir del catálogo saneado y los
    vectores del modo MODO. `por_nombre` se busca por prefijo de nombre; `mapa` lleva la llave
    forzada NN_categoria y es el que se recorre para ir de una categoría a la más cercana."""
    grupos, nombres = defaultdict(list), {}
    for posicion, doc in enumerate(catalogo):
        clave = clave_categoria(doc)
        if clave:
            grupos[clave].append(posicion)
            nombres.setdefault(clave, doc["categoria"])

    centroides = {c: _centroide(vectores, normas, posiciones) for c, posiciones in grupos.items()}
    vecinas = _vecinas(centroides)

    orden, sim = ordenar_por_cercania(sorted(grupos), vecinas)
    ancho = max(2, len(str(max(len(orden) - 1, 0))))
    llaves = {clave: llave_relacional(lugar, ancho, clave) for lugar, clave in enumerate(orden)}
    eslabon = lambda a, b: sim.get((a, b) if a < b else (b, a), 0.0)
    eslabones = {
        clave: (eslabon(clave, orden[i - 1]) if i else 0.0, eslabon(clave, orden[i + 1]) if i + 1 < len(orden) else 0.0)
        for i, clave in enumerate(orden)
    }

    por_nombre, mapa = ArbolB(P.ARBOL_B_GRADO), ArbolB(P.ARBOL_B_GRADO)
    for clave, posiciones in grupos.items():
        docs = ArbolB(P.ARBOL_B_GRADO)
        for posicion in posiciones:
            doc = catalogo[posicion]
            docs.insertar((doc["idioma"], normalizar(doc["nombre"]), posicion), posicion)
        categoria = Categoria(clave, nombres[clave], docs, centroides[clave], vecinas[clave], llaves[clave], eslabones[clave])
        por_nombre.insertar(clave, categoria)
        mapa.insertar(llaves[clave], categoria)
    return por_nombre, mapa


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


def puentes(categorias, mapa, tocadas, textos, idioma, visto, omitir, necesarios):
    """Rutas desde las categorías terminadas hacia ramas de otros árboles con documentos libres.

    categorias árbol por nombre (para buscar las categorías de `tocadas` y las que nombran los textos)
    mapa       árbol de llaves NN_categoria: por él se camina, hacia las llaves que siguen y las que anteceden
    tocadas    claves de categorías en las que la persona ya valoró o buscó algo
    textos     consultas de la persona (una que nombra una categoría completa también la termina)
    visto      posición -> ¿ya lo valoró o ya lo buscó? (decide si una categoría está terminada)
    omitir     posición -> ¿no ofrecerlo? (visto, o ya sugerido por otra vía)
    necesarios documentos libres a reunir antes de parar

    Desde cada categoría terminada se avanza por el mapa en los dos sentidos. La similitud
    acumulada es el producto de los eslabones recorridos; un eslabón por debajo de
    CATEGORIA_SIM_MIN es un corte entre bloques y ese sentido se detiene (no se salta a
    categorías sin relación). Los pasos se toman de mejor a peor similitud acumulada.

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

    cola, caminantes, turno = [], {}, 0
    alcanzadas = set(origenes)

    def adelantar(origen, sentido):
        """Siguiente paso de un caminante: (categoría padre, categoría destino, similitud) o None."""
        nonlocal turno
        padre, similitud, pasos = caminantes[(origen, sentido)]
        destino = next(pasos, None)
        if destino is None:
            return
        _, categoria = destino
        eslabon = padre.eslabones[1 if sentido > 0 else 0]
        if eslabon < P.CATEGORIA_SIM_MIN or categoria.clave in alcanzadas:
            return  # corte entre bloques, o ya la alcanzó otro camino
        turno += 1
        heapq.heappush(cola, (-similitud * eslabon, turno, origen, sentido, padre, categoria))

    for clave in sorted(origenes):
        categoria = origenes[clave]
        caminantes[(clave, 1)] = (categoria, 1.0, mapa.siguientes(categoria.llave))
        caminantes[(clave, -1)] = (categoria, 1.0, mapa.anteriores(categoria.llave))
        adelantar(clave, 1)
        adelantar(clave, -1)

    rutas, reunidos, exploradas = [], 0, 0
    while cola and reunidos < necesarios and exploradas < P.REC_PUENTE_MAX_CATEGORIAS:
        menos, _, origen, sentido, padre, categoria = heapq.heappop(cola)
        if categoria.clave in alcanzadas:
            continue
        alcanzadas.add(categoria.clave)
        exploradas += 1
        libres = [p for p in posiciones(categoria, idioma) if not omitir(p)]
        if libres:
            rutas.append((-menos, origenes[origen], padre, categoria, libres))
            reunidos += len(libres)
        caminantes[(origen, sentido)] = (categoria, -menos, caminantes[(origen, sentido)][2])
        adelantar(origen, sentido)
    return rutas
