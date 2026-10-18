// Buscador predictivo multilenguaje: cada tecla dispara una consulta al SRI.
// Este módulo solo cablea el DOM con el resto (api, render, historial, perfil, servidor, sugerencias).
import * as Api from "./api.js";
import * as Historial from "./historial.js";
import * as Perfil from "./perfil.js";
import { actualizarRecomendaciones } from "./recomendaciones.js";
import { pintarContador, pintarPrediccion, pintarResultados } from "./render.js";
import * as Servidor from "./servidor.js";
import { actualizarSugerencias } from "./sugerencias.js";

const inputBusqueda = document.getElementById("buscador");
const contenedorPrediccion = document.getElementById("prediccion");
const listaResultados = document.getElementById("resultados");
const contador = document.getElementById("contador");
const desglose = document.getElementById("desglose");
const botonesIdioma = document.querySelectorAll(".opcion-idioma");
const seccionHistorial = document.getElementById("historial");
const listaHistorial = document.getElementById("lista-historial");
const botonBorrarHistorial = document.getElementById("borrar-historial");
const botonOlvidarReacciones = document.getElementById("olvidar-reacciones");
const refsRecomendaciones = {
    seccion: document.getElementById("recomendaciones"),
    lista: document.getElementById("lista-recomendaciones"),
    vacio: document.getElementById("vacio-recomendaciones"),
};
const refsSugerencias = {
    seccion: document.getElementById("sugerencias"),
    lista: document.getElementById("lista-sugerencias"),
    titulo: document.getElementById("titulo-sugerencias"),
};

// Idioma dominante actual: arranca en el que el backend marcó como activo.
let idiomaActual = document.querySelector(".opcion-idioma.activa")?.dataset.idioma || "es";
let secuenciaBusqueda = 0;
let temporizadorHistorial = null;

// --- Búsqueda -------------------------------------------------------------
async function buscar(consulta) {
    const mia = ++secuenciaBusqueda;
    let datos;
    try {
        datos = await Api.buscar(consulta, idiomaActual);
    } catch (error) {
        if (mia === secuenciaBusqueda) contador.textContent = "No se pudo consultar el servidor";
        return;
    }
    if (mia !== secuenciaBusqueda) return;  // respuesta vieja: llegó una consulta más nueva

    idiomaActual = datos.idioma_dominante;
    marcarBotonActivo();
    desglose.textContent = `${nombreIdiomaActual()} domina el ranking`;
    pintarPrediccion(contenedorPrediccion, datos.terminos_expandidos, datos.emojis);
    pintarContador(contador, datos);
    pintarResultados(listaResultados, datos.resultados, datos.terminos_expandidos, idiomaActual, {
        // Elegir un resultado alimenta el aprendizaje de la consulta actual
        alElegir: (id, posicion) => {
            if (inputBusqueda.value.trim()) Api.enviarSeleccion(inputBusqueda.value, id, posicion);
        },
        // Las reacciones cambian el ranking: se vuelve a consultar con el texto actual
        alReaccionar: async (id, tipo) => {
            if (!(await Api.enviarReaccion(id, tipo))) return;
            Perfil.registrarReaccion(id, tipo);   // tu perfil: solo en este navegador
            refrescarRecomendaciones();
            buscar(inputBusqueda.value);
        },
    });
    // Lo mostrado sirve de impresiones si esta consulta se confirma
    Servidor.recordarMostrados(consulta, datos.resultados.map((r) => r.id));
}

// --- Selector de idioma ----------------------------------------------------
function marcarBotonActivo() {
    botonesIdioma.forEach((boton) => {
        boton.classList.toggle("activa", boton.dataset.idioma === idiomaActual);
    });
}

function nombreIdiomaActual() {
    const boton = document.querySelector(".opcion-idioma.activa");
    return boton ? boton.textContent.trim() : idiomaActual;
}

function banderaDeIdioma(codigo) {
    const boton = document.querySelector(`.opcion-idioma[data-idioma="${codigo}"]`);
    return boton ? boton.textContent.trim().split(" ")[0] : "";
}

botonesIdioma.forEach((boton) => {
    boton.addEventListener("click", () => {
        idiomaActual = boton.dataset.idioma;
        marcarBotonActivo();
        buscar(inputBusqueda.value);
        refrescarRecomendaciones();
    });
});

// --- Confirmar una búsqueda (historial local + servidor) -----------------------
function confirmar(consulta, idioma, inmediato = false) {
    const texto = Historial.guardarEnHistorial(consulta, idioma);
    if (texto === null) return;
    actualizarPerfil();
    Servidor.encolar(texto, inmediato);
}

function programarGuardado() {
    clearTimeout(temporizadorHistorial);
    const texto = inputBusqueda.value;
    if (texto.trim().length < 2) return;
    temporizadorHistorial = setTimeout(() => confirmar(texto, idiomaActual), Historial.PAUSA_GUARDADO_MS);
}

async function repetirBusqueda(consulta, idioma = idiomaActual) {
    clearTimeout(temporizadorHistorial);
    inputBusqueda.value = consulta;
    if (document.querySelector(`.opcion-idioma[data-idioma="${idioma}"]`)) {
        idiomaActual = idioma;
        marcarBotonActivo();
    }
    actualizarSugerencias(consulta, refsSugerencias, repetirBusqueda);
    await buscar(consulta);          // primero los resultados: así quedan como impresiones
    confirmar(consulta, idiomaActual, true);
    inputBusqueda.focus();
}

function pintarHistorial() {
    Historial.pintarHistorial(seccionHistorial, listaHistorial, banderaDeIdioma, {
        alRepetir: (entrada) => repetirBusqueda(entrada.consulta, entrada.idioma),
        alQuitar: (consulta) => {
            Historial.quitarDelHistorial(consulta);
            actualizarPerfil();
        },
    });
}

// --- Sugerencias para ti (perfil local: historial + reacciones) ------------------
function refrescarRecomendaciones() {
    botonOlvidarReacciones.hidden = !Perfil.hayReacciones();
    actualizarRecomendaciones(
        refsRecomendaciones,
        idiomaActual,
        // Elegir una sugerencia la busca por su nombre, en su idioma
        (item) => repetirBusqueda(item.nombre, item.idioma),
    );
}

// El historial es parte del perfil: cada vez que cambia, también cambian las sugerencias
function actualizarPerfil() {
    pintarHistorial();
    refrescarRecomendaciones();
}

botonOlvidarReacciones.addEventListener("click", () => {
    Perfil.olvidarReacciones();
    refrescarRecomendaciones();
});

botonBorrarHistorial.addEventListener("click", () => {
    clearTimeout(temporizadorHistorial);
    Historial.borrarHistorial();
    actualizarPerfil();
});

window.addEventListener("pagehide", Servidor.vaciarPendiente);

// --- Entrada del usuario -------------------------------------------------------
// Búsqueda reactiva: se dispara en cada tecla presionada
inputBusqueda.addEventListener("input", (evento) => {
    buscar(evento.target.value);
    actualizarSugerencias(evento.target.value, refsSugerencias, repetirBusqueda);
    programarGuardado();
});

// Enter confirma la búsqueda: se guarda sin esperar la pausa
inputBusqueda.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") {
        clearTimeout(temporizadorHistorial);
        confirmar(inputBusqueda.value, idiomaActual, true);
    }
});

// Carga inicial: muestra el catálogo completo (sin ranking, sin consulta)
buscar("");
actualizarPerfil();
actualizarSugerencias("", refsSugerencias, repetirBusqueda);


