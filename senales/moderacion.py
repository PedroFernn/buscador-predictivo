"""Moderación de lo que se cuenta y se sugiere a otras personas (las sugerencias son públicas).

No se registran consultas con correos, direcciones web, secuencias largas de dígitos
(teléfonos, tarjetas, identificaciones) ni términos de la lista de bloqueo.
"""
import re

from nucleo.texto import clave_consulta

MIN_DIGITOS_SENSIBLES = 8  # se toleran separadores entre dígitos
_RE_SENSIBLE = re.compile(
    r"[^\s@]+@[^\s@]+\.[^\s@]+"                        # correo electrónico
    r"|https?://|www\."                                  # direcciones web
    r"|(?:\d[ ().\-]?){%d,}" % MIN_DIGITOS_SENSIBLES,    # secuencias largas de dígitos
    re.IGNORECASE,
)


class Moderador:
    def __init__(self, bloqueados=(), activo=True):
        self.activo = activo
        self.bloqueados = frozenset(t for termino in bloqueados for t in clave_consulta(termino).split())

    def sensible(self, texto, clave):
        """True si la consulta no debe contarse ni sugerirse (datos personales o bloqueada)."""
        if not self.activo:
            return False
        if _RE_SENSIBLE.search(texto):
            return True
        return bool(self.bloqueados) and any(t in self.bloqueados for t in clave.split())
