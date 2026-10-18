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
