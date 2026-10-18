// "Sugerencias para ti": documentos del catálogo que encajan con la tendencia de la persona,
// calculada por el servidor (POST /api/recomendaciones) con su historial y sus reacciones.
// Sin huellas suficientes el panel queda vacío y solo explica cómo llenarlo.
import { pedirRecomendaciones } from "./api.js";
import { armarPerfil, perfilVacio } from "./perfil.js";

const LIMITE_RECOMENDACIONES = 6;
const MENSAJE_VACIO =
    "Aún no hay sugerencias. Busca y reacciona (👍 😍 👎) a los resultados: " +
    "con unas pocas interacciones verás aquí lo que encaja contigo.";
let secuencia = 0;
let controlador = null;

function elemento(clase, etiqueta, texto) {
    const nodo = document.createElement(etiqueta);
    nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
}

function tarjeta(item, alElegir) {
    const li = elemento("item-recomendacion", "li");
    const boton = elemento("recomendacion", "button");
    boton.type = "button";
    const motivos = (item.motivos || []).join(", ");
    boton.title = [item.descripcion, motivos && `Porque te interesa: ${motivos}`].filter(Boolean).join("\n");
    boton.append(
        elemento("emoji", "span", item.emoji),
        elemento("nombre", "span", item.nombre),
        elemento("categoria", "span", `${item.bandera} ${item.categoria}`.trim()),
    );
    boton.addEventListener("click", () => alElegir(item));
    li.append(boton);
    return li;
}

function pintar({ seccion, lista, vacio }, items, alElegir) {
    lista.replaceChildren(...items.map((item) => tarjeta(item, alElegir)));
    vacio.textContent = MENSAJE_VACIO;
    vacio.hidden = items.length > 0;
    seccion.dataset.vacio = items.length === 0 ? "1" : "0";
}

// `refs` = { seccion, lista, vacio }; `alElegir(item)` busca ese elemento
export async function actualizarRecomendaciones(refs, idioma, alElegir) {
    const mia = ++secuencia;
    const perfil = armarPerfil();
    if (perfilVacio(perfil)) {
        pintar(refs, [], alElegir);  // sin huellas no hace falta preguntar
        return;
    }
    if (controlador) controlador.abort();
    controlador = new AbortController();
    let items = [];
    try {
        const datos = await pedirRecomendaciones(perfil, idioma, LIMITE_RECOMENDACIONES, controlador.signal);
        items = Array.isArray(datos.elementos) ? datos.elementos : [];
    } catch (error) {
        if (error.name === "AbortError") return;  // llegó una petición más nueva
        // Sin servidor: el panel queda vacío; el resto de la página sigue funcionando.
    }
    if (mia !== secuencia) return;  // respuesta vieja: se descarta
    pintar(refs, items, alElegir);
}
