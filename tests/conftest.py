import pytest

from senales import Senales
from tests.utiles import Reloj


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def senales(reloj):
    """Señales en memoria, con reloj controlado y sin sincronización entre procesos."""
    s = Senales(reloj=reloj, sync_s=0)
    yield s
    s.cerrar()
