import pytest

from busqueda import Buscador
from senales.reacciones import Reacciones, factor_reaccion
from tests.utiles import DOCS_PAN, RepoFalso

DOCS = [
    {"id": 1, "nombre": "Pan dulce", "categoria": "Comida", "descripcion": "pan", "emoji": "🥐", "idioma": "es"},
    {"id": 2, "nombre": "Pan integral", "categoria": "Comida", "descripcion": "pan", "emoji": "🍞", "idioma": "es"},
    {"id": 3, "nombre": "Pan rustico", "categoria": "Comida", "descripcion": "pan", "emoji": "🥖", "idioma": "es"},
]
T0 = 1_000_000.0


def test_registrar_suma_y_devuelve_conteos():
    r = Reacciones()
    assert r.registrar(1, "me_encanta", T0)["me_encanta"] == 1
    assert r.registrar(1, "me_encanta", T0)["me_encanta"] == 2
    assert r.puntos(1) == 4.0


def test_tipo_invalido():
    with pytest.raises(ValueError):
        Reacciones().registrar(1, "odio", T0)


def test_sin_reacciones_los_pesos_son_uniformes():
    r = Reacciones()
    assert {r.peso(i, T0) for i in (1, 2, 3)} == {1.0}


def test_el_me_encanta_sube_y_el_no_me_gusta_baja():
    r = Reacciones()
    r.registrar(2, "me_encanta", T0)
    r.registrar(3, "no_me_gusta", T0)
    assert r.peso(2, T0) > r.peso(1, T0) > r.peso(3, T0)


def test_sin_datos_el_factor_es_neutro():
    assert factor_reaccion(0, 0) == 1.0


def test_pocas_reacciones_pesan_menos_que_muchas():
    assert factor_reaccion(2, 0) < factor_reaccion(200, 0)
    assert factor_reaccion(0, 200) < factor_reaccion(0, 2)


def test_el_factor_queda_acotado():
    assert 0.5 < factor_reaccion(0, 10**6)
    assert factor_reaccion(10**6, 0) < 1.5


def test_la_proporcion_real_manda_con_mucha_evidencia():
    assert factor_reaccion(900, 100) > factor_reaccion(100, 900)
    assert factor_reaccion(500, 500) == pytest.approx(1.0, abs=1e-6)


def test_la_evidencia_pierde_la_mitad_en_una_vida_media():
    r = Reacciones(vida_media_s=100)
    r.registrar(1, "me_encanta", T0)  # +2.0 de evidencia positiva
    positiva, negativa = r._decaida(1, T0 + 100)
    assert positiva == pytest.approx(1.0)
    assert negativa == 0.0


def test_una_reaccion_vieja_pesa_menos_que_una_reciente():
    r = Reacciones(vida_media_s=100)
    r.registrar(1, "me_encanta", T0)
    r.registrar(2, "me_encanta", T0 + 300)
    ahora = T0 + 300
    assert r.peso(2, ahora) > r.peso(1, ahora) > r.peso(3, ahora)


def test_los_conteos_brutos_no_decaen():
    r = Reacciones(vida_media_s=100)
    r.registrar(1, "me_encanta", T0)
    assert r.conteos(1)["me_encanta"] == 1 and r.puntos(1) == 2.0
    assert r.peso(1, T0 + 10_000) == pytest.approx(1.0, abs=1e-6)  # la evidencia sí se evaporó


def test_sin_vida_media_no_hay_decaimiento():
    r = Reacciones(vida_media_s=0)
    r.registrar(1, "me_gusta", T0)
    assert r._decaida(1, T0 + 10**9) == (1.0, 0.0)


def test_la_reaccion_reordena_el_listado_vacio(senales):
    b = Buscador(RepoFalso(DOCS), senales=senales)
    ultimo = [d["id"] for d in b.buscar("", "es")["resultados"]][-1]
    senales.reaccionar(ultimo, "me_encanta")
    senales.reaccionar(ultimo, "me_encanta")
    assert b.buscar("", "es")["resultados"][0]["id"] == ultimo


def test_la_reaccion_no_altera_la_relevancia_mostrada(senales):
    b = Buscador(RepoFalso(DOCS), senales=senales)
    antes = {d["id"]: d["score"] for d in b.buscar("pan", "es")["resultados"]}
    senales.reaccionar(2, "me_encanta")
    despues = {d["id"]: d["score"] for d in b.buscar("pan", "es")["resultados"]}
    assert antes == despues


def test_los_resultados_traen_los_conteos(senales):
    b = Buscador(RepoFalso(DOCS_PAN), senales=senales)
    senales.reaccionar(1, "me_gusta")
    por_id = {r["id"]: r["reacciones"] for r in b.buscar("pan", "es")["resultados"]}
    assert por_id[1]["me_gusta"] == 1 and por_id[2]["me_gusta"] == 0


def test_sin_senales_funciona_igual():
    assert len(Buscador(RepoFalso(DOCS)).buscar("pan", "es")["resultados"]) == 3
