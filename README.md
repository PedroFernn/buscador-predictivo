# 🔮 Buscador Predictivo Multilenguaje — SRI

Buscador reactivo (una consulta por cada tecla) sobre un catálogo en **español, inglés y portugués**,
construido como un *Sistema de Recuperación de Información* (SRI) con modelo vectorial TF-IDF.
Además del coseno de términos, el orden final incorpora un prior de idioma elegido por el usuario,
emojis, reacciones (👍 😍 👎), aprendizaje a partir de los resultados que la gente elige y sugerencias
ordenadas por la frecuencia real de las consultas.

```
SRI = { D, Q, F, R(qk, dj) }
```

| Componente | Qué es en este proyecto |
|---|---|
| **D** | Catálogo de documentos (el de ejemplo trae 1 144: 600 es, 276 en, 268 pt) en `catalogo.json` o en una base SQL. Cada uno con `nombre`, `categoria`, `descripcion`, `emoji` e **`idioma`**. |
| **Q** | Lo que el usuario escribe en tiempo real, aunque esté incompleto; puede incluir abreviaturas y emojis. |
| **F** | Modelo de Espacio Vectorial TF-IDF con normalización **por campo** (estilo BM25F). El idioma no forma parte del vector. |
| **R(qk, dj)** | Similitud coseno, reescalada por idioma/emoji y luego ponderada por reacciones y aprendizaje. |
## Tabla de contenidos

1. [Qué hace](#1-qué-hace) · 2. [Arquitectura](#2-arquitectura) · 3. [Estructura del proyecto](#3-estructura-del-proyecto)
4. [Instalación y configuración](#4-instalación-y-configuración) · 5. [Modelo de recuperación](#5-modelo-de-recuperación-sri)
6. [Idioma y falsos amigos](#6-idioma-y-falsos-amigos) · 7. [Emojis](#7-emojis-en-la-consulta)
8. [Del score al orden final](#8-del-score-al-orden-final) · 9. [Sugerencias por frecuencia](#9-sugerencias-por-frecuencia-zipf-y-heaps)
10. [API](#10-referencia-de-la-api) · 11. [Interfaz web](#11-interfaz-web) · 12. [Datos](#12-datos-y-repositorios)
13. [Pruebas](#13-pruebas) · 14. [Extender](#14-cómo-extender-el-sistema) · 15. [Limitaciones](#15-limitaciones-conocidas)
16. [Qué cambió respecto a la versión anterior](#16-qué-cambió-respecto-a-la-versión-anterior)

------
## 1. Qué hace

- **Búsqueda reactiva** TF-IDF con expansión por prefijo: escribir `pan` ya encuentra *Pan* y *Pancake*.
- **Selector de idioma dominante** (🇲🇽 es · 🇬🇧 en · 🇧🇷 pt): no filtra ni traduce, solo decide qué idioma
  recibe el factor más alto. Resuelve los *falsos amigos* (`polvo`, `pie`, `pan`, …).
- **Emojis como consulta**: solos (`🐙`), mezclados (`polvo 🐙`) o pegados (`polvo🐙`).
- **Consulta simplificada**: abreviaturas (`ct` → `caro`), palabras de relleno, sinónimos es/en/pt y
  *modo sinopsis* (prioriza la descripción para consultas descriptivas).
- **Reacciones** (me gusta / me encanta / no me gusta): factor acotado, con confianza (Beta) y decaimiento.
- **Aprendizaje por clics** con CTR corregido por posición: qué eligió la gente, y qué se le mostró.
- **Sugerencias por frecuencia real** de consultas (Zipf), sobre una tabla con ventana deslizante.
- **Señales persistentes**: reacciones, clics, impresiones y consultas viven en SQLite y sobreviven a
  reinicios; con un archivo en disco las comparten todos los workers.
- **Historial local** de las últimas 10 búsquedas en el navegador.
- **Fuente de datos intercambiable**: JSON o SQL (SQLite, PostgreSQL, MySQL) con recarga en caliente.

------
## 2. Arquitectura

Capas con dependencias en un solo sentido (cada una solo conoce a las de abajo):

```
 static/js/ + templates/        interfaz (módulos ES, sin innerHTML)
        │  HTTP/JSON
   api/                         blueprints delgados: validan entradas y llaman a los servicios
        │
   busqueda/        senales/    el motor (funciones puras)  ·  lo que aprende el sistema del uso
        │              │
        └── nucleo/ ───┘        texto, léxico, emojis, estadística (sin estado, sin Flask)
   datos/                       repositorios del catálogo (JSON / SQL)
   app.py + config.py           create_app(): único lugar que cablea todo (inyección de dependencias)
```

`busqueda/` **no importa** `senales/`: el `Buscador` recibe un objeto con `pesos(consulta, ids)` y
`conteos(id)` (ver `busqueda/buscador.py`). Sin ese objeto el motor es recuperación pura, que es lo que
usan `scripts/calibrar.py` y las pruebas de regresión. No hay estado global: `create_app()` construye
el catálogo, las señales y el buscador y los deja en `app.extensions`.

### Flujo de una búsqueda

```
GET /api/buscar?q=...&idioma=...
  1. analizar      emojis → conceptos · abreviaturas · relleno · sinónimos · prefijos → vector de consulta
  2. puntuar       acumula peso_q × peso_d por término sobre los postings → coseno; mezcla con emoji e idioma
  3. señales       senales.pesos(consulta, ids de los candidatos) → (reacciones, aprendizaje)
  4. ordenar       score × peso, desempate por nombre
  5. serializar    primeros 12 + desglose del score + conteos de reacciones
```

Cada paso es una función pequeña y probada por separado (`busqueda/consulta.py`, `ranking.py`).

------
## 3. Estructura del proyecto

```
buscador-predictivo/
├── app.py                 create_app(): ensambla config + repositorio + señales + buscador + blueprints
├── config.py              Config: único módulo que lee variables de entorno
├── requirements.txt · requirements-dev.txt · pytest.ini · .gitignore
├── nucleo/
│   ├── texto.py           normalizar, tokenizar, clave_consulta (única copia; la ñ es una letra)
│   ├── lexico.py          ABREVIATURAS, STOPWORDS, GRUPOS_SEMANTICOS → SINONIMOS
│   ├── emojis.py          extracción de emojis y significado curado (CONCEPTOS_EMOJI)
│   └── estadistica.py     ajuste_loglog, ajuste_zipf
├── busqueda/
│   ├── parametros.py      todas las constantes ajustables (pesos, idioma, emoji, sinónimos, límite)
│   ├── indice.py          construir_indice(): idf, postings por modo, emoji → documentos
│   ├── consulta.py        interpretar_consulta, vector_consulta, analizar (emojis + texto)
│   ├── ranking.py         puntuar, ordenar, explicar, decorar (funciones puras)
│   ├── buscador.py        Buscador: fachada (recarga en caliente, señales opcionales)
│   └── evaluacion.py      nDCG / MRR / Éxito@3, conjunto de oro, rejilla de constantes
├── senales/
│   ├── almacen.py         AlmacenEventos: tabla única `eventos` en SQLite (WAL)
│   ├── reacciones.py      Beta suavizado + decaimiento
│   ├── clics.py           CTR suavizado y corregido por posición, por consulta y por término
│   ├── consultas.py       HistorialConsultas: sugerencias por frecuencia (SQL + ventana + cache)
│   ├── moderacion.py      datos personales y lista de bloqueo
│   └── servicio.py        Senales: fachada única y `pesos()`; persistencia y sincronización entre procesos
├── api/
│   ├── buscar.py          GET /  ·  GET /api/buscar
│   ├── senales.py         POST /api/reaccion  ·  POST /api/seleccion
│   ├── sugerencias.py     GET /api/sugerencias  ·  POST /api/consultas  ·  GET /api/historial/estadisticas
│   └── validacion.py      entero(), posicion(), objeto_json(): validación en un solo lugar
├── datos/
│   ├── repositorio.py     RepositorioJSON / RepositorioSQL (SQLAlchemy)
│   └── migrar.py          catalogo.json → base SQL
├── scripts/
│   ├── calibrar.py        rejilla de constantes contra evaluacion/oro.csv
│   └── simular.py         Zipf + Heaps sobre un flujo sintético, latencia de sugerir()
├── evaluacion/            aquí va oro.csv (ver LEEME.md)
├── static/{js/*.js, style.css} · templates/index.html
└── tests/                 pytest (ver sección 13)
```

------
## 4. Instalación y configuración

### Requisitos

**Python 3.9+** (anotaciones `list[dict]`), **Flask 2.0+** y **SQLAlchemy 1.4+**. `nucleo/`, `busqueda/` y
`senales/` solo usan la biblioteca estándar (SQLite viene con Python).

```bash
pip install -r requirements.txt        # o requirements-dev.txt para correr las pruebas
python app.py                          # http://localhost:5000, usa catalogo.json (en la raíz del proyecto)
```

Para otras bases: `pip install "psycopg[binary]"` (PostgreSQL) o `pip install pymysql` (MySQL/MariaDB).

### Variables de entorno (todas opcionales)

| Variable | Defecto | Efecto |
|---|---|---|
| `DATABASE_URL` | sin definir | Fuente del catálogo. Sin definir usa `catalogo.json`. Acepta `sqlite:///catalogo.db`, `postgresql://u:c@host/db`, `mysql+pymysql://u:c@host/db?charset=utf8mb4` (el `utf8mb4` es necesario por los emojis). `postgres://` se corrige solo. |
| `RECARGA_SEGUNDOS` | `0` | Con `> 0`, el índice se reconstruye cuando una consulta llega con más de esa antigüedad. `0` = solo al arrancar. |
| `SENALES_DB` | `./senales.db` | Archivo SQLite con reacciones, clics, impresiones y consultas. `:memory:` = volátil (pruebas). |
| `HISTORIAL_VENTANA_DIAS` | `7` | Ventana deslizante de las sugerencias por frecuencia. |
| `HISTORIAL_MIN_FRECUENCIA` | `3` | Veces que debe repetirse una consulta (en la ventana) para sugerirse. |
| `HISTORIAL_BLOQUEADOS` | vacío | Términos separados por coma que nunca se cuentan ni se sugieren. |
| `SENALES_RETENCION_DIAS` | `90` | Cuánto se conservan clics e impresiones (las reacciones se conservan: decaen). |

Un valor inválido (`abc`) cae al defecto en vez de impedir el arranque.

### Producción

```bash
SENALES_DB=/var/lib/buscador/senales.db gunicorn -w 4 "app:create_app()"
```

- Con `SENALES_DB` en un archivo, **los workers comparten las señales**: SQLite en modo WAL admite varios
  lectores y un escritor (con espera de hasta 5 s). Cada proceso mantiene agregados en memoria y los
  reconstruye desde el log cuando otro proceso escribió (a lo más cada 5 s, ver `Senales._sincronizar`):
  una reacción hecha en el worker A se ve en el B con ese retraso, no al reiniciar.
- Las sugerencias leen siempre de la tabla; su cache de prefijos (30 s) es por proceso.
- `app.run(debug=True)` es solo para desarrollo.

------
## 5. Modelo de recuperación (SRI)

### 5.1 Preprocesamiento de texto

Catálogo y consulta pasan por el mismo pipeline (`normalizar` + `tokenizar` en `nucleo/texto.py`):

1. **Minúsculas** y **descomposición NFD**.
2. **La `ñ` se protege**: `n` + virgulilla se reemplaza por `ñ` antes de quitar marcas. Es otra letra, no una
   `n` acentuada: `"año"` y `"ano"` son distintos para el motor, y los grupos semánticos usan la ñ (`pequeño`).
3. **Eliminación de marcas** (categoría Unicode `Mn`): `"é"` → `e`.
4. **Regex** `[a-z0-9ñ]+`; todo lo demás separa tokens.

`"Jícama"`, `"CAFÉ"` y `"niño"` tokenizan a `jicama`, `cafe` y `niño`. `clave_consulta` aplica las mismas
reglas pero conserva los emojis como tokens y descarta sus tonos de piel.

### 5.2 Formalización

**IDF suavizado.** Con $N$ documentos y $\mathrm{df}(t)$ documentos que contienen $t$:

$$\mathrm{idf}(t) = \log_{10}\!\left(1 + \frac{N}{\mathrm{df}(t)}\right)$$

El `+1` evita $\mathrm{idf}=0$ en términos presentes en todos los documentos. El $\mathrm{tf}(t,c)$ es la
cuenta cruda dentro del campo $c$ (sin atenuar). Cada documento cuenta **una vez** por término para el
`df`, aunque el término aparezca en varios campos.

**Vector de documento.** Para cada campo $c$ con peso $w_c$:

$$w_{\text{bruto}}(t, c) = \mathrm{tf}(t, c)\cdot \mathrm{idf}(t), \qquad
\hat v_c(t) = \frac{w_{\text{bruto}}(t, c)}{\lVert \vec w_c \rVert_2}, \qquad
\vec d = \sum_{c} w_c\,\hat v_c$$

$\vec d$ no se renormaliza: su norma $\lVert\vec d\rVert_2$ se guarda aparte y es el denominador del coseno.

**Vector de consulta.** Cada prefijo $p$ escrito se expande a todo término $t$ del vocabulario que empiece
con $p$:

$$w_q(t) = \max_{p\,:\,t\text{ empieza con }p}\Big[\mathrm{idf}(t)\cdot\frac{|p|}{|t|}\Big]$$

**Coseno:**

$$\mathrm{coseno}(\vec q,\vec d)=\frac{\vec q\cdot\vec d}{\lVert\vec q\rVert_2\,\lVert\vec d\rVert_2}$$

### 5.3 Pesos por campo y modos de búsqueda

Cada campo se vectoriza y normaliza **por separado** antes de combinarse. Así una descripción larga o
con palabras raras no le roba peso al nombre (el catálogo está desbalanceado entre idiomas, y el idf es
global para mantener comparables los términos).

| Modo | `nombre` | `categoria` | `descripcion` | Cuándo se activa |
|---|:-:|:-:|:-:|---|
| `nombre` (por defecto) | 0.60 | 0.15 | 0.25 | consultas cortas y literales |
| `sinopsis` | 0.25 | 0.10 | 0.65 | hay abreviaturas, o algún término es un concepto con sinónimos, o la consulta tiene ≥ 3 términos únicos |

### 5.4 Interpretación de la consulta (`interpretar_consulta`)

1. **Abreviaturas / jerga** (`ABREVIATURAS`): `ct → caro`, `q/k → que`, `xq/pq → porque`, `tb → tambien`,
   `x → por`, `xa → para`, `d → de`, `bn → bien`, `pls/plz → please`, `thx → thanks`, … Los términos
   expandidos se tratan como **exactos** (sin expansión por prefijo).
2. **Palabras de relleno** (`STOPWORDS`, es/en/pt): se eliminan. Si solo había relleno (`"es la"`), se
   busca literal por prefijo.
3. **Términos de emoji** (`extra`): se agregan a los del texto (ver [§7](#7-emojis-en-la-consulta)).
4. **Sinónimos** (`GRUPOS_SEMANTICOS`, 25 grupos es/en/pt): buscar `caro` activa `expensive`, `costoso`,
   `luxo`… Los sinónimos pesan `FACTOR_SINONIMO = 0.70` respecto a lo escrito literalmente.
5. **Cobertura mínima de conceptos**: si el usuario escribió una palabra conocida completa (`caro`), sus
   prefijos solo cuentan si cubren al menos `COBERTURA_MIN_CONCEPTO = 70 %` del término (evita `caroco`).

### 5.5 Ponderación por cobertura del prefijo

Escribir `pan` podía devolver **Pancake** antes que **Pan**, porque *pancake* es más raro (idf mayor). Por
eso cada término expandido se pondera por la fracción que el usuario ya escribió:

```python
cobertura = len(prefijo) / len(termino)   # "pan" → pan: 3/3 = 1.0 ; pancake: 3/7 = 0.43
peso = IDF[termino] * cobertura
```


### 5.6 Índice (`construir_indice`)

Corre al arrancar y, opcionalmente, cada `RECARGA_SEGUNDOS` (`Buscador.recargar()`, con intercambio
atómico: las consultas en curso siguen con el índice anterior; si la base falla se conserva el anterior).
Devuelve un `Indice` inmutable:

| Campo | Contenido |
|---|---|
| `catalogo` | Documentos ya saneados (`idioma` válido, `emoji` por defecto `📄`, `NULL` → `""`). Se descartan los que no tienen ni nombre ni descripción. La posición en la lista es la identidad **interna** del documento. |
| `ids` | Conjunto de `id` de repositorio presentes (la API lo usa para rechazar ids inexistentes). |
| `idf` | $\mathrm{idf}(t)$ global por término. |
| `vocabulario` | Llaves de `idf`, **ordenadas**: permite `bisect_left` para saltar al primer término con el prefijo (O(log V)). |
| `postings` | Por modo: `término → [(posición, peso)]`, con el peso del término en el vector combinado del documento. |
| `normas` | Por modo: norma del vector de cada documento. |
| `emoji_a_docs` | `clave de emoji normalizada → [posición]`. Se lee del dato crudo: el `📄` de relleno no cuenta. |

### 5.7 Candidatos y costo

Un documento solo entra al conjunto de candidatos si comparte **al menos un término expandido** con la
consulta o si su emoji coincide. El idioma desempata, no recupera: sin ese filtro, `jicama` devolvería el
catálogo entero con puntajes minúsculos.

El producto punto se **acumula por término**: para cada término de la consulta se recorren sus postings y se
suma `peso_q × peso_d` al documento. El costo es O(postings tocados) y no depende del largo de las
descripciones ni de cuántos términos del vector de cada documento no aparecen en la consulta (antes: un
`.get()` por término de la consulta y por candidato). Las señales de uso se aplican **solo a los candidatos**
recuperados, no a todo el catálogo.

## 6. Idioma y falsos amigos

El catálogo incluye **13 pares homógrafos**: la misma palabra con significados distintos según el idioma.

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

El vector de términos de un par es casi idéntico, así que un TF-IDF puro los empataría. El desempate se
aplica **después** del coseno:

```python
BOOST_IDIOMA_DOMINANTE   = 1.10   # documento del idioma elegido
FACTOR_IDIOMA_CON_EMOJI  = 0.85   # otro idioma, pero coincide con el emoji escrito
FACTOR_IDIOMA_SECUNDARIO = 0.35   # otro idioma, sin emoji coincidente
```

$$\mathrm{ScoreFinal}(q,d)=\mathrm{base}(q,d)\times\mathrm{factor\_idioma}(d)$$

La razón entre dominante y secundario es $1.10/0.35\approx3.14$, independiente del catálogo. Con el mismo
texto, cambiar el selector invierte quién recibe el multiplicador alto:

```
q = "polvo"  modo 🇲🇽 es  ->  Polvo (es) ≈ 0.99   Polvo (pt) ≈ 0.31
q = "polvo"  modo 🇧🇷 pt  ->  Polvo (pt) ≈ 0.99   Polvo (es) ≈ 0.31
```

Un documento extranjero relevante aparece siempre, solo que más abajo. Si la consulta apunta de verdad a
él (`"saudade"`, `"butterfly"`), gana sin problema porque no hay homógrafo compitiendo.

> **Efecto conocido:** como el boost multiplica y es `> 1`, `ScoreFinal` puede superar 1.0 (la barra de
> relevancia de la interfaz pasaría del 100 %). No hay `min(score, 1.0)`.

## 7. Emojis en la consulta

`emojis.extraer_emojis()` separa los emojis del texto (entiende tonos de piel, secuencias ZWJ como `👨‍🏫`,
banderas y *keycaps*); el resto sigue el pipeline normal. Cada emoji se entiende de tres formas:

1. **Coincidencia directa** con el campo `emoji` de los documentos, vía el índice `emoji → doc_id`. Ignora
   selectores de variación y tonos (`⚖` = `⚖️`, `👍🏽` = `👍`) y funciona entre idiomas: `📈` trae *Inversión*,
   *Investment* e *Investimento*.
2. **Significado curado** (`CONCEPTOS_EMOJI` en `nucleo/emojis.py`): liga emojis a palabras ancla de
   `GRUPOS_SEMANTICOS`, y de ahí hereda sus equivalentes es/en/pt (`😭` → `triste` → *Tristeza*, *Sadness*).
3. **Nombre Unicode**, solo si el catálogo no usa ese emoji: `🦄` → `unicorn`.

Con coincidencia directa, el score deja de ser solo el coseno:

$$\mathrm{base}=(1-W)\cdot\mathrm{coseno}+W\cdot m,\qquad
W=\begin{cases}0.85&\text{solo emojis}\\0.50&\text{emojis + texto}\end{cases}$$

con $m=1$ si el emoji del documento coincide. Sin emojis $W=0$ y el ranking es el de siempre. El emoji
**gana al selector de idioma** (`FACTOR_IDIOMA_CON_EMOJI = 0.85` en lugar de `0.35`):

```
q = "polvo"    modo 🇲🇽 es  ->  Polvo (es) 0.99   Polvo (pt) 0.33
q = "polvo 🐙" modo 🇲🇽 es  ->  Polvo (pt) 0.82   Pulpo (es) 0.55   Polvo (es) 0.50
```

Entre documentos que comparten emoji (`💃` lo usan 17) el empate exacto se resuelve por `nombre`
(alfabético). La respuesta incluye `emojis` (`[{"emoji": "🐙", "coincidencias": 2}]`) y cada resultado un
`emoji_coincide`.


------
## 8. Del score al orden final

El **orden** de los resultados no es el score mostrado. El score (`score`, la insignia de relevancia) solo
refleja similitud + idioma + emoji; el orden además multiplica por un **peso** de señales de usuario:

$$\mathrm{orden}(q,d)=\underbrace{\mathrm{ScoreFinal}(q,d)}_{\texttt{score}}\times\underbrace{\mathrm{peso\_reacciones}(d)\times\mathrm{factor\_aprendizaje}(q,d)}_{\texttt{peso}}$$

Desempate: `nombre` ascendente. Se devuelven los primeros `LIMITE_RESULTADOS = 12`; `total_coincidencias`
cuenta todos los candidatos con score > 0. Los dos factores salen de **una sola función**,
`Senales.pesos(consulta, ids)`, y valen exactamente 1.0 cuando no hay señales (el ranking queda idéntico al
de la recuperación pura). Todas las señales son filas de una misma tabla de eventos:

| `tipo` | `doc_id` | `consulta` | `posicion` | Para qué sirve |
|---|:-:|:-:|:-:|---|
| `me_gusta` · `me_encanta` · `no_me_gusta` | ✓ | | | evidencia de reacciones |
| `clic` | ✓ | clave | ✓ | numerador del CTR |
| `impresion` | ✓ | clave | ✓ | denominador del CTR |
| `consulta` | | clave | | frecuencia → sugerencias (con la forma original en `texto`) |

### 8.1 Reacciones (`senales/reacciones.py`)

| Reacción | Puntos |
|---|:-:|
| `me_gusta` | +1.0 |
| `me_encanta` | +2.0 |
| `no_me_gusta` | −1.5 (evidencia en contra) |

Valoración suavizada con prior Beta(2, 2), sobre evidencia que decae con vida media de 21 días:

$$v=\frac{P+a}{P+N+a+b},\qquad \mathrm{peso\_reacciones}=1+0.5\,(2v-1)\in(0.5,\;1.5)$$

Sin reacciones vale exactamente 1.0; pocas reacciones pesan menos que muchas; la proporción real manda con
mucha evidencia. **No hay prior Zipf**: antes el rango por puntos premiaba (+30 %) al que ya estaba arriba. Los
conteos brutos que muestra la interfaz no decaen; el decaimiento se calcula en cada consulta (ya no hay
cache de pesos de una hora).

### 8.2 Aprendizaje por clics (`senales/clics.py`)

Dos mapas, ambos con `[clics ponderados, impresiones]` por documento: por **consulta exacta** (peso 2) y por
**término** (peso 1, sin stopwords). Elegir *"pan dulce"* también enseña algo a *"pan"*.

- **Corrección por posición.** Un resultado en el lugar $k$ se clica menos por estar más abajo, no por ser
  peor. Cada clic se pondera por $1/P(\text{examinar }k)\approx 1+\log_2 k$ (tope 4).
- **CTR suavizado.** Con $C$ = clics ponderados e $I$ = impresiones (sumados con los pesos exacta/término):

$$\mathrm{ctr}=\min\Big(1,\frac{C+\alpha}{I+\alpha+\beta}\Big),\quad p_0=\frac{\alpha}{\alpha+\beta}=0.1,\qquad
\mathrm{factor\_aprendizaje}=1+0.4\tanh\frac{\mathrm{ctr}-p_0}{0.25}$$

con $\alpha=1,\ \beta=9$. Sin datos de la consulta no hay factor (1.0). Un documento muy elegido sube
(hasta ≈ 1.4); uno **mostrado muchas veces sin que nadie lo elija baja un poco** (piso ≈ 0.85): es la señal
negativa débil que antes no existía. Se quitó el prior Zipf sobre rangos (círculo de popularidad).

Las impresiones las envía la interfaz al confirmar una consulta (`mostrados` en `POST /api/consultas`: los
ids de los resultados que se mostraron, en orden). Memoria acotada: 5 000 consultas y 5 000 términos por
mapa; al superarlos se desalojan los de menos interacciones (más una fracción del 10 %).

### 8.3 Ejemplo numérico

Tres documentos con texto idéntico (`A`, `B`, `C`) y la consulta `pan`. Tras un clic en `C` en el lugar 1
(sin impresiones registradas): $C=2\cdot1+1=3$, $\mathrm{ctr}=(3+1)/10=0.4$ →
factor $1+0.4\tanh(1.2)=1.33$; `A` y `B` quedan en 1.0. `C` pasa de última (orden alfabético) a primera, pero
su `score` mostrado no cambia. Si además se registraron las impresiones (los tres mostrados una vez para
`pan`), `C` queda en ≈ 1.27 y `A`, `B` en ≈ 0.96: lo ignorado baja un poco.

### 8.4 Consulta vacía

Sin texto no hay score: se devuelve el catálogo ordenado por `(idioma ≠ dominante, −peso_reacciones, nombre)`
con `score = null`. Esta lista de "recomendados" **solo depende de las reacciones**.

------
## 9. Sugerencias por frecuencia (Zipf y Heaps)

Las consultas reales siguen una ley de Zipf (unas pocas dominan el tráfico) y el número de consultas
distintas crece como $K\cdot n^\beta$ (Heaps) sin tope. Por eso la tabla tiene que *olvidar*.

`senales/consultas.py` reemplaza al antiguo registro en memoria (puerta de admisión LRU, cubos de tiempo,
cabeza/cola, desalojo por lotes, persistencia en JSON) por una consulta SQL sobre la tabla de eventos:

- **Ventana deslizante exacta** (`HISTORIAL_VENTANA_DIAS`): cuentan las apariciones de ese periodo; lo anterior
  se purga (cada 500 escrituras y al arrancar), así que la tabla se aplana en vez de crecer.
- **Prefijo = rango** sobre el índice `(tipo, consulta, ts)`, sin recorrer todo.
- **Umbral público** (`HISTORIAL_MIN_FRECUENCIA`): una consulta solo se sugiere si se repitió; el umbral
  reemplaza a la puerta de admisión y se cuenta desde la primera vez.
- **Moderación** (`senales/moderacion.py`): no se cuentan correos, URLs, secuencias de 8+ dígitos ni términos
  bloqueados; tampoco se guardan sus clics ni impresiones. Al arrancar se borra lo ya guardado que la lista de
  bloqueo actual rechazaría.
- **Cache de prefijos** (LRU, 2 048 entradas, TTL 30 s) para los prefijos populares; una escritura local lo vacía.
- Orden: mayor frecuencia, luego la más reciente, luego alfabético. La respuesta lleva `origen`: `"cache"` o `"tabla"`.

### Medición (`python -m scripts.simular`)

Flujo sintético Zipf de 200 000 consultas (1 por segundo simulado) con una ventana de 8 h:

| n | consultas distintas (sin política) | filas en la tabla (con ventana) |
|--:|--:|--:|
| 10 000 | 3 512 | 10 000 |
| 100 000 | 23 913 | 28 801 |
| 200 000 | 42 277 | **28 801** |

Heaps (términos distintos): $V(n)\approx 1.94\,n^{0.763}$ (R² = 1.000); Zipf de las consultas: exponente ≈ 1.1
(R² = 0.999); las 500 consultas más frecuentes cubren ≈ 67 % del tráfico. `sugerir()`: mediana de 33 µs desde la
tabla y 5.5 µs desde el cache (p99 1.6 ms y 25 µs). Son cifras de una simulación; mídelas con tu tráfico.

------
## 10. Referencia de la API

Todas las respuestas son JSON. Las dependencias llegan por `app.extensions`, no por módulos globales.

| Método y ruta | Módulo | Descripción |
|---|---|---|
| `GET /` | `api/buscar.py` | Página principal |
| `GET /api/buscar` | `api/buscar.py` | Búsqueda con ranking |
| `POST /api/reaccion` | `api/senales.py` | Registra una reacción |
| `POST /api/seleccion` | `api/senales.py` | Registra qué resultado eligió la persona (y en qué lugar) |
| `GET /api/sugerencias` | `api/sugerencias.py` | Consultas más frecuentes con un prefijo |
| `POST /api/consultas` | `api/sugerencias.py` | Cuenta una consulta confirmada (+ impresiones) |
| `GET /api/historial/estadisticas` | `api/sugerencias.py` | Ventana, eventos por tipo, moderación, Zipf medido |

### `GET /api/buscar?q=<texto>&idioma=es|en|pt`

`idioma` inválido o ausente cae a `es`. `q` se recorta con `strip()`.

```json
{
  "consulta": "polvo", "consulta_simplificada": "polvo", "abreviaturas": {}, "emojis": [],
  "modo": "nombre", "idioma_dominante": "es", "terminos_expandidos": ["polvo"], "total_coincidencias": 2,
  "resultados": [
    {"id": 41, "nombre": "Polvo", "categoria": "Materia", "descripcion": "...",
     "emoji": "💨", "idioma": "es", "idioma_nombre": "Español", "bandera": "🇲🇽",
     "score": 0.9894, "peso": 1.4121, "homografo": true, "emoji_coincide": false,
     "reacciones": {"me_gusta": 0, "no_me_gusta": 0, "me_encanta": 0},
     "explicacion": {"coseno": 0.9, "emoji": 0.0, "factor_idioma": 1.1, "score": 0.9894,
                     "reacciones": 1.2, "aprendizaje": 1.18, "orden": 1.4}}
  ]
}
```

- `resultados` se recorta a 12; `total_coincidencias` cuenta todos los candidatos con score > 0.
- `score` es solo la similitud (con idioma y emoji); **no incluye** `peso`. El orden usa `score × peso`.
- `homografo: true` marca documentos que comparten `nombre` con otro resultado **dentro de esa misma página**.
- Consulta sin texto ni emojis útiles (`"!!!"`) → cero resultados. Con `q` vacío: catálogo completo, `score = null`.

### `POST /api/reaccion`

```json
{"id": 41, "tipo": "me_gusta"}        // tipo ∈ me_gusta | no_me_gusta | me_encanta
```

`200` → `{"id": 41, "conteos": {...}, "puntos": 1.0}`. `400` si el cuerpo no es un objeto JSON, si `id` no es
entero (se acepta un string de dígitos ASCII) o si `tipo` no es válido. **`404`** si el `id` no existe en el catálogo.

### `POST /api/seleccion`

```json
{"q": "pan dulce", "id": 41, "pos": 3}     // pos = lugar del resultado (1..50), opcional
```

`200` → `{"registrada": true|false}` (`false` si la consulta está vacía, es demasiado larga o es sensible).
`400` si el cuerpo no es un objeto JSON o el `id` es inválido; `404` si el `id` no existe. Una `pos` fuera de
rango se ignora (el clic se registra sin posición). La consulta se recorta a 200 caracteres.

### `GET /api/sugerencias?q=<prefijo>&limite=8`

`limite` entre 1 y 20 (defecto 8; un valor no numérico cae a 8). Con `q` vacío, las más buscadas.
Lleva `Cache-Control: public, max-age=15`.

```json
{"prefijo": "pan", "origen": "tabla",
 "sugerencias": [{"consulta": "pan dulce", "frecuencia": 12}]}
```

### `POST /api/consultas`

```json
{"q": "mole poblano", "mostrados": [41, 7, 12]}     // mostrados: ids de lo que se vio, en orden (opcional)
```

Siempre `200` → `{"registrada": true|false}`. `true` si la consulta se guardó; `false` si estaba vacía, era
muy larga (más de 64 caracteres normalizados) o la moderación la descartó. `mostrados` se filtra (ids
inexistentes, inválidos y repetidos se ignoran) y cada uno queda como una impresión con su posición.

### `GET /api/historial/estadisticas`

`consultas_vivas`, `ocurrencias_en_ventana`, `ventana_segundos`, `min_frecuencia_publica`, `prefijos_en_cache`,
`descartadas_por_moderacion`, `zipf` (`{exponente, r2, puntos}` o `null` con menos de 10 consultas),
`eventos` (filas por tipo), `aprendizaje` (`consultas_con_datos`, `terminos_con_datos`) y `max_claves`.

------
## 11. Interfaz web

`static/js/` son módulos ES (`<script type="module">`), cada uno con una responsabilidad:

| Módulo | Qué hace |
|---|---|
| `main.js` | Cablea el DOM: búsqueda por tecla (con guardia contra respuestas fuera de orden), idioma, Enter |
| `api.js` | Todas las llamadas `fetch` |
| `render.js` | Pinta resultados, resaltado, predicción y contador **con DOM y `textContent`** |
| `historial.js` | Historial local (`localStorage`): recientes primero, sin duplicados, con contador de usos |
| `servidor.js` | Consultas confirmadas → servidor, con los ids mostrados como impresiones |
| `sugerencias.js` | Sugerencias del servidor con cache LRU en el navegador y respaldo local si cae |
| `util.js` | `normalizar` (mismas reglas que `nucleo/texto.py`) |

- **Sin `innerHTML`.** Nada del catálogo ni del servidor se interpreta como HTML (el resaltado crea nodos
  `<mark>`; el resto es texto). Un nombre como `<img onerror=…>` se muestra literal.
- **Consultas confirmadas.** El servidor cuenta búsquedas confirmadas, no cada tecla: Enter, una pausa de 1 s,
  elegir una sugerencia o repetir del historial. Una búsqueda que solo se extiende (`pan` → `pancake`)
  reemplaza a la pendiente; se envía al cambiar de búsqueda, confirmar, tras 8 s o al cerrar la página.
- **Impresiones.** Al confirmar se envían los ids de los resultados mostrados *para esa misma consulta*.
- **Clic y posición.** Elegir un resultado envía `{q, id, pos}`; reaccionar no cuenta como elegir.
- Si `/api/sugerencias` falla, el navegador lo da por caído 60 s y muestra tus búsquedas más repetidas.

------
## 12. Datos y repositorios

### Formato de `catalogo.json`

Lista de objetos con `nombre`, `categoria`, `descripcion`, `emoji` e `idioma` (`es|en|pt`). `RepositorioJSON`
asigna `id` por posición (desde 1).

> ⚠️ Con JSON, **reordenar o insertar documentos cambia los `id`** y desalinea reacciones y clics ya
> acumulados. Con SQL los `id` son estables.

### Esquema SQL (`datos/repositorio.py`)

```
categorias(id PK, nombre UNIQUE)
documentos(id PK, nombre, descripcion, emoji, idioma, categoria_id → categorias.id)
```

La categoría deja de ser texto repetido; el motor la recibe ya resuelta a su nombre, así que el ranking es
idéntico al de la versión JSON.

### `datos/migrar.py`

```bash
python -m datos.migrar                                   # → sqlite:///catalogo.db
python -m datos.migrar --url postgresql://u:c@host/db    # otra base
python -m datos.migrar --reemplazar                      # vacía documentos y categorías antes
DATABASE_URL=sqlite:///catalogo.db python app.py
```

Se niega a importar sobre una tabla con datos salvo `--reemplazar`. Todo ocurre en una transacción.

### Cambios en caliente

Con `RECARGA_SEGUNDOS=300` el índice se reconstruye cuando una consulta llega con más de 5 minutos de
antigüedad. La reconstrucción es **completa**, no incremental.


------
## 13. Pruebas

```bash
pip install -r requirements-dev.txt
python -m pytest -q                       # 97 pruebas, < 1 s
```

| Archivo | Cubre |
|---|---|
| `test_texto.py` | normalización, ñ, claves de consulta, ajustes Zipf/Heaps |
| `test_busqueda.py` | **regresión contra el motor original** (46 consultas congeladas en `golden_busqueda.json`), índice, desglose, recarga |
| `test_reacciones.py` · `test_clics.py` | factores, suavizado, decaimiento, posición, CTR, memoria acotada |
| `test_consultas.py` | orden, ventana, umbral, cache, moderación |
| `test_senales.py` | persistencia tras reinicio, dos procesos sobre un archivo, purga, retención, hilos |
| `test_api.py` | los 7 endpoints con el cliente de Flask: validación, 404, impresiones, configuración |
| `test_evaluacion.py` | métricas, rejilla, restauración de constantes, conjunto de oro sintético |

`tests/datos_prueba.py` es un catálogo sintético de 46 documentos (falsos amigos, emojis, ñ). Antes de
cambiar el ranking o el motor, añade tus consultas reales a `evaluacion/oro.csv` y corre
`python -m scripts.calibrar`.

No hay pruebas automáticas del JavaScript en el repositorio. Los módulos se verificaron con un arnés
desechable (esbuild + jsdom contra el servidor real): carga, búsqueda, idioma, clic, reacción, Enter, historial,
sugerencias y no-XSS.

------
## 14. Cómo extender el sistema

- **Sinónimos, abreviaturas, relleno:** `nucleo/lexico.py` (sin acentos, minúsculas, con la ñ).
- **Significado de emojis:** `CONCEPTOS_EMOJI` en `nucleo/emojis.py`.
- **Constantes de ranking:** `busqueda/parametros.py`; valida con `scripts/calibrar.py`. Las de `CAMPOS` obligan a reindexar.
- **Una señal nueva:** agrega un `tipo` a la tabla de eventos (`senales/almacen.py`), un agregado como `clics.py` y
  multiplícala en `Senales.pesos()`; el motor no cambia.
- **Otra fuente de datos:** una clase con `listar()` en `datos/repositorio.py` y elígela en `crear_repositorio()`.
- **Otro endpoint:** un blueprint en `api/` y su registro en `api/__init__.py`.

------
## 15. Limitaciones conocidas

- **IDs por posición con JSON:** reordenar o insertar en `catalogo.json` cambia los `id` y desalinea las señales.
- **Cualquiera puede enviar señales:** no hay autenticación ni límite de frecuencia en `/api/reaccion`,
  `/api/seleccion` ni `/api/consultas` (clics e impresiones falsos mueven el ranking). Valida que el `id`
  exista, pero no quién lo envía.
- **Impresiones solo de consultas confirmadas** y enviadas por el cliente: no se registra cada resultado visto.
- **Consistencia entre workers:** hasta `sync_s` (5 s); la reconstrucción relee el log completo dentro de la
  retención (O(eventos)). Con mucho volumen conviene un agregado incremental.
- **SQLite = un escritor.** Con mucha escritura concurrente, mueve las señales a PostgreSQL o Redis.
- **Las 3 primeras apariciones no se sugieren** (umbral público) y una consulta muy larga o sensible nunca.
- **Sin tolerancia a typos ni morfología.** Sinónimos y abreviaturas son manuales; no hay BM25F ni búsqueda difusa.
- **Sin exploración:** el aprendizaje sigue premiando lo ya elegido; el CTR por posición lo mitiga, no lo elimina.

------
## 16. Qué cambió respecto a la versión anterior

Refactor guiado por el documento de propuestas de mejora (`Propuestas de mejora — buscador-predictivo.md`).

### Archivos

| Antes | Ahora |
|---|---|
| `sri.py` | `nucleo/texto.py` · `nucleo/lexico.py` · `busqueda/{parametros,indice,consulta,ranking,buscador}.py` |
| `emojis.py` | `nucleo/emojis.py` |
| `reacciones.py` + `reacciones_api.py` | `senales/reacciones.py` + `api/senales.py` |
| `aprendizaje.py` + `aprendizaje_api.py` | `senales/clics.py` + `api/senales.py` |
| `frecuencia.py` + `historial_api.py` | `senales/consultas.py` + `senales/almacen.py` + `api/sugerencias.py` (**ya registrado**) |
| `repositorio.py`, `migrar.py` | `datos/repositorio.py`, `datos/migrar.py` (`python -m datos.migrar`) |
| `calibrar.py`, `simular.py` | `scripts/calibrar.py`, `scripts/simular.py` (`python -m scripts.…`); métricas en `busqueda/evaluacion.py` |
| `test_*.py` (70, unittest) | `tests/` (97, pytest) |
| `static/script.js` | `static/js/*.js` (módulos ES) |

### Propuestas

| Propuesta | Estado |
|---|---|
| **A.1** reorganizar por responsabilidad | ✅ |
| **A.2** partir `buscar()` | ✅ analizar → puntuar → señales → ordenar → serializar |
| **A.3** una sola utilidad de rango Zipf y un validador | ✅ validador único (`api/validacion.py`); la utilidad de rango **no hace falta**: B quitó los priors Zipf |
| **A.4** sin singletons globales | ✅ `create_app()` inyecta; nada se crea al importar |
| **A.5** registrar `bp_historial` | ✅ |
| **A.6** puntuar solo candidatos | ✅ (los factores ya no dependen de rangos sobre todo el catálogo) |
| **A.7** acumular por término | ✅ postings `(posición, peso)`; la salida es idéntica a la anterior (regresión) |
| **A.8** escapar el HTML | ✅ DOM + `textContent`, sin `innerHTML` |
| **B** unificar señales / quitar priors Zipf / CTR por posición / SQLite / reemplazar `frecuencia.py` | ✅ |
| **C** SQLite FTS5 (u otro motor) | ⏸ no hecho: la propuesta misma pide validarlo antes contra un conjunto de oro, y no hay `oro.csv` ni `catalogo.json` en lo entregado |
| **D** FastAPI + Pydantic | ⏸ no hecho (opcional, ganancia moderada) |

### Cambios de comportamiento (no es un refactor puro)

- **Recuperación y score: sin cambios** (46 consultas congeladas coinciden exactamente).
- **Reacciones:** sin el prior Zipf (+30 %); el decaimiento se evalúa en cada consulta (sin cache de una hora).
- **Clics:** CTR suavizado con posición e impresiones (puede **bajar** documentos ignorados, piso ≈ 0.85, y el
  máximo sigue ≈ 1.4); sin el prior Zipf (+20 %).
- **Sugerencias:** ventana exacta (antes cubos de 6 h), sin puerta de admisión (el umbral público cuenta desde la
  primera vez), `origen` ∈ `cache|tabla` (antes `cabeza|cache|cola|mixto`), `registrada` = se guardó.
- **Persistencia:** reacciones, clics y consultas sobreviven al reinicio y se comparten entre workers.
  `HISTORIAL_ARCHIVO`, `HISTORIAL_MAX_CONSULTAS` y `HISTORIAL_TAM_CABEZA` desaparecen; aparece `SENALES_DB`.
- **API:** `404` para ids inexistentes en `/api/reaccion` y `/api/seleccion`; `pos` en `/api/seleccion`;
  `mostrados` en `/api/consultas`.
- **Los datos de señales anteriores no se migran** (estaban solo en memoria, salvo el JSON de frecuencias).

### Orden recomendado a partir de aquí

1. Crear `evaluacion/oro.csv` con consultas reales y correr `python -m scripts.calibrar` (línea base).
2. Evaluar **C** (FTS5) contra ese conjunto de oro.
3. Antes de abrirlo al público: autenticación o límites de frecuencia en los endpoints de señales.
