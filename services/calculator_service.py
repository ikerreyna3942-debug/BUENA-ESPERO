import unicodedata
import re

def normalizar_texto(texto: str) -> str:
    """Normaliza texto a MAYÚSCULAS sin acentos y sin espacios duplicados."""
    if not texto:
        return ""
    texto_str = str(texto).strip()
    # Eliminar acentos
    texto_sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto_str)
        if unicodedata.category(c) != "Mn"
    )
    # Convertir a mayúsculas y limpiar espacios
    limpio = re.sub(r"\s+", " ", texto_sin_acentos.upper()).strip()
    return limpio

def calcular_metro_cubico(frente, fondo, alto) -> float:
    """Calcula el volumen en m3 a partir de dimensiones en cm."""
    try:
        f = float(frente) if frente not in [None, "", "n/A", "N/A"] else 0.0
        fo = float(fondo) if fondo not in [None, "", "n/A", "N/A"] else 0.0
        a = float(alto) if alto not in [None, "", "n/A", "N/A"] else 0.0
        if f > 0 and fo > 0 and a > 0:
            return round((f * fo * a) / 1000000.0, 6)
        return 0.0
    except (ValueError, TypeError):
        return 0.0

def formatear_medida_concatenada(frente, fondo, alto, diametro=None) -> str:
    """Genera la cadena de medida normalizada tipo 125X184X91 CM o 35 CM DIAM."""
    f = str(frente).strip() if frente not in [None, "", "n/A", "N/A"] else ""
    fo = str(fondo).strip() if fondo not in [None, "", "n/A", "N/A"] else ""
    a = str(alto).strip() if alto not in [None, "", "n/A", "N/A"] else ""
    d = str(diametro).strip() if diametro not in [None, "", "n/A", "N/A"] else ""
    
    if d and d != "0":
        return f"{d} CM DIAM"
    if f and fo and a:
        return f"{f}X{fo}X{a} CM"
    return ""
