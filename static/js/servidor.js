// Consultas confirmadas -> servidor (frecuencia real e impresiones).
// El servidor cuenta solo búsquedas confirmadas, no cada tecla. Igual que el historial local,
// una búsqueda que solo se extiende ("pan" -> "pancake") reemplaza a la pendiente en vez de
// contarse dos veces; se envía cuando la persona cambia de búsqueda, confirma con Enter,
// deja pasar ESPERA_SERVIDOR_MS o cierra la página.
import { enviarConsulta } from "./api.js";
import { normalizar } from "./util.js";

const ESPERA_SERVIDOR_MS = 8000;
let pendiente = null;      // { texto, clave, mostrados }
let temporizador = null;
let ultimos = { clave: "", ids: [] };  // ids de los resultados mostrados más recientes

// Se llama cada vez que llegan resultados: sirven de impresiones si la consulta se confirma
export function recordarMostrados(consulta, ids) {
    ultimos = { clave: normalizar(consulta.trim()), ids };
}

export function vaciarPendiente() {
    clearTimeout(temporizador);
    if (pendiente) {
        enviarConsulta(pendiente.texto, pendiente.mostrados);
        pendiente = null;
    }
}

export function encolar(texto, inmediato) {
    const clave = normalizar(texto.trim());
    if (clave.length < 2) return;
    if (pendiente && !clave.startsWith(pendiente.clave)) {
        vaciarPendiente();  // otra búsqueda distinta: la anterior ya es firme
    }
    // Las impresiones solo valen si lo mostrado corresponde a esta misma consulta
    const mostrados = ultimos.clave === clave ? ultimos.ids : [];
    pendiente = { texto: texto.trim(), clave, mostrados };
    clearTimeout(temporizador);
    if (inmediato) {
        vaciarPendiente();
    } else {
        temporizador = setTimeout(vaciarPendiente, ESPERA_SERVIDOR_MS);
    }
}
