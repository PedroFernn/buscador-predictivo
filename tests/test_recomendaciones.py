"""Sugerencias personales: pesos del perfil, motor de recomendación y POST /api/recomendaciones."""
import math

import pytest

from app import create_app
from busqueda import Buscador
from busqueda import parametros as P
from config import Config
from senales import perfil
from senales.reacciones import PUNTOS, VIDA_MEDIA_S
from tests.datos_prueba import DOCS
from tests.utiles import RepoFalso

CATALOGO = [{"id": i, **d} for i, d in enumerate(DOCS, start=1)]
PAN_ES, PASTEL_ES, CAFE_ES = 4, 9, 39   # ids del catálogo sintético


def nombres(resultado):
    return [e["nombre"] for e in resultado["elementos"]]


def ids(resultado):
    return [e["id"] for e in resultado["elementos"]]


@pytest.fixture
def buscador():
    return Buscador(RepoFalso(CATALOGO))


@pytest.fixture
def cliente(senales):
    app = create_app(Config(), repositorio=RepoFalso(CATALOGO), senales=senales)
    return app.test_client()


# --- pesos del perfil (senales/perfil.py) -------------------------------------------------
def test_la_reaccion_pesa_lo_que_dice_reacciones_y_decae_a_la_mitad_por_vida_media():
    assert perfil.peso_reaccion("me_encanta", 0) == PUNTOS["me_encanta"]
    assert perfil.peso_reaccion("no_me_gusta", 0) < 0
    assert perfil.peso_reaccion("me_gusta", VIDA_MEDIA_S) == pytest.approx(PUNTOS["me_gusta"] / 2)
    assert perfil.peso_reaccion("me_gusta", -999) == PUNTOS["me_gusta"]   # "en el futuro" cuenta como ahora


def test_repetir_una_busqueda_pesa_de_forma_sublineal_y_acotada():
    uno, diez, mil = (perfil.peso_consulta(n, 0) for n in (1, 10, 1_000))
    assert uno == perfil.PESO_CONSULTA
    assert diez == pytest.approx(perfil.PESO_CONSULTA * (1 + math.log(10)))
    assert diez < 10 * uno                       # 10 repeticiones no valen 10 veces
    assert perfil.peso_consulta(10**9, 0) == mil  # y hay tope


def test_ponderar_perfil_usa_el_reloj_del_servidor(senales, reloj):
    ahora_ms = reloj.t * 1000
    consultas, reacciones = senales.ponderar_perfil(
        [("pan", 1, reloj.t), ("pastel", 1, None)],
        [(PAN_ES, "me_gusta", reloj.t - VIDA_MEDIA_S), (PASTEL_ES, "no_me_gusta", None)],
    )
    assert consultas[0][1] == consultas[1][1]             # hora None = reciente
    assert reacciones[0][1] == pytest.approx(PUNTOS["me_gusta"] / 2)
    assert reacciones[1][1] == PUNTOS["no_me_gusta"] and ahora_ms > 0


# --- el motor (busqueda/recomendador.py) ----------------------------------------------------
def test_sin_huellas_suficientes_no_se_sugiere_nada(buscador):
    assert buscador.recomendar([], [], "es") == {"elementos": []}
    # una sola huella por debajo del mínimo: aunque sea muy fuerte
    assert buscador.recomendar([], [(PAN_ES, 2.0)], "es") == {"elementos": []}
    assert P.REC_MIN_SENALES == 3
    assert buscador.recomendar([("postre", 1.0)], [(PAN_ES, 1.0)], "es") == {"elementos": []}


def test_con_suficientes_huellas_aparece_lo_que_encaja_con_la_tendencia(buscador):
    r = buscador.recomendar([("postre", 0.5), ("dulce", 0.5)], [(PAN_ES, 1.0)], "es")
    assert "Pastel" in nombres(r)                 # postre horneado dulce: comparte con lo buscado y lo valorado
    for e in r["elementos"]:
        assert e["afinidad"] >= P.REC_AFINIDAD_MIN
        assert {"id", "nombre", "categoria", "emoji", "idioma", "bandera", "descripcion", "motivos"} <= set(e)
    assert [e["afinidad"] for e in r["elementos"]] == sorted((e["afinidad"] for e in r["elementos"]), reverse=True)


def test_nunca_sugiere_lo_ya_valorado_ni_un_duplicado_de_nombre_e_idioma(buscador):
    r = buscador.recomendar([("postre", 0.5), ("dulce", 0.5)], [(PAN_ES, 1.0), (PASTEL_ES, -1.5)], "es")
    assert PAN_ES not in ids(r) and PASTEL_ES not in ids(r)

    docs = CATALOGO + [{"id": 99, "nombre": "Pastel", "categoria": "Otra", "idioma": "es",
                        "descripcion": "postre horneado dulce con crema", "emoji": "🎂"}]
    b = Buscador(RepoFalso(docs))
    r = b.recomendar([("horneado", 0.5), ("dulce", 0.5)], [(PASTEL_ES, 2.0)], "es")
    assert 99 not in ids(r)                        # mismo nombre e idioma que algo que ya valoró


def test_no_sugiere_lo_que_la_persona_ya_busco_por_nombre(buscador):
    r = buscador.recomendar([("pastel", 1.0), ("postre", 0.5)], [(PAN_ES, 1.0)], "es")
    assert "Pastel" not in nombres(r)              # su búsqueda "pastel" ya lo mostró


def test_lo_que_no_gusto_hunde_a_lo_parecido():
    def doc(i, nombre, descripcion):
        return {"id": i, "nombre": nombre, "categoria": "C", "descripcion": descripcion, "emoji": "🍽️", "idioma": "es"}

    docs = [
        doc(1, "Gustado", "crema dulce suave"),
        doc(2, "Hermano del rechazo", "crema amarga espesa"),   # comparte "crema" con lo gustado, "amarga" con lo rechazado
        doc(3, "Rechazado", "amarga espesa densa"),
        doc(4, "Neutro", "crema suave ligera"),
    ]
    b = Buscador(RepoFalso(docs))
    consultas = [("crema", 0.5), ("suave", 0.5)]
    afinidad = lambda r, n: next((e["afinidad"] for e in r["elementos"] if e["nombre"] == n), 0.0)

    base = b.recomendar(consultas, [(1, 1.0), (4, 1.0)], "es")
    con_rechazo = b.recomendar(consultas, [(1, 1.0), (4, 1.0), (3, -1.5)], "es")
    assert afinidad(base, "Hermano del rechazo") > 0           # sin rechazo sí se sugiere
    assert afinidad(con_rechazo, "Hermano del rechazo") < afinidad(base, "Hermano del rechazo")
    assert 3 not in ids(con_rechazo)


def test_solo_rechazos_no_dan_sugerencias(buscador):
    assert buscador.recomendar([], [(PAN_ES, -1.5), (PASTEL_ES, -1.5), (CAFE_ES, -1.5)], "es") == {"elementos": []}


def test_el_prior_de_idioma_ordena_las_sugerencias(buscador):
    consultas, valoradas = [("horneado", 0.5), ("baked", 0.5)], [(PAN_ES, 1.0)]
    es = buscador.recomendar(consultas, valoradas, "es", 12)
    en = buscador.recomendar(consultas, valoradas, "en", 12)
    por_idioma = lambda r: [e["idioma"] for e in r["elementos"]]
    assert por_idioma(es)[0] == "es" and por_idioma(en)[0] == "en"


def test_limite_orden_determinista_y_sin_efectos_en_el_motor(buscador):
    args = ([("postre", 0.5), ("dulce", 0.5), ("fruta", 0.5)], [(PAN_ES, 1.0)], "es")
    a, b = buscador.recomendar(*args, 3), buscador.recomendar(*args, 3)
    assert a == b and len(a["elementos"]) <= 3
    assert len(buscador.recomendar(*args, 99)["elementos"]) <= P.REC_LIMITE_MAX


def test_el_perfil_se_poda_para_no_crecer_con_el_uso(buscador):
    from busqueda.recomendador import construir_perfil
    muchas = [(d["nombre"], 0.5) for d in DOCS]
    positivo, negativo = construir_perfil(buscador.indice, muchas, [(i, 1.0) for i in range(1, 30)])
    assert len(positivo) <= P.REC_MAX_TERMINOS and len(negativo) == 0


def test_los_ids_inexistentes_y_las_consultas_raras_se_ignoran(buscador):
    r = buscador.recomendar([("🦄", 0.5), ("!!!", 0.5), ("postre", 0.5)], [(9999, 2.0), (PAN_ES, 1.0)], "es")
    assert isinstance(r["elementos"], list)


# --- la API ---------------------------------------------------------------------------------
PERFIL = {
    "consultas": [{"q": "postre", "n": 2, "ts": 1_000_000_000}, {"q": "dulce", "n": 1, "ts": 1_000_000_000}],
    "reacciones": [{"id": PAN_ES, "tipo": "me_gusta", "ts": 1_000_000_000}],
    "idioma": "es",
}


def test_la_api_devuelve_sugerencias_y_no_permite_cachearlas(cliente):
    r = cliente.post("/api/recomendaciones", json=PERFIL)
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    assert "Pastel" in nombres(r.get_json())


def test_la_api_esta_vacia_al_inicio_y_con_pocas_huellas(cliente):
    assert cliente.post("/api/recomendaciones", json={}).get_json() == {"elementos": []}
    assert cliente.post("/api/recomendaciones", json={"consultas": PERFIL["consultas"][:1]}).get_json() == {"elementos": []}


def test_la_api_no_guarda_nada_del_perfil(cliente):
    antes = cliente.get("/api/historial/estadisticas").get_json()
    cliente.post("/api/recomendaciones", json=PERFIL)
    despues = cliente.get("/api/historial/estadisticas").get_json()
    assert despues["eventos"] == antes["eventos"] and despues["consultas_vivas"] == antes["consultas_vivas"]


@pytest.mark.parametrize("cuerpo", [
    {"consultas": "pan", "reacciones": 5},
    {"consultas": [1, None, {"q": 3}, {"q": "  "}], "reacciones": [1, {"id": True, "tipo": "me_gusta"}, {"id": 4, "tipo": "odio"}]},
    {"consultas": [{"q": "x" * 5000, "n": "mucho", "ts": "ayer"}], "reacciones": [{"id": "²", "tipo": "me_gusta"}]},
    {"idioma": "xx", "limite": "abc"},
])
def test_la_api_ignora_entradas_malas_sin_romperse(cliente, cuerpo):
    r = cliente.post("/api/recomendaciones", json=cuerpo)
    assert r.status_code == 200 and r.get_json() == {"elementos": []}


def test_la_api_rechaza_lo_que_no_es_un_objeto_json(cliente):
    assert cliente.post("/api/recomendaciones", data="no json").status_code == 400
    assert cliente.post("/api/recomendaciones", json=[1, 2]).status_code == 400


def test_la_api_respeta_idioma_y_limite_y_se_queda_con_la_ultima_reaccion_por_documento(cliente):
    ancho = {**PERFIL, "limite": 2}
    assert len(cliente.post("/api/recomendaciones", json=ancho).get_json()["elementos"]) <= 2
    # idioma inválido cae al por defecto (es), igual que /api/buscar
    r_xx = cliente.post("/api/recomendaciones", json={**PERFIL, "idioma": "xx"}).get_json()
    assert r_xx == cliente.post("/api/recomendaciones", json=PERFIL).get_json()

    # primero 👍 y después 👎 al mismo documento: manda la más reciente (peso negativo)
    reacciones = [{"id": PAN_ES, "tipo": "me_encanta", "ts": 1_000}, {"id": PAN_ES, "tipo": "no_me_gusta", "ts": 2_000}]
    con = cliente.post("/api/recomendaciones", json={**PERFIL, "reacciones": reacciones}).get_json()
    solo_neg = cliente.post("/api/recomendaciones", json={**PERFIL, "reacciones": reacciones[1:]}).get_json()
    assert con == solo_neg
