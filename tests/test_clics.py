from busqueda import Buscador
from senales.clics import Clics, peso_posicion
from tests.utiles import DOCS_PAN, RepoFalso

# Mismo texto en los tres: sin aprendizaje, el orden es por nombre (A, B, C)
DOCS = [{**d, "idioma": "es"} for d in DOCS_PAN]


def primero(b, consulta):
    return b.buscar(consulta, "es")["resultados"][0]["id"]


def test_sin_datos_no_hay_factores():
    assert Clics().factores("pan", [1, 2, 3]) == {}
    assert Clics().factores("", [1]) == {}


def test_la_consulta_vacia_o_larga_no_se_registra(senales):
    assert not senales.registrar_clic("   ", 1)
    assert not senales.registrar_clic("x" * 500, 1)


def test_el_clic_sube_al_documento_elegido(senales):
    b = Buscador(RepoFalso(DOCS), senales=senales)
    assert primero(b, "pan") == 1
    senales.registrar_clic("pan", 3)
    assert primero(b, "pan") == 3


def test_aprende_por_termino_entre_consultas(senales):
    b = Buscador(RepoFalso(DOCS), senales=senales)
    senales.registrar_clic("pan dulce", 2)
    # "pan" nunca se eligió, pero comparte el término "pan" con "pan dulce"
    assert primero(b, "pan") == 2


def test_el_aprendizaje_no_cambia_la_relevancia_mostrada(senales):
    b = Buscador(RepoFalso(DOCS), senales=senales)
    antes = {d["id"]: d["score"] for d in b.buscar("pan", "es")["resultados"]}
    senales.registrar_clic("pan", 3)
    despues = {d["id"]: d["score"] for d in b.buscar("pan", "es")["resultados"]}
    assert antes == despues


def test_peso_posicion_crece_con_el_lugar_y_esta_acotado():
    assert peso_posicion(None) == peso_posicion(1) == 1.0
    assert peso_posicion(2) < peso_posicion(4) < peso_posicion(8)
    assert peso_posicion(10**6) == 4.0


def test_un_clic_lejos_de_la_cima_vale_mas_que_uno_en_el_primer_lugar():
    c1, c2 = Clics(), Clics()
    c1.clic("pan", 1, posicion=1)
    c2.clic("pan", 1, posicion=8)
    assert c2.factores("pan", [1])[1] > c1.factores("pan", [1])[1] > 1.0


def test_lo_mostrado_y_nunca_elegido_baja_un_poco_pero_acotado():
    c = Clics()
    for _ in range(300):
        c.impresion("pan", 1)
    f = c.factores("pan", [1, 2])
    assert 0.8 < f[1] < 1.0
    assert f[2] == 1.0  # sin datos de ese documento: neutro


def test_el_ctr_distingue_entre_elegido_e_ignorado():
    c = Clics()
    for _ in range(10):
        c.impresion("pan", 1)
        c.impresion("pan", 2)
    for _ in range(4):
        c.clic("pan", 2, posicion=1)
    f = c.factores("pan", [1, 2])
    assert f[2] > 1.0 > f[1]


def test_el_factor_queda_acotado():
    c = Clics()
    for _ in range(10_000):
        c.clic("pan", 1, posicion=8)
    assert c.factores("pan", [1])[1] < 1.4 + 1e-9


def test_memoria_acotada():
    c = Clics(max_claves=20)
    for i in range(300):
        c.clic(f"consulta{i} extra", i % 5 + 1)
    e = c.estadisticas()
    assert e["consultas_con_datos"] <= 20 and e["terminos_con_datos"] <= 20


def test_la_moderacion_evita_guardar_datos_personales(senales):
    assert not senales.registrar_clic("juan@correo.com", 1)
    assert not senales.registrar_impresiones("55 1234 5678", [1, 2])
    assert senales.almacen.conteo_por_tipo() == {}
