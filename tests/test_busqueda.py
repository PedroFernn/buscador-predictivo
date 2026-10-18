import json
from pathlib import Path

import pytest

from busqueda import Buscador
from busqueda import parametros as P
from busqueda.indice import construir_indice
from tests.datos_prueba import CONSULTAS, DOCS
from tests.utiles import DOCS_ENE, DOCS_PAN, RepoFalso


def ids(resultado):
    return [r["id"] for r in resultado["resultados"]]


def test_ene_y_n_no_colisionan_en_la_busqueda():
    b = Buscador(RepoFalso(DOCS_ENE))
    assert ids(b.buscar("caña", "es")) == [1]
    assert ids(b.buscar("cana", "es")) == [2]


def test_el_ranking_coincide_con_el_motor_original_congelado():
    """Regresión del refactor A: 46 consultas (homógrafos, emojis, abreviaturas, ñ, typos...)
    sobre un catálogo sintético, comparadas con la salida del motor anterior a la refactorización."""
    golden = json.loads((Path(__file__).parent / "golden_busqueda.json").read_text(encoding="utf-8"))
    assert [(g["q"], g["idioma"]) for g in golden] == CONSULTAS
    b = Buscador(RepoFalso([{"id": i, **d} for i, d in enumerate(DOCS, start=1)]))
    for g in golden:
        r = b.buscar(g["q"], g["idioma"])
        nuevo = {
            "q": g["q"], "idioma": g["idioma"], "modo": r["modo"], "simplificada": r["consulta_simplificada"],
            "terminos": r["terminos_expandidos"], "total": r["total_coincidencias"],
            "abreviaturas": r["abreviaturas"], "emojis": r["emojis"],
            "resultados": [[x["id"], x["score"], x["homografo"], x["emoji_coincide"]] for x in r["resultados"]],
        }
        assert nuevo == g, f"cambió el resultado de {g['q']!r} ({g['idioma']})"


def test_los_falsos_amigos_se_marcan_y_el_idioma_decide():
    b = Buscador(RepoFalso([{"id": i, **d} for i, d in enumerate(DOCS, start=1)]))
    es, pt = b.buscar("polvo", "es"), b.buscar("polvo", "pt")
    assert ids(es)[0] == 1 and ids(pt)[0] == 2
    assert all(r["homografo"] for r in es["resultados"] if r["nombre"] == "Polvo")


def test_el_indice_acumula_postings_por_modo_y_ids():
    indice = construir_indice(RepoFalso(DOCS_PAN).listar())
    assert indice.ids == frozenset({1, 2, 3})
    assert {p for p, _ in indice.postings["nombre"]["pan"]} == {0, 1, 2}
    assert len(indice.normas["sinopsis"]) == 3
    assert indice.emoji_a_docs["🍞"] == [1]


def test_documentos_sin_nombre_ni_descripcion_se_descartan():
    docs = [*DOCS_PAN, {"id": 9, "nombre": None, "categoria": "X", "descripcion": None, "emoji": None, "idioma": "xx"}]
    b = Buscador(RepoFalso(docs))
    assert b.resumen()[0] == 3
    assert not b.existe(9) and b.existe(2)


def test_resumen_cuenta_por_idioma():
    total, idiomas = Buscador(RepoFalso(DOCS_PAN)).resumen()
    assert total == 3
    assert {i["codigo"]: i["total"] for i in idiomas} == {"es": 2, "en": 1, "pt": 0}


def test_consulta_sin_coincidencias_devuelve_lista_vacia():
    r = Buscador(RepoFalso(DOCS_PAN)).buscar("zzzz", "es")
    assert r["resultados"] == [] and r["total_coincidencias"] == 0


def test_recarga_automatica_reindexa_y_sobrevive_a_un_fallo():
    repo = RepoFalso(DOCS_PAN[:1])
    b = Buscador(repo, recarga_segundos=0.001)
    assert b.resumen()[0] == 1
    repo.docs = DOCS_PAN
    import time
    time.sleep(0.01)
    assert b.resumen()[0] == 3

    def roto():
        raise RuntimeError("base caída")
    repo.listar = roto
    time.sleep(0.01)
    assert b.resumen()[0] == 3  # sigue con el índice anterior


class TestDesglose:
    def armar(self, senales):
        return Buscador(RepoFalso(DOCS_PAN), senales=senales)

    def test_el_desglose_reconstruye_score_y_orden(self, senales):
        b = self.armar(senales)
        senales.reaccionar(2, "me_encanta")
        senales.registrar_clic("pan", 2)
        for r in b.buscar("pan", "es")["resultados"]:
            e = r["explicacion"]
            assert (e["coseno"] + e["emoji"]) * e["factor_idioma"] == pytest.approx(r["score"], abs=1e-3)
            assert e["score"] == pytest.approx(r["score"], abs=1e-4)
            assert e["reacciones"] * e["aprendizaje"] == pytest.approx(r["peso"], abs=1e-3)
            assert e["score"] * r["peso"] == pytest.approx(e["orden"], abs=1e-3)

    def test_el_idioma_y_el_emoji_aparecen_en_el_desglose(self, senales):
        b = self.armar(senales)
        por_id = {r["id"]: r["explicacion"] for r in b.buscar("pan", "es")["resultados"]}
        assert por_id[1]["factor_idioma"] == P.BOOST_IDIOMA_DOMINANTE
        assert por_id[3]["factor_idioma"] == P.FACTOR_IDIOMA_SECUNDARIO
        con_emoji = {r["id"]: r["explicacion"] for r in b.buscar("pan 🍞", "es")["resultados"]}
        assert con_emoji[2]["emoji"] > 0
        assert con_emoji[1]["emoji"] == 0

    def test_sin_consulta_solo_cuentan_las_reacciones(self, senales):
        for r in self.armar(senales).buscar("", "es")["resultados"]:
            assert r["explicacion"]["score"] is None
            assert r["explicacion"]["orden"] == r["peso"]

    def test_sin_senales_el_desglose_es_neutro(self):
        e = Buscador(RepoFalso(DOCS_PAN)).buscar("pan", "es")["resultados"][0]["explicacion"]
        assert (e["reacciones"], e["aprendizaje"]) == (1.0, 1.0)
