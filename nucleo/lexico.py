"""Léxico del motor: abreviaturas, palabras de relleno y grupos semánticos (es / en / pt).

Solo datos y su derivado SINONIMOS. Extiende aquí (sin acentos, en minúsculas y con la ñ).
Lo usan busqueda/ (interpretar la consulta) y senales/ (términos de una consulta): vive en
nucleo/ para que ninguno dependa del otro.
"""
from collections import defaultdict

from nucleo.texto import tokenizar

# Abreviaturas / jerga de chat -> palabra completa
ABREVIATURAS = {
    "ct": "caro",
    "q": "que", "k": "que", "xq": "porque", "pq": "porque", "porq": "porque",
    "tb": "tambien", "tbn": "tambien", "tmb": "tambien", "tbm": "tambem",
    "x": "por", "xa": "para", "d": "de", "bn": "bien", "cmo": "como",
    "dnd": "donde", "qn": "quien", "xfa": "favor", "xfis": "favor",
    "msj": "mensaje", "grax": "gracias", "vc": "voce",
    "pls": "please", "plz": "please", "thx": "thanks",
}

# Palabras de relleno que se eliminan al simplificar la consulta
STOPWORDS = frozenset("""
    el la los las un una unos unas lo al del de en con sin por para y o u e
    que es son ser sea esta este esto esa eso ese hay muy mas menos como
    cual cuales donde cuando quien se su sus mi mis tu tus me te le les
    algo cosa cosas quiero quisiera busco buscar necesito dame dime favor
    the a an of in on at to for and or is are be it this that these those
    something thing things want need looking find show please with from
    um uma uns umas os as do da dos das no na nos nas em com sem pelo pela
    voce isso isto algum alguma quero preciso procuro
    porque tambien tambem gracias thanks because also why
""".split())

# Grupos de conceptos equivalentes (es / en / pt). Buscar uno activa los demás.
GRUPOS_SEMANTICOS = [
    "caro costoso costosa carisimo costly expensive pricey luxury lujo luxo "
    "custoso valioso valuable",
    "barato ganga cheap inexpensive affordable bargain oferta pechincha",
    "dinero plata money cash moneda finanzas dinheiro financiero financial",
    "grande enorme gigante big large huge giant",
    "pequeño chico diminuto small little tiny mini",
    "rapido veloz velocidad fast quick speed velocidade",
    "lento despacio slow devagar",
    "comida alimento food meal refeicao comer eat",
    "bebida beber drink liquido liquid",
    "miedo temor susto fear scared afraid medo",
    "feliz alegre contento happy glad alegria felicidad",
    "triste tristeza sad sorrow",
    "enojo enojado enfado ira anger angry raiva",
    "enfermo enfermedad sick ill disease doente",
    "medico doctor physician medicina medicine",
    "trabajo empleo job work profesion profession emprego trabalho",
    "casa hogar home house vivienda lar",
    "dificil complicado hard difficult tough",
    "facil sencillo simple easy",
    "viejo antiguo old ancient anciano velho",
    "bonito hermoso lindo bello beautiful pretty belo",
    "coche carro auto car automovil vehiculo vehicle",
    "escuela colegio school estudiar study educacion education escola",
    "frio cold helado gelado",
    "calor caliente hot heat quente",
]


def construir_sinonimos():
    mapa = defaultdict(set)
    for grupo in GRUPOS_SEMANTICOS:
        terminos = set(tokenizar(grupo))
        for t in terminos:
            mapa[t] |= terminos
    return {t: grupo - {t} for t, grupo in mapa.items()}


SINONIMOS = construir_sinonimos()
