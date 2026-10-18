import pytest

from senales import Senales
from senales.almacen import AlmacenEventos
from senales.consultas import HistorialConsultas
from senales.moderacion import Moderador
from tests.utiles import Reloj


def historial(reloj=None, ventana_s=1000, min_frecuencia=1, bloqueados=(), moderar=True, almacen=None):
    reloj = reloj or Reloj()
    return HistorialConsultas(almacen or AlmacenEventos(), reloj, Moderador(bloqueados, moderar),
                              ventana_s, min_frecuencia)


def cargar(h, consultas):
    """consultas: {texto: veces}"""
    for texto, veces in consultas.items():
        for _ in range(veces):
            h.registrar(texto)


def nombres(h, prefijo="", k=10):
    return [s["consulta"] for s in h.sugerir(prefijo, k)["sugerencias"]]


def test_ordena_por_frecuencia_real():
    h = historial()
    cargar(h, {"polvo": 5, "pulpo": 9, "pan": 2})
    assert h.sugerir("p")["sugerencias"] == [
        {"consulta": "pulpo", "frecuencia": 9},
        {"consulta": "polvo", "frecuencia": 5},
        {"consulta": "pan", "frecuencia": 2},
    ]


def test_prefijo_vacio_da_las_mas_buscadas():
    h = historial()
    cargar(h, {"a1": 1, "b2": 4, "c3": 2})
    assert nombres(h, "", 2) == ["b2", "c3"]


def test_empate_gana_la_mas_reciente_y_luego_el_alfabeto():
    reloj = Reloj()
    h = historial(reloj)
    cargar(h, {"zeta": 2})
    reloj.t += 5
    cargar(h, {"alfa": 2})
    assert nombres(h) == ["alfa", "zeta"]          # alfa es más reciente
    h2 = historial(Reloj())
    cargar(h2, {"zeta": 1, "alfa": 1})              # mismo instante: alfabético
    assert nombres(h2) == ["alfa", "zeta"]


def test_se_muestra_la_forma_original_mas_reciente():
    h = historial()
    h.registrar("polvo")
    h.registrar("POLVO")
    assert h.sugerir("pol")["sugerencias"] == [{"consulta": "POLVO", "frecuencia": 2}]


def test_la_ene_es_una_letra_distinta_en_el_prefijo():
    h = historial()
    cargar(h, {"año nuevo": 3, "ano": 2})
    assert nombres(h, "añ") == ["año nuevo"]


def test_el_prefijo_con_espacio_final_no_confunde_pan_con_pancake():
    h = historial()
    cargar(h, {"pan dulce": 2, "pancake": 5})
    assert nombres(h, "pan ") == ["pan dulce"]
    assert nombres(h, "pan") == ["pancake", "pan dulce"]


def test_vencen_las_consultas_fuera_de_la_ventana():
    reloj = Reloj()
    h = historial(reloj, ventana_s=300)
    cargar(h, {"vieja": 5})
    reloj.t += 200
    cargar(h, {"reciente": 5})
    assert set(nombres(h)) == {"vieja", "reciente"}
    reloj.t += 150  # "vieja" (hace 350 s) sale de la ventana; "reciente" (hace 150 s) sigue
    assert nombres(h) == ["reciente"]
    reloj.t += 10_000
    assert nombres(h) == [] and h.estadisticas()["consultas_vivas"] == 0


def test_una_repeticion_cuenta_solo_dentro_de_la_ventana():
    reloj = Reloj()
    h = historial(reloj, ventana_s=300)
    cargar(h, {"x1": 2})
    reloj.t += 200
    cargar(h, {"x1": 3})
    assert h.sugerir("x1")["sugerencias"][0]["frecuencia"] == 5
    reloj.t += 150  # las 2 primeras salieron de la ventana
    assert h.sugerir("x1")["sugerencias"][0]["frecuencia"] == 3


def test_umbral_publico_se_cuenta_pero_no_se_sugiere():
    reloj = Reloj()
    h = historial(reloj, min_frecuencia=3)
    cargar(h, {"mole": 2})
    assert h.sugerir("mo")["sugerencias"] == []
    assert h.estadisticas()["consultas_vivas"] == 1
    h.registrar("mole")
    assert h.sugerir("mo")["sugerencias"] == [{"consulta": "mole", "frecuencia": 3}]
    assert h.estadisticas()["min_frecuencia_publica"] == 3


def test_cache_de_prefijos_y_ttl():
    reloj = Reloj()
    h = historial(reloj)
    cargar(h, {"mole": 2})
    assert h.sugerir("mo")["origen"] == "tabla"
    assert h.sugerir("mo")["origen"] == "cache"
    reloj.t += 31
    assert h.sugerir("mo")["origen"] == "tabla"
    h.registrar("mole")  # una escritura local invalida el cache
    assert h.sugerir("mo")["origen"] == "tabla"


def test_cache_acotado():
    h = historial()
    h.max_cache = 5
    cargar(h, {f"q{i}": 1 for i in range(30)})
    for i in range(30):
        h.sugerir(f"q{i}")
    assert h.estadisticas()["prefijos_en_cache"] <= 5


def test_el_k_se_acota():
    h = historial()
    cargar(h, {f"c{i:02d}": 1 for i in range(60)})
    assert len(h.sugerir("", 10_000)["sugerencias"]) == 50
    assert len(h.sugerir("", -3)["sugerencias"]) == 1


def test_consultas_invalidas_no_se_registran():
    h = historial()
    assert not h.registrar("!!!") and not h.registrar("") and not h.registrar(None)
    assert not h.registrar("x" * 5000)
    assert h.estadisticas()["consultas_vivas"] == 0


class TestModeracion:
    def test_los_datos_personales_no_se_cuentan(self):
        h = historial()
        textos = ("juan@correo.com", "https://sitio.mx/x", "www.sitio.mx", "55 1234 5678", "4111-1111-1111-1111")
        for texto in textos:
            for _ in range(3):
                assert not h.registrar(texto), texto
        e = h.estadisticas()
        assert e["consultas_vivas"] == 0
        assert e["descartadas_por_moderacion"] == 3 * len(textos)

    def test_las_consultas_normales_con_numeros_pasan(self):
        h = historial()
        assert h.registrar("iphone 15 pro") and h.registrar("receta 2024")

    def test_lista_de_bloqueo(self):
        h = historial(bloqueados=["Prohibída"])
        for _ in range(3):
            assert not h.registrar("cosa PROHIBIDA")
        assert h.registrar("cosa permitida")

    def test_moderar_false_la_desactiva(self):
        assert historial(moderar=False).registrar("juan@correo.com")

    def test_al_arrancar_se_aplica_la_lista_de_bloqueo_actual(self):
        almacen = AlmacenEventos()
        cargar(historial(almacen=almacen), {"cosa prohibida": 4, "cosa permitida": 4})
        b = historial(almacen=almacen, bloqueados=["prohibida"])
        assert b.aplicar_bloqueo() == 4
        assert nombres(b) == ["cosa permitida"]


def test_estadisticas_incluyen_el_ajuste_zipf():
    h = historial()
    cargar(h, {f"c{i}": max(1, 200 // (i + 1)) for i in range(60)})
    z = h.estadisticas()["zipf"]
    assert z is not None and z["puntos"] >= 10
    assert 0.5 < z["exponente"] < 1.5
