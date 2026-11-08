// Todas las llamadas al servidor, en un solo lugar.

async function pedirJSON(url, opciones) {
    const respuesta = await fetch(url, opciones);
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    return respuesta.json();
}

function publicar(url, cuerpo, extra = {}) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
        ...extra,
    });
}

export function buscar(consulta, idioma) {
    return pedirJSON(`/api/buscar?q=${encodeURIComponent(consulta)}&idioma=${encodeURIComponent(idioma)}`);
}

export function pedirSugerencias(prefijo, limite, senal) {
    return pedirJSON(`/api/sugerencias?q=${encodeURIComponent(prefijo)}&limite=${limite}`, { signal: senal });
}

// Consulta confirmada (frecuencia real) + los ids que se mostraron, en orden (impresiones)
export function enviarConsulta(texto, mostrados) {
    try {
        publicar("/api/consultas", { q: texto, mostrados }, { keepalive: true }).catch(() => {});
    } catch (error) {
        // Sin red o sin endpoint: el historial local sigue funcionando.
    }
}

// Qué resultado eligió la persona para la consulta, y en qué posición (1 = primero)
export function enviarSeleccion(consulta, id, pos) {
    publicar("/api/seleccion", { q: consulta, id, pos }).catch(() => {});
}

export async function enviarReaccion(id, tipo) {
    const respuesta = await publicar("/api/reaccion", { id, tipo });
    return respuesta.ok;
}

// Sugerencias personales: el perfil (historial + reacciones) viaja en el cuerpo y no se guarda
export function pedirRecomendaciones(perfil, idioma, limite, senal) {
    return pedirJSON("/api/recomendaciones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...perfil, idioma, limite }),
        signal: senal,
    });
}

// Página /analitica (ver api/analitica.py): catálogo, uso real y sondeo de una consulta
export function analiticaCorpus() {
    return pedirJSON("/api/analitica/corpus");
}

export function analiticaUso() {
    return pedirJSON("/api/analitica/uso");
}

export function analiticaSondeo(consulta, senal) {
    return pedirJSON(`/api/analitica/sondeo?q=${encodeURIComponent(consulta)}`, { signal: senal });
}

// Herramientas de administración (apagadas si el servidor no tiene ADMIN_TOKEN; ver api/admin.py).
// Sin `cuerpo` es un GET; con él, un POST JSON. Lanza Error con el mensaje del servidor y `status`.
export async function admin(ruta, token, cuerpo) {
    const respuesta = await fetch(ruta, {
        method: cuerpo === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": token },
        body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
    const datos = await respuesta.json().catch(() => ({}));
    if (!respuesta.ok) {
        const error = new Error(datos.error || `HTTP ${respuesta.status}`);
        error.status = respuesta.status;
        throw error;
    }
    return datos;
}

