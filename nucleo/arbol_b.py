"""Árbol B balanceado (Bayer y McCreight, 1972) con claves ordenadas y un valor por clave.

Se usa como vocabulario del índice: `término -> idf`. Su operación clave es `prefijo()`:
saltar al primer término con el prefijo escrito y recorrer en orden solo los que lo
comparten (O(log V + k) para k coincidencias), sin materializar el vocabulario completo.
`rango()` hace lo mismo con cualquier clave ordenable (p. ej. tuplas), y es lo que usan
los árboles por categoría (ver busqueda/categorias.py).

Grado mínimo t (Cormen et al., Introducción a los algoritmos, cap. 18):
    - todo nodo salvo la raíz tiene entre t-1 y 2t-1 claves;
    - un nodo interno con n claves tiene n+1 hijos;
    - todas las hojas están a la misma profundidad (altura O(log_t V)).

El catálogo se reindexa completo en cada carga, así que no hay borrado: solo inserción,
búsqueda y recorrido por rango. Referencias: Manning, Raghavan y Schütze,
Introduction to Information Retrieval (2008), §3.1 (diccionarios con árboles B).
"""
from bisect import bisect_left


class _Nodo:
    __slots__ = ("claves", "valores", "hijos")

    def __init__(self):
        self.claves = []
        self.valores = []
        self.hijos = []  # vacío en las hojas

    @property
    def hoja(self):
        return not self.hijos


class ArbolB:
    def __init__(self, grado=16):
        if grado < 2:
            raise ValueError("el grado mínimo de un árbol B es 2")
        self.t = grado
        self.raiz = _Nodo()
        self._n = 0

    # --- consulta ---------------------------------------------------------
    def __len__(self):
        return self._n

    def obtener(self, clave, defecto=None):
        nodo = self.raiz
        while True:
            i = bisect_left(nodo.claves, clave)
            if i < len(nodo.claves) and nodo.claves[i] == clave:
                return nodo.valores[i]
            if nodo.hoja:
                return defecto
            nodo = nodo.hijos[i]

    def __contains__(self, clave):
        centinela = object()
        return self.obtener(clave, centinela) is not centinela

    def __getitem__(self, clave):
        centinela = object()
        valor = self.obtener(clave, centinela)
        if valor is centinela:
            raise KeyError(clave)
        return valor

    def items(self):
        """(clave, valor) en orden ascendente. Recorrido completo: las hojas (casi todo el árbol)
        se entregan de una sola vez con zip, sin evaluar un criterio de corte por clave."""
        def visitar(nodo):
            if nodo.hoja:
                yield from zip(nodo.claves, nodo.valores)
                return
            for i, hijo in enumerate(nodo.hijos):
                yield from visitar(hijo)
                if i < len(nodo.claves):
                    yield nodo.claves[i], nodo.valores[i]

        return visitar(self.raiz)

    def __iter__(self):
        return (clave for clave, _ in self.items())

    def prefijo(self, texto, visitados=None):
        """(clave, valor) en orden de todas las claves (str) que empiezan con `texto`.

        `visitados` (lista, opcional) recibe cada nodo que se toca: es lo que usa traza()."""
        return self._recorrer(texto, lambda clave: clave.startswith(texto), visitados)

    def rango(self, desde, hasta):
        """(clave, valor) en orden con desde <= clave < hasta (sirve con tuplas)."""
        return self._recorrer(desde, lambda clave: clave < hasta)

    def _recorrer(self, desde, dentro, visitados=None):
        """Recorrido en orden desde la primera clave >= `desde` (None: desde el inicio),
        mientras `dentro(clave)` sea verdadero. Visita solo las ramas que hacen falta."""
        terminado = [False]

        def visitar(nodo):
            if visitados is not None:
                visitados.append(nodo)
            i = 0 if desde is None else bisect_left(nodo.claves, desde)
            while True:
                if not nodo.hoja:
                    yield from visitar(nodo.hijos[i])
                    if terminado[0]:
                        return
                if i == len(nodo.claves):
                    return
                clave = nodo.claves[i]
                if not dentro(clave):
                    terminado[0] = True  # pasamos la última clave del recorrido
                    return
                yield clave, nodo.valores[i]
                i += 1

        yield from visitar(self.raiz)

    @property
    def altura(self):
        nodo, h = self.raiz, 1
        while not nodo.hoja:
            nodo, h = nodo.hijos[0], h + 1
        return h

    # --- estructura (para medir y dibujar el árbol) ------------------------
    def niveles(self):
        """Claves de cada nodo, de izquierda a derecha, un renglón por nivel (raíz primero)."""
        niveles, actual = [], [self.raiz]
        while actual:
            niveles.append([len(nodo.claves) for nodo in actual])
            actual = [hijo for nodo in actual for hijo in nodo.hijos]
        return niveles

    def estadisticas(self):
        """Altura, nodos, hojas, claves y llenado medio (claves / capacidad de los nodos)."""
        niveles = self.niveles()
        nodos = sum(len(nivel) for nivel in niveles)
        return {
            "altura": len(niveles),
            "nodos": nodos,
            "hojas": len(niveles[-1]),
            "claves": self._n,
            "llenado": self._n / (nodos * (2 * self.t - 1)),
        }

    def traza(self, texto):
        """Nodos que toca `prefijo(texto)`, como (nivel, ordinal) con el ordinal contado de
        izquierda a derecha dentro del nivel (el mismo orden de niveles()).

        Devuelve (descenso, barrido): el descenso es el camino de la raíz a la primera hoja
        (O(log V)); el barrido, el resto de nodos que se recorren para entregar las k
        coincidencias. Solo para visualizar: recorre el árbol entero para numerar los nodos."""
        visitados = []
        for _ in self.prefijo(texto, visitados):
            pass
        lugar, actual, nivel = {}, [self.raiz], 0
        while actual:
            for ordinal, nodo in enumerate(actual):
                lugar[id(nodo)] = (nivel, ordinal)
            actual = [hijo for nodo in actual for hijo in nodo.hijos]
            nivel += 1
        # visitados está en orden de visita: el descenso termina en la primera hoja
        corte = next((i + 1 for i, nodo in enumerate(visitados) if nodo.hoja), len(visitados))
        marcados = [lugar[id(nodo)] for nodo in visitados]
        return marcados[:corte], marcados[corte:]

    # --- inserción --------------------------------------------------------
    def insertar(self, clave, valor):
        """Inserta; si la clave ya existe, reemplaza su valor."""
        nodo = self.raiz
        while True:  # actualización in situ: no altera la estructura
            i = bisect_left(nodo.claves, clave)
            if i < len(nodo.claves) and nodo.claves[i] == clave:
                nodo.valores[i] = valor
                return
            if nodo.hoja:
                break
            nodo = nodo.hijos[i]

        if len(self.raiz.claves) == 2 * self.t - 1:
            nueva = _Nodo()
            nueva.hijos.append(self.raiz)
            self._dividir_hijo(nueva, 0)
            self.raiz = nueva
        self._insertar_no_lleno(self.raiz, clave, valor)
        self._n += 1

    def _dividir_hijo(self, padre, i):
        """Parte el hijo lleno `padre.hijos[i]` y sube su clave mediana al padre."""
        t = self.t
        y = padre.hijos[i]
        z = _Nodo()
        mediana_c, mediana_v = y.claves[t - 1], y.valores[t - 1]
        z.claves, z.valores = y.claves[t:], y.valores[t:]
        if y.hijos:
            z.hijos, y.hijos = y.hijos[t:], y.hijos[:t]
        y.claves, y.valores = y.claves[: t - 1], y.valores[: t - 1]
        padre.claves.insert(i, mediana_c)
        padre.valores.insert(i, mediana_v)
        padre.hijos.insert(i + 1, z)

    def _insertar_no_lleno(self, nodo, clave, valor):
        while not nodo.hoja:
            i = bisect_left(nodo.claves, clave)
            if len(nodo.hijos[i].claves) == 2 * self.t - 1:
                self._dividir_hijo(nodo, i)
                if clave > nodo.claves[i]:
                    i += 1
            nodo = nodo.hijos[i]
        i = bisect_left(nodo.claves, clave)
        nodo.claves.insert(i, clave)
        nodo.valores.insert(i, valor)

    # --- verificación -----------------------------------------------------
    def verificar(self):
        """Comprueba los invariantes del árbol B; lanza AssertionError si alguno falla."""
        t = self.t
        profundidades = set()
        total = 0

        def revisar(nodo, minimo, maximo, profundidad, es_raiz):
            nonlocal total
            n = len(nodo.claves)
            assert len(nodo.valores) == n
            assert n <= 2 * t - 1, "nodo desbordado"
            assert es_raiz or n >= t - 1, "nodo con pocas claves"
            assert nodo.claves == sorted(nodo.claves) and len(set(nodo.claves)) == n
            if n:
                assert minimo is None or nodo.claves[0] > minimo
                assert maximo is None or nodo.claves[-1] < maximo
            total += n
            if nodo.hoja:
                profundidades.add(profundidad)
                return
            assert len(nodo.hijos) == n + 1
            limites = [minimo, *nodo.claves, maximo]
            for k, hijo in enumerate(nodo.hijos):
                revisar(hijo, limites[k], limites[k + 1], profundidad + 1, False)

        revisar(self.raiz, None, None, 1, True)
        assert len(profundidades) == 1, "las hojas no están a la misma profundidad"
        assert total == self._n

