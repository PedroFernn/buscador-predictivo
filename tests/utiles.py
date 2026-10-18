"""Piezas compartidas por las pruebas."""


class RepoFalso:
    def __init__(self, docs):
        self.docs = docs

    def listar(self):
        return [dict(d) for d in self.docs]


class Reloj:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# Mismo texto en todos: sin señales, el orden es por nombre
DOCS_PAN = [
    {"id": 1, "nombre": "A", "categoria": "C", "descripcion": "pan", "emoji": "🥐", "idioma": "es"},
    {"id": 2, "nombre": "B", "categoria": "C", "descripcion": "pan", "emoji": "🍞", "idioma": "es"},
    {"id": 3, "nombre": "C", "categoria": "C", "descripcion": "pan", "emoji": "🥖", "idioma": "en"},
]

DOCS_ENE = [
    {"id": 1, "nombre": "Caña", "categoria": "Planta", "descripcion": "tallo dulce", "emoji": "🎋", "idioma": "es"},
    {"id": 2, "nombre": "Cana", "categoria": "Cabello", "descripcion": "pelo blanco", "emoji": "👴", "idioma": "es"},
]
