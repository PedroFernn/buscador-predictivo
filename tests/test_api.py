import pytest

from app import create_app
from config import Config
from senales import Senales
from tests.utiles import DOCS_PAN, RepoFalso


@pytest.fixture
def cliente(senales):
    app = create_app(Config(), repositorio=RepoFalso(DOCS_PAN), senales=senales)
    return app.test_client()


def test_la_pagina_principal_se_sirve(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert b"js/main.js" in r.data


def test_buscar_y_el_idioma_invalido_cae_al_por_defecto(cliente):
    datos = cliente.get("/api/buscar?q=pan&idioma=xx").get_json()
    assert datos["idioma_dominante"] == "es"
    assert [r["id"] for r in datos["resultados"]][0] == 1
    assert cliente.get("/api/buscar?q=pan&idioma=en").get_json()["resultados"][0]["id"] == 3


def test_reaccionar(cliente):
    r = cliente.post("/api/reaccion", json={"id": 2, "tipo": "me_encanta"})
    assert r.status_code == 200
    assert r.get_json()["conteos"]["me_encanta"] == 1 and r.get_json()["puntos"] == 2.0
    assert cliente.post("/api/reaccion", json={"id": "2", "tipo": "me_gusta"}).status_code == 200


@pytest.mark.parametrize("cuerpo, codigo", [
    ({"id": 2, "tipo": "odio"}, 400),
    ({"id": "x", "tipo": "me_gusta"}, 400),
    ({"id": True, "tipo": "me_gusta"}, 400),
    ({"id": "²", "tipo": "me_gusta"}, 400),   # dígito Unicode que no es 0-9
    ({"id": 999, "tipo": "me_gusta"}, 404),    # no existe en el catálogo
    ([1, 2], 400),
])
def test_reaccion_con_entradas_malas(cliente, cuerpo, codigo):
    assert cliente.post("/api/reaccion", json=cuerpo).status_code == codigo


def test_seleccion_reordena_y_valida(cliente):
    assert cliente.get("/api/buscar?q=pan").get_json()["resultados"][0]["id"] == 1
    r = cliente.post("/api/seleccion", json={"q": "pan", "id": 2, "pos": 2})
    assert r.get_json() == {"registrada": True}
    assert cliente.get("/api/buscar?q=pan").get_json()["resultados"][0]["id"] == 2
    assert cliente.post("/api/seleccion", json={"q": "  ", "id": 2}).get_json() == {"registrada": False}
    assert cliente.post("/api/seleccion", json={"q": "pan", "id": "x"}).status_code == 400
    assert cliente.post("/api/seleccion", json={"q": "pan", "id": 999}).status_code == 404
    assert cliente.post("/api/seleccion", data="no json").status_code == 400
    # una posición fuera de rango se ignora (cuenta como sin posición) pero el clic se registra
    assert cliente.post("/api/seleccion", json={"q": "pan", "id": 2, "pos": 9999}).get_json()["registrada"]


def test_registrar_consulta_y_sugerir(cliente):
    for _ in range(3):
        assert cliente.post("/api/consultas", json={"q": "Mole poblano"}).status_code == 200
    r = cliente.get("/api/sugerencias?q=mol&limite=5")
    assert r.get_json()["sugerencias"][0] == {"consulta": "Mole poblano", "frecuencia": 3}
    assert "max-age" in r.headers["Cache-Control"]


def test_las_consultas_guardan_solo_impresiones_de_ids_reales(cliente):
    r = cliente.post("/api/consultas", json={"q": "pan", "mostrados": [3, 1, 999, "x", 1, 2]})
    assert r.get_json() == {"registrada": True}
    eventos = cliente.get("/api/historial/estadisticas").get_json()["eventos"]
    assert eventos["impresion"] == 3  # 3, 1, 2: sin el inexistente, el inválido ni el repetido


def test_entradas_malas_de_consultas_y_sugerencias(cliente):
    assert cliente.post("/api/consultas", data="no json").status_code == 200
    assert cliente.post("/api/consultas", json={"q": 123}).status_code == 200
    assert cliente.get("/api/sugerencias?q=x&limite=abc").status_code == 200
    assert not cliente.post("/api/consultas", json={"q": "x" * 5000}).get_json()["registrada"]


def test_estadisticas(cliente):
    datos = cliente.get("/api/historial/estadisticas").get_json()
    for clave in ("consultas_vivas", "ventana_segundos", "eventos", "aprendizaje", "zipf"):
        assert clave in datos


def test_el_catalogo_nuevo_se_ve_tras_recargar_sin_perder_senales(senales):
    repo = RepoFalso(DOCS_PAN[:2])
    app = create_app(Config(), repositorio=repo, senales=senales)
    c = app.test_client()
    assert c.post("/api/reaccion", json={"id": 3, "tipo": "me_gusta"}).status_code == 404
    repo.docs = DOCS_PAN
    app.extensions["buscador"].recargar()
    assert c.post("/api/reaccion", json={"id": 3, "tipo": "me_gusta"}).status_code == 200


def test_config_desde_entorno(monkeypatch):
    monkeypatch.setenv("HISTORIAL_VENTANA_DIAS", "3")
    monkeypatch.setenv("HISTORIAL_MIN_FRECUENCIA", "abc")  # inválido: cae al valor por defecto
    monkeypatch.setenv("HISTORIAL_BLOQUEADOS", "uno, dos,,")
    monkeypatch.setenv("SENALES_DB", ":memory:")
    c = Config.desde_entorno()
    assert (c.ventana_dias, c.min_frecuencia, c.senales_db) == (3, 3, ":memory:")
    assert c.bloqueados == ("uno", " dos")
