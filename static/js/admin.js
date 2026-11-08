// Herramientas de prueba: borrar señales (servidor y navegador) y generar datos aleatorios.
// Solo se carga si el servidor tiene ADMIN_TOKEN (ver templates/index.html y api/admin.py).
// Dos puertas a lo mismo: los atajos bajo la caja de búsqueda y el panel plegable (opciones finas).
// Tras cada acción la página se recarga: así el historial, las sugerencias y los resultados
// vuelven a pintarse desde cero sin tocar main.js.
import * as Api from "./api.js";
import * as Historial from "./historial.js";
import * as Perfil from "./perfil.js";
import * as Servidor from "./servidor.js";

const CLAVE_TOKEN = "admin_token";
const CLAVE_MENSAJE = "admin_mensaje";

const panel = document.getElementById("herramientas");
if (panel) iniciar(panel);

function leerSesion(clave) {
    try {
        return sessionStorage.getItem(clave) || "";
    } catch (error) {
        return "";
    }
}

function guardarSesion(clave, valor) {
    try {
        if (valor) sessionStorage.setItem(clave, valor);
        else sessionStorage.removeItem(clave);
    } catch (error) {
        // Sin almacenamiento de sesión: hay que volver a pegar el token tras recargar.
    }
}

function resumir(conteos) {
    const partes = Object.entries(conteos || {}).filter(([, n]) => n > 0).map(([tipo, n]) => `${tipo} ${n}`);
    return partes.length ? partes.join(" · ") : "nada";
}

function iniciar(raiz) {
    const campoToken = raiz.querySelector("#admin-token");
    const estados = [raiz.querySelector("#admin-estado"), document.getElementById("rapido-estado")].filter(Boolean);
    const botones = document.querySelectorAll("#herramientas button, .accion-rapida");
    const marcado = (selector) => raiz.querySelector(selector).checked;
    const numero = (selector) => {
        const valor = raiz.querySelector(selector).value.trim();
        return valor === "" ? undefined : Number(valor);
    };

    campoToken.value = leerSesion(CLAVE_TOKEN);
    campoToken.addEventListener("input", () => guardarSesion(CLAVE_TOKEN, campoToken.value.trim()));

    const pendiente = leerSesion(CLAVE_MENSAJE);
    if (pendiente) {
        guardarSesion(CLAVE_MENSAJE, "");
        mostrar(pendiente);
    }
    raiz.addEventListener("toggle", () => {
        if (raiz.open && campoToken.value.trim()) refrescarEstado();
    });

    function mostrar(texto, esError = false) {
        for (const estado of estados) {
            estado.textContent = texto;
            estado.classList.toggle("error", esError);
        }
    }

    // El token se pide una sola vez por pestaña (queda en sessionStorage y en el campo del panel)
    function token() {
        let valor = campoToken.value.trim();
        if (!valor) {
            valor = (prompt("Token de administración (el ADMIN_TOKEN del servidor):") || "").trim();
            campoToken.value = valor;
            guardarSesion(CLAVE_TOKEN, valor);
        }
        return valor;
    }

    function llamar(ruta, cuerpo) {
        return Api.admin(ruta, token(), cuerpo);
    }

    function deshabilitar(si) {
        botones.forEach((boton) => { boton.disabled = si; });
    }

    async function ejecutar(accion) {
        if (!token()) return mostrar("Hace falta el token de administración.", true);
        deshabilitar(true);
        mostrar("Trabajando…");
        try {
            await accion();
        } catch (error) {
            if (error.status === 401) {   // token equivocado: que lo vuelva a pedir
                campoToken.value = "";
                guardarSesion(CLAVE_TOKEN, "");
                mostrar("Token inválido: vuelve a intentarlo.", true);
            } else {
                mostrar(`No se pudo: ${error.message}`, true);
            }
            deshabilitar(false);
        }
    }

    async function refrescarEstado() {
        try {
            mostrar(`En el servidor: ${resumir((await llamar("/api/admin/estado")).eventos)}`);
        } catch (error) {
            mostrar(`No se pudo leer el estado: ${error.message}`, true);
        }
    }

    // Se llama como último paso de una acción, en un bloque síncrono: no se cuela ninguna consulta pendiente
    function recargarCon(texto) {
        guardarSesion(CLAVE_MENSAJE, texto);
        location.reload();
    }

    function limpiarLocal() {
        Servidor.descartarPendiente();
        Historial.borrarHistorial();
        Perfil.olvidarReacciones();
    }

    function llenarLocal(perfil) {
        Servidor.descartarPendiente();
        for (const consulta of perfil.consultas) {
            for (let i = 0; i < consulta.n; i++) Historial.guardarEnHistorial(consulta.q, consulta.idioma);
        }
        for (const reaccion of perfil.reacciones) Perfil.registrarReaccion(reaccion.id, reaccion.tipo);
    }

    // --- Acciones (las usan los atajos y el panel) ---
    async function limpiarTodo() {
        const datos = await llamar("/api/admin/reiniciar", { alcance: "todo" });
        limpiarLocal();
        recargarCon(`Buscador limpio. Borrado: ${resumir(datos.borrados)}.`);
    }

    // Reemplaza lo que haya por un estado aleatorio (los números y la semilla salen del panel)
    async function estadoAleatorio() {
        const local = marcado("#sim-local");
        const datos = await llamar("/api/admin/simular", {
            reemplazar: true,
            consultas: numero("#sim-consultas"),
            reacciones: numero("#sim-reacciones"),
            semilla: numero("#sim-semilla"),
            perfil_local: local,
        });
        if (local) {
            limpiarLocal();
            if (datos.perfil_local) llenarLocal(datos.perfil_local);
        }
        recargarCon(`Estado aleatorio (semilla ${datos.semilla}): ${resumir(datos.insertados)}.`);
    }

    const alPulsar = (selector, alActivar) => document.querySelector(selector)?.addEventListener("click", alActivar);

    const pedirLimpiar = () => {
        if (confirm("Limpiar el buscador: reacciones, clics y consultas del servidor, y el historial y las reacciones de este navegador. No se puede deshacer. ¿Seguir?")) {
            ejecutar(limpiarTodo);
        }
    };
    alPulsar("#rapido-limpiar", pedirLimpiar);
    alPulsar("#admin-borrar-todo", pedirLimpiar);

    alPulsar("#rapido-aleatorio", () => {
        if (confirm("Esto BORRA lo que haya (servidor y, si está marcado en el panel, este navegador) y carga datos aleatorios. ¿Seguir?")) {
            ejecutar(estadoAleatorio);
        }
    });

    // --- Solo panel: opciones finas ---
    alPulsar("#admin-borrar", () => {
        const alcance = [...raiz.querySelectorAll('input[name="alcance"]:checked')].map((c) => c.value);
        const local = marcado("#borrar-local");
        if (!alcance.length && !local) return mostrar("Marca algo para borrar.", true);
        if (!confirm("¿Borrar lo seleccionado? No se puede deshacer.")) return;
        ejecutar(async () => {
            const datos = alcance.length ? await llamar("/api/admin/reiniciar", { alcance }) : { borrados: {} };
            if (local) limpiarLocal();
            recargarCon(`Borrado en el servidor: ${resumir(datos.borrados)}${local ? ". Navegador limpio." : "."}`);
        });
    });

    // Suma datos aleatorios a lo que ya hay (el atajo "Estado aleatorio" los reemplaza)
    alPulsar("#admin-generar", () => {
        const local = marcado("#sim-local");
        ejecutar(async () => {
            const datos = await llamar("/api/admin/simular", {
                consultas: numero("#sim-consultas"),
                reacciones: numero("#sim-reacciones"),
                semilla: numero("#sim-semilla"),
                perfil_local: local,
            });
            if (local && datos.perfil_local) llenarLocal(datos.perfil_local);
            recargarCon(`Generado (semilla ${datos.semilla}): ${resumir(datos.insertados)}.`);
        });
    });
}
