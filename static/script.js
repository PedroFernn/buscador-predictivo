// Buscador predictivo multilenguaje: cada tecla dispara una consulta al SRI

const inputBusqueda = document.getElementById("buscador");
const contenedorPrediccion = document.getElementById("prediccion");
const listaResultados = document.getElementById("resultados");
const contador = document.getElementById("contador");
const desglose = document.getElementById("desglose");
const botonesIdioma = document.querySelectorAll(".opcion-idioma");

// Idioma dominante actual: arranca en el que el backend marcó como activo.
let idiomaActual =
    document.querySelector(".opcion-idioma.activa")?.dataset.idioma || "es";

async function buscar(consulta) {
    const url =
        `/api/buscar?q=${encodeURIComponent(consulta)}` +
        `&idioma=${encodeURIComponent(idiomaActual)}`;
    const respuesta = await fetch(url);
    const datos = await respuesta.json();

    idiomaActual = datos.idioma_dominante;
    marcarBotonActivo();

    pintarDesglose();
    pintarPrediccion(datos.terminos_expandidos, datos.emojis);
    pintarContador(datos);
    pintarResultados(datos.resultados, datos.terminos_expandidos);
}

// --- Selector de idioma ----------------------------------------------
function marcarBotonActivo() {
    botonesIdioma.forEach((boton) => {
        boton.classList.toggle("activa", boton.dataset.idioma === idiomaActual);
    });
}

function nombreIdiomaActual() {
    const boton = document.querySelector(".opcion-idioma.activa");
    return boton ? boton.textContent.trim() : idiomaActual;
}

function pintarDesglose() {
    desglose.textContent = `${nombreIdiomaActual()} domina el ranking`;
}

botonesIdioma.forEach((boton) => {
    boton.addEventListener("click", () => {
        idiomaActual = boton.dataset.idioma;
        marcarBotonActivo();
        buscar(inputBusqueda.value);
    });
});

// --- Pintado de resultados -------------------------------------------

// Muestra qué entendió el sistema: los emojis detectados (con cuántos
// documentos lo usan; 0 = se interpretó por su significado) y los términos
// a los que se expandió la consulta (Q -> F)
function pintarPrediccion(terminos, emojis) {
    const hayTerminos = terminos && terminos.length > 0;
    const hayEmojis = emojis && emojis.length > 0;
    if (!hayTerminos && !hayEmojis) {
        contenedorPrediccion.innerHTML = "";
        return;
    }
    const chipsEmoji = (emojis || [])
        .map((e) => {
            const titulo = e.coincidencias > 0
                ? `${e.coincidencias} documento(s) usan este emoji`
                : "Ningún documento lo usa: interpretado por su significado";
            const cuenta = e.coincidencias > 0 ? ` ×${e.coincidencias}` : "";
            return `<span class="chip chip-emoji" title="${titulo}">${e.emoji}${cuenta}</span>`;
        })
        .join("");
    const chips = (terminos || [])
        .slice(0, 8)
        .map((t) => `<span class="chip">${t}</span>`)
        .join("");
    contenedorPrediccion.innerHTML =
        `<span class="etiqueta">Prediciendo:</span>${chipsEmoji}${chips}`;
}

function pintarContador(datos) {
    if (datos.consulta === "") {
        contador.textContent = `${datos.total_coincidencias} documento(s) en total`;
    } else {
        contador.textContent =
            `Mostrando ${datos.resultados.length} de ${datos.total_coincidencias} ` +
            `coincidencias, ordenadas por relevancia`;
    }
}

function pintarResultados(items, terminos) {
    listaResultados.innerHTML = "";

    if (items.length === 0) {
        listaResultados.innerHTML = `<li class="vacio">Sin coincidencias relevantes 🤔</li>`;
        return;
    }

    items.forEach((item, idx) => {
        const esSecundario = item.idioma !== idiomaActual;
        const li = document.createElement("li");
        li.className = esSecundario ? "resultado secundario" : "resultado";
        li.innerHTML = `
            <span class="indice">#${idx + 1}</span>
            <span class="emoji${item.emoji_coincide ? " coincide" : ""}">${item.emoji}</span>
            <span class="info">
                <span class="fila-nombre">
                    <span class="nombre">${resaltar(item.nombre, terminos)}</span>
                    <span class="categoria">${item.categoria}</span>
                    <span class="idioma">${item.bandera} ${item.idioma_nombre}</span>
                    ${item.homografo ? `<span class="homografo">falso amigo</span>` : ""}
                </span>
                <span class="descripcion">${resaltar(item.descripcion, terminos)}</span>
            </span>
            ${insigniaRelevancia(item.score)}
        `;
        listaResultados.appendChild(li);
    });
}

// Insignia R(qk, dj): porcentaje + barra. No se muestra si no hay consulta activa.
function insigniaRelevancia(score) {
    if (score === null || score === undefined) return "";
    const porcentaje = Math.round(score * 100);
    return `
        <span class="relevancia">
            <span class="porcentaje">${porcentaje}%</span>
            <span class="barra"><span style="width:${porcentaje}%"></span></span>
        </span>
    `;
}

function normalizar(texto) {
    return texto
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
}

function resaltar(texto, terminos) {
    if (!terminos || terminos.length === 0) return texto;
    return texto.replace(/[\p{L}\p{N}]+/gu, (palabra) => {
        const norm = normalizar(palabra);
        const coincide = terminos.some((t) => norm.startsWith(t));
        return coincide ? `<mark>${palabra}</mark>` : palabra;
    });
}

// Búsqueda reactiva: se dispara en cada tecla presionada
inputBusqueda.addEventListener("input", (evento) => {
    buscar(evento.target.value);
});

// Carga inicial: muestra el catálogo completo (sin ranking, sin consulta)
buscar("");
