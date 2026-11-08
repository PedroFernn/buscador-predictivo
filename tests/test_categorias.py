import pytest

from busqueda import Buscador
from busqueda import categorias as C
from busqueda.indice import construir_indice
from nucleo.arbol_b import ArbolB
from tests.utiles import RepoFalso


def doc(i, nombre, categoria, descripcion, idioma="es"):
    return {"id": i, "nombre": nombre, "categoria": categoria, "descripcion": descripcion, "emoji": "📄", "idioma": idioma}


# Frutas ~ Verduras (comestible, dulce) ~ Granos (huerto); Metales no se parece a nada.
DOCS = [
    doc(1, "Manzana", "Frutas", "fruta dulce roja de arbol comestible jugosa"),
    doc(2, "Pera", "Frutas", "fruta dulce verde de arbol comestible jugosa"),
    doc(3, "Mango", "Frutas", "fruta tropical dulce de arbol comestible jugosa"),
    doc(4, "Zanahoria", "Verduras", "verdura naranja de huerto comestible dulce raiz"),
    doc(5, "Lechuga", "Verduras", "verdura verde de hoja de huerto comestible fresca"),
    doc(6, "Betabel", "Verduras", "verdura roja de raiz de huerto comestible dulce"),
    doc(7, "Frijol", "Granos", "grano de huerto seco que se cosecha y se cocina en sopa"),
    doc(8, "Maiz", "Granos", "grano dorado de huerto seco molido para harina"),
    doc(9, "Arroz", "Granos", "grano blanco seco de cultivo inundado para cocinar"),
    doc(10, "Hierro", "Metales", "metal duro brillante extraido de mina"),
    doc(11, "Cobre", "Metales", "metal rojizo brillante conductor de mina"),
    doc(12, "Plomo", "Metales", "metal pesado gris blando de mina"),
    doc(13, "Apple", "Frutas", "sweet red fruit that grows on a tree", "en"),
]
NOMBRES = {d["id"]: d["nombre"] for d in DOCS}


@pytest.fixture(scope="module")
def indice():
    return construir_indice(RepoFalso(DOCS).listar())


@pytest.fixture
def buscador():
    return Buscador(RepoFalso(DOCS))


def categorias_de(resultado):
    return {e["categoria"] for e in resultado["elementos"]}


def test_el_bosque_es_un_arbol_b_de_arboles_b(indice):
    indice.categorias.verificar()
    assert [c for c, _ in indice.categorias.items()] == ["frutas", "granos", "metales", "verduras"]
    for _, categoria in indice.categorias.items():
        assert isinstance(categoria.docs, ArbolB)
        categoria.docs.verificar()


def test_los_documentos_de_un_idioma_son_un_tramo_del_arbol(indice):
    frutas = indice.categorias["frutas"]
    es = C.posiciones(frutas, "es")
    en = C.posiciones(frutas, "en")
    assert [indice.catalogo[p]["nombre"] for p in es] == ["Mango", "Manzana", "Pera"]  # orden del árbol
    assert [indice.catalogo[p]["nombre"] for p in en] == ["Apple"]
    assert C.posiciones(frutas, "pt") == []


def test_las_vecinas_siguen_el_parecido_y_no_incluyen_lo_ajeno(indice):
    vecinas = lambda c: [v for v, _ in indice.categorias[c].vecinas]
    assert vecinas("frutas") == ["verduras"]
    assert set(vecinas("verduras")) == {"frutas", "granos"}
    assert vecinas("metales") == []
    sims = [s for _, s in indice.categorias["verduras"].vecinas]
    assert sims == sorted(sims, reverse=True)


def test_nombradas_por_usa_el_prefijo_del_arbol_de_categorias(indice):
    nombres = lambda t: [c.nombre for c in C.nombradas_por(indice.categorias, t)]
    assert nombres("frutas") == ["Frutas"] and nombres("Frutas") == ["Frutas"]
    assert nombres("fru") == [] and nombres("") == [] and nombres("zzz") == []


def test_terminar_una_categoria_lleva_a_la_rama_mas_cercana_de_otro_arbol(buscador):
    # Valoró toda la categoría Frutas (ids 1-3): ya no queda nada por ver ahí.
    r = buscador.recomendar([("fruta", 1.0)], [(1, 2.0), (2, 2.0), (3, 2.0)], "es", limite=6)
    por_puente = [e for e in r["elementos"] if "puente" in e]
    assert por_puente, "debía continuar por otra rama"
    assert all(e["puente"]["desde"] == "Frutas" for e in por_puente)
    assert {e["puente"]["hacia"] for e in por_puente} <= {"Verduras", "Granos"}
    assert "Metales" not in categorias_de(r) and "Frutas" not in categorias_de(r)
    assert not {1, 2, 3} & {e["id"] for e in r["elementos"]}


def test_el_puente_sigue_de_rama_en_rama_cuando_la_vecina_ya_esta_cubierta(buscador):
    r = buscador.recomendar([("fruta", 1.0)], [(1, 2.0), (2, 2.0), (3, 2.0)], "es", limite=6)
    assert {"Verduras", "Granos"} == categorias_de(r)  # Granos solo se alcanza pasando por Verduras
    granos = next(e for e in r["elementos"] if e["categoria"] == "Granos")
    assert granos["puente"] == {"desde": "Frutas", "hacia": "Granos"}
    # lo directo va primero y lo que llega por puente, después
    marcas = ["puente" in e for e in r["elementos"]]
    assert marcas == sorted(marcas)


def test_buscar_una_categoria_por_su_nombre_y_verla_entera_tambien_la_termina(buscador):
    r = buscador.recomendar([("frutas", 1.0), ("dulce", 1.0)], [(1, 1.0)], "es", limite=6)
    assert any(e.get("puente", {}).get("desde") == "Frutas" for e in r["elementos"])
    assert "Metales" not in categorias_de(r)


def test_sin_categoria_terminada_no_hay_puentes(buscador):
    r = buscador.recomendar([("fruta", 1.0)], [(1, 2.0), (4, 2.0)], "es", limite=6)
    assert r["elementos"] and not any("puente" in e for e in r["elementos"])


def test_si_la_afinidad_directa_llena_la_lista_no_se_usan_puentes(buscador):
    r = buscador.recomendar([("fruta", 1.0)], [(1, 2.0), (2, 2.0), (3, 2.0)], "es", limite=1)
    assert len(r["elementos"]) == 1 and "puente" not in r["elementos"][0]


def test_un_puente_no_ofrece_lo_que_no_gusto():
    docs = [*DOCS]
    buscador = Buscador(RepoFalso(docs))
    # Terminó Frutas y rechazó Zanahoria/Betabel: Verduras ya no debe ser la rama preferida de esas dos
    r = buscador.recomendar([("fruta", 1.0)], [(1, 2.0), (2, 2.0), (3, 2.0), (4, -2.0), (6, -2.0)], "es", limite=6)
    ids = {e["id"] for e in r["elementos"]}
    assert not {4, 6} & ids


def test_el_resultado_es_determinista(buscador):
    args = ([("fruta", 1.0)], [(1, 2.0), (2, 2.0), (3, 2.0)], "es", 6)
    assert buscador.recomendar(*args) == buscador.recomendar(*args)
