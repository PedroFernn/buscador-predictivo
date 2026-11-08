"""Datos de las figuras añadidas en /analitica: cache por prefijo, retención, árbol con claves."""
import random

import pytest

from app import create_app
from config import Config
from nucleo.arbol_b import ArbolB
from senales import Senales
from senales.retencion import medir
from tests.utiles import DOCS_PAN, RepoFalso, Reloj


@pytest.fixture
def reloj():
    return Reloj()


def senales_con(reloj, **kw):
    return Senales(reloj=reloj, sync_s=0, **kw)


# --- cache de prefijos -----------------------------------------------------------------------
def test_los_aciertos_cuentan_solo_lo_servido_desde_el_cache(reloj):
    s = senales_con(reloj)
    try:
        for _ in range(3):
            reloj.t += 1
            s.registrar_consulta("pan dulce")
        s.historial.vaciar_cache()
        s.sugerir("pan", 8)                      # tabla: no es acierto
        s.sugerir("pan", 8)                      # cache: acierto
        s.sugerir("pan", 8)                      # cache: acierto
        datos = s.aciertos_cache()
        assert datos["peticiones"] == 3 and datos["aciertos"] == 2
        assert datos["tasa"] == pytest.approx(2 / 3, abs=1e-4)
        assert datos["puntos"][0]["prefijo"] == "pan" and datos["puntos"][0]["rango"] == 1
    finally:
        s.cerrar()


def test_la_tasa_sin_peticiones_es_nula(reloj):
    s = senales_con(reloj)
    try:
        datos = s.aciertos_cache()
        assert datos["tasa"] is None and datos["puntos"] == []
    finally:
        s.cerrar()


def test_el_cache_por_prefijo_se_acota(reloj, monkeypatch):
    import senales.consultas as consultas
    monkeypatch.setattr(consultas, "STATS_PREFIJOS_MAX", 20)
    s = senales_con(reloj)
    try:
        for i in range(60):
            s.sugerir(f"p{i}", 8)
        s.sugerir("popular", 8)
        assert len(s.historial._peticiones) <= 20
        assert "popular" in s.historial._peticiones
    finally:
        s.cerrar()


# --- árbol con claves ----------------------------------------------------------------------------
def test_estructura_guarda_claves_y_enlaces_coherentes():
    a = ArbolB(2)
    for i in range(22):
        a.insertar(f"t{i:02d}", i)
    niveles = a.estructura()
    assert len(niveles) == a.altura
    assert sum(len(n["claves"]) for nivel in niveles for n in nivel) == len(a)
    for i, nivel in enumerate(niveles[:-1]):
        for nodo in nivel:
            assert all(0 <= c < len(niveles[i + 1]) for c in nodo["hijos"])
            assert len(nodo["hijos"]) == len(nodo["claves"]) + 1
    hojas = niveles[-1]
    assert all(n["hijos"] == [] for n in hojas)
    claves_en_orden = [c for nivel in niveles[-1:] for n in nivel for c in n["claves"]]
    assert claves_en_orden == sorted(claves_en_orden)


def test_la_demostracion_devuelve_un_arbol_pequeno_con_traza(reloj):
    cliente = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales_con(reloj)).test_client()
    datos = cliente.get("/api/analitica/arbol-demo?grado=2&n=22&q=pan").get_json()
    assert datos["grado"] == 2 and 1 <= datos["claves"] <= 22  # el catálogo de prueba es pequeño
    assert datos["niveles"][0][0]["claves"]               # la raíz tiene claves a la vista
    assert datos["prefijo"] == "pan"
    assert datos["traza"]["descenso"][0] == [0, 0]
    sin = cliente.get("/api/analitica/arbol-demo?grado=9&n=999").get_json()
    assert sin["grado"] == 3 and sin["claves"] <= 40 and sin["traza"] is None  # grado acotado a 2..3


def test_la_demostracion_con_grado_tres_tambien_funciona(reloj):
    cliente = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales_con(reloj)).test_client()
    datos = cliente.get("/api/analitica/arbol-demo?grado=3&n=30").get_json()
    assert datos["grado"] == 3
    assert all(len(n["claves"]) <= 5 for nivel in datos["niveles"] for n in nivel)


# --- retención ------------------------------------------------------------------------------------
def test_la_retencion_aplana_la_tabla_y_no_el_vocabulario():
    r = medir(12_000, ventana=3_000)
    ultimo = r["puntos"][-1]
    assert ultimo["n"] == 12_000
    assert ultimo["filas"] <= 3_000 + 10_000            # la purga corre cada 10k eventos
    assert ultimo["consultas"] > ultimo["filas"] / 4    # sin política crecen con cada evento nuevo
    consultas = [p["consultas"] for p in r["puntos"]]
    assert consultas == sorted(consultas)


def test_el_endpoint_de_retencion_acota_y_reutiliza(reloj):
    cliente = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales_con(reloj)).test_client()
    a = cliente.get("/api/analitica/retencion?eventos=1500").get_json()
    b = cliente.get("/api/analitica/retencion?eventos=1500").get_json()
    assert a["eventos"] == 1500 and a == b
    assert cliente.get("/api/analitica/retencion?eventos=zz").get_json()["eventos"] == 60000


def test_el_endpoint_de_cache_responde_sin_peticiones(reloj):
    cliente = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales_con(reloj)).test_client()
    datos = cliente.get("/api/analitica/cache").get_json()
    assert datos["peticiones"] == 0 and datos["tasa"] is None
