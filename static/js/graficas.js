// Gráficas SVG sin dependencias (el proyecto no usa frameworks). Cada función dibuja dentro de un
// contenedor y se puede volver a llamar con datos nuevos: reemplaza lo anterior. El color y la
// tipografía viven en static/analitica.css (clases .g-*), no aquí.

const ANCHO = 640;

export const esc = (texto) => String(texto).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

export function num(valor, decimales = 0) {
    return Number(valor).toLocaleString("es-MX", { maximumFractionDigits: decimales });
}

// --- Escalas y marcas ---------------------------------------------------------------------
function redondeoAgradable(max) {
    if (!(max > 0)) return 1;
    const e = 10 ** Math.floor(Math.log10(max));
    const f = max / e;
    const paso = [1, 1.5, 2, 3, 4, 5, 6, 8, 10].find((p) => f <= p + 1e-9);
    return paso * e;
}

function dominioDe(valores, log) {
    const vs = valores.filter((v) => Number.isFinite(v) && (!log || v > 0));
    if (!vs.length) return log ? [1, 10] : [0, 1];
    if (log) {
        const a = Math.floor(Math.log10(Math.min(...vs)));
        const b = Math.ceil(Math.log10(Math.max(...vs)));
        return [10 ** a, 10 ** (b === a ? a + 1 : b)];
    }
    return [0, redondeoAgradable(Math.max(...vs))];
}

function escala(dominio, rango, log) {
    const f = log ? Math.log10 : (v) => v;
    const a = f(dominio[0]);
    const b = f(dominio[1]);
    return (v) => rango[0] + ((f(v) - a) / (b - a || 1)) * (rango[1] - rango[0]);
}

function marcas(dominio, log) {
    const salida = [];
    if (log) {
        for (let e = Math.round(Math.log10(dominio[0])); e <= Math.round(Math.log10(dominio[1])); e++) {
            salida.push(Number((10 ** e).toPrecision(12)));
        }
        return salida;
    }
    const paso = redondeoAgradable((dominio[1] - dominio[0]) / 5);
    for (let v = dominio[0]; v <= dominio[1] + paso * 1e-9; v += paso) salida.push(Number(v.toPrecision(12)));
    return salida;
}

function compacto(v) {
    if (v >= 1e6) return `${num(v / 1e6, 1)} M`;
    if (v >= 1e4) return `${num(v / 1e3, 1)} k`;
    return num(v, v < 1 ? 2 : 0);
}

// --- Tooltips (un solo elemento para toda la página) ------------------------------------------
let globo = null;

export function activarTooltips() {
    if (globo) return;
    globo = document.createElement("div");
    globo.className = "g-globo";
    globo.hidden = true;
    document.body.appendChild(globo);
    document.addEventListener("pointermove", (evento) => {
        const elemento = evento.target.closest ? evento.target.closest("[data-tip]") : null;
        if (!elemento) {
            globo.hidden = true;
            return;
        }
        globo.textContent = elemento.dataset.tip;
        globo.hidden = false;
        const izquierda = Math.min(evento.clientX + 14, window.innerWidth - globo.offsetWidth - 8);
        globo.style.left = `${Math.max(4, izquierda)}px`;
        globo.style.top = `${evento.clientY + 16}px`;
    });
    document.addEventListener("pointerleave", () => { globo.hidden = true; });
}

export function vacio(contenedor, mensaje) {
    contenedor.innerHTML = `<p class="g-vacio">${esc(mensaje)}</p>`;
}

// Las líneas continuas se "dibujan" al aparecer (solo si se pide animar)
function animarTrazos(contenedor) {
    contenedor.querySelectorAll("path.g-trazo").forEach((trazo) => {
        if (typeof trazo.getTotalLength !== "function") return;
        const largo = trazo.getTotalLength();
        trazo.style.strokeDasharray = `${largo}`;
        trazo.style.strokeDashoffset = `${largo}`;
        requestAnimationFrame(() => {
            trazo.style.transition = "stroke-dashoffset 0.9s ease-out";
            trazo.style.strokeDashoffset = "0";
        });
    });
}

// --- Dispersión (Zipf, Heaps) -------------------------------------------------------------------
// cfg: {
//   series:    [{ nombre, clase, puntos: [[x, y]], linea?: bool, tip?: (x, y) => texto }],
//   ajustes:   [{ nombre, clase, f: (x) => y, x0, x1 }],           curva teórica ajustada
//   resaltados:[{ x, y, etiqueta? }],                              puntos que se quieren destacar
//   logX, logY, etiquetaX, etiquetaY, aria, animar, domX?, domY?   dominios fijos (para animar sin saltos)
//   leyenda:   "arriba" (por defecto; Zipf, donde los datos bajan) o "abajo" (Heaps, donde suben), siempre a la derecha
// }
// Devuelve los dominios usados, por si quien llama quiere fijarlos.
export function dominiosDe(cfg) {
    const todos = cfg.series.flatMap((s) => s.puntos);
    return {
        domX: cfg.domX || dominioDe(todos.map((p) => p[0]), cfg.logX),
        domY: cfg.domY || dominioDe(todos.map((p) => p[1]), cfg.logY),
    };
}

export function dispersion(contenedor, cfg) {
    const alto = 340;
    const m = { i: 62, d: 18, a: 16, b: 50 };
    const { domX, domY } = dominiosDe(cfg);
    const ex = escala(domX, [m.i, ANCHO - m.d], cfg.logX);
    const ey = escala(domY, [alto - m.b, m.a], cfg.logY);
    const valido = (x, y) => Number.isFinite(x) && Number.isFinite(y)
        && (!cfg.logX || x > 0) && (!cfg.logY || y > 0);

    let svg = `<svg class="grafica${cfg.animar ? " anima" : ""}" viewBox="0 0 ${ANCHO} ${alto}" role="img" aria-label="${esc(cfg.aria || "")}">`;

    for (const v of marcas(domY, cfg.logY)) {
        const y = ey(v);
        svg += `<line class="g-rej" x1="${m.i}" x2="${ANCHO - m.d}" y1="${y}" y2="${y}"/>`
            + `<text class="g-marca" x="${m.i - 8}" y="${y + 4}" text-anchor="end">${compacto(v)}</text>`;
    }
    for (const v of marcas(domX, cfg.logX)) {
        const x = ex(v);
        svg += `<line class="g-rej" x1="${x}" x2="${x}" y1="${m.a}" y2="${alto - m.b}"/>`
            + `<text class="g-marca" x="${x}" y="${alto - m.b + 16}" text-anchor="middle">${compacto(v)}</text>`;
    }
    svg += `<line class="g-eje" x1="${m.i}" x2="${ANCHO - m.d}" y1="${alto - m.b}" y2="${alto - m.b}"/>`
        + `<line class="g-eje" x1="${m.i}" x2="${m.i}" y1="${m.a}" y2="${alto - m.b}"/>`
        + `<text class="g-titulo-eje" x="${(m.i + ANCHO - m.d) / 2}" y="${alto - 8}" text-anchor="middle">${esc(cfg.etiquetaX || "")}</text>`
        + `<text class="g-titulo-eje" transform="translate(14 ${(m.a + alto - m.b) / 2}) rotate(-90)" text-anchor="middle">${esc(cfg.etiquetaY || "")}</text>`;

    // Curvas ajustadas (debajo de los puntos)
    for (const ajuste of cfg.ajustes || []) {
        const trozos = [];
        const a = Math.max(ajuste.x0, domX[0]);
        const b = Math.min(ajuste.x1, domX[1]);
        for (let i = 0; i <= 48 && b > a; i++) {
            const x = cfg.logX ? a * (b / a) ** (i / 48) : a + ((b - a) * i) / 48;
            const y = ajuste.f(x);
            if (valido(x, y) && y >= domY[0] && y <= domY[1]) trozos.push(`${trozos.length ? "L" : "M"}${ex(x).toFixed(1)} ${ey(y).toFixed(1)}`);
        }
        if (trozos.length > 1) svg += `<path class="g-ajuste ${ajuste.clase || ""}" d="${trozos.join(" ")}"/>`;
    }

    for (const serie of cfg.series) {
        const visibles = serie.puntos.filter(([x, y]) => valido(x, y));
        if (serie.linea && visibles.length > 1) {
            svg += `<path class="g-trazo ${serie.clase || ""}" d="${visibles.map(([x, y], i) => `${i ? "L" : "M"}${ex(x).toFixed(1)} ${ey(y).toFixed(1)}`).join(" ")}"/>`;
        }
        for (const [x, y] of visibles) {
            const tip = serie.tip ? serie.tip(x, y) : `${serie.nombre}: (${num(x)}, ${num(y, 2)})`;
            svg += `<circle class="g-punto ${serie.clase || ""}" cx="${ex(x).toFixed(1)}" cy="${ey(y).toFixed(1)}" r="${serie.linea ? 3 : 3.4}" data-tip="${esc(tip)}"/>`;
        }
    }

    for (const r of cfg.resaltados || []) {
        if (!valido(r.x, r.y)) continue;
        const x = ex(r.x);
        const y = ey(r.y);
        svg += `<circle class="g-punto resaltado" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.5" data-tip="${esc(r.tip || r.etiqueta || "")}"/>`;
        if (r.etiqueta) svg += `<text class="g-etiqueta-punto" x="${(x + 8).toFixed(1)}" y="${(y - 7).toFixed(1)}">${esc(r.etiqueta)}</text>`;
    }

    // Leyenda a la derecha, en la esquina que los datos dejan libre
    const leyenda = [...cfg.series.map((s) => [s.nombre, s.clase, "punto"]), ...(cfg.ajustes || []).map((a) => [a.nombre, a.clase, "ajuste"])];
    const derecha = ANCHO - m.d - 10;
    const arriba = cfg.leyenda !== "abajo";
    leyenda.forEach(([nombre, clase, tipo], i) => {
        const y = arriba
            ? m.a + 16 + i * 17
            : alto - m.b - 12 - (leyenda.length - 1 - i) * 17;
        svg += `<text class="g-leyenda" x="${derecha - 26}" y="${y}" text-anchor="end">${esc(nombre)}</text>`;
        svg += tipo === "punto"
            ? `<circle class="g-punto ${clase || ""}" cx="${derecha - 10}" cy="${y - 4}" r="4"/>`
            : `<line class="g-ajuste ${clase || ""}" x1="${derecha - 20}" x2="${derecha}" y1="${y - 4}" y2="${y - 4}"/>`;
    });

    contenedor.innerHTML = `${svg}</svg>`;
    if (cfg.animar) animarTrazos(contenedor);
    return { domX, domY };
}

// --- Barras --------------------------------------------------------------------------------------
function recortar(texto, largo) {
    texto = String(texto);
    return texto.length > largo ? `${texto.slice(0, largo - 1)}…` : texto;
}

// filas: [{ etiqueta, valor, resaltado?, tip? }]   opc: { formato?, aria?, animar?, ancho_etiqueta? }
export function barrasHorizontales(contenedor, filas, opc = {}) {
    if (!filas.length) return vacio(contenedor, opc.vacio || "Sin datos todavía.");
    const formato = opc.formato || ((v) => num(v));
    const altoFila = 25;
    const etiqueta = opc.ancho_etiqueta || 150;
    const derecha = 74;
    const alto = filas.length * altoFila + 8;
    const maximo = Math.max(...filas.map((f) => f.valor), 1);
    const util = ANCHO - etiqueta - derecha;

    let svg = `<svg class="grafica${opc.animar ? " anima" : ""}" viewBox="0 0 ${ANCHO} ${alto}" role="img" aria-label="${esc(opc.aria || "")}">`;
    filas.forEach((fila, i) => {
        const y = 4 + i * altoFila;
        const largo = Math.max(2, (fila.valor / maximo) * util);
        const tip = fila.tip || `${fila.etiqueta}: ${formato(fila.valor)}`;
        svg += `<text class="g-marca" x="${etiqueta - 8}" y="${y + 15}" text-anchor="end">${esc(recortar(fila.etiqueta, 22))}</text>`
            + `<rect class="g-barra${fila.resaltado ? " resaltado" : ""}" x="${etiqueta}" y="${y + 2}" width="${largo.toFixed(1)}" height="${altoFila - 8}" rx="3" data-tip="${esc(tip)}"/>`
            + `<text class="g-valor" x="${(etiqueta + largo + 6).toFixed(1)}" y="${y + 15}">${esc(formato(fila.valor))}</text>`;
    });
    contenedor.innerHTML = `${svg}</svg>`;
}

// columnas: [{ etiqueta, valor, tip? }]   opc: { log?, etiquetaY?, aria?, animar? }
export function barrasVerticales(contenedor, columnas, opc = {}) {
    if (!columnas.length) return vacio(contenedor, opc.vacio || "Sin datos todavía.");
    const alto = 300;
    const m = { i: 56, d: 12, a: 14, b: 54 };
    const dom = opc.log ? dominioDe(columnas.map((c) => c.valor), true) : dominioDe(columnas.map((c) => c.valor), false);
    const ey = escala(dom, [alto - m.b, m.a], opc.log);
    const ancho = (ANCHO - m.i - m.d) / columnas.length;

    let svg = `<svg class="grafica${opc.animar ? " anima" : ""}" viewBox="0 0 ${ANCHO} ${alto}" role="img" aria-label="${esc(opc.aria || "")}">`;
    for (const v of marcas(dom, opc.log)) {
        const y = ey(v);
        svg += `<line class="g-rej" x1="${m.i}" x2="${ANCHO - m.d}" y1="${y}" y2="${y}"/>`
            + `<text class="g-marca" x="${m.i - 8}" y="${y + 4}" text-anchor="end">${compacto(v)}</text>`;
    }
    columnas.forEach((col, i) => {
        const x = m.i + i * ancho + ancho * 0.12;
        const base = alto - m.b;
        const arriba = col.valor > 0 && (!opc.log || col.valor >= 1) ? ey(col.valor) : base;
        const tip = col.tip || `${col.etiqueta}: ${num(col.valor)}`;
        svg += `<rect class="g-barra${col.resaltado ? " resaltado" : ""}" x="${x.toFixed(1)}" y="${arriba.toFixed(1)}" width="${(ancho * 0.76).toFixed(1)}" height="${Math.max(0, base - arriba).toFixed(1)}" rx="2" data-tip="${esc(tip)}"/>`
            + `<text class="g-marca" x="${(x + ancho * 0.38).toFixed(1)}" y="${base + 15}" text-anchor="middle">${esc(col.etiqueta)}</text>`;
    });
    svg += `<line class="g-eje" x1="${m.i}" x2="${ANCHO - m.d}" y1="${alto - m.b}" y2="${alto - m.b}"/>`
        + `<text class="g-titulo-eje" x="${(m.i + ANCHO - m.d) / 2}" y="${alto - 8}" text-anchor="middle">${esc(opc.etiquetaX || "")}</text>`
        + `<text class="g-titulo-eje" transform="translate(14 ${(m.a + alto - m.b) / 2}) rotate(-90)" text-anchor="middle">${esc(opc.etiquetaY || "")}</text>`;
    contenedor.innerHTML = `${svg}</svg>`;
}

// --- Árbol B por niveles -------------------------------------------------------------------------
// niveles: [{ nodos, claves, celdas: [llenado 0-1] }] (raíz primero), tal como lo manda la API.
// traza:   { descenso: [[nivel, ordinal]], barrido: [[nivel, ordinal]] } o null.
// El eje horizontal es el orden alfabético del vocabulario: cada nivel ocupa todo el ancho, así el
// camino del prefijo cae en la misma región en todos los niveles.
export function arbolPorNiveles(contenedor, niveles, traza, opc = {}) {
    if (!niveles.length) return vacio(contenedor, "El árbol está vacío.");
    const etiqueta = 92;
    const altoFila = 34;
    const separacion = 16;
    const util = ANCHO - etiqueta - 10;
    const alto = niveles.length * (altoFila + separacion) + 30;
    const celdaDe = (nivel, ordinal) => {
        const { nodos, celdas } = niveles[nivel];
        return nodos <= celdas.length ? ordinal : Math.floor((ordinal * celdas.length) / nodos);
    };

    // Qué celdas toca la traza (el descenso pesa más que el barrido si coinciden)
    const marcadas = niveles.map(() => new Map());
    if (traza) {
        for (const [nivel, ordinal] of traza.barrido) marcadas[nivel].set(celdaDe(nivel, ordinal), "barrido");
        for (const [nivel, ordinal] of traza.descenso) marcadas[nivel].set(celdaDe(nivel, ordinal), "descenso");
    }

    let svg = `<svg class="grafica${opc.animar ? " anima" : ""}" viewBox="0 0 ${ANCHO} ${alto}" role="img" aria-label="${esc(opc.aria || "Árbol B del vocabulario por niveles")}">`;
    const centros = [];
    niveles.forEach((nivel, i) => {
        const y = 6 + i * (altoFila + separacion);
        const total = nivel.celdas.length;
        const ancho = util / total;
        const hueco = ancho > 6 ? 1.5 : 0.4;
        const nombre = i === 0 ? "Raíz" : i === niveles.length - 1 ? "Hojas" : `Nivel ${i + 1}`;
        svg += `<text class="g-marca fuerte" x="${etiqueta - 10}" y="${y + 14}" text-anchor="end">${nombre}</text>`
            + `<text class="g-marca" x="${etiqueta - 10}" y="${y + 28}" text-anchor="end">${num(nivel.nodos)} ${nivel.nodos === 1 ? "nodo" : "nodos"}</text>`;
        nivel.celdas.forEach((llenado, j) => {
            const x = etiqueta + j * ancho;
            const marca = marcadas[i].get(j);
            const que = nivel.nodos <= total ? `Nodo ${j + 1}` : `Nodos ${Math.ceil((j * nivel.nodos) / total) + 1}–${Math.ceil(((j + 1) * nivel.nodos) / total)}`;
            const tip = `${nombre} · ${que} · llenado ${Math.round(llenado * 100)} %${marca ? ` · ${marca}` : ""}`;
            svg += `<rect class="g-nodo${marca ? ` ${marca}` : ""}" x="${x.toFixed(2)}" y="${y}" width="${Math.max(ancho - hueco, 0.6).toFixed(2)}" height="${altoFila}" rx="${ancho > 6 ? 3 : 0}" style="--llenado:${llenado}" data-tip="${esc(tip)}"/>`;
            if (marca === "descenso" && !centros[i]) centros[i] = [x + (ancho - hueco) / 2, y + altoFila / 2];
        });
    });
    // El camino de la raíz a la hoja, como una línea que atraviesa los niveles. La raíz ocupa todo el
    // ancho: su punto se alinea con el del nivel siguiente para que la línea no haga un quiebre falso.
    const camino = centros.filter(Boolean).map((punto, i, todos) => (i === 0 && todos.length > 1 ? [todos[1][0], punto[1]] : punto));
    if (camino.length > 1) svg += `<polyline class="g-camino" points="${camino.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}"/>`;
    svg += `<text class="g-titulo-eje" x="${etiqueta + util / 2}" y="${alto - 6}" text-anchor="middle">← orden alfabético del vocabulario →</text>`;
    contenedor.innerHTML = `${svg}</svg>`;
}
