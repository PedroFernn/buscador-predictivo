"""Reiniciar señales y generar datos de prueba (api/admin.py, senales/poblar.py)."""
import pytest

from app import create_app
from busqueda.buscador import Buscador
from config import Config
from senales import poblar
from tests.utiles import RepoFalso

TOKEN = "secreto-largo"
CABECERA = {"X-Admin-Token": TOKEN}

DOCS = [
    {"id": i, "nombre": nombre, "categoria": categoria, "descripcion": descripcion, "emoji": "🍽️", "idioma": idioma}
    for i, (nombre, categoria, descripcion, idioma) in enumerate([
        ("Pan dulce", "Panadería", "pan suave con azúcar", "es"),
        ("Pan de muerto", "Panadería", "pan tradicional con azahar", "es"),
        ("Tamal verde", "Antojito", "masa de maíz con salsa verde", "es"),
        ("Tamal oaxaqueño", "Antojito", "masa envuelta en hoja de plátano", "es"),
        ("Sourdough bread", "Bakery", "crusty bread with a long ferment", "en"),
        ("Banana pancake", "Breakfast", "fluffy pancake with banana", "en"),
        ("Pão de queijo", "Padaria", "pãozinho de queijo mineiro", "pt"),
        ("Brigadeiro", "Doce", "doce de chocolate brasileiro", "pt"),
    ], start=1)
]


@pytest.fixture
def app(senales):
    return create_app(Config(admin_token=TOKEN), repositorio=RepoFalso(DOCS), senales=senales)


@pytest.fixture
def cliente(app):
    return app.test_client()


def _post(cliente, ruta, cuerpo, cabecera=CABECERA):
    return cliente.post(ruta, json=cuerpo, headers=cabecera)


# --- acceso --------------------------------------------------------------------------------------

def test_sin_token_configurado_todo_queda_apagado(senales):
    cliente = create_app(Config(), repositorio=RepoFalso(DOCS), senales=senales).test_client()
    assert cliente.get("/api/admin/estado", headers=CABECERA).status_code == 403
    assert cliente.post("/api/admin/reiniciar", json={}, headers=CABECERA).status_code == 403
    pagina = cliente.get("/").data
    assert b"herramientas" not in pagina and b"admin.js" not in pagina
    assert b"rapido-limpiar" not in pagina and b"rapido-aleatorio" not in pagina


def test_con_token_configurado_la_pagina_trae_el_panel(cliente):
    pagina = cliente.get("/").data
    assert b'id="herramientas"' in pagina and b"js/admin.js" in pagina and b"admin.css" in pagina
    assert b'id="rapido-limpiar"' in pagina and b'id="rapido-aleatorio"' in pagina and b'id="rapido-estado"' in pagina


@pytest.mark.parametrize("cabecera", [{}, {"X-Admin-Token": "otro"}, {"X-Admin-Token": ""}])
def test_token_ausente_o_incorrecto(cliente, cabecera):
    assert cliente.get("/api/admin/estado", headers=cabecera).status_code == 401
    assert _post(cliente, "/api/admin/reiniciar", {"alcance": "todo"}, cabecera).status_code == 401
    assert _post(cliente, "/api/admin/simular", {}, cabecera).status_code == 401


# --- reiniciar -----------------------------------------------------------------------------------

def _usar(cliente, doc=2):
    """Una reacción, un clic y una consulta (con sugerencia ya resuelta y en caché)."""
    assert cliente.post("/api/reaccion", json={"id": doc, "tipo": "me_encanta"}).status_code == 200
    assert cliente.post("/api/seleccion", json={"q": "pan", "id": doc, "pos": 2}).status_code == 200
    assert cliente.post("/api/consultas", json={"q": "pan dulce", "mostrados": [1, 2]}).status_code == 200
    assert cliente.get("/api/sugerencias?q=pan").get_json()["sugerencias"]


def test_reiniciar_solo_lo_pedido(cliente, senales):
    _usar(cliente)
    r = _post(cliente, "/api/admin/reiniciar", {"alcance": ["reacciones"]})
    assert r.status_code == 200
    assert r.get_json()["borrados"] == {"reacciones": 1}
    assert senales.conteos(2)["me_encanta"] == 0
    eventos = cliente.get("/api/admin/estado", headers=CABECERA).get_json()["eventos"]
    assert "me_encanta" not in eventos and eventos["clic"] == 1 and eventos["consulta"] >= 1


def test_reiniciar_consultas_vacia_tambien_las_sugerencias_en_cache(cliente):
    _usar(cliente)
    _post(cliente, "/api/admin/reiniciar", {"alcance": ["consultas"]})
    assert cliente.get("/api/sugerencias?q=pan").get_json()["sugerencias"] == []


def test_limpieza_total_deja_el_buscador_como_nuevo(cliente, senales):
    orden_inicial = [r["id"] for r in cliente.get("/api/buscar?q=pan").get_json()["resultados"]]
    # Sin relleno en el índice, "Pan de muerto" (2) y "Pan dulce" (1) empatan y gana el nombre: el
    # primero ya es el 2, así que se reacciona al 1 para que el orden cambie de verdad.
    _usar(cliente, doc=1)
    assert [r["id"] for r in cliente.get("/api/buscar?q=pan").get_json()["resultados"]] != orden_inicial
    r = _post(cliente, "/api/admin/reiniciar", {"alcance": "todo"})
    assert r.get_json()["eventos"] == {}
    assert [r["id"] for r in cliente.get("/api/buscar?q=pan").get_json()["resultados"]] == orden_inicial
    assert senales.estadisticas()["eventos"] == {}


def test_el_alcance_por_defecto_es_todo(cliente):
    _usar(cliente)
    assert _post(cliente, "/api/admin/reiniciar", {}).get_json()["eventos"] == {}


@pytest.mark.parametrize("cuerpo", [{"alcance": "nada"}, {"alcance": []}, {"alcance": ["clics", "x"]}, {"alcance": 3}])
def test_alcance_invalido(cliente, cuerpo):
    r = _post(cliente, "/api/admin/reiniciar", cuerpo)
    assert r.status_code == 400 and "validos" in r.get_json()


def test_un_alcance_invalido_no_borra_nada(cliente):
    _usar(cliente)
    _post(cliente, "/api/admin/reiniciar", {"alcance": ["clics", "x"]})
    assert cliente.get("/api/admin/estado", headers=CABECERA).get_json()["eventos"]["clic"] == 1


def test_cuerpo_que_no_es_un_objeto(cliente):
    assert _post(cliente, "/api/admin/reiniciar", [1]).status_code == 400
    assert _post(cliente, "/api/admin/simular", [1]).status_code == 400


# --- generar -------------------------------------------------------------------------------------

def test_simular_inserta_de_todo_y_alimenta_las_sugerencias(cliente):
    r = _post(cliente, "/api/admin/simular", {"consultas": 120, "reacciones": 80, "semilla": 7})
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["semilla"] == 7 and "perfil_local" not in datos
    assert datos["insertados"]["consulta"] == 120
    assert datos["insertados"]["impresion"] > 120 and datos["insertados"]["clic"] > 0
    assert sum(datos["insertados"][t] for t in ("me_gusta", "me_encanta", "no_me_gusta") if t in datos["insertados"]) == 80
    assert datos["eventos"]["consulta"] == 120
    # alguna consulta se repitió lo suficiente para que "Más buscadas" tenga algo
    assert cliente.get("/api/sugerencias?q=").get_json()["sugerencias"]


def test_simular_devuelve_el_perfil_local_solo_si_se_pide(cliente):
    datos = _post(cliente, "/api/admin/simular", {"semilla": 3, "perfil_local": True}).get_json()
    perfil = datos["perfil_local"]
    assert perfil["consultas"] and perfil["reacciones"]
    assert all(set(c) == {"q", "n", "idioma"} and 1 <= c["n"] <= poblar.PERFIL_REPETICIONES for c in perfil["consultas"])
    assert all(r["id"] in {d["id"] for d in DOCS} for r in perfil["reacciones"])


def test_simular_respeta_los_topes_y_valida_los_numeros(cliente):
    datos = _post(cliente, "/api/admin/simular", {"consultas": 10**9, "reacciones": 0, "semilla": 1}).get_json()
    assert datos["insertados"]["consulta"] == 2_000
    assert not any(t in datos["insertados"] for t in ("me_gusta", "me_encanta", "no_me_gusta"))
    # basura: se usan los valores por defecto en lugar de fallar
    datos = _post(cliente, "/api/admin/simular", {"consultas": "mucho", "reacciones": None, "semilla": "x"}).get_json()
    assert datos["insertados"]["consulta"] == 200


def test_simular_suma_por_defecto_y_reemplaza_si_se_pide(cliente, senales):
    _usar(cliente)                                   # una reacción 😍 al documento 2, un clic, una consulta
    r = _post(cliente, "/api/admin/simular", {"consultas": 30, "reacciones": 20, "semilla": 4}).get_json()
    assert "borrados" not in r and r["eventos"]["clic"] >= 1 and senales.conteos(2)["me_encanta"] >= 1

    antes = sum(sum(senales.conteos(d["id"]).values()) for d in DOCS)
    r = _post(cliente, "/api/admin/simular", {"consultas": 30, "reacciones": 20, "semilla": 4, "reemplazar": True}).get_json()
    assert r["borrados"]["reacciones"] == antes      # lo anterior se fue (la de _usar y las 20 de antes)
    assert r["eventos"] == r["insertados"]           # y solo queda lo recién generado
    assert sum(sum(senales.conteos(d["id"]).values()) for d in DOCS) == 20


def test_reemplazar_deja_el_mismo_estado_con_la_misma_semilla(cliente):
    cuerpo = {"consultas": 40, "reacciones": 40, "semilla": 9, "reemplazar": True}
    a = _post(cliente, "/api/admin/simular", cuerpo).get_json()["eventos"]
    b = _post(cliente, "/api/admin/simular", cuerpo).get_json()["eventos"]
    assert a == b


def test_reemplazar_solo_cuenta_si_es_true(cliente):
    _usar(cliente)
    _post(cliente, "/api/admin/simular", {"consultas": 5, "reacciones": 0, "semilla": 1, "reemplazar": "si"})
    assert cliente.get("/api/admin/estado", headers=CABECERA).get_json()["eventos"]["clic"] >= 1


def test_simular_sin_semilla_devuelve_la_que_uso(cliente):
    assert isinstance(_post(cliente, "/api/admin/simular", {"consultas": 5}).get_json()["semilla"], int)


# --- poblar.generar ------------------------------------------------------------------------------

@pytest.fixture
def buscador(senales):
    return Buscador(RepoFalso(DOCS), senales=senales)


def test_misma_semilla_mismas_filas(buscador, senales, reloj):
    a = poblar.generar(buscador, senales, consultas=60, reacciones=40, semilla=11, ahora=reloj())
    b = poblar.generar(buscador, senales, consultas=60, reacciones=40, semilla=11, ahora=reloj())
    c = poblar.generar(buscador, senales, consultas=60, reacciones=40, semilla=12, ahora=reloj())
    assert a.filas == b.filas and a.perfil_local == b.perfil_local
    assert a.filas != c.filas


def test_las_horas_caen_en_el_pasado_y_dentro_de_lo_que_el_sistema_recuerda(buscador, senales, reloj):
    muestra = poblar.generar(buscador, senales, consultas=80, reacciones=80, semilla=5)
    ventana = senales.historial.ventana_s
    for tipo, _, _, _, _, ts in muestra.filas:
        limite = poblar.DIAS_REACCIONES * poblar.DIA_S if tipo.startswith(("me_", "no_")) else ventana
        assert reloj() - limite <= ts <= reloj()


def test_las_filas_cargadas_pasan_por_el_motor_como_datos_reales(buscador, senales):
    muestra = poblar.generar(buscador, senales, consultas=80, reacciones=60, semilla=2)
    assert senales.cargar_eventos(muestra.filas) == len(muestra.filas)
    assert senales.estadisticas()["eventos"] == muestra.resumen
    assert sum(sum(senales.conteos(d["id"]).values()) for d in DOCS) == 60
    assert senales.sugerir("")  # hay consultas frecuentes


def test_el_perfil_local_no_tiene_consultas_que_sean_prefijo_de_otra(buscador, senales):
    from nucleo.texto import normalizar
    for semilla in range(20):
        consultas = poblar.generar(buscador, senales, consultas=150, semilla=semilla).perfil_local["consultas"]
        claves = [normalizar(c["q"]) for c in consultas]
        assert not any(a != b and b.startswith(a) for a in claves for b in claves)
        assert len(claves) == len(set(claves)) <= poblar.PERFIL_CONSULTAS


def test_catalogo_vacio_o_sin_pedir_nada(senales):
    vacio = Buscador(RepoFalso([]), senales=senales)
    assert poblar.generar(vacio, senales, semilla=1).filas == []
    lleno = Buscador(RepoFalso(DOCS), senales=senales)
    assert poblar.generar(lleno, senales, consultas=0, reacciones=0, semilla=1).filas == []
    assert senales.cargar_eventos([]) == 0


