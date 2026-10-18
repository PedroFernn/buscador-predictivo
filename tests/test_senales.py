"""Persistencia, varios procesos, retención y moderación del servicio de señales."""
import time

import pytest

from senales import Senales
from tests.utiles import Reloj


def test_las_senales_sobreviven_a_un_reinicio(tmp_path):
    ruta = tmp_path / "senales.db"
    reloj = Reloj()
    a = Senales(ruta, reloj=reloj)
    a.reaccionar(2, "me_encanta")
    a.registrar_clic("pan", 3, posicion=2)
    a.registrar_consulta("mole poblano", mostrados=[1, 2, 3])
    pesos_a = a.pesos("pan", [1, 2, 3])
    a.cerrar()

    b = Senales(ruta, reloj=reloj)  # "reinicio": proceso nuevo, mismo archivo
    assert b.conteos(2)["me_encanta"] == 1
    assert b.pesos("pan", [1, 2, 3]) == pytest.approx(pesos_a)
    assert b.sugerir("mol")["sugerencias"] == [{"consulta": "mole poblano", "frecuencia": 1}]
    assert b.estadisticas()["eventos"] == {"me_encanta": 1, "clic": 1, "consulta": 1, "impresion": 3}
    b.cerrar()


def test_dos_procesos_comparten_las_senales(tmp_path):
    ruta = tmp_path / "senales.db"
    a = Senales(ruta, sync_s=1e-6)
    b = Senales(ruta, sync_s=1e-6)
    assert b.conteos(1)["me_gusta"] == 0
    a.reaccionar(1, "me_gusta")
    a.registrar_clic("pan", 2)
    time.sleep(0.01)
    assert b.conteos(1)["me_gusta"] == 1       # b ve la escritura de a, sin reiniciar
    assert b.pesos("pan", [1, 2])[2][1] > 1.0
    b.registrar_consulta("pan dulce")
    assert a.sugerir("pan")["sugerencias"][0]["consulta"] == "pan dulce"
    a.cerrar()
    b.cerrar()


def test_la_purga_quita_lo_que_sale_de_su_ventana(tmp_path, reloj):
    s = Senales(tmp_path / "s.db", reloj=reloj, ventana_s=100, retencion_s=500, sync_s=0)
    s.registrar_consulta("vieja")
    s.registrar_clic("vieja", 1)
    s.reaccionar(1, "me_gusta")
    reloj.t += 600
    s._purgar()
    # las reacciones no se purgan (decaen); consultas y clics sí
    assert s.almacen.conteo_por_tipo() == {"me_gusta": 1}
    s.cerrar()


def test_la_purga_corre_sola_cada_tantas_escrituras(reloj):
    s = Senales(reloj=reloj, ventana_s=100, sync_s=0)
    s.registrar_consulta("vieja")
    reloj.t += 1000
    for i in range(600):
        s.reaccionar(1, "me_gusta")
    assert s.almacen.conteo_por_tipo().get("consulta", 0) == 0
    s.cerrar()


def test_la_retencion_limita_lo_que_se_reconstruye(tmp_path, reloj):
    ruta = tmp_path / "s.db"
    a = Senales(ruta, reloj=reloj, retencion_s=500)
    a.registrar_clic("pan", 1)
    a.cerrar()
    reloj.t += 600
    b = Senales(ruta, reloj=reloj, retencion_s=500)  # el clic ya no entra en el aprendizaje
    assert b.pesos("pan", [1])[1][1] == 1.0
    b.cerrar()


def test_registrar_consulta_guarda_impresiones_en_orden(senales):
    assert senales.registrar_consulta("pan", mostrados=[7, 3, 9])
    filas = [f for f in senales.almacen.leer(("impresion",))]
    assert [(f[1], f[3]) for f in filas] == [(7, 1), (3, 2), (9, 3)]
    assert not senales.registrar_consulta("juan@correo.com", mostrados=[1])
    assert len(senales.almacen.leer(("impresion",))) == 3  # lo sensible no deja impresiones


def test_reaccion_invalida(senales):
    with pytest.raises(ValueError):
        senales.reaccionar(1, "odio")


def test_el_candado_tolera_hilos(senales):
    import threading

    def trabajo():
        for i in range(50):
            senales.reaccionar(i % 3, "me_gusta")
            senales.registrar_consulta(f"consulta {i % 5}")
            senales.pesos("consulta", [0, 1, 2])

    hilos = [threading.Thread(target=trabajo) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sum(senales.conteos(i)["me_gusta"] for i in range(3)) == 300
