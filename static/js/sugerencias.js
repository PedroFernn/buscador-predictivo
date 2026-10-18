// Sugerencias por frecuencia (Zipf). El servidor devuelve, ya ordenadas por frecuencia real,
// las consultas más buscadas con el prefijo escrito. Los prefijos populares se repiten
// muchísimo, así que además hay un cache LRU en el navegador: lo ya pedido no vuelve a viajar.
import { pedirSugerencias } from "./api.js";
import { leerHistorial } from "./historial.js";
import { claveSugerencia } from "./util.js";

const LIMITE_SUGERENCIAS = 6;
const MAX_CACHE_SUGERENCIAS = 200;
const TTL_CACHE_SUGERENCIAS_MS = 30000;
const REINTENTO_SERVIDOR_MS = 60000;
const cache = new Map();  // clave -> { ts, datos }; el orden del Map es el LRU
let secuencia = 0;
let controlador = null;
let servidorCaidoHasta = 0;

async function pedir(prefijo) {
    const clave = claveSugerencia(prefijo);
    const guardada = cache.get(clave);
    if (guardada && Date.now() - guardada.ts < TTL_CACHE_SUGERENCIAS_MS) {
        cache.delete(clave);
        cache.set(clave, guardada);  // la más reciente al final
        return guardada.datos;
    }
    if (controlador) controlador.abort();
    controlador = new AbortController();
    const datos = await pedirSugerencias(prefijo, LIMITE_SUGERENCIAS, controlador.signal);
    cache.delete(clave);
    cache.set(clave, { ts: Date.now(), datos });
    if (cache.size > MAX_CACHE_SUGERENCIAS) {
        cache.delete(cache.keys().next().value);  // fuera la menos usada
    }
    return datos;
}

// Respaldo si el servidor no responde: tus propias búsquedas, las más repetidas primero.
function locales(prefijo) {
    const p = claveSugerencia(prefijo);
    return leerHistorial()
        .filter((e) => claveSugerencia(e.consulta).startsWith(p))
        .sort((a, b) => (b.n || 1) - (a.n || 1) || b.ts - a.ts)
        .slice(0, LIMITE_SUGERENCIAS)
        .map((e) => ({ consulta: e.consulta, frecuencia: e.n || 1 }));
}

function pintar({ seccion, lista, titulo }, items, prefijo, local, alElegir) {
    const actual = claveSugerencia(prefijo);
    const visibles = items.filter((i) => claveSugerencia(i.consulta) !== actual);
    lista.replaceChildren();
    seccion.hidden = visibles.length === 0;
    titulo.textContent = actual === ""
        ? (local ? "🔁 Tus búsquedas más repetidas" : "🔥 Más buscadas")
        : (local ? "🔁 Tus búsquedas con ese inicio" : "🔥 Sugerencias populares");

    for (const item of visibles) {
        const li = document.createElement("li");
        li.className = "item-sugerencia";
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "sugerencia";
        boton.title = local
            ? `La has buscado ${item.frecuencia} vez/veces`
            : `Buscada ${item.frecuencia} vez/veces en la ventana reciente`;
        const texto = document.createElement("span");
        texto.textContent = item.consulta;
        const cuenta = document.createElement("span");
        cuenta.className = "frecuencia";
        cuenta.textContent = `×${item.frecuencia}`;
        boton.append(texto, cuenta);
        boton.addEventListener("click", () => alElegir(item.consulta));
        li.append(boton);
        lista.append(li);
    }
}

// `refs` = { seccion, lista, titulo }; `alElegir(consulta)` repite esa búsqueda
export async function actualizarSugerencias(prefijo, refs, alElegir) {
    const mia = ++secuencia;
    let items = null;
    let local = false;
    if (Date.now() >= servidorCaidoHasta) {
        try {
            items = (await pedir(prefijo)).sugerencias;
        } catch (error) {
            if (error.name === "AbortError") return;  // llegó una tecla más nueva
            servidorCaidoHasta = Date.now() + REINTENTO_SERVIDOR_MS;
        }
    }
    if (mia !== secuencia) return;  // respuesta vieja: se descarta
    if (items === null) {
        items = locales(prefijo);
        local = true;
    }
    pintar(refs, items, prefijo, local, alElegir);
}
