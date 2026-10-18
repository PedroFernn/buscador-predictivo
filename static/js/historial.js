// Historial local de búsquedas (localStorage): las más recientes primero, sin duplicados,
// con el idioma dominante que estaba activo al buscar.
import { normalizar } from "./util.js";

const CLAVE_HISTORIAL = "buscador_historial";
export const MAX_HISTORIAL = 10;
export const PAUSA_GUARDADO_MS = 1000;   // se guarda cuando el usuario deja de teclear
const VENTANA_PREFIJO_MS = 8000;         // "pan" -> "pancake" reemplaza, no se acumula

export function leerHistorial() {
    try {
        const crudo = localStorage.getItem(CLAVE_HISTORIAL);
        const datos = crudo ? JSON.parse(crudo) : [];
        return Array.isArray(datos) ? datos.filter((e) => e && typeof e.consulta === "string") : [];
    } catch (error) {
        return [];
    }
}

function escribirHistorial(entradas) {
    try {
        localStorage.setItem(CLAVE_HISTORIAL, JSON.stringify(entradas));
    } catch (error) {
        // Almacenamiento no disponible (modo privado, cuota): se ignora.
    }
}

// Devuelve el texto guardado, o null si es demasiado corto
export function guardarEnHistorial(consulta, idioma) {
    const texto = consulta.trim();
    if (texto.length < 2) return null;

    const clave = normalizar(texto);
    const ahora = Date.now();
    let entradas = leerHistorial();

    // Si lo recién escrito solo extiende la última búsqueda guardada hace pocos segundos
    // (el usuario seguía tecleando), esa entrada se reemplaza.
    const ultima = entradas[0];
    if (
        ultima &&
        ahora - ultima.ts < VENTANA_PREFIJO_MS &&
        clave !== normalizar(ultima.consulta) &&
        clave.startsWith(normalizar(ultima.consulta))
    ) {
        entradas.shift();
    }

    // Sin duplicados: repetir una búsqueda la sube al primer lugar y suma un uso (n).
    const previa = entradas.find((e) => normalizar(e.consulta) === clave);
    const n = previa ? (previa.n || 1) + 1 : 1;
    entradas = entradas.filter((e) => normalizar(e.consulta) !== clave);
    entradas.unshift({ consulta: texto, idioma, ts: ahora, n });
    escribirHistorial(entradas.slice(0, MAX_HISTORIAL));
    return texto;
}

export function quitarDelHistorial(consulta) {
    const clave = normalizar(consulta);
    escribirHistorial(leerHistorial().filter((e) => normalizar(e.consulta) !== clave));
}

export function borrarHistorial() {
    escribirHistorial([]);
}

function boton(clase, texto, titulo) {
    const nodo = document.createElement("button");
    nodo.type = "button";
    nodo.className = clase;
    nodo.textContent = texto;
    nodo.title = titulo;
    return nodo;
}

export function pintarHistorial(seccion, lista, banderaDe, { alRepetir, alQuitar }) {
    const entradas = leerHistorial();
    lista.replaceChildren();
    seccion.hidden = entradas.length === 0;
    for (const entrada of entradas) {
        const li = document.createElement("li");
        li.className = "item-historial";
        const reutilizar = boton("reutilizar", `${banderaDe(entrada.idioma)} ${entrada.consulta}`.trim(), "Repetir esta búsqueda");
        reutilizar.addEventListener("click", () => alRepetir(entrada));
        const quitar = boton("quitar", "×", "Quitar del historial");
        quitar.setAttribute("aria-label", `Quitar "${entrada.consulta}" del historial`);
        quitar.addEventListener("click", () => alQuitar(entrada.consulta));
        li.append(reutilizar, quitar);
        lista.append(li);
    }
}
