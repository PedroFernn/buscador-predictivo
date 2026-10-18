// Perfil personal, solo en este navegador (localStorage). Alimenta "Sugerencias para ti".
//   - búsquedas: no se guardan aparte, son el propio historial (historial.js): quitar una del
//     historial, o borrarlo, también la quita del perfil. Ahí vive su frecuencia (n) y su hora.
//   - reacciones: la última por documento (cambiar 👍 por 👎 reemplaza, no suma).
// El servidor no guarda nada de esto: viaja en cada petición a /api/recomendaciones.
import { leerHistorial } from "./historial.js";

const CLAVE_REACCIONES = "buscador_reacciones";
const MAX_REACCIONES = 100;
const TIPOS = new Set(["me_gusta", "me_encanta", "no_me_gusta"]);

export function leerReacciones() {
    try {
        const crudo = localStorage.getItem(CLAVE_REACCIONES);
        const datos = crudo ? JSON.parse(crudo) : [];
        return Array.isArray(datos)
            ? datos.filter((r) => r && Number.isInteger(r.id) && TIPOS.has(r.tipo) && Number.isFinite(r.ts))
            : [];
    } catch (error) {
        return [];
    }
}

function escribirReacciones(reacciones) {
    try {
        localStorage.setItem(CLAVE_REACCIONES, JSON.stringify(reacciones));
    } catch (error) {
        // Almacenamiento no disponible (modo privado, cuota): se ignora.
    }
}

export function registrarReaccion(id, tipo) {
    if (!Number.isInteger(id) || !TIPOS.has(tipo)) return;
    const resto = leerReacciones().filter((r) => r.id !== id);
    resto.unshift({ id, tipo, ts: Date.now() });
    escribirReacciones(resto.slice(0, MAX_REACCIONES));  // si se pasa, salen las más viejas
}

export function olvidarReacciones() {
    escribirReacciones([]);
}

export function hayReacciones() {
    return leerReacciones().length > 0;
}

// Lo que se envía al servidor
export function armarPerfil() {
    return {
        consultas: leerHistorial().map((e) => ({ q: e.consulta, n: e.n || 1, ts: e.ts })),
        reacciones: leerReacciones(),
    };
}

export function perfilVacio(perfil) {
    return perfil.consultas.length === 0 && perfil.reacciones.length === 0;
}
