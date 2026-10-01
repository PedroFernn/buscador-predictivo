# Buscador Predictivo Multilenguaje — SRI

Sistema de Recuperación de Información con modelo vectorial TF-IDF sobre un
catálogo en **tres idiomas**, con un selector que decide cuál domina el
ranking.

```
SRI = { D, Q, F, R(qk, dj) }
```

| Componente | Qué es en este proyecto |
|---|---|
| **D** | 1144 documentos (600 es, 276 en, 268 pt) en `catalogo.json` o en una base SQL. Cada uno con `nombre`, `categoria`, `descripcion` e **`idioma`**. |
| **Q** | Lo que el usuario escribe en tiempo real, aunque esté incompleto. |
| **F** | Modelo de Espacio Vectorial TF-IDF, con normalización **por campo** (estilo BM25F). El idioma no forma parte del vector. |
| **R(qk, dj)** | Similitud coseno sobre ese espacio de términos, **reescalada después** por un factor según el idioma del documento. |

## Preprocesamiento de texto

Antes de tokenizar, todo texto —catálogo y consulta por igual— pasa por el
mismo pipeline (`normalizar` + `tokenizar`):

1. **Minúsculas** — `texto.lower()`.
2. **Descomposición Unicode NFD** — `unicodedata.normalize("NFD", texto)`
   separa cada carácter acentuado en su letra base más un carácter de "marca
   combinante" (diacrítico) aparte. Por ejemplo, `"é"` se descompone en `e` +
   `´` (dos *code points*).
3. **Eliminación de marcas combinantes** — se descarta todo carácter cuya
   categoría Unicode sea `Mn` (*nonspacing mark*), es decir, los diacríticos
   sueltos que dejó el paso anterior. `"é"` vuelve a quedar en un solo
   carácter: `e`.
4. **Extracción por regex** — `re.findall(r"[a-z0-9]+", texto)` recorta el
   texto ya sin acentos y en minúsculas a secuencias de letras y dígitos;
   cualquier otro carácter (espacios, guiones, puntuación) actúa como
   separador de tokens.

```python
def normalizar(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")

def tokenizar(texto):
    return re.findall(r"[a-z0-9]+", normalizar(texto))
```

Con esto, `"Jícama"`, `"CAFÉ"` y `"niño"` tokenizan a `jicama`, `cafe` y
`nino` — exactamente lo que permite que escribir "jicama" sin tilde
encuentre "Jícama" en el catálogo.

**Un caso a tener en cuenta:** el paso NFD no distingue un diacrítico que
solo marca acento de uno que cambia la letra. La `ñ` también se descompone
en `n` + marca combinante, así que se elimina igual que una tilde:
`"año"` tokeniza a `ano`, indistinguible de la palabra "ano". Hoy no genera
colisiones porque ningún par de homógrafos del catálogo depende de una `ñ`,
pero es un efecto real del pipeline, no un caso hipotético.

## Formalización matemática

**IDF suavizado.** Para $N$ documentos totales y $\mathrm{df}(t)$ documentos
donde aparece el término $t$:

$$\mathrm{idf}(t) = \log_{10}\!\left(1 + \frac{N}{\mathrm{df}(t)}\right)$$

El "+1" dentro del logaritmo es lo que evita $\mathrm{idf}(t)=0$ para un
término que apareciera en todos los documentos (a diferencia del IDF clásico
$\log(N/\mathrm{df})$, que sí llega a 0 ahí) — ningún término queda
completamente invisible para el vector. El $\mathrm{tf}(t,c)$ correspondiente
es la cuenta cruda de ocurrencias de $t$ dentro del campo $c$ (`Counter`),
sin atenuar: no hay tf logarítmico ni sublineal.

**Vector de un documento, por campo y luego combinado.** Para cada campo
$c \in \{\text{nombre}, \text{categoria}, \text{descripcion}\}$ con peso
$w_c$ (ver [Normalización por campos](#normalización-por-campos)):

$$w_{\text{bruto}}(t, c) = \mathrm{tf}(t, c) \cdot \mathrm{idf}(t)$$

$$\hat v_c(t) = \frac{w_{\text{bruto}}(t, c)}{\lVert \vec w_c \rVert_2}$$

$$\vec d = \sum_{c} w_c \cdot \hat v_c$$

$\vec d$ en sí **no** se vuelve a normalizar a norma 1: su norma
$\lVert \vec d \rVert_2$ se guarda aparte (`norma_total` en el código) y se
usa directamente como denominador al calcular el coseno.

**Vector de la consulta.** Para cada prefijo $p$ escrito por el usuario, se
expande a todo término $t$ del vocabulario que empiece con $p$:

$$w_q(t) = \max_{p \,:\, t \text{ empieza con } p} \Big[\mathrm{idf}(t) \cdot \frac{|p|}{|t|}\Big]$$

**Similitud coseno y score final.**

$$\mathrm{coseno}(\vec q, \vec d) = \frac{\vec q \cdot \vec d}{\lVert \vec q \rVert_2 \, \lVert \vec d \rVert_2}$$

$$\mathrm{ScoreFinal}(q, d) = \mathrm{coseno}(\vec q, \vec d) \times \mathrm{factor\_idioma}(d), \qquad
\mathrm{factor\_idioma}(d) = \begin{cases} 1.10 & \text{si } \mathrm{idioma}(d) = \text{dominante} \\ 0.35 & \text{en otro caso} \end{cases}$$

## La dimensión de idioma

El catálogo incluye **13 pares homógrafos**: palabras escritas exactamente
igual que significan cosas distintas según el idioma.

| Palabra | Español | Otro idioma |
|---|---|---|
| polvo | suciedad en el aire | 🇧🇷 pulpo |
| rato | momento breve | 🇧🇷 ratón |
| vaso | recipiente para beber | 🇧🇷 maceta |
| cena | comida de la noche | 🇧🇷 escena de una película |
| copo | copo de nieve | 🇧🇷 vaso de vidrio |
| oficina | espacio de trabajo | 🇧🇷 taller mecánico |
| pasta | fideos | 🇧🇷 carpeta de documentos |
| berro | planta comestible | 🇧🇷 grito muy fuerte |
| pan | alimento horneado | 🇬🇧 sartén |
| pie | extremidad del cuerpo | 🇬🇧 tarta / pastel |
| red | red de computadoras | 🇬🇧 el color rojo |
| tuna | fruto del nopal | 🇬🇧 atún |
| mole | salsa mexicana | 🇬🇧 topo (animal) |

Para estos pares la parte de términos del vector es prácticamente idéntica
(mismo `nombre`, campos comparables), así que un TF-IDF puro los empataría o
los ordenaría al azar. El desempate no vive en el vector: vive en un ajuste
que se aplica **después** de calcular el coseno.

## El ajuste por idioma

Esto es la implementación concreta de $\mathrm{factor\_idioma}(d)$ en la
ecuación de $\mathrm{ScoreFinal}$ de la sección anterior:

```python
BOOST_IDIOMA_DOMINANTE = 1.10
FACTOR_IDIOMA_SECUNDARIO = 0.35
```

```python
coseno_texto = producto_punto / (norma_q * norma_doc)

if doc["idioma"] == dominante:
    factor_idioma = BOOST_IDIOMA_DOMINANTE
else:
    factor_idioma = FACTOR_IDIOMA_SECUNDARIO

score_final = coseno_texto * factor_idioma
```

El idioma **no** entra al producto punto ni a las normas: la similitud de
términos se calcula primero, igual que en un TF-IDF normal, y solo al final
se multiplica por 1.10 si el documento es del idioma elegido en el selector,
o por 0.35 si no lo es. El selector (🇲🇽 Español · 🇬🇧 Inglés · 🇧🇷 Portugués)
no filtra ni traduce nada — solo decide qué idioma recibe el `factor_idioma`
más alto en esa consulta.

### La proporción entre idiomas es constante

Cuando dos homógrafos comparten casi el mismo coseno de términos (el caso
típico de estos pares), el que gana el idioma dominante termina con un score
`1.10 / 0.35 ≈ 3.14` veces mayor que el otro — sin importar el catálogo,
porque esa razón depende solo de las dos constantes, no del contenido. Con el
mismo texto escrito, cambiar el selector invierte cuál de los dos documentos
recibe el multiplicador alto:

```
q = "polvo"  modo 🇲🇽 es  ->  Polvo (es) ≈ 0.99   Polvo (pt) ≈ 0.31
q = "polvo"  modo 🇧🇷 pt  ->  Polvo (pt) ≈ 0.99   Polvo (es) ≈ 0.31
```

Los puntajes salen espejados entre los dos modos, pero **no** salen parejos
entre sí: la brecha entre el dominante y el secundario es grande a propósito,
para que el desempate sea inequívoco.

### Un efecto secundario: el score puede superar 1.0

Como el ajuste multiplica el coseno en vez de mezclarse con él, y
`BOOST_IDIOMA_DOMINANTE > 1`, un documento cuyo vector de términos es casi
idéntico a la consulta (coseno cercano a 1.0, típico de un `nombre` corto que
coincide exacto y sin mucho ruido de `categoria`/`descripcion`) puede terminar
con `score_final > 1.0`. El código no lo limita, y la interfaz lo dibujaría
como una barra de relevancia por encima del 100%. Ver
[Limitaciones conocidas](#limitaciones-conocidas).

## Normalización por campos

Para que el ajuste anterior funcione bien hay que evitar un sesgo del modelo.
El catálogo está desbalanceado (117 documentos en español contra 16 y 18),
así que las palabras de una descripción en portugués son raras vistas sobre
el total y reciben un idf altísimo. Con una bolsa de palabras común, esa
descripción se llevaría una porción desproporcionada del vector y le robaría
peso a su propio nombre: el documento extranjero perdería por un artefacto
del corpus, no por semántica.

La solución **no** fue calcular el idf por idioma (eso rompe la
comparabilidad: el mismo término valdría distinto según quién lo escribiera).
El idf sigue siendo global; lo que cambia es que cada campo se vectoriza y se
**normaliza por separado** antes de combinarse:

```python
CAMPOS = (("nombre", 0.60), ("categoria", 0.15), ("descripcion", 0.25))
```

Así el nombre aporta siempre el 60% de la dirección del vector, sin importar
qué tan largas o raras sean las palabras de la descripción. Es el enfoque de
recuperación por campos (la idea detrás de BM25F).

## Cómo se construye el índice

`construir_indice(CATALOGO)` corre **una sola vez**, al importarse el módulo
(justo al arrancar `python app.py`), no en cada request. Devuelve cuatro
estructuras que el resto de la app solo lee:

| Estructura | Tipo | Qué contiene |
|---|---|---|
| `IDF` | `dict[str, float]` | $\mathrm{idf}(t)$ de cada término — global, no por campo ni por idioma. |
| `VOCABULARIO` | `list[str]` ordenada | Las llaves de `IDF`, alfabéticamente. |
| `VECTORES_DOCUMENTOS` | `list[(dict, float)]` | Por cada `doc_id`: su $\vec d$ ya combinado entre campos, y $\lVert \vec d \rVert_2$ precalculada. |
| `INDICE_INVERTIDO` | `dict[str, list[int]]` | Por cada término, la lista de `doc_id` donde aparece — el *posting list* clásico de un SRI. |

Pasos, en el orden en que corren dentro de la función:

1. **Tokenización por campo.** Cada documento se tokeniza tres veces por
   separado (`nombre`, `categoria`, `descripcion`), guardando los tokens de
   cada campo aparte — es lo que permite normalizar y pesar cada campo de
   forma independiente en el paso 4.

2. **Document frequency ($\mathrm{df}$).** Por documento se arma un solo
   `set` con la unión de tokens de sus tres campos, y se incrementa
   `df[termino]` **una vez por documento**, no una vez por ocurrencia ni una
   vez por campo:

   ```python
   for campos in tokens_por_doc:
       presentes = set()
       for tokens in campos.values():
           presentes.update(tokens)
       for termino in presentes:
           df[termino] += 1
   ```

   Un término que aparece en `nombre` y también en `descripcion` del mismo
   documento solo cuenta 1 para su `df`, no 2. Es lo que hace que
   $\mathrm{idf}(t)$ mida "en cuántos documentos distintos aparece $t$" — la
   definición estándar — y no se infle por repeticiones entre campos del
   mismo documento.

3. **`IDF` y `VOCABULARIO`.** Con `df` completo se calcula $\mathrm{idf}(t)$
   por término, y se ordena el resultado en `VOCABULARIO`. Que esté ordenada
   es lo que permite que `vector_consulta` use `bisect.bisect_left` para
   saltar directo al primer término que podría empezar con el prefijo
   escrito — búsqueda binaria, $O(\log V)$ para encontrar el punto de
   entrada — en vez de recorrer las $V$ palabras del vocabulario en cada
   tecla presionada.

4. **Vector y norma por documento.** Para cada documento se calcula $\vec d$
   (la combinación ponderada de sus tres campos normalizados, ver
   [Formalización matemática](#formalización-matemática)) y se guarda junto
   con $\lVert \vec d \rVert_2$ ya resuelta — así el coseno de cada consulta
   no recalcula esa norma en cada request, solo el producto punto.

5. **Índice invertido.** Por cada término que quedó en el $\vec d$ de un
   documento (es decir, cada término presente en al menos uno de sus tres
   campos) se agrega ese `doc_id` a `INDICE_INVERTIDO[termino]`. El
   *posting list* de un término es, por construcción, el mismo conjunto de
   documentos que contribuyó a su `df` en el paso 2.

## El idioma desempata, no recupera

Un documento solo entra al conjunto de candidatos si comparte **al menos un
término real** (ya expandido por prefijo) con la consulta. Eso se resuelve
con el índice invertido construido en el paso anterior, antes de que el
ajuste de idioma entre en juego:

```python
candidatos_ids = set()
for termino in terminos_expandidos:
    candidatos_ids.update(INDICE_INVERTIDO.get(termino, []))
```

Un documento que no comparte ningún término nunca llega a `candidatos_ids`,
así que el `factor_idioma` no tiene nada que rescatar. Sin ese filtro previo,
buscar "jicama" devolvería el catálogo entero con puntajes minúsculos, porque
los tres idiomas siempre están activos en la consulta.

**Costo en tiempo de consulta.** Gracias al índice invertido, este paso no
recorre `TOTAL_DOCUMENTOS` (la búsqueda es reactiva — una consulta por cada
tecla en `script.js`); su costo es proporcional a la suma de los *posting
lists* de los términos ya expandidos, no al tamaño del catálogo. Después,
puntuar cada candidato recorre solo los términos de la consulta —
`vector_q.items()` — buscando cada uno con `.get()` en el vector del
documento, nunca al revés:

```python
producto_punto = sum(
    peso_q * vector_doc.get(termino, 0.0)
    for termino, peso_q in vector_q.items()
)
```

Eso hace que puntuar un candidato cueste $O(|\vec q|)$ — el número de
términos expandidos de la consulta — y toda la etapa de scoring,
$O(|\text{candidatos}| \times |\vec q|)$: no depende de qué tan largo sea
el vector del documento, aunque su `descripcion` tenga muchas más palabras
que la consulta. Con 151 documentos la diferencia frente a un recorrido
completo es imperceptible, pero es el mismo mecanismo que hace viable un
buscador reactivo sobre un catálogo bastante más grande.

### Resultado

Un documento extranjero relevante para la consulta aparece siempre, solo que
más abajo, atenuado por el `FACTOR_IDIOMA_SECUNDARIO`. Y cuando la consulta
apunta de verdad a un documento extranjero, gana sin problema:
`"saudade"` → Saudade (pt), `"butterfly"` → Butterfly (en) — ahí no hay
ningún homógrafo compitiendo, así que el resultado es el único candidato y el
boost o la penalización no cambian el orden.

Una consulta como `"fruta tropical"` es un buen ejemplo del comportamiento:
los nombres, categorías y descripciones en español (el idioma dominante por
defecto) se llevan las primeras posiciones, y una fruta genuinamente tropical
descrita en portugués se cuela entre ellas — pero por debajo, penalizada por
el 0.35 y no excluida por él.

## Ponderación por cobertura del prefijo

Al añadir palabras largas al catálogo apareció un efecto secundario: escribir
`"pan"` podía devolver **Pancake** antes que **Pan**, porque "pancake" es un
término más raro y su idf es más alto.

Cada término expandido se pondera también por qué fracción de él ya escribió
el usuario:

```python
cobertura = len(prefijo) / len(termino)   # "pan" -> pan: 3/3 = 1.0 ; pancake: 3/7 = 0.43
peso = IDF[termino] * cobertura
```

Es el criterio de cualquier autocompletado: a menos letras por adivinar, más
probable es la sugerencia. La coincidencia exacta vuelve a ganar sin que las
búsquedas conceptuales se vean afectadas — y como el vocabulario es global,
un prefijo corto en español puede seguir expandiendo hacia un término que
solo aparece en la descripción de un documento etiquetado con otro idioma;
la ponderación por cobertura hace que eso no le gane a la coincidencia
exacta.

## API

`GET /api/buscar?q=...&idioma=es|en|pt` devuelve:

```json
{
  "consulta": "polvo",
  "idioma_dominante": "es",
  "terminos_expandidos": ["polvo"],
  "total_coincidencias": 2,
  "resultados": [
    {"nombre": "Polvo", "categoria": "Materia", "emoji": "💨",
     "idioma": "es", "idioma_nombre": "Español", "bandera": "🇲🇽",
     "homografo": true, "descripcion": "...", "score": 0.9894},
    {"nombre": "Polvo", "categoria": "Animal", "emoji": "🐙",
     "idioma": "pt", "idioma_nombre": "Portugués", "bandera": "🇧🇷",
     "homografo": true, "descripcion": "...", "score": 0.3148}
  ]
}
```

Notas sobre el contrato:

- `resultados` se recorta a los primeros **12** candidatos
  (`LIMITE_SUGERENCIAS`), ordenados por `score_final` descendente.
  `total_coincidencias` sí cuenta **todos** los candidatos con score > 0, no
  solo los 12 devueltos.
- `homografo: true` marca los documentos que comparten `nombre` con otro
  resultado **dentro de esa misma página de 12**. Es solo una señal para la
  interfaz (que los etiqueta como *falso amigo*); no altera el ranking, que
  ya decidió `R(qk, dj)`.
- `idioma` inválido o ausente cae a `"es"` (`IDIOMA_POR_DEFECTO`).
- Una consulta sin texto ni emojis útiles (`"!!!"`) devuelve cero resultados.
- Con `q` vacío no hay ranking: se devuelve el catálogo completo, ordenado
  primero por si el documento es del idioma dominante y luego por `nombre`
  alfabético, sin `score` (`null`). Así carga la página al abrirse.

## Estructura

```
buscador-predictivo/
├── app.py              # rutas Flask (delgado)
├── sri.py              # D, Q, F, R(qk,dj) + ajuste por idioma (sin Flask, sin I/O)
├── emojis.py           # detectar, normalizar e interpretar emojis de la consulta
├── repositorio.py      # fuente de datos: JSON o SQL + esquema de tablas
├── migrar.py           # crea tablas e importa catalogo.json a SQL
├── catalogo.json       # el catálogo original (fuente por defecto / semilla para SQL)
├── requirements.txt    # Flask + SQLAlchemy
├── templates/
│   └── index.html
└── static/
    ├── style.css        # banderas, marca de falso amigo, barra de relevancia
    └── script.js
```

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
python app.py                      # usa catalogo.json
```

## Emojis en la consulta

Se puede buscar con emojis solos (`🐙`), mezclados con texto (`polvo 🐙`) o
pegados a él (`polvo🐙`). `emojis.extraer_emojis()` los separa del texto
(entiende tonos de piel, secuencias ZWJ como `👨‍🏫`, banderas y keycaps) y el
resto de la consulta sigue el pipeline de siempre. Cada emoji se entiende de
tres formas:

1. **Coincidencia directa.** Se compara con el campo `emoji` de los documentos
   mediante un índice `emoji → doc_id`. Ignora selectores de variación y tonos
   (`⚖` = `⚖️`, `👍🏽` = `👍`), y funciona entre idiomas: `📈` trae *Inversión*,
   *Investment* e *Investimento*. Los documentos sin emoji no cuentan (el `📄`
   de relleno no se indexa).
2. **Significado curado.** `CONCEPTOS_EMOJI` (en `emojis.py`) liga emojis a
   palabras ancla de `GRUPOS_SEMANTICOS`, y de ahí hereda sus equivalentes en
   es/en/pt: `😭` (que el catálogo no usa) → `triste` → *Tristeza*, *Sadness*.
3. **Nombre Unicode**, solo si el catálogo no usa ese emoji: `🦄` → `unicorn`.

Con coincidencia directa, el score deja de ser solo el coseno:

$$\mathrm{base} = (1-W)\cdot\mathrm{coseno} + W\cdot m, \qquad
W = \begin{cases} 0.85 & \text{solo emojis} \\ 0.50 & \text{emojis + texto} \end{cases}$$

donde $m = 1$ si el emoji del documento coincide. Sin emojis, $W = 0$ y el
ranking es exactamente el de antes.

**El emoji gana al selector de idioma.** Un documento que coincide con el emoji
recibe `FACTOR_IDIOMA_CON_EMOJI = 0.85` en lugar de `0.35` (el dominante sigue
con `1.10`). Así el emoji desempata a los falsos amigos aunque el selector diga
otra cosa:

```
q = "polvo"    modo 🇲🇽 es  ->  Polvo (es) 0.99   Polvo (pt) 0.33
q = "polvo 🐙" modo 🇲🇽 es  ->  Polvo (pt) 0.82   Pulpo (es) 0.55   Polvo (es) 0.50
```

Entre documentos que comparten emoji (`💃` lo usan 17) el orden de empate es
alfabético por `nombre`. La respuesta de la API incluye `emojis`
(`[{"emoji": "🐙", "coincidencias": 2}]`) y cada resultado un `emoji_coincide`.

## Fuente de datos: JSON o SQL

`sri.py` solo recibe un `RepositorioCatalogo` con un método, `listar()`, que
devuelve dicts con `id, nombre, categoria, descripcion, emoji, idioma`. De
dónde salgan es asunto de `repositorio.py`, y se elige con `DATABASE_URL`:

| `DATABASE_URL` | Fuente |
|---|---|
| sin definir | `catalogo.json` |
| `sqlite:///catalogo.db` | SQLite |
| `postgresql://usuario:clave@host/base` | PostgreSQL (`pip install "psycopg[binary]"`) |
| `mysql+pymysql://usuario:clave@host/base?charset=utf8mb4` | MySQL / MariaDB (`pip install pymysql`; `utf8mb4` es necesario por los emojis) |

```bash
python migrar.py                                   # crea tablas e importa a sqlite:///catalogo.db
DATABASE_URL=sqlite:///catalogo.db python app.py
```

Esquema (en `repositorio.py`): `categorias(id, nombre UNIQUE)` y
`documentos(id, nombre, descripcion, emoji, idioma, categoria_id → categorias)`.
La categoría deja de ser texto repetido en cada fila; el motor la recibe ya
resuelta a su nombre, así que el ranking es idéntico al de la versión JSON.
`migrar.py` se niega a importar sobre una tabla con datos salvo `--reemplazar`.

**Cambios en caliente.** El índice se construye al arrancar. Con
`RECARGA_SEGUNDOS=300` se reconstruye solo cuando una consulta llega con más de
5 minutos de antigüedad; si la base falla en ese momento se sigue sirviendo el
índice anterior. Con `0` (por defecto) hay que reiniciar la app.

Abrir `http://localhost:5000`, escribir `polvo` (o `pie`, `pan`, `rato`,
`tuna`) y **cambiar de idioma con el selector** sin borrar el texto: el orden
se invierte en el momento.

## Limitaciones conocidas

- `CONCEPTOS_EMOJI` es curado a mano y corto a propósito: un emoji ambiguo
  (`🦖` ¿"grande"?) mete más ruido que ayuda. Fuera de él, solo hay coincidencia
  directa o el nombre Unicode (en inglés). No hay traducción de nombres de
  emoji a es/pt (eso requeriría los datos CLDR).
- El emoji compuesto que el catálogo no tenga idéntico no coincide por partes:
  `👩‍🏫` no encuentra un documento con `👨‍🏫` (se interpreta por nombre).
- Los empates exactos de score se ordenan por `nombre`; antes quedaban en el
  orden interno de un `set`. Los scores no cambian, solo quién entra al corte
  de 12 cuando hay más empatados.

- El idioma dominante lo elige el usuario a mano. Un sistema real lo
  **detectaría** a partir de la consulta o lo aprendería del historial, en vez
  de pedir un clic.
- El ajuste de idioma es multiplicativo y sin tope: con
  `BOOST_IDIOMA_DOMINANTE = 1.10`, un documento con coseno de términos muy
  alto puede terminar con `score_final` por encima de 1.0 (más del 100% en la
  barra de relevancia). No hay `min(score, 1.0)` en el código.
- `1.10` y `0.35` son constantes fijas, iguales para todo el catálogo. No se
  recalibran según cuántos documentos hay por idioma ni según qué tan cerca
  esté el coseno de un par específico — a diferencia de los pesos de `CAMPOS`,
  que sí se combinan proporcionalmente.
- El etiquetado `homografo: true` solo compara dentro de los 12 resultados
  devueltos. Un documento cuyo par homógrafo cayó fuera de esa página no se
  marca como falso amigo, aunque exista en el catálogo.
- La expansión de prefijos de 1-2 letras sigue siendo ambigua por naturaleza:
  con tan poca información, ningún criterio puramente léxico puede acertar.
- La normalización NFD elimina la `ñ` igual que un acento (ver
  [Preprocesamiento de texto](#preprocesamiento-de-texto)): `"año"` y `"ano"`
  tokenizan idéntico. No afecta al catálogo actual, pero es un riesgo real
  si se agregan palabras que dependan de la `ñ` para distinguirse.
- El vocabulario y el índice (ver
  [Cómo se construye el índice](#cómo-se-construye-el-índice)) se calculan
  al arrancar y, opcionalmente, cada `RECARGA_SEGUNDOS`
  (ver [Fuente de datos](#fuente-de-datos-json-o-sql)). Reconstruirlo es
  completo, no incremental; con catálogos de cientos de miles de filas habría
  que pasar a actualizaciones parciales.
- Los pesos de `CAMPOS` están puestos a mano. Con datos de uso reales
  (qué resultado terminó eligiendo la gente) se aprenderían, que es lo que
  hace cualquier buscador en producción.
