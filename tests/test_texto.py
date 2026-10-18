from nucleo.estadistica import ajuste_loglog, ajuste_zipf
from nucleo.lexico import SINONIMOS
from nucleo.texto import clave_consulta, normalizar, tokenizar


def test_normalizar_conserva_la_ene_y_quita_los_acentos():
    assert normalizar("Niño CAFÉ") == "niño cafe"
    assert tokenizar("Año nuevo, Jícama") == ["año", "nuevo", "jicama"]


def test_los_grupos_semanticos_usan_la_ene():
    assert "tiny" in SINONIMOS["pequeño"]
    assert "pequeno" not in SINONIMOS


def test_clave_sin_acentos_ni_mayusculas():
    assert clave_consulta("  Jícama   CAFÉ ") == "jicama cafe"


def test_clave_emoji_es_un_token_y_el_tono_de_piel_no_cuenta():
    assert clave_consulta("polvo🐙") == "polvo 🐙"
    assert clave_consulta("👍🏽") == "👍"


def test_clave_puntuacion_sola_no_es_consulta():
    assert clave_consulta("!!!") == ""
    assert clave_consulta(None) == ""


def test_clave_prefijo_conserva_espacio_final():
    assert clave_consulta("pan ", parcial=True) == "pan "
    assert clave_consulta("pan ", parcial=False) == "pan"


def test_la_ene_es_una_letra_distinta():
    assert clave_consulta("Año") == "año"
    assert clave_consulta("año") != clave_consulta("ano")
    assert clave_consulta("NIÑO") == "niño"
    assert clave_consulta("Pingüino ÁÉÍ") == "pinguino aei"


def test_ajuste_recupera_el_exponente_de_una_ley_potencial():
    frecs = [round(10_000 / r**1.1) + 1 for r in range(1, 400)]
    assert abs(ajuste_zipf(frecs)["exponente"] - 1.1) < 0.05
    pendiente, _, r2 = ajuste_loglog([10, 100, 1000, 10000], [5, 25, 125, 625])
    assert round(pendiente, 2) == 0.70
    assert r2 > 0.999


def test_ajuste_con_pocos_datos_devuelve_none():
    assert ajuste_zipf([5, 3, 1]) is None
    assert ajuste_loglog([1, 2], [1, 2]) is None
