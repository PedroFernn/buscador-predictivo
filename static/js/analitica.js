// Página /analitica: el índice invertido, Zipf, Heaps y los árboles B del motor, graficados.
//   - Catálogo (GET /api/analitica/corpus): se pide al abrir y cada tanto por si se reindexó.
//   - Uso real (GET /api/analitica/uso): se vuelve a pedir cada pocos segundos mientras "En vivo" esté activo.
//   - Sondeo (GET /api/analitica/sondeo): lo que toca la consulta escrita arriba; se resalta en todas las gráficas.
// Este módulo solo cablea datos con gráficas; el dibujo vive en graficas.js.
import * as Api from "./api.js";
import {
    activarTooltips, arbolConClaves, arbolPorNiveles, barrasHorizontales, barrasVerticales, dispersion, dominiosDe, esc, num, vacio,
} from "./graficas.js";

const REFRESCO_USO_MS = 4000;
const REFRESCO_CORPUS_MS = 30000;
const PAUSA_SONDEO_MS = 160;
const REPRODUCCION_MS = 2800;
const MAX_RESALTADOS = 40;      // términos de la consulta que se marcan en la gráfica de Zipf
const MAX_ETIQUETADOS = 3;      // de esos, los que llevan nombre al lado

const $ = (id) => document.getElementById(id);

// Datos que vienen de endpoints propios (no del catálogo ni del uso en vivo)
const extra = { cache: null, retencion: null, demo: null };

const estado = {
    arbolModo: "vocabulario",   // "vocabulario" | "demo"
    corpus: null,
    uso: null,
    sondeo: null,
    modo: "nombre",
    zipf: { fuente: "catalogo", escala: "log" },
    heaps: { fuente: "catalogo", escala: "log" },
    histogramaLog: false,
    actualizadoUso: 0,
    reproduccion: 0,   // id del requestAnimationFrame de "Reproducir"
};

// --- Piezas de interfaz -----------------------------------------------------------------------
function chips(contenedor, items) {
    contenedor.innerHTML = items.map(([etiqueta, valor, ayuda]) => (
        `<div class="dato"${ayuda ? ` title="${esc(ayuda)}"` : ""}><span>${esc(etiqueta)}</span><b>${esc(valor)}</b></div>`
    )).join("");
}

function lista(contenedor, filas) {
    contenedor.innerHTML = filas.length
        ? filas.map(([nombre, cantidad]) => `<li><span>${esc(nombre)}</span><b>${esc(cantidad)}</b></li>`).join("")
        : "";
}

function segmentado(id, inicial, alCambiar) {
    const grupo = $(id);
    const marcar = (valor) => grupo.querySelectorAll("button").forEach((boton) => {
        boton.setAttribute("aria-pressed", String(boton.dataset.valor === valor));
    });
    marcar(inicial);
    grupo.addEventListener("click", (evento) => {
        const boton = evento.target.closest("button");
        if (!boton) return;
        marcar(boton.dataset.valor);
        alCambiar(boton.dataset.valor);
    });
}

function pulso(elemento) {
    elemento.classList.remove("pulso");
    void elemento.offsetWidth;          // reinicia la animación si ya estaba corriendo
    elemento.classList.add("pulso");
}

const porcentaje = (parte, total) => (total ? num((100 * parte) / total, parte / total < 0.1 ? 1 : 0) : "0");

// --- Resumen ---------------------------------------------------------------------------------------
function pintarResumen() {
    const c = estado.corpus;
    if (!c) return;
    chips($("resumen"), [
        ["Documentos", num(c.documentos)],
        ["Términos distintos (V)", num(c.terminos), "Tamaño del vocabulario del catálogo"],
        ["Tokens (N)", num(c.tokens), "Palabras en total: nombre, categoría y descripción de todos los documentos"],
        ["Grado t del árbol B", num(c.grado), `Cada nodo guarda entre ${c.grado - 1} y ${2 * c.grado - 1} claves`],
        ["Consultas en la ventana", estado.uso ? num(estado.uso.eventos) : "—", "Consultas confirmadas que siguen vivas en la ventana deslizante"],
    ]);
}

// --- 1 · Índice invertido ----------------------------------------------------------------------------
function pintarIndice(animar = false) {
    const c = estado.corpus;
    if (!c) return;
    const ii = c.indice_invertido[estado.modo];
    const enConsulta = new Set(((estado.sondeo && estado.sondeo.terminos) || []).map((t) => t.termino));

    chips($("chips-indice"), [
        ["Términos con posting", num(ii.terminos)],
        ["Postings (término, documento)", num(ii.postings), "Pares guardados en total"],
        ["Documentos por término: media", num(ii.df_medio, 1)],
        ["Mediana", num(ii.df_mediana)],
        ["Máximo", num(ii.df_max)],
        ["Términos en un solo documento", `${num(ii.en_un_documento)} (${porcentaje(ii.en_un_documento, ii.terminos)} %)`],
    ]);

    barrasHorizontales($("graf-top"), ii.top.map((t) => ({
        etiqueta: t.termino,
        valor: t.df,
        resaltado: enConsulta.has(t.termino),
        tip: `${t.termino}: en ${num(t.df)} documentos · idf ${t.idf} · rango Zipf ${t.rango ? num(t.rango) : "—"}`,
    })), { aria: "Términos con más documentos", animar });

    barrasVerticales($("graf-histo"), ii.histograma.map((h) => ({
        etiqueta: h.desde >= 1000 ? `${num(h.desde / 1000, 1)}k` : String(h.desde),
        valor: h.terminos,
        tip: `${num(h.terminos)} términos aparecen en ${h.desde === h.hasta ? h.desde : `${num(h.desde)}–${num(h.hasta)}`} documentos`,
    })), {
        log: estado.histogramaLog,
        etiquetaX: "documentos por término (desde; cubos de potencias de 2)",
        etiquetaY: estado.histogramaLog ? "términos (escala log)" : "términos",
        aria: "Histograma de la longitud de los postings",
        animar,
    });

    pintarPostingsDeLaConsulta();
}

function pintarPostingsDeLaConsulta() {
    const s = estado.sondeo;
    const grafica = $("graf-sondeo");
    const resumen = $("resumen-postings");
    if (!s || s.vacio || !s.terminos.length) {
        vacio(grafica, s && s.consulta ? "Esa consulta no se expande a ningún término del índice." : "Escribe una consulta arriba para ver qué postings recorre.");
        resumen.textContent = "";
        return;
    }
    barrasHorizontales(grafica, s.terminos.slice(0, 15).map((t) => ({
        etiqueta: t.termino,
        valor: t.df,
        tip: `${t.termino}: ${num(t.df)} documentos · peso en la consulta ${t.peso} · posting de altura ${t.altura}`,
    })), { aria: "Postings que recorre la consulta" });
    resumen.textContent = `Modo «${s.modo}»: la consulta se expande a ${num(s.terminos_total)} términos y lee ${num(s.postings_tocados)} `
        + `de ${num(s.postings_totales)} postings (${porcentaje(s.postings_tocados, s.postings_totales)} %). `
        + `Quedan ${num(s.candidatos)} documentos candidatos; no se recorrió el catálogo entero.`;
}

// --- 2 · Zipf ---------------------------------------------------------------------------------------------
// Qué fracción de las peticiones de sugerencias sale del cache, por rango del prefijo
function pintarCache() {
    const c = extra.cache;
    if (!c) return;
    chips($("chips-cache"), [
        ["Peticiones de sugerencias", num(c.peticiones)],
        ["Servidas desde el cache", c.tasa === null ? "—" : `${porcentaje(c.tasa, 1)} %`, "Aciertos / peticiones, en toda la medición"],
        ["Prefijos distintos pedidos", num(c.prefijos)],
        ["Prefijos guardados ahora", num(c.en_cache), "Entradas vivas en el cache (TTL 30 s, máximo 2 048)"],
    ]);
    if (!c.puntos.length) {
        vacio($("graf-cache"), "Todavía no hay peticiones de sugerencias: escribe en el buscador para llenar esta gráfica.");
        $("nota-cache").textContent = "";
        return;
    }
    dispersion($("graf-cache"), {
        logX: true, logY: false, domY: [0, 1],
        etiquetaX: "rango del prefijo (1 = el más pedido)", etiquetaY: "fracción servida desde el cache",
        aria: "Tasa de aciertos del cache frente al rango del prefijo",
        series: [{
            nombre: "Prefijos pedidos", clase: "serie-2", puntos: c.puntos.map((p) => [p.rango, p.tasa]),
            tip: (r, t) => {
                const punto = c.puntos[r - 1];
                return `«${punto.prefijo}» · rango ${num(r)} · ${num(punto.peticiones)} peticiones · ${porcentaje(t, 1)} % desde cache`;
            },
        }],
    });
    $("nota-cache").textContent = "Cada consulta nueva vacía el cache, así que la tasa baja cuando entran muchas escrituras entre peticiones. "
        + "Los prefijos populares (rangos bajos) son los que más se benefician.";
}

// Sin política frente a la ventana: simulación con la misma ley, por eso no depende del tráfico real
function pintarRetencion() {
    const r = extra.retencion;
    if (!r) return vacio($("graf-retencion"), "Calculando la comparación…");
    const pts = r.puntos;
    dispersion($("graf-retencion"), {
        logX: true, logY: true, leyenda: "abajo",
        etiquetaX: "eventos simulados (n)", etiquetaY: "filas, consultas o términos",
        aria: "Consultas y términos distintos sin política frente a las filas con ventana",
        series: [
            { nombre: "Sin política: consultas distintas", clase: "serie-1", linea: true, puntos: pts.map((p) => [p.n, p.consultas]), tip: (n, v) => `${num(n)} eventos → ${num(v)} consultas distintas sin política` },
            { nombre: "Sin política: términos distintos", clase: "ajuste-2", linea: true, puntos: pts.map((p) => [p.n, p.terminos]), tip: (n, v) => `${num(n)} eventos → ${num(v)} términos distintos sin política` },
            { nombre: `Tabla con ventana de ${num(r.ventana_segundos / 3600, 0)} h (filas)`, clase: "serie-2", linea: true, puntos: pts.map((p) => [p.n, p.filas]), tip: (n, v) => `${num(n)} eventos → ${num(v)} filas en la tabla con ventana` },
        ],
    });
    const ultimo = pts[pts.length - 1];
    chips($("chips-retencion"), [
        ["Filas con ventana al final", num(ultimo.filas), `Se aplana: la purga conserva solo la ventana de ${num(r.ventana_segundos)} s`],
        ["Consultas distintas sin política", num(ultimo.consultas), "Crecen sin tope: cada consulta nueva se suma"],
        ["Eventos simulados", num(r.eventos)],
        ["β de consultas", r.heaps_consultas ? String(r.heaps_consultas.beta) : "—"],
    ]);
    $("nota-retencion").textContent = `Simulación con la misma ley Zipf que scripts/simular.py (tardó ${num(r.segundos, 1)} s). `
        + "El tráfico real no tiene historia sin política que medir, así que la comparación se hace con el flujo sintético.";
}

async function cargarRetencion() {
    try {
        extra.retencion = await Api.analiticaRetencion();
        pintarRetencion();
    } catch (error) {
        vacio($("graf-retencion"), "No se pudo calcular la comparación.");
    }
}

async function cargarCache() {
    try {
        const nuevo = await Api.analiticaCache();
        if (JSON.stringify(nuevo) === JSON.stringify(extra.cache)) return;
        extra.cache = nuevo;
        pintarCache();
    } catch (error) {
        // se queda lo último que se pintó; el aviso general lo da el reloj en vivo
    }
}

function pintarZipf(animar = false) {
    const { fuente, escala } = estado.zipf;
    const logaritmica = escala === "log";
    const grafica = $("graf-zipf");
    const base = { logX: logaritmica, logY: logaritmica, etiquetaX: "rango", animar, aria: "Frecuencia contra rango (Zipf)" };

    if (fuente === "catalogo") {
        const z = estado.corpus && estado.corpus.zipf;
        if (!z) return;
        const a = z.ajuste;
        $("nota-zipf").textContent = `La recta solo se dibuja donde se ajustó (rangos 1 a ${num(z.ajuste_hasta_rango)}). `
            + "La meseta de abajo son términos que aparecen una sola vez: no se ajustan. "
            + "Los textos del catálogo son cortos y sin palabras de relleno: su exponente no tiene por qué parecerse al de un texto corrido.";
        const resaltados = ((estado.sondeo && estado.sondeo.terminos) || [])
            .filter((t) => t.rango && t.frecuencia)
            .slice(0, MAX_RESALTADOS)
            .map((t, i) => ({
                x: t.rango, y: t.frecuencia, etiqueta: i < MAX_ETIQUETADOS ? t.termino : "",
                tip: `${t.termino} · rango ${num(t.rango)} · ${num(t.frecuencia)} apariciones`,
            }));
        dispersion(grafica, {
            ...base,
            etiquetaY: "frecuencia del término",
            series: [{ nombre: "Términos del catálogo", puntos: z.puntos, tip: (r, f) => `rango ${num(r)} · ${num(f)} apariciones` }],
            ajustes: a ? [{
                nombre: `ajuste: f ≈ ${num(a.constante, 0)} / r^${a.exponente}`, clase: "ajuste-1",
                f: (r) => a.constante * r ** -a.exponente, x0: 1, x1: z.ajuste_hasta_rango,
            }] : [],
            resaltados,
        });
        chips($("chips-zipf"), [
            ["Exponente s", a ? String(a.exponente) : "—", "f(r) ≈ C / r^s; en lenguaje natural s ronda 1"],
            ["R² del ajuste", a ? String(a.r2) : "—", `Sobre los primeros ${num(z.ajuste_hasta_rango)} rangos, en log-log`],
            ["Términos distintos", num(z.terminos)],
            ["Tokens", num(z.tokens)],
        ]);
        lista($("top-zipf"), z.top.map((t) => [t.termino, num(t.frecuencia)]));
        $("titulo-top-zipf").textContent = "Términos más frecuentes";
        return;
    }

    const u = estado.uso;
    if (!u) return;
    $("nota-zipf").textContent = "Con pocas consultas la recta no es fiable: el ajuste necesita al menos 10 consultas distintas.";
    if (!u.zipf.puntos.length) {
        vacio(grafica, "Todavía no hay consultas registradas: busca algo en el buscador (o genera datos en «Herramientas de prueba»).");
    } else {
        const a = u.zipf.ajuste;
        dispersion(grafica, {
            ...base,
            etiquetaY: "veces que se buscó",
            series: [{ nombre: "Consultas distintas", clase: "serie-2", puntos: u.zipf.puntos, tip: (r, f) => `rango ${num(r)} · buscada ${num(f)} veces` }],
            ajustes: a ? [{
                nombre: `ajuste: f ≈ ${num(a.constante, 1)} / r^${a.exponente}`, clase: "ajuste-1",
                f: (r) => a.constante * r ** -a.exponente, x0: 1, x1: a.puntos,
            }] : [],
        });
    }
    const a = u.zipf.ajuste;
    chips($("chips-zipf"), [
        ["Exponente s", a ? String(a.exponente) : "—", a ? "f(r) ≈ C / r^s" : "Hacen falta al menos 10 consultas distintas"],
        ["R² del ajuste", a ? String(a.r2) : "—"],
        ["Consultas distintas", num(u.distintas)],
        ["Consultas en la ventana", num(u.eventos)],
    ]);
    lista($("top-zipf"), u.zipf.top.map((t) => [t.consulta, num(t.frecuencia)]));
    $("titulo-top-zipf").textContent = u.zipf.top.length
        ? "Consultas más buscadas (las que ya alcanzaron el umbral público)"
        : "Aún ninguna consulta alcanza el umbral público";
}

// --- 3 · Heaps -----------------------------------------------------------------------------------------------
function datosHeaps() {
    const logaritmica = estado.heaps.escala === "log";
    const base = { logX: logaritmica, logY: logaritmica, leyenda: "abajo", aria: "Vocabulario contra texto leído (Heaps)" };

    if (estado.heaps.fuente === "catalogo") {
        const h = estado.corpus && estado.corpus.heaps;
        const c = estado.corpus;
        if (!h || !h.puntos.length) return null;
        const a = h.ajuste;
        return {
            cfg: {
                ...base,
                etiquetaX: "tokens leídos (n)", etiquetaY: "términos distintos V(n)",
                series: [{
                    nombre: "Catálogo leído documento a documento", clase: "serie-1", linea: true, puntos: h.puntos,
                    tip: (n, v) => `${num(n)} tokens leídos → ${num(v)} términos distintos`,
                }],
                ajustes: a ? [{
                    nombre: `ajuste: V ≈ ${num(a.constante, 2)} · n^${a.exponente}`, clase: "ajuste-1",
                    f: (n) => a.constante * n ** a.exponente, x0: h.puntos[0][0], x1: c.tokens,
                }] : [],
            },
            chips: [
                ["Exponente β", a ? String(a.exponente) : "—", "V(n) ≈ K · n^β; en texto natural suele estar entre 0.4 y 0.6"],
                ["Constante K", a ? num(a.constante, 2) : "—"],
                ["R² del ajuste", a ? String(a.r2) : "—"],
                ["Con 10× más texto", a ? `≈ ${num(a.constante * (10 * c.tokens) ** a.exponente)} términos` : "—", "Extrapolación del ajuste: no es una medición"],
            ],
            nota: `Orden de lectura: ${h.orden}. Con descripciones cortas y vocabulario muy variado, β puede salir mayor que en texto corrido.`,
        };
    }

    const u = estado.uso;
    if (!u || u.heaps.consultas.puntos.length < 2) return { vacio: "Todavía no hay consultas suficientes: busca algo en el buscador (o genera datos en «Herramientas de prueba»)." };
    const q = u.heaps.consultas.ajuste;
    const t = u.heaps.terminos.ajuste;
    const ley = (a, simbolo) => (a ? [{ nombre: `${simbolo}: ${num(a.k, 2)} · n^${a.beta}`, clase: simbolo === "consultas" ? "ajuste-1" : "ajuste-2", f: (n) => a.k * n ** a.beta, x0: 1, x1: u.eventos }] : []);
    return {
        cfg: {
            ...base,
            etiquetaX: "consultas leídas (n)", etiquetaY: "distintas vistas",
            series: [
                { nombre: "Consultas distintas", clase: "serie-1", linea: true, puntos: u.heaps.consultas.puntos, tip: (n, v) => `${num(n)} consultas → ${num(v)} distintas` },
                { nombre: "Términos distintos", clase: "serie-2", linea: true, puntos: u.heaps.terminos.puntos, tip: (n, v) => `${num(n)} consultas → ${num(v)} términos distintos` },
            ],
            ajustes: [...ley(q, "consultas"), ...ley(t, "términos")],
        },
        chips: [
            ["β de consultas", q ? String(q.beta) : "—", "Cerca de 1 = casi cada consulta es nueva; menor = se repiten"],
            ["β de términos", t ? String(t.beta) : "—"],
            ["Consultas leídas", num(u.eventos)],
            ["Distintas", num(u.distintas)],
        ],
        nota: "Solo cuenta lo que la ventana deslizante conserva: lo anterior se purga, así que es el tramo vivo, no toda la historia.",
    };
}

function pintarHeaps(animar = false) {
    const datos = datosHeaps();
    const grafica = $("graf-heaps");
    $("heaps-reproducir").disabled = !datos || !datos.cfg;
    if (!datos) return;
    if (!datos.cfg) {
        vacio(grafica, datos.vacio);
        chips($("chips-heaps"), []);
        $("nota-heaps").textContent = "";
        return;
    }
    dispersion(grafica, { ...datos.cfg, animar });
    chips($("chips-heaps"), datos.chips);
    $("nota-heaps").textContent = `${datos.nota} Los textos del catálogo son cortos y sin relleno: no compares β con los de texto corrido.`;
}

function detenerReproduccion() {
    if (estado.reproduccion) cancelAnimationFrame(estado.reproduccion);
    estado.reproduccion = 0;
    $("heaps-reproducir").textContent = "▶ Reproducir";
}

// Vuelve a dibujar la curva punto por punto, con los ejes ya fijados: se ve cómo crece el vocabulario
function reproducirHeaps() {
    if (estado.reproduccion) {
        detenerReproduccion();
        pintarHeaps();
        return;
    }
    const datos = datosHeaps();
    if (!datos || !datos.cfg) return;
    const fijos = dominiosDe(datos.cfg);
    const total = Math.max(...datos.cfg.series.map((s) => s.puntos.length));
    const inicio = performance.now();
    $("heaps-reproducir").textContent = "⏸ Detener";
    const paso = (ahora) => {
        const avance = Math.min(1, (ahora - inicio) / REPRODUCCION_MS);
        const k = Math.max(1, Math.ceil(avance * total));
        dispersion($("graf-heaps"), {
            ...datos.cfg,
            ...fijos,
            ajustes: avance < 1 ? [] : datos.cfg.ajustes,
            series: datos.cfg.series.map((s) => ({ ...s, puntos: s.puntos.slice(0, k) })),
        });
        if (avance < 1) {
            estado.reproduccion = requestAnimationFrame(paso);
        } else {
            detenerReproduccion();
        }
    };
    estado.reproduccion = requestAnimationFrame(paso);
}

// --- 4 · Árboles B --------------------------------------------------------------------------------------------
// Las categorías en el orden de sus llaves forzadas NN_categoria: el valor es la similitud con la llave que sigue
function pintarMapa(nombradas) {
    const m = estado.corpus && estado.corpus.arboles.mapa;
    if (!m) return;
    barrasHorizontales($("graf-mapa"), m.filas.map((f) => ({
        etiqueta: f.llave,
        valor: Math.round(f.enlace * 100),
        resaltado: nombradas.has(f.nombre),
        tip: f.enlace >= m.sim_min
            ? `${f.llave} (${num(f.documentos)} documentos): se parece ${num(f.enlace * 100, 0)} % a la llave que sigue`
            : `${f.llave} (${num(f.documentos)} documentos): corte, la llave que sigue ya no se le parece`,
    })), { formato: (v) => `${num(v)} %`, ancho_etiqueta: 200, aria: "Categorías en el orden de sus llaves y similitud con la siguiente", vacio: "No hay categorías." });
    const conserva = m.preservacion === null ? "no aplica" : `${porcentaje(m.preservacion, 1)} %`;
    $("nota-mapa").textContent = `${num(m.categorias)} categorías en ${num(m.bloques)} ${m.bloques === 1 ? "bloque" : "bloques"}. `
        + "Al terminar una categoría, el recorrido pasa a la llave que sigue o que antecede mientras el valor supere el mínimo; "
        + "un valor menor es un corte entre bloques y ahí se detiene. "
        + `Un orden lineal no conserva todas las vecindades: la categoría más parecida quedó contigua en ${conserva} de los casos.`
        + (m.recortado ? ` Se muestran las primeras ${num(m.filas.length)}.` : "");
}

function pintarArbolDemo() {
    const q = (estado.sondeo && estado.sondeo.consulta) || "";
    const grafica = $("graf-arbol");
    if (extra.demo && extra.demo.q === q) return pintarDemoListo(extra.demo.datos);
    grafica.innerHTML = '<p class="g-vacio">Cargando la demostración…</p>';
    Api.analiticaArbolDemo(q).then((datos) => {
        extra.demo = { q, datos };
        if (estado.arbolModo === "demo") pintarDemoListo(datos);
    }).catch(() => { vacio(grafica, "No se pudo cargar la demostración."); });
}

function pintarDemoListo(datos) {
    arbolConClaves($("graf-arbol"), datos.niveles, datos.traza, { aria: "Árbol B pequeño con sus claves" });
    $("titulo-arbol").textContent = `Demostración: árbol de grado ${datos.grado} con sus claves`;
    chips($("chips-arboles"), [
        ["Grado t", num(datos.grado), "Cada nodo guarda entre 1 y 2t-1 claves"],
        ["Términos en el árbol", num(datos.claves), "Repartidos en el alfabeto entre los más frecuentes"],
        ["Altura", num(datos.altura), "Niveles desde la raíz hasta las hojas"],
        ["Prefijo de la consulta", datos.prefijo || "—", "El último término de la consulta del sondeo"],
    ]);
    $("resumen-arbol").textContent = datos.traza
        ? `Demostración de grado ${datos.grado} con ${num(datos.claves)} términos repartidos en el alfabeto. El prefijo «${datos.prefijo}» baja por el camino naranja `
          + `(${num(datos.niveles.length)} niveles) y barre las hojas contiguas en violeta. Pasa el ratón sobre una caja para ver sus claves.`
        : `Demostración de grado ${datos.grado} con ${num(datos.claves)} términos repartidos en el alfabeto. Escribe una consulta arriba para ver su camino. Pasa el ratón sobre una caja para ver sus claves.`;
}

function pintarArboles(animar = false) {
    const c = estado.corpus;
    if (!c) return;
    const a = c.arboles;
    const v = a.vocabulario;
    const s = estado.sondeo;
    const traza = s && s.vocabulario ? s.vocabulario : null;
    if (estado.arbolModo === "demo") {
        pintarArbolDemo();
        return;
    }
    $("titulo-arbol").textContent = "Árbol del vocabulario, nivel por nivel";

    chips($("chips-arboles"), [
        ["Grado t", num(a.grado), `Cada nodo guarda entre ${a.grado - 1} y ${2 * a.grado - 1} claves (la raíz, menos)`],
        ["Altura del vocabulario", `${v.altura} (cota ${v.cota_altura})`, "Todas las hojas a la misma profundidad; h ≤ 1 + log_t((n+1)/2)"],
        ["Nodos", num(v.nodos)],
        ["Hojas", num(v.hojas)],
        ["Términos (claves)", num(v.claves)],
        ["Llenado medio", `${porcentaje(v.llenado, 1)} %`, "Claves guardadas / capacidad de los nodos"],
    ]);
    arbolPorNiveles($("graf-arbol"), v.niveles, traza, { animar });
    $("resumen-arbol").textContent = traza
        ? `El prefijo «${traza.prefijo}» bajó ${num(traza.descenso.length)} niveles y recorrió ${num(traza.nodos_tocados)} de ${num(traza.nodos_total)} nodos `
          + `(${porcentaje(traza.nodos_tocados, traza.nodos_total)} %) para entregar ${num(traza.expandidos)} de ${num(traza.terminos_total)} términos, sin leer el vocabulario completo.`
        : "Escribe una consulta arriba: el camino de la raíz a la hoja (naranja) y el barrido de las hojas contiguas (violeta) se marcan aquí.";

    // Un árbol B por término (los postings)
    const p = a.postings[estado.modo];
    barrasVerticales($("graf-alturas"), p.alturas.map((x) => ({
        etiqueta: `h = ${x.altura}`,
        valor: x.arboles,
        tip: `${num(x.arboles)} árboles de postings tienen altura ${x.altura}`,
    })), { log: true, etiquetaY: "árboles (escala log)", aria: "Alturas de los árboles de postings", animar });
    $("nota-alturas").textContent = `${porcentaje(p.una_hoja, p.arboles)} % de los ${num(p.arboles)} árboles de postings son una sola hoja `
        + `(hasta ${num(2 * a.grado - 1)} documentos). Aquí el árbol B funciona como lista ordenada: su beneficio real está en el vocabulario y en las categorías, no en los postings.`;

    // Un árbol B por categoría
    const k = a.categorias;
    const nombradas = new Set(((s && s.categorias) || []).map((cat) => cat.nombre));
    barrasHorizontales($("graf-categorias"), k.top.map((cat) => ({
        etiqueta: cat.nombre,
        valor: cat.documentos,
        resaltado: nombradas.has(cat.nombre),
        tip: `${cat.nombre}: ${num(cat.documentos)} documentos en un árbol B de altura ${cat.altura}`,
    })), { aria: "Documentos por categoría", animar });
    $("nota-categorias").textContent = `${num(k.categorias)} categorías en un árbol B de altura ${k.altura}; cada una guarda sus documentos `
        + `en su propio árbol (clave: idioma, nombre, posición). Se resaltan las categorías que la consulta nombra completas.`;
    pintarMapa(nombradas);
}

// --- Sondeo de una consulta ----------------------------------------------------------------------------------
let secuenciaSondeo = 0;
let controladorSondeo = null;
let temporizadorSondeo = null;

function textoResumenSondeo(s) {
    if (!s) return "Escribe algo (p. ej. «pol» o «fruta tropical») y mira qué toca por dentro: se resalta en todas las gráficas.";
    if (s.vacio) return `«${s.consulta}» no se expande a ningún término del índice ni a ningún emoji del catálogo.`;
    const v = s.vocabulario;
    return `Modo «${s.modo}» · ${num(s.terminos_total)} términos · ${num(s.postings_tocados)} postings leídos de ${num(s.postings_totales)} · ${num(s.candidatos)} candidatos`
        + (v ? ` · vocabulario: ${num(v.nodos_tocados)} de ${num(v.nodos_total)} nodos` : "");
}

function pintarSondeo() {
    $("sondeo-resumen").textContent = textoResumenSondeo(estado.sondeo);
    pintarIndice();
    pintarZipf();
    pintarArboles();
}

async function sondear(texto) {
    const mia = ++secuenciaSondeo;
    if (controladorSondeo) controladorSondeo.abort();
    if (!texto.trim()) {
        estado.sondeo = null;
        pintarSondeo();
        return;
    }
    controladorSondeo = new AbortController();
    try {
        const datos = await Api.analiticaSondeo(texto, controladorSondeo.signal);
        if (mia !== secuenciaSondeo) return;   // llegó una consulta más nueva
        estado.sondeo = datos;
    } catch (error) {
        if (error.name !== "AbortError") $("sondeo-resumen").textContent = "No se pudo consultar el servidor";
        return;
    }
    pintarSondeo();
}

// --- Carga de datos y "en vivo" ---------------------------------------------------------------------------------
function estadoVivo(texto, error = false) {
    const el = $("estado-vivo");
    el.textContent = texto;
    el.classList.toggle("error", error);
}

function refrescarReloj() {
    if (!$("en-vivo").checked) return estadoVivo("En pausa");
    if (!estado.actualizadoUso) return undefined;
    const segundos = Math.round((Date.now() - estado.actualizadoUso) / 1000);
    return estadoVivo(`Actualizado hace ${segundos} s`);
}

async function cargarCorpus(primera = false) {
    try {
        const nuevo = await Api.analiticaCorpus();
        if (JSON.stringify(nuevo) === JSON.stringify(estado.corpus)) return;
        estado.corpus = nuevo;
        pintarResumen();
        pintarIndice(primera);
        pintarZipf(primera);
        if (!estado.reproduccion) pintarHeaps(primera);
        pintarArboles(primera);
    } catch (error) {
        document.querySelectorAll(".g-vacio").forEach((el) => { el.textContent = "No se pudo consultar el servidor."; });
    }
}

async function cargarUso(primera = false) {
    try {
        const nuevo = await Api.analiticaUso();
        estado.actualizadoUso = Date.now();
        refrescarReloj();
        if (JSON.stringify(nuevo) === JSON.stringify(estado.uso)) return;
        estado.uso = nuevo;
        pintarResumen();
        if (estado.zipf.fuente === "consultas") {
            pintarZipf(primera);
            pulso($("panel-zipf"));
        }
        if (estado.heaps.fuente === "consultas" && !estado.reproduccion) {
            pintarHeaps(primera);
            pulso($("panel-heaps"));
        }
    } catch (error) {
        estadoVivo("Sin conexión con el servidor", true);
    }
}

// --- Arranque ------------------------------------------------------------------------------------------------------
activarTooltips();

segmentado("modo-indice", estado.modo, (valor) => {
    estado.modo = valor;
    pintarIndice(true);
    pintarArboles();
});
segmentado("zipf-fuente", estado.zipf.fuente, (valor) => { estado.zipf.fuente = valor; pintarZipf(true); });
segmentado("zipf-escala", estado.zipf.escala, (valor) => { estado.zipf.escala = valor; pintarZipf(true); });
segmentado("heaps-fuente", estado.heaps.fuente, (valor) => { detenerReproduccion(); estado.heaps.fuente = valor; pintarHeaps(true); });
segmentado("arbol-modo", estado.arbolModo, (valor) => { estado.arbolModo = valor; pintarArboles(true); });
segmentado("heaps-escala", estado.heaps.escala, (valor) => { detenerReproduccion(); estado.heaps.escala = valor; pintarHeaps(true); });

$("histo-log").addEventListener("change", (evento) => {
    estado.histogramaLog = evento.target.checked;
    pintarIndice();
});
$("heaps-reproducir").addEventListener("click", reproducirHeaps);
$("en-vivo").addEventListener("change", () => {
    refrescarReloj();
    if ($("en-vivo").checked) cargarUso();
});
$("sondeo-q").addEventListener("input", (evento) => {
    clearTimeout(temporizadorSondeo);
    temporizadorSondeo = setTimeout(() => sondear(evento.target.value), PAUSA_SONDEO_MS);
});

setInterval(() => { if ($("en-vivo").checked && !document.hidden) cargarUso(); }, REFRESCO_USO_MS);
setInterval(() => { if (!document.hidden) cargarCorpus(); }, REFRESCO_CORPUS_MS);
setInterval(refrescarReloj, 1000);

// /analitica?q=pol abre con esa consulta ya sondeada
const inicial = new URLSearchParams(window.location.search).get("q");
if (inicial) $("sondeo-q").value = inicial;

cargarCache();
cargarRetencion();
setInterval(() => { if ($("en-vivo").checked && !document.hidden) cargarCache(); }, REFRESCO_USO_MS);

Promise.all([cargarCorpus(true), cargarUso(true)]).then(() => {
    if (inicial) sondear(inicial);
});

