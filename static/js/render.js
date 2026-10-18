// Pintado con DOM y textContent: nada del catálogo ni del servidor pasa por innerHTML.
import { normalizar } from "./util.js";

const REACCIONES = [
    { tipo: "me_gusta", icono: "👍", titulo: "Me gusta" },
    { tipo: "me_encanta", icono: "😍", titulo: "Me encanta" },
    { tipo: "no_me_gusta", icono: "👎", titulo: "No me gusta" },
];

function crear(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
}

// Resalta los términos coincidentes con <mark>; el resto queda como nodos de texto
export function resaltar(texto, terminos) {
    const fragmento = document.createDocumentFragment();
    const hayTerminos = terminos && terminos.length > 0;
    let ultimo = 0;
    for (const m of texto.matchAll(/[\p{L}\p{N}]+/gu)) {
        const palabra = m[0];
        if (m.index > ultimo) fragmento.append(texto.slice(ultimo, m.index));
        const coincide = hayTerminos && terminos.some((t) => normalizar(palabra).startsWith(t));
        fragmento.append(coincide ? crear("mark", "", palabra) : palabra);
        ultimo = m.index + palabra.length;
    }
    if (ultimo < texto.length) fragmento.append(texto.slice(ultimo));
    return fragmento;
}

// Muestra qué entendió el sistema: los emojis detectados (con cuántos documentos los usan;
// 0 = se interpretó por su significado) y los términos a los que se expandió la consulta
export function pintarPrediccion(contenedor, terminos, emojis) {
    contenedor.replaceChildren();
    if (!(terminos && terminos.length) && !(emojis && emojis.length)) return;
    contenedor.append(crear("span", "etiqueta", "Prediciendo:"));
    for (const e of emojis || []) {
        const chip = crear("span", "chip chip-emoji", e.coincidencias > 0 ? `${e.emoji} ×${Number(e.coincidencias)}` : e.emoji);
        chip.title = e.coincidencias > 0
            ? `${e.coincidencias} documento(s) usan este emoji`
            : "Ningún documento lo usa: interpretado por su significado";
        contenedor.append(chip);
    }
    for (const t of (terminos || []).slice(0, 8)) contenedor.append(crear("span", "chip", t));
}

export function pintarContador(contador, datos) {
    contador.textContent = datos.consulta === ""
        ? `${datos.total_coincidencias} documento(s) en total`
        : `Mostrando ${datos.resultados.length} de ${datos.total_coincidencias} coincidencias, ordenadas por relevancia`;
}

// Desglose del score por componente (viene en `explicacion`); se muestra como tooltip.
function textoExplicacion(e) {
    if (!e) return "";
    const f = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(2));
    return [
        `Coseno ${f(e.coseno)} + emoji ${f(e.emoji)}`,
        `× idioma ${f(e.factor_idioma)} = score ${f(e.score)}`,
        `Reacciones ×${f(e.reacciones)} · aprendizaje ×${f(e.aprendizaje)}`,
        `Orden (score × peso): ${f(e.orden)}`,
    ].join("\n");
}

// Insignia R(qk, dj): porcentaje + barra. No se muestra si no hay consulta activa.
// El score puede superar 1.0 (boost de idioma): la barra y el porcentaje se acotan a 100.
function insigniaRelevancia(score, explicacion) {
    if (score === null || score === undefined) return null;
    const porcentaje = Math.min(100, Math.max(0, Math.round(score * 100)));
    const insignia = crear("span", "relevancia");
    insignia.title = textoExplicacion(explicacion);
    const barra = crear("span", "barra");
    const relleno = document.createElement("span");
    relleno.style.width = `${porcentaje}%`;
    barra.append(relleno);
    insignia.append(crear("span", "porcentaje", `${porcentaje}%`), barra);
    return insignia;
}

function botonesReaccion(item, alReaccionar) {
    const contenedor = crear("div", "reacciones");
    for (const r of REACCIONES) {
        const boton = crear("button", "reaccion");
        boton.type = "button";
        boton.dataset.tipo = r.tipo;
        boton.title = r.titulo;
        boton.setAttribute("aria-label", r.titulo);
        boton.append(`${r.icono} `, crear("span", "cuenta", String(Number(item.reacciones[r.tipo]) || 0)));
        boton.addEventListener("click", (evento) => {
            evento.stopPropagation(); // no cuenta como selección del resultado
            alReaccionar(item.id, r.tipo);
        });
        contenedor.append(boton);
    }
    return contenedor;
}

function filaResultado(item, posicion, terminos, idiomaActual, manejadores) {
    const li = crear("li", item.idioma !== idiomaActual ? "resultado secundario" : "resultado");

    const nombre = crear("span", "nombre");
    nombre.append(resaltar(item.nombre, terminos));
    const filaNombre = crear("span", "fila-nombre");
    filaNombre.append(
        nombre,
        crear("span", "categoria", item.categoria),
        crear("span", "idioma", `${item.bandera} ${item.idioma_nombre}`),
    );
    if (item.homografo) filaNombre.append(crear("span", "homografo", "falso amigo"));

    const descripcion = crear("span", "descripcion");
    descripcion.append(resaltar(item.descripcion, terminos));
    const info = crear("span", "info");
    info.append(filaNombre, descripcion, botonesReaccion(item, manejadores.alReaccionar));

    li.append(
        crear("span", "indice", `#${posicion}`),
        crear("span", item.emoji_coincide ? "emoji coincide" : "emoji", item.emoji),
        info,
    );
    const insignia = insigniaRelevancia(item.score, item.explicacion);
    if (insignia) li.append(insignia);

    // Elegir un resultado alimenta el aprendizaje de la consulta actual (con su posición)
    li.addEventListener("click", () => manejadores.alElegir(item.id, posicion));
    return li;
}

export function pintarResultados(lista, items, terminos, idiomaActual, manejadores) {
    lista.replaceChildren();
    if (items.length === 0) {
        lista.append(crear("li", "vacio", "Sin coincidencias relevantes 🤔"));
        return;
    }
    items.forEach((item, idx) => {
        lista.append(filaResultado(item, idx + 1, terminos, idiomaActual, manejadores));
    });
}
