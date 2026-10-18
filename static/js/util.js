// Mismas reglas que nucleo/texto.py: sin diacríticos, salvo la ñ (es otra letra)
export function normalizar(texto) {
    return texto
        .toLowerCase()
        .normalize("NFD")
        .replace(/n\u0303/g, "\u00f1")
        .replace(/[\u0300-\u036f]/g, "");
}

// Clave de un prefijo de sugerencia: normalizado, espacios colapsados, sin espacio inicial
export function claveSugerencia(prefijo) {
    return normalizar(prefijo).replace(/\s+/g, " ").replace(/^ /, "");
}
