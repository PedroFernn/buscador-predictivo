"""Datos de la página /analitica: ajustes, estructura de los árboles B, índice invertido y API."""
import math
import random

import pytest

from app import create_app
from busqueda import parametros as P
from busqueda.analitica import Analitica
from busqueda.indice import construir_indice
from config import Config
from nucleo.arbol_b import ArbolB
from nucleo.estadistica import ajuste_potencia, curva_heaps, puntos_log, rango_frecuencia
from senales import Senales
from tests.utiles import DOCS_PAN, RepoFalso, Reloj


def corpus(n=300, vocabulario=900, semilla=3):
    """Catálogo con vocabulario tipo Zipf: pocas palabras muy repetidas y una cola larga."""
    rng = random.Random(semilla)
    palabras = [f"pal{i}" for i in range(vocabulario)]
    pesos = [1 / (r + 1) for r in range(vocabulario)]
    return [
        {"id": i + 1, "nombre": " ".join(rng.choices(palabras, pesos, k=2)),
         "categoria": f"Cat {i % 7}", "descripcion": " ".join(rng.choices(palabras, pesos, k=rng.randint(5, 20))),
         "emoji": "🍞", "idioma": ("es", "en", "pt")[i % 3]}
        for i in range(n)
    ]


@pytest.fixture(scope="module")
def analitica():
    return Analitica(construir_indice(corpus()))


# --- nucleo/estadistica.py -----------------------------------------------------------------
def test_puntos_log_incluyen_los_extremos_y_no_se_repiten():
    assert puntos_log(0) == [] and puntos_log(1) == [1]
    assert puntos_log(5, 120) == [1, 2, 3, 4, 5]
    grande = puntos_log(1_000_000, 100)
    assert grande[0] == 1 and grande[-1] == 1_000_000
    assert grande == sorted(set(grande)) and len(grande) <= 101


def test_ajuste_potencia_recupera_el_exponente_y_la_constante():
    xs = [10, 100, 1000, 10000]
    ajuste = ajuste_potencia(xs, [3 * x ** 0.7 for x in xs])
    assert ajuste["exponente"] == pytest.approx(0.7)
    assert ajuste["constante"] == pytest.approx(3)
    assert ajuste["r2"] == pytest.approx(1)
    assert ajuste_potencia([1, 2], [1, 2]) is None


def test_rango_frecuencia_conserva_primero_y_ultimo():
    frecuencias = sorted((1000 // (r + 1) + 1 for r in range(5000)), reverse=True)
    puntos = rango_frecuencia(frecuencias, 50)
    assert puntos[0] == (1, frecuencias[0]) and puntos[-1] == (5000, frecuencias[-1])
    assert len(puntos) <= 51


def test_curva_heaps_cuenta_elementos_y_distintos():
    curva = curva_heaps([["a", "b"], ["a"], ["c", "a", "d"], []])
    assert curva == [(1, 2, 2), (2, 3, 2), (3, 6, 4)]  # la última no aporta elementos: se omite
    assert curva_heaps([]) == []


# --- nucleo/arbol_b.py: estructura ------------------------------------------------------
def arbol(n=400, grado=3):
    a = ArbolB(grado)
    for i in range(n):
        a.insertar(f"t{i:04d}", i)
    return a


def test_niveles_y_estadisticas_cuadran_con_el_arbol():
    a = arbol()
    niveles = a.niveles()
    e = a.estadisticas()
    assert len(niveles) == a.altura == e["altura"]
    assert sum(sum(nivel) for nivel in niveles) == len(a) == e["claves"]
    assert len(niveles[0]) == 1 and e["hojas"] == len(niveles[-1])
    assert e["nodos"] == sum(len(nivel) for nivel in niveles)
    assert 0 < e["llenado"] <= 1


def test_traza_del_prefijo_baja_por_un_camino_y_barre_hojas_contiguas():
    a = arbol()
    descenso, barrido = a.traza("t012")  # 10 claves de 400
    niveles = a.niveles()
    assert [nivel for nivel, _ in descenso] == list(range(len(niveles)))   # raíz -> hoja, un nodo por nivel
    assert descenso[0] == (0, 0)
    assert all(0 <= o < len(niveles[n]) for n, o in descenso + barrido)
    assert len(descenso) + len(barrido) < sum(len(n) for n in niveles) / 4  # toca una fracción del árbol
    # El barrido de un prefijo que abarca muchas claves toca más nodos que el de una clave suelta
    assert len(a.traza("t0")[1]) > len(a.traza("t0123")[1])


def test_traza_de_un_arbol_de_una_hoja():
    a = ArbolB(8)
    a.insertar("pan", 1)
    assert a.traza("p") == ([(0, 0)], [])


# --- busqueda/analitica.py ------------------------------------------------------------------
def test_indice_invertido_cuadra_con_los_postings(analitica):
    indice = analitica.indice
    for modo in P.CAMPOS_POR_MODO:
        ii = analitica.indice_invertido(modo)
        assert ii["terminos"] == len(indice.postings[modo])
        assert ii["postings"] == sum(len(a) for a in indice.postings[modo].values())
        assert sum(h["terminos"] for h in ii["histograma"]) == ii["terminos"]
        top = [t["df"] for t in ii["top"]]
        assert top == sorted(top, reverse=True) and top[0] == ii["df_max"]


def test_zipf_del_catalogo_tiene_pendiente_cercana_a_uno(analitica):
    z = analitica.zipf()
    assert z["ajuste"] is not None and 0.6 < z["ajuste"]["exponente"] < 1.5
    assert z["puntos"][0][0] == 1 and z["puntos"][0][1] == z["top"][0]["frecuencia"]
    assert z["tokens"] == analitica.corpus()["tokens"]


def test_heaps_del_catalogo_crece_como_potencia_menor_que_uno(analitica):
    h = analitica.heaps()
    assert h["ajuste"] is not None and 0.3 < h["ajuste"]["exponente"] < 1
    ns, vs = zip(*h["puntos"])
    assert list(ns) == sorted(ns) and list(vs) == sorted(vs)
    assert vs[-1] == analitica.corpus()["terminos"]       # al leer todo, el vocabulario completo


def test_arboles_reportan_altura_dentro_de_la_cota(analitica):
    v = analitica.arboles()["vocabulario"]
    assert v["altura"] <= math.ceil(v["cota_altura"])
    assert sum(n["nodos"] for n in v["niveles"]) == v["nodos"]
    assert all(len(n["celdas"]) <= 160 and all(0 <= c <= 1 for c in n["celdas"]) for n in v["niveles"])
    postings = analitica.arboles()["postings"]["nombre"]
    assert sum(x["arboles"] for x in postings["alturas"]) == postings["arboles"]


def test_sondeo_lee_menos_postings_que_el_total(analitica):
    s = analitica.sondeo("pal1")
    assert not s["vacio"] and s["terminos"]
    assert 0 < s["postings_tocados"] < s["postings_totales"]
    v = s["vocabulario"]
    assert v["prefijo"] == "pal1" and v["nodos_tocados"] < v["nodos_total"]
    assert v["expandidos"] == s["terminos_total"] or v["expandidos"] >= 1


def test_sondeo_de_consulta_vacia_o_sin_coincidencias(analitica):
    assert analitica.sondeo("")["vacio"] is True
    assert analitica.sondeo("qqqqqqq")["vacio"] is True


def test_sondeo_reconoce_la_categoria_que_la_consulta_nombra(analitica):
    assert [c["nombre"] for c in analitica.sondeo("cat 3")["categorias"]] == ["Cat 3"]


# --- API --------------------------------------------------------------------------------------
@pytest.fixture
def cliente(senales):
    return create_app(Config(), repositorio=RepoFalso(corpus()), senales=senales).test_client()


def test_la_pagina_y_su_enlace_se_sirven(cliente):
    pagina = cliente.get("/analitica")
    assert pagina.status_code == 200 and b"js/analitica.js" in pagina.data
    assert b'href="/analitica"' in cliente.get("/").data


def test_corpus_entrega_todo_lo_que_pinta_la_pagina(cliente):
    datos = cliente.get("/api/analitica/corpus").get_json()
    for clave in ("documentos", "terminos", "tokens", "grado", "indice_invertido", "zipf", "heaps", "arboles"):
        assert clave in datos
    assert set(datos["indice_invertido"]) == set(P.CAMPOS_POR_MODO)
    assert datos["documentos"] == 300


def test_sondeo_por_api_y_consulta_demasiado_larga(cliente):
    datos = cliente.get("/api/analitica/sondeo?q=pal1").get_json()
    assert datos["consulta"] == "pal1" and datos["vocabulario"]["prefijo"] == "pal1"
    largo = cliente.get("/api/analitica/sondeo?q=" + "a" * 5000).get_json()
    assert len(largo["consulta"]) == 200


def test_uso_sin_consultas_esta_vacio_pero_bien_formado(cliente):
    datos = cliente.get("/api/analitica/uso").get_json()
    assert datos["eventos"] == 0 and datos["zipf"]["puntos"] == [] and datos["zipf"]["ajuste"] is None
    assert datos["heaps"]["consultas"]["puntos"] == []


def test_uso_mide_zipf_y_heaps_sobre_las_consultas_registradas(reloj):
    senales = Senales(reloj=reloj, sync_s=0, min_frecuencia=2)
    try:
        cliente = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales).test_client()
        rng = random.Random(1)
        pesos = [1 / (r + 1) for r in range(60)]
        for _ in range(400):
            reloj.t += 1
            senales.registrar_consulta(f"consulta{rng.choices(range(60), pesos)[0]}")
        datos = cliente.get("/api/analitica/uso").get_json()
        assert datos["eventos"] == 400 and datos["distintas"] <= 60
        assert datos["zipf"]["ajuste"]["exponente"] > 0.3
        assert datos["heaps"]["consultas"]["ajuste"]["beta"] < 1
        # solo se muestran las consultas que alcanzaron el umbral público
        assert all(t["frecuencia"] >= 2 for t in datos["zipf"]["top"])
        assert datos["heaps"]["terminos"]["puntos"][-1][1] <= datos["distintas"]
    finally:
        senales.cerrar()


def test_uso_se_actualiza_al_registrar_una_consulta_nueva(reloj):
    senales = Senales(reloj=reloj, sync_s=0)
    try:
        cliente = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales).test_client()
        assert cliente.get("/api/analitica/uso").get_json()["eventos"] == 0
        senales.registrar_consulta("pan dulce")
        assert cliente.get("/api/analitica/uso").get_json()["eventos"] == 1   # el cache se invalida al escribir
    finally:
        senales.cerrar()
