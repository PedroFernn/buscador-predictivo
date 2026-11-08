"""Árboles relacionales: llaves NN_categoria, orden por cercanía y recorrido entre bloques."""
import random

import pytest

from busqueda import Buscador
from busqueda import categorias as C
from busqueda import parametros as P
from busqueda.analitica import Analitica
from busqueda.indice import construir_indice
from nucleo.arbol_b import ArbolB
from tests.test_categorias import DOCS
from tests.utiles import RepoFalso


# --- ArbolB.siguientes / anteriores ----------------------------------------------------------
@pytest.mark.parametrize("grado", [2, 3, 16])
def test_siguientes_y_anteriores_siguen_el_orden_del_arbol(grado):
    rng = random.Random(grado)
    claves = rng.sample(range(5000), 500)
    a = ArbolB(grado)
    for k in claves:
        a.insertar(k, -k)
    orden = sorted(claves)
    for k in [-1, 0, orden[10], orden[250], orden[-1], 6000, *rng.sample(range(5000), 40)]:
        assert [c for c, _ in a.siguientes(k)] == [c for c in orden if c > k]
        assert [c for c, _ in a.anteriores(k)] == [c for c in reversed(orden) if c < k]
    assert dict(a.siguientes(orden[0]))[orden[1]] == -orden[1]


def test_siguientes_y_anteriores_son_perezosos():
    a = ArbolB(2)
    for k in range(1000):
        a.insertar(k, k)
    visitados = []
    primeras = []
    for clave, _ in a.anteriores(10**6):
        primeras.append(clave)
        if len(primeras) == 3:
            break
    assert primeras == [999, 998, 997]
    assert list(a.siguientes(999)) == [] and list(a.anteriores(0)) == []
    assert visitados == []


# --- orden por cercania ---------------------------------------------------------------------
VECINAS = {
    "a": (("b", 0.9),), "b": (("a", 0.9), ("c", 0.8)), "c": (("b", 0.8),),
    "d": (("e", 0.7),), "e": (("d", 0.7),), "f": (),
}


def test_las_cadenas_agrupan_lo_parecido_y_van_de_mayor_a_menor():
    orden, sim = C.ordenar_por_cercania(sorted(VECINAS), VECINAS)
    assert orden == ["a", "b", "c", "d", "e", "f"]
    assert sim[("a", "b")] == 0.9


def test_un_nodo_central_solo_enlaza_dos_vecinas():
    vecinas = {"h": (("x", 0.9), ("y", 0.8), ("z", 0.7)), "x": (("h", 0.9),), "y": (("h", 0.8),), "z": (("h", 0.7),)}
    orden, _ = C.ordenar_por_cercania(sorted(vecinas), vecinas)
    i = orden.index("h")
    contiguas = {orden[j] for j in (i - 1, i + 1) if 0 <= j < len(orden)}
    assert contiguas == {"x", "y"}            # las dos más cercanas; z queda fuera del eslabón


def test_el_orden_es_determinista_y_completo():
    claves = [f"c{i:02d}" for i in range(30)]
    rng = random.Random(3)
    vecinas = {c: tuple((o, round(rng.random(), 3)) for o in rng.sample(claves, 4) if o != c) for c in claves}
    a, _ = C.ordenar_por_cercania(claves, vecinas)
    b, _ = C.ordenar_por_cercania(list(reversed(claves)), vecinas)
    assert a == b and sorted(a) == claves


def test_preservacion_cuenta_las_vecinas_mas_cercanas_contiguas():
    vecinas = {"a": (("b", 0.9),), "b": (("c", 0.8),), "c": (("a", 0.5),)}
    assert C.preservacion(["a", "b", "c"], vecinas) == pytest.approx(2 / 3)   # c -> a no es contigua
    assert C.preservacion(["a", "b"], {"a": (), "b": ()}) is None


# --- llaves ---------------------------------------------------------------------------------
def test_la_llave_lleva_prefijo_numerico_con_ceros_y_nombre_con_guiones():
    assert C.llave_relacional(5, 2, "ciencias de la salud") == "05_ciencias_de_la_salud"
    assert C.llave_relacional(5, 3, "salud") == "005_salud"


def test_el_orden_alfabetico_de_las_llaves_es_el_orden_numerico_aunque_pasen_de_cien():
    docs = [{"id": i, "nombre": f"doc{i}", "categoria": f"categoria {i}", "descripcion": f"texto{i} comun",
             "emoji": "📄", "idioma": "es"} for i in range(1, 121)]
    indice = construir_indice(docs)
    llaves = [k for k, _ in indice.mapa.items()]
    assert len(llaves) == 120 and all(k[:3].isdigit() and k[3] == "_" for k in llaves)   # ancho 3
    assert [int(k[:3]) for k in llaves] == list(range(120))


def test_el_mapa_y_el_arbol_por_nombre_guardan_las_mismas_categorias():
    indice = construir_indice(RepoFalso(DOCS).listar())
    indice.mapa.verificar()
    assert [k for k, _ in indice.mapa.items()] == ["00_frutas", "01_verduras", "02_granos", "03_metales"]
    for llave, categoria in indice.mapa.items():
        assert categoria.llave == llave and indice.categorias[categoria.clave] is categoria


def test_los_eslabones_son_simetricos_y_cero_entre_bloques():
    indice = construir_indice(RepoFalso(DOCS).listar())
    cats = [c for _, c in indice.mapa.items()]
    for a, b in zip(cats, cats[1:]):
        assert a.eslabones[1] == b.eslabones[0]
    assert cats[0].eslabones[0] == 0.0 and cats[-1].eslabones[1] == 0.0
    assert cats[-2].eslabones[1] < P.CATEGORIA_SIM_MIN     # entre Granos y Metales: corte


def test_al_acabar_un_bloque_la_llave_que_sigue_es_la_mas_cercana():
    indice = construir_indice(RepoFalso(DOCS).listar())
    frutas = indice.categorias["frutas"]
    siguiente = next(indice.mapa.siguientes(frutas.llave))[1]
    assert siguiente.clave == frutas.vecinas[0][0] == "verduras"
    assert int(siguiente.llave[:2]) == int(frutas.llave[:2]) + 1


# --- recorrido en puentes ---------------------------------------------------------------------
@pytest.fixture
def buscador():
    return Buscador(RepoFalso(DOCS))


def rutas(indice, terminada, necesarios=99):
    """puentes() partiendo de una categoría ya vista entera, sin omitir nada."""
    vistas = {p for _, p in indice.categorias[terminada].docs.items()}
    return C.puentes(indice.categorias, indice.mapa, {terminada}, [], "es", lambda p: p in vistas, lambda p: p in vistas, necesarios)


def test_desde_el_medio_de_la_cadena_el_puente_sale_en_los_dos_sentidos():
    indice = construir_indice(RepoFalso(DOCS).listar())
    llegadas = [(r[3].clave, round(r[0], 4)) for r in rutas(indice, "verduras")]
    assert [c for c, _ in llegadas] == ["frutas", "granos"]        # la llave anterior y la siguiente
    assert llegadas[0][1] > llegadas[1][1]                         # de mejor a peor similitud
    assert {r[2].clave for r in rutas(indice, "verduras")} == {"verduras"}


def test_la_similitud_acumulada_es_el_producto_de_los_eslabones():
    indice = construir_indice(RepoFalso(DOCS).listar())
    por_destino = {r[3].clave: r for r in rutas(indice, "granos")}
    verduras, frutas = por_destino["verduras"], por_destino["frutas"]
    assert verduras[0] == pytest.approx(indice.categorias["granos"].eslabones[0])
    assert frutas[0] == pytest.approx(verduras[0] * indice.categorias["verduras"].eslabones[0])
    assert frutas[2].clave == "verduras"                           # a Frutas se llegó pasando por Verduras


def test_una_categoria_sin_eslabones_no_tiene_a_donde_ir():
    indice = construir_indice(RepoFalso(DOCS).listar())
    assert rutas(indice, "metales") == []


def test_un_corte_entre_bloques_detiene_el_recorrido(buscador):
    # Terminó Granos: siguiente llave es Metales, pero el eslabón no se parece -> no se salta
    r = buscador.recomendar([("grano", 1.0)], [(7, 2.0), (8, 2.0), (9, 2.0)], "es", limite=8)
    assert "Metales" not in {e["categoria"] for e in r["elementos"]}
    assert {e["puente"]["hacia"] for e in r["elementos"] if "puente" in e} <= {"Verduras", "Frutas"}


def test_el_puente_mas_lejano_vale_menos_que_el_cercano(buscador):
    r = buscador.recomendar([("fruta", 1.0)], [(1, 2.0), (2, 2.0), (3, 2.0)], "es", limite=8)
    por_categoria = {}
    for e in r["elementos"]:
        por_categoria.setdefault(e["categoria"], []).append(e["afinidad"])
    assert max(por_categoria["Verduras"]) > max(por_categoria["Granos"])


# --- conserva la vecindad cuando hay temas ------------------------------------------------------
def corpus_por_familias(semilla=11):
    rng = random.Random(semilla)
    familias = {"salud": "medico paciente clinica sintoma terapia hospital dolor receta",
                "cocina": "receta sabor horno ingrediente salsa guiso cocer especia",
                "tecnologia": "software red servidor codigo datos sistema programa nube",
                "deporte": "equipo partido liga entrenar campo torneo jugador gol"}
    todas = sum((v.split() for v in familias.values()), [])
    cats = [(f"{fam} {k}", fam) for fam in familias for k in range(6)]
    rng.shuffle(cats)
    docs, n = [], 0
    for nombre, fam in cats:
        for _ in range(8):
            n += 1
            palabras = rng.sample(familias[fam].split(), 5) + rng.sample(todas, 1)
            docs.append({"id": n, "nombre": f"doc{n}", "categoria": nombre, "descripcion": " ".join(palabras),
                         "emoji": "📄", "idioma": "es"})
    return docs, dict(cats)


def test_el_orden_agrupa_las_familias_y_conserva_la_mayoria_de_vecindades():
    docs, familia = corpus_por_familias()
    indice = construir_indice(docs)
    cats = [c for _, c in indice.mapa.items()]
    familias = [familia[c.nombre] for c in cats]
    assert sum(1 for a, b in zip(familias, familias[1:]) if a != b) == 3        # cuatro bloques, sin mezclarse
    conservada = C.preservacion([c.clave for c in cats], {c.clave: c.vecinas for c in cats})
    assert conservada >= 0.7


# --- datos de la página ------------------------------------------------------------------------
def test_el_mapa_se_expone_a_la_pagina_con_su_preservacion():
    indice = construir_indice(RepoFalso(DOCS).listar())
    mapa = Analitica(indice).arboles()["mapa"]
    assert [f["llave"] for f in mapa["filas"]] == ["00_frutas", "01_verduras", "02_granos", "03_metales"]
    assert mapa["bloques"] == 2 and mapa["categorias"] == 4 and mapa["recortado"] is False
    assert mapa["filas"][0]["enlace"] > mapa["sim_min"] > mapa["filas"][2]["enlace"] or mapa["filas"][2]["enlace"] == 0
    assert 0 <= mapa["preservacion"] <= 1


def test_el_sondeo_de_categoria_trae_su_llave():
    indice = construir_indice(RepoFalso(DOCS).listar())
    cat = Analitica(indice).sondeo("frutas")["categorias"]
    assert [c["llave"] for c in cat] == ["00_frutas"]
