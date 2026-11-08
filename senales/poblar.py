"""poblar.py — datos de prueba: consultas, impresiones, clics y reacciones aleatorios pero plausibles.

Se arman con el propio catálogo y con el propio motor (cada consulta se busca de verdad, así que
las impresiones y los clics salen de resultados reales):

  consultas    muestra Zipf de consultas derivadas de nombres, primeras palabras, categorías y
               prefijos del catálogo; las más populares se repiten lo bastante para aparecer
               en "Más buscadas".
  impresiones  los resultados que el motor devolvió, en su posición.
  clics        con probabilidad P_CLIC; suelen elegir el documento del que salió la consulta y,
               si no, se reparten con sesgo de posición (1/posición).
  reacciones   documentos por popularidad Zipf; cada uno con una "calidad" oculta que decide si
               gusta o no, así el ranking recibe una señal con sentido y no ruido uniforme.

No escribe nada: devuelve filas (tipo, doc_id, consulta, posicion, texto, ts) para
Senales.cargar_eventos(). Con la misma semilla, el mismo catálogo y las mismas señales previas
da las mismas filas. Las horas se reparten en el pasado, dentro de lo que la ventana de consultas
y la vida media de las reacciones todavía tienen en cuenta.
"""
import random
from collections import Counter
from dataclasses import dataclass

from nucleo.texto import clave_consulta, normalizar, tokenizar
from senales.consultas import LARGO_MAX_CONSULTA
from senales.servicio import DIA_S

ZIPF_CONSULTAS = 1.1        # unas pocas consultas concentran el tráfico
ZIPF_DOCUMENTOS = 0.8       # y unos pocos documentos concentran las reacciones
CONSULTAS_POR_DISTINTA = 4  # cuántas búsquedas por cada consulta distinta, en promedio
MIN_DISTINTAS = 5
P_CLIC = 0.6                # probabilidad de que una búsqueda termine en clic
P_CLIC_ESPERADO = 0.7       # ... y de que sea el documento del que salió la consulta, si aparece
P_ME_ENCANTA = 0.25         # entre las reacciones positivas
DIAS_REACCIONES = 30
PERFIL_CONSULTAS = 8        # lo que se devuelve para llenar el perfil del navegador
PERFIL_REPETICIONES = 5
PERFIL_REACCIONES = 12


@dataclass(frozen=True)
class Muestra:
    semilla: int
    filas: list          # eventos listos para Senales.cargar_eventos()
    resumen: dict        # tipo de evento -> cuántos
    perfil_local: dict   # {"consultas": [{q, n, idioma}], "reacciones": [{id, tipo}]}


def _variantes(doc):
    """Formas en que alguien buscaría este documento."""
    tokens = tokenizar(doc["nombre"])
    formas = [doc["nombre"]]
    if len(tokens) > 1:
        formas.append(tokens[0])
    if doc["categoria"]:
        formas.append(doc["categoria"])
    if tokens and len(tokens[0]) > 4:
        formas.append(tokens[0][:4])  # a medio escribir
    return formas


def _consultas_posibles(catalogo, moderador, rng, cuantas):
    """Hasta `cuantas` consultas distintas: (texto, clave, idioma, id del documento de origen)."""
    orden = list(catalogo)
    rng.shuffle(orden)
    vistas, salida = set(), []
    for doc in orden:
        texto = rng.choice(_variantes(doc))
        clave = clave_consulta(texto)
        if clave in vistas or not 2 <= len(clave) <= LARGO_MAX_CONSULTA:
            continue
        if moderador.sensible(texto, clave):
            continue
        vistas.add(clave)
        salida.append((texto, clave, doc["idioma"], doc["id"]))
        if len(salida) == cuantas:
            break
    return salida


def _posicion_clic(rng, ids, doc_id):
    if doc_id in ids and rng.random() < P_CLIC_ESPERADO:
        return ids.index(doc_id) + 1
    posiciones = range(1, len(ids) + 1)
    return rng.choices(posiciones, weights=[1 / p for p in posiciones])[0]


def _filas_de_consultas(buscador, senales, catalogo, cuantas, rng, ahora):
    """-> (filas, veces por clave, {clave: (texto, idioma)})."""
    distintas = max(MIN_DISTINTAS, cuantas // CONSULTAS_POR_DISTINTA)
    pool = _consultas_posibles(catalogo, senales.historial.moderador, rng, distintas) if cuantas else []
    if not pool:
        return [], Counter(), {}
    pesos = [1 / (r + 1) ** ZIPF_CONSULTAS for r in range(len(pool))]
    ventana = senales.historial.ventana_s * 0.95   # todo cabe en la ventana: nada se purga al instante
    resultados, filas, veces = {}, [], Counter()
    for texto, clave, idioma, doc_id in rng.choices(pool, weights=pesos, k=cuantas):
        if clave not in resultados:
            resultados[clave] = [r["id"] for r in buscador.buscar(texto, idioma)["resultados"]]
        ids = resultados[clave]
        t = ahora - rng.random() * ventana
        forma = " ".join(texto.split())[:LARGO_MAX_CONSULTA * 2]
        filas.append(("consulta", None, clave, None, forma if forma != clave else None, t))
        filas.extend(("impresion", i, clave, pos, None, t) for pos, i in enumerate(ids, 1))
        if ids and rng.random() < P_CLIC:
            pos = _posicion_clic(rng, ids, doc_id)
            filas.append(("clic", ids[pos - 1], clave, pos, None, min(ahora, t + rng.uniform(1, 30))))
        veces[clave] += 1
    return filas, veces, {clave: (texto, idioma) for texto, clave, idioma, _ in pool}


def _filas_de_reacciones(catalogo, cuantas, rng, ahora):
    if not cuantas or not catalogo:
        return []
    orden = list(catalogo)
    rng.shuffle(orden)
    pesos = [1 / (r + 1) ** ZIPF_DOCUMENTOS for r in range(len(orden))]
    calidad = {doc["id"]: rng.random() for doc in orden}
    filas = []
    for doc in rng.choices(orden, weights=pesos, k=cuantas):
        if rng.random() < calidad[doc["id"]]:
            tipo = "me_encanta" if rng.random() < P_ME_ENCANTA else "me_gusta"
        else:
            tipo = "no_me_gusta"
        filas.append((tipo, doc["id"], None, None, None, ahora - rng.random() * DIAS_REACCIONES * DIA_S))
    return filas


def _perfil_local(veces, por_clave, filas_reacciones):
    """Lo que el navegador puede guardar para que "Sugerencias para ti" tenga con qué trabajar.

    Sin consultas que sean prefijo una de otra: historial.js trata una búsqueda que solo extiende
    a la anterior como la misma y la reemplazaría.
    """
    consultas, normalizadas = [], []
    for clave, n in veces.most_common():
        texto, idioma = por_clave[clave]
        norm = normalizar(texto.strip())
        if any(norm.startswith(u) or u.startswith(norm) for u in normalizadas):
            continue
        normalizadas.append(norm)
        consultas.append({"q": texto.strip(), "n": min(n, PERFIL_REPETICIONES), "idioma": idioma})
        if len(consultas) == PERFIL_CONSULTAS:
            break
    vistos, reacciones = set(), []
    for tipo, doc_id, *_ in filas_reacciones:
        if doc_id in vistos:
            continue
        vistos.add(doc_id)
        reacciones.append({"id": doc_id, "tipo": tipo})
        if len(reacciones) == PERFIL_REACCIONES:
            break
    return {"consultas": consultas, "reacciones": reacciones}


def generar(buscador, senales, *, consultas=200, reacciones=300, semilla=None, ahora=None):
    """Arma una muestra de uso. `consultas` son búsquedas (con sus impresiones y clics)."""
    semilla = random.randrange(2**31) if semilla is None else int(semilla)
    rng = random.Random(semilla)
    ahora = senales.ahora() if ahora is None else ahora
    catalogo = [d for d in buscador.indice.catalogo if "id" in d]
    filas_q, veces, por_clave = _filas_de_consultas(buscador, senales, catalogo, max(0, consultas), rng, ahora)
    filas_r = _filas_de_reacciones(catalogo, max(0, reacciones), rng, ahora)
    filas = filas_q + filas_r
    return Muestra(
        semilla=semilla,
        filas=filas,
        resumen=dict(Counter(f[0] for f in filas)),
        perfil_local=_perfil_local(veces, por_clave, filas_r),
    )
