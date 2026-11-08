"""Lo que el motor hace por dentro, convertido en datos para graficar.

Índice invertido, ley de Zipf, ley de Heaps y árboles B, medidos sobre un `Indice` ya construido.
Funciones puras: no tocan Flask ni las señales (el Zipf/Heaps del tráfico real de consultas sale de
senales/consultas.py, `HistorialConsultas.uso()`).

El `Indice` es inmutable (al recargar el catálogo se construye otro), así que todo lo que no depende
de la consulta se calcula una vez por `Analitica`. Lo único que cambia por petición es `sondeo()`:
qué términos, postings y nodos del árbol toca una consulta concreta.
"""
import math
import random
from collections import Counter

from busqueda import categorias as C
from busqueda import parametros as P
from busqueda import ranking
from busqueda.consulta import analizar
from nucleo.arbol_b import ArbolB
from nucleo.estadistica import ajuste_potencia, curva_heaps, rango_frecuencia
from nucleo.lexico import tokenizar_contenido

MAPA_MAX_FILAS = 40      # categorías que se listan en el mapa relacional
MAX_CELDAS = 160       # un nivel del árbol se dibuja con a lo más este número de celdas
ZIPF_MAX_RANGOS = 1000  # el ajuste de Zipf usa los primeros rangos (igual que nucleo.estadistica.ajuste_zipf)
HEAPS_N_MIN = 10        # el arranque de la curva de Heaps (pocos tokens) no se ajusta si hay de sobra
SONDEO_MAX_TERMINOS = 40
SEMILLA_HEAPS = 0       # orden fijo de lectura de los documentos: la curva sale igual en cada carga


def _redondear(valor, cifras=3):
    return None if valor is None else round(valor, cifras)


def _ley(ajuste, signo=1):
    """Un ajuste de ajuste_potencia() en forma serializable (exponente con el signo pedido)."""
    if ajuste is None:
        return None
    return {
        "exponente": _redondear(signo * ajuste["exponente"]),
        "constante": _redondear(ajuste["constante"]),
        "r2": _redondear(ajuste["r2"]),
        "puntos": ajuste["puntos"],
    }


def _celdas(claves_por_nodo, capacidad, max_celdas=MAX_CELDAS):
    """Llenado (0-1) de cada celda de un nivel. Con más nodos que celdas, el nodo de ordinal `o`
    cae en la celda `o * m // n` y la celda guarda el llenado medio de sus nodos."""
    n = len(claves_por_nodo)
    if n <= max_celdas:
        return [round(c / capacidad, 3) for c in claves_por_nodo]
    sumas, cuentas = [0] * max_celdas, [0] * max_celdas
    for ordinal, claves in enumerate(claves_por_nodo):
        celda = ordinal * max_celdas // n
        sumas[celda] += claves
        cuentas[celda] += 1
    return [round(s / (c * capacidad), 3) if c else 0.0 for s, c in zip(sumas, cuentas)]


def _histograma_log2(valores):
    """Cuántos valores caen en [1], [2-3], [4-7], [8-15]... (cubos de potencias de 2)."""
    cubos = Counter(int(math.log2(v)) for v in valores if v >= 1)
    if not cubos:
        return []
    return [
        {"desde": 2 ** k, "hasta": 2 ** (k + 1) - 1, "terminos": cubos.get(k, 0)}
        for k in range(max(cubos) + 1)
    ]


class Analitica:
    def __init__(self, indice):
        self.indice = indice
        campos = [campo for campo, _ in P.CAMPOS]
        # Mismos tokens que el índice (nombre, categoría y descripción)
        self._tokens = [[t for campo in campos for t in tokenizar_contenido(doc[campo])] for doc in indice.catalogo]
        self.frecuencias = Counter(t for tokens in self._tokens for t in tokens)
        self._ranking = sorted(self.frecuencias.items(), key=lambda par: (-par[1], par[0]))
        self.rango = {termino: i for i, (termino, _) in enumerate(self._ranking, 1)}

    # --- todo lo que depende solo del catálogo ----------------------------------
    def corpus(self):
        vocabulario = self.indice.vocabulario
        return {
            "documentos": len(self.indice.catalogo),
            "terminos": len(self.frecuencias),
            "tokens": sum(self.frecuencias.values()),
            "grado": P.ARBOL_B_GRADO,
            "indice_invertido": {modo: self.indice_invertido(modo) for modo in P.CAMPOS_POR_MODO},
            "zipf": self.zipf(),
            "heaps": self.heaps(),
            "arboles": self.arboles(),
            "vocabulario_terminos": len(vocabulario),
        }

    def indice_invertido(self, modo, top=15):
        """Listas de postings de un modo: cuántos documentos tiene cada término (su df)."""
        postings = self.indice.postings[modo]
        largos = {termino: len(arbol) for termino, arbol in postings.items()}
        valores = sorted(largos.values())
        total = sum(valores)
        mayores = sorted(largos.items(), key=lambda par: (-par[1], par[0]))[:top]
        return {
            "modo": modo,
            "terminos": len(largos),
            "postings": total,
            "df_medio": round(total / len(largos), 2) if largos else 0,
            "df_mediana": valores[len(valores) // 2] if valores else 0,
            "df_max": valores[-1] if valores else 0,
            "en_un_documento": sum(1 for v in valores if v == 1),
            "top": [
                {"termino": t, "df": n, "idf": round(self.indice.idf[t], 3), "rango": self.rango.get(t)}
                for t, n in mayores
            ],
            "histograma": _histograma_log2(valores),
        }

    def zipf(self):
        """Frecuencia de cada término contra su rango: f(r) ≈ C / r^s."""
        frecuencias = [f for _, f in self._ranking]
        m = min(len(frecuencias), ZIPF_MAX_RANGOS)
        ajuste = ajuste_potencia(range(1, m + 1), frecuencias[:m]) if m >= 10 else None
        return {
            "terminos": len(frecuencias),
            "tokens": sum(frecuencias),
            "puntos": [list(par) for par in rango_frecuencia(frecuencias)],
            "ajuste": _ley(ajuste, signo=-1),  # exponente = s
            "ajuste_hasta_rango": m,
            "top": [{"termino": t, "frecuencia": f} for t, f in self._ranking[:12]],
        }

    def heaps(self):
        """Términos distintos contra tokens leídos: V(n) ≈ K · n^β (documentos en orden fijo y mezclado)."""
        orden = list(range(len(self._tokens)))
        random.Random(SEMILLA_HEAPS).shuffle(orden)
        curva = curva_heaps([self._tokens[i] for i in orden])
        puntos = [(leidos, distintos) for _, leidos, distintos in curva]
        ajustables = [(n, v) for n, v in puntos if n >= HEAPS_N_MIN]
        base = ajustables if len(ajustables) >= 3 else puntos
        ajuste = ajuste_potencia(*zip(*base)) if len(base) >= 3 else None
        return {
            "puntos": [list(par) for par in puntos],
            "documentos": [i for i, _, _ in curva],
            "ajuste": _ley(ajuste),  # exponente = β, constante = K
            "orden": f"documentos mezclados con semilla {SEMILLA_HEAPS}",
        }

    def arboles(self):
        t = P.ARBOL_B_GRADO
        capacidad = 2 * t - 1
        vocabulario = self.indice.vocabulario
        niveles = vocabulario.niveles()
        estadisticas = vocabulario.estadisticas()
        n = estadisticas["claves"]
        return {
            "grado": t,
            "vocabulario": {
                **{k: _redondear(v) for k, v in estadisticas.items()},
                # Cormen et al., cap. 18: h ≤ 1 + log_t((n + 1) / 2)
                "cota_altura": _redondear(1 + math.log((n + 1) / 2, t), 2) if n else 0,
                "niveles": [
                    {"nodos": len(nivel), "claves": sum(nivel), "celdas": _celdas(nivel, capacidad)}
                    for nivel in niveles
                ],
            },
            "postings": {modo: self._bosque_de_postings(modo) for modo in P.CAMPOS_POR_MODO},
            "categorias": self._bosque_de_categorias(),
            "mapa": self._mapa_relacional(),
        }

    def _bosque_de_postings(self, modo):
        """Un árbol B por término: cuántos hay de cada altura y cuántos son una sola hoja (≈ una lista)."""
        alturas, nodos, claves = Counter(), 0, 0
        for arbol in self.indice.postings[modo].values():
            e = arbol.estadisticas()
            alturas[e["altura"]] += 1
            nodos += e["nodos"]
            claves += e["claves"]
        arboles = sum(alturas.values())
        return {
            "arboles": arboles,
            "nodos": nodos,
            "claves": claves,
            "alturas": [{"altura": h, "arboles": alturas[h]} for h in sorted(alturas)],
            "una_hoja": alturas.get(1, 0),
        }

    def _mapa_relacional(self):
        """Las categorías en el orden de sus llaves NN_categoria y cuánto se parece cada una a la que sigue."""
        mapa = self.indice.mapa
        categorias = [c for _, c in mapa.items()]
        filas = [
            {"llave": c.llave, "nombre": c.nombre, "documentos": len(c.docs), "enlace": round(c.eslabones[1], 3)}
            for c in categorias
        ]
        cortes = sum(1 for c in categorias[:-1] if c.eslabones[1] < P.CATEGORIA_SIM_MIN)
        conservada = C.preservacion([c.clave for c in categorias], {c.clave: c.vecinas for c in categorias})
        return {
            "categorias": len(filas),
            "bloques": (cortes + 1) if filas else 0,
            "preservacion": _redondear(conservada),
            "sim_min": P.CATEGORIA_SIM_MIN,
            "filas": filas[:MAPA_MAX_FILAS],
            "recortado": len(filas) > MAPA_MAX_FILAS,
        }

    def _bosque_de_categorias(self):
        """El árbol de categorías y, dentro de cada una, su propio árbol de documentos."""
        arbol = self.indice.categorias
        filas = [(c.nombre, len(c.docs), c.docs.altura) for _, c in arbol.items()]
        filas.sort(key=lambda f: (-f[1], f[0]))
        return {
            "categorias": len(arbol),
            "altura": arbol.altura,
            "documentos": sum(f[1] for f in filas),
            "top": [{"nombre": nombre, "documentos": n, "altura": h} for nombre, n, h in filas[:12]],
            "alturas": sorted({f[2] for f in filas}),
        }

    def arbol_demo(self, grado=2, n=22, consulta=""):
        """Un árbol B pequeño con sus claves visibles. Toma n términos repartidos en el alfabeto entre
        los más frecuentes (así son palabras reconocibles) y, si la consulta tiene un prefijo, su recorrido."""
        candidatos = sorted(t for t, _ in self._ranking[: max(60, 3 * n)])
        if len(candidatos) > n:
            paso = len(candidatos) / n
            muestra = sorted({candidatos[int(i * paso)] for i in range(n)})
        else:
            muestra = candidatos
        arbol = ArbolB(grado)
        for termino in muestra:
            arbol.insertar(termino, self.indice.idf.get(termino, 0.0))
        tokens = tokenizar_contenido(consulta) if consulta else []
        prefijo = tokens[-1] if tokens else None
        traza = None
        if prefijo:
            descenso, barrido = arbol.traza(prefijo)
            traza = {"descenso": [list(x) for x in descenso], "barrido": [list(x) for x in barrido]}
        return {
            "grado": grado,
            "claves": len(muestra),
            "altura": arbol.altura,
            "niveles": arbol.estructura(),
            "prefijo": prefijo,
            "traza": traza,
        }

    # --- lo que toca una consulta concreta ----------------------------------------
    def sondeo(self, consulta):
        """Qué pasa por dentro al buscar `consulta`: términos a los que se expande, postings que se
        recorren y nodos del árbol del vocabulario que se visitan."""
        indice = self.indice
        analisis = analizar(consulta, indice)
        base = {"consulta": consulta, "modo": analisis.modo, "vacio": analisis.vacio}
        if analisis.vacio:
            return {**base, "terminos": [], "terminos_total": 0, "postings_tocados": 0,
                    "postings_totales": 0, "candidatos": 0, "vocabulario": None, "categorias": []}

        postings = indice.postings[analisis.modo]
        terminos = []
        for termino, peso in analisis.vector.pesos.items():
            posting = postings.get(termino)
            terminos.append({
                "termino": termino,
                "peso": round(peso, 3),
                "df": len(posting) if posting else 0,
                "altura": posting.altura if posting else 0,
                "rango": self.rango.get(termino),
                "frecuencia": self.frecuencias.get(termino, 0),
            })
        terminos.sort(key=lambda fila: (-fila["df"], fila["termino"]))
        productos = ranking.acumular_productos(analisis.vector, postings)

        return {
            **base,
            "terminos": terminos[:SONDEO_MAX_TERMINOS],
            "terminos_total": len(terminos),
            "postings_tocados": sum(fila["df"] for fila in terminos),
            "postings_totales": sum(len(a) for a in postings.values()),
            "candidatos": len(productos),
            "vocabulario": self._sondeo_vocabulario(analisis),
            "categorias": [
                {"nombre": c.nombre, "documentos": len(c.docs), "altura": c.docs.altura, "llave": c.llave}
                for c in C.nombradas_por(indice.categorias, consulta)
            ],
        }

    def _sondeo_vocabulario(self, analisis):
        """El prefijo que se está escribiendo (el último término no exacto) y su recorrido en el árbol."""
        terminos = analisis.interpretacion.terminos if analisis.interpretacion else []
        prefijos = [t for t, exacto in terminos if not exacto]
        if not prefijos:
            return None
        prefijo = prefijos[-1]
        vocabulario = self.indice.vocabulario
        descenso, barrido = vocabulario.traza(prefijo)
        return {
            "prefijo": prefijo,
            "expandidos": sum(1 for _ in vocabulario.prefijo(prefijo)),
            "descenso": [list(par) for par in descenso],
            "barrido": [list(par) for par in barrido],
            "nodos_tocados": len(descenso) + len(barrido),
            "nodos_total": vocabulario.estadisticas()["nodos"],
            "terminos_total": len(vocabulario),
        }



