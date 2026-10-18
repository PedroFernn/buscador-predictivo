import csv

import pytest

from busqueda import Buscador
from busqueda import parametros as P
from busqueda.evaluacion import (cargar_oro, constantes, evaluar, exito_en_k, ndcg_en_k,
                                 reciproco_primer_acierto, rejilla)
from tests.datos_prueba import DOCS
from tests.utiles import DOCS_PAN, RepoFalso


def test_cargar_oro(tmp_path):
    ruta = tmp_path / "oro.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["consulta", "idioma", "doc_id", "relevancia"])
        w.writerow(["pan", "es", 2, 3])
        w.writerow(["pan", "es", 1, 1])
    assert cargar_oro(ruta) == {("pan", "es"): {2: 3, 1: 1}}
    with open(ruta, "a", encoding="utf-8") as f:
        f.write("pan,es,xx,3\n")
    with pytest.raises(ValueError):
        cargar_oro(ruta)


def test_metricas():
    assert ndcg_en_k([3, 0], [3, 0]) == pytest.approx(1.0)
    assert ndcg_en_k([0, 3], [3, 0]) < 1.0
    assert reciproco_primer_acierto([0, 0, 2]) == 1 / 3
    assert exito_en_k([0, 0, 0, 3], k=3) == 0.0


def test_evaluar_y_rejilla():
    b = Buscador(RepoFalso(DOCS_PAN))
    # Con el selector en "en", el documento 3 (inglés) debe ir primero; el oro lo exige
    assert evaluar(b, {("pan", "en"): {3: 3}}) == (1.0, 1.0, 1.0)

    espacio = {"BOOST_IDIOMA_DOMINANTE": (1.0,), "FACTOR_IDIOMA_SECUNDARIO": (1.0, 0.35)}
    filas = rejilla(b, {("pan", "es"): {3: 3}}, espacio=espacio)
    # En español, 3 solo sube si el idioma secundario no se penaliza tanto
    assert filas[0][0]["FACTOR_IDIOMA_SECUNDARIO"] == 1.0
    assert filas[0][1][0] >= filas[1][1][0]


def test_las_constantes_se_restauran_incluso_con_error():
    original = P.BOOST_IDIOMA_DOMINANTE
    with constantes({"BOOST_IDIOMA_DOMINANTE": 9.9}):
        assert P.BOOST_IDIOMA_DOMINANTE == 9.9
    assert P.BOOST_IDIOMA_DOMINANTE == original
    with pytest.raises(RuntimeError):
        with constantes({"BOOST_IDIOMA_DOMINANTE": 9.9}):
            raise RuntimeError
    assert P.BOOST_IDIOMA_DOMINANTE == original


def test_conjunto_de_oro_sintetico_se_mantiene_perfecto():
    """Red de seguridad antes de tocar el ranking: casos que deben quedar siempre en el primer lugar."""
    b = Buscador(RepoFalso([{"id": i, **d} for i, d in enumerate(DOCS, start=1)]))
    oro = {
        ("polvo", "es"): {1: 3},      # falso amigo: el idioma decide
        ("polvo", "pt"): {2: 3},
        ("pie", "en"): {8: 3},
        ("pie 🥧", "es"): {8: 3},     # el emoji pesa más que el selector
        ("tuna", "en"): {14: 3},
        ("tristeza", "es"): {32: 3},
        ("cafe", "es"): {39: 3},
        ("jicama", "es"): {43: 3},
    }
    ndcg, mrr, exito = evaluar(b, oro, k=10)
    assert (ndcg, mrr, exito) == (1.0, 1.0, 1.0)
