import bisect
import random

import pytest

from busqueda import parametros as P
from busqueda.consulta import vector_consulta
from busqueda.indice import construir_indice
from nucleo.arbol_b import ArbolB
from tests.datos_prueba import DOCS
from tests.utiles import RepoFalso


def palabras(n, semilla=7):
    azar = random.Random(semilla)
    return {"".join(azar.choice("abcñ") for _ in range(azar.randint(1, 6))) for _ in range(n)}


@pytest.mark.parametrize("grado", [2, 3, 5, 16])
def test_insertar_mantiene_los_invariantes_y_el_orden(grado):
    claves = list(palabras(600))
    random.Random(1).shuffle(claves)
    arbol = ArbolB(grado)
    for i, c in enumerate(claves):
        arbol.insertar(c, i)
        if i % 50 == 0:
            arbol.verificar()
    arbol.verificar()
    assert len(arbol) == len(claves)
    assert list(arbol) == sorted(claves)
    assert all(arbol[c] == i for i, c in enumerate(claves))
    assert "zzzz" not in arbol and arbol.obtener("zzzz", -1) == -1


def test_clave_repetida_reemplaza_el_valor_sin_crecer():
    arbol = ArbolB(2)
    for c in "abcdefghij":
        arbol.insertar(c, 1)
    arbol.insertar("e", 99)
    assert len(arbol) == 10 and arbol["e"] == 99
    arbol.verificar()


def test_prefijo_equivale_a_bisect_sobre_la_lista_ordenada():
    claves = sorted(palabras(800))
    arbol = ArbolB(3)
    for c in reversed(claves):
        arbol.insertar(c, len(c))
    for p in ["a", "ab", "ñ", "cc", "abc", "zz", "bañ"]:
        esperado = [c for c in claves[bisect.bisect_left(claves, p):] if c.startswith(p)]
        # (el corte por bisect + startswith da el mismo conjunto contiguo)
        assert [c for c, _ in arbol.prefijo(p)] == esperado


def test_la_altura_crece_logaritmicamente():
    arbol = ArbolB(16)
    for i in range(20000):
        arbol.insertar(f"{i:06d}", i)
    arbol.verificar()
    assert arbol.altura <= 4


def test_grado_invalido():
    with pytest.raises(ValueError):
        ArbolB(1)


def test_el_vocabulario_del_indice_es_un_arbol_b_consistente_con_idf():
    indice = construir_indice(RepoFalso([{"id": i, **d} for i, d in enumerate(DOCS, start=1)]).listar())
    indice.vocabulario.verificar()
    assert len(indice.vocabulario) == len(indice.idf)
    assert dict(indice.vocabulario.items()) == indice.idf


def test_vector_consulta_igual_al_de_la_lista_ordenada():
    indice = construir_indice(RepoFalso([{"id": i, **d} for i, d in enumerate(DOCS, start=1)]).listar())
    ordenado = sorted(indice.idf)
    for token in ["p", "po", "pan", "ca", "x"]:
        esperado = {}
        for t in ordenado[bisect.bisect_left(ordenado, token):]:
            if not t.startswith(token):
                break
            esperado[t] = indice.idf[t] * (len(token) / len(t))
        v = vector_consulta([(token, False)], indice.idf, indice.vocabulario)
        assert v.pesos == {t: p for t, p in esperado.items() if p > 0} or (not esperado and not v.pesos)


def _indice_de_prueba():
    return construir_indice(RepoFalso([{"id": i, **d} for i, d in enumerate(DOCS, start=1)]).listar())


def test_los_postings_son_arboles_b_ordenados_por_posicion_y_completos():
    indice = _indice_de_prueba()
    for modo, por_termino in indice.postings.items():
        for termino, posting in por_termino.items():
            assert isinstance(posting, ArbolB)
            posting.verificar()
            posiciones = [p for p, _ in posting.items()]
            assert posiciones == sorted(posiciones)
            assert all(indice.vectores[modo][p][termino] == peso for p, peso in posting.items())
        for posicion, vector in enumerate(indice.vectores[modo]):  # nada se pierde al indexar
            assert all(posicion in por_termino[termino] for termino in vector)


def test_el_resultado_no_depende_del_grado_de_los_postings(monkeypatch):
    from busqueda import Buscador

    docs = [{"id": i, **d} for i, d in enumerate(DOCS, start=1)]
    consultas = ["pan", "polvo", "p", "ca", "caro", "polvo 🐙", "pie 🥧", "ct", "una cosa dulce muy rica"]

    def correr():
        buscador = Buscador(RepoFalso(docs))
        return buscador, [buscador.buscar(q, idioma) for q in consultas for idioma in ("es", "en", "pt")]

    _, esperado = correr()
    monkeypatch.setattr(P, "ARBOL_B_GRADO", 2)  # nodos de a lo sumo 3 claves: postings de varios niveles
    buscador, obtenido = correr()
    assert any(p.altura > 1 for p in buscador.indice.postings["nombre"].values())
    assert obtenido == esperado
