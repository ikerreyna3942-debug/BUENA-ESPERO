import os
import json
import shutil
import string
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Any

def _get_existing_path(relative_patterns: List[str], fallback: str) -> Path:
    """Busca dinámicamente carpetas en todas las unidades lógicas disponibles (C:, D:, G:, I:, etc.) o en el Home."""
    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    for d in drives:
        for rel in relative_patterns:
            p = Path(d) / rel
            if p.exists():
                return p
    # Buscar en Home de usuario
    user_home = Path.home()
    for rel in relative_patterns:
        p = user_home / rel
        if p.exists():
            return p
    return Path(fallback)

PATH_FINAL_FOTOS = _get_existing_path([
    r".shortcut-targets-by-id\1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B\fotos odoo",
    r"Mi unidad\PROYECTOS FINALES\ALTA DE ODO 2\fotos odoo",
    r"Mi unidad\fotos odoo",
    r"fotos odoo"
], fallback=r"I:\.shortcut-targets-by-id\1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B\fotos odoo")

PATH_ORIGEN_FOTOS = _get_existing_path([
    r"Mi unidad\DOC ANIPA\Fotos general\Informacion mia\Interior",
    r"DOC ANIPA\Fotos general\Informacion mia\Interior",
    r"Fotos general\Informacion mia\Interior",
    r"Interior"
], fallback=r"I:\Mi unidad\DOC ANIPA\Fotos general\Informacion mia\Interior")

BASE_APP_DIR = Path(__file__).resolve().parent.parent

def normalizar_busqueda(s: str) -> str:
    """Normaliza un texto para búsquedas eliminando acentos, mayúsculas y extensiones."""
    if not s:
        return ""
    txt = str(s).strip().lower()
    # Si viene con sufijo de subcarpeta tipo "SOFA AURA - 01 (Salas\...)"
    if " (" in txt and txt.endswith(")"):
        txt = txt.split(" (")[0].strip()
    # Remover extensiones comunes
    for ext in [".jpg", ".png", ".jpeg", ".webp", ".bmp"]:
        if txt.endswith(ext):
            txt = txt[:-len(ext)].strip()
    # Remover acentos
    txt = unicodedata.normalize("NFKD", txt)
    return "".join(c for c in txt if not unicodedata.combining(c)).strip()

def resolver_ruta_foto(ruta_str: str) -> Optional[str]:
    """Resuelve la ruta real existente en cualquier disco local o nube montada dinámicamente."""
    if not ruta_str:
        return None
    
    p = Path(ruta_str)
    if p.exists() and p.is_file():
        return str(p)
    
    s = str(ruta_str)
    # Probar cambiando unidad entre todas las unidades montadas
    if len(s) >= 2 and s[1] == ":":
        sub_path = s[2:].lstrip("\\/")
        for d in [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]:
            cand = Path(d) / sub_path
            if cand.exists() and cand.is_file():
                return str(cand)
    
    # Probar buscando directamente en PATH_ORIGEN_FOTOS o PATH_FINAL_FOTOS
    filename = p.name
    cand1 = PATH_ORIGEN_FOTOS / filename
    if cand1.exists() and cand1.is_file():
        return str(cand1)
    
    cand2 = PATH_FINAL_FOTOS / filename
    if cand2.exists() and cand2.is_file():
        return str(cand2)
        
    return None

class PhotoService:
    def __init__(self):
        self.final_photos = []
        self.origen_photos = []
        self.load_catalogs()

    def load_catalogs(self):
        """Carga inicial rápida desde caché JSON."""
        possible_final = [
            BASE_APP_DIR / "db_fotos_final" / "catalogo_fotos_final.json",
            Path("app_alta_odoo/db_fotos_final/catalogo_fotos_final.json"),
            Path("db_fotos_final/catalogo_fotos_final.json")
        ]
        for pf in possible_final:
            if pf.exists():
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        self.final_photos = json.load(f)
                        break
                except Exception:
                    pass

        possible_origen = [
            BASE_APP_DIR / "db_fotos_interior" / "catalogo_fotos_interior.json",
            Path("app_alta_odoo/db_fotos_interior/catalogo_fotos_interior.json"),
            Path("db_fotos_interior/catalogo_fotos_interior.json")
        ]
        for po in possible_origen:
            if po.exists():
                try:
                    with open(po, "r", encoding="utf-8") as f:
                        self.origen_photos = json.load(f)
                        break
                except Exception:
                    pass

    def rescan_catalogs(self) -> Dict[str, int]:
        """Escanea dinámicamente las carpetas de fotos base y fotos final para detectar nuevos archivos o carpetas."""
        # 1. Escanear fotos origen / base (Interior)
        if PATH_ORIGEN_FOTOS and PATH_ORIGEN_FOTOS.exists():
            origen_files = []
            for root, dirs, files in os.walk(PATH_ORIGEN_FOTOS):
                rel_path = os.path.relpath(root, PATH_ORIGEN_FOTOS)
                category_name = rel_path.split(os.sep)[0] if rel_path != "." else "RAIZ"
                for file in files:
                    if file.lower() == "desktop.ini" or file.startswith("."):
                        continue
                    ext = os.path.splitext(file)[1].lower()
                    if ext in [".jpg", ".png", ".jpeg", ".webp", ".bmp"]:
                        full_p = os.path.join(root, file)
                        origen_files.append({
                            "nombre_archivo": file,
                            "nombre_sin_ext": os.path.splitext(file)[0],
                            "extension": ext,
                            "categoria_principal": category_name,
                            "subcarpeta_rel": rel_path,
                            "ruta_completa": full_p
                        })
            self.origen_photos = origen_files
            # Guardar JSON actualizado
            for out_p in [BASE_APP_DIR / "db_fotos_interior" / "catalogo_fotos_interior.json", Path("app_alta_odoo/db_fotos_interior/catalogo_fotos_interior.json")]:
                if out_p.parent.exists():
                    try:
                        with open(out_p, "w", encoding="utf-8") as f:
                            json.dump(origen_files, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

        # 2. Escanear fotos final
        if PATH_FINAL_FOTOS and PATH_FINAL_FOTOS.exists():
            final_files = []
            for root, dirs, files in os.walk(PATH_FINAL_FOTOS):
                rel_path = os.path.relpath(root, PATH_FINAL_FOTOS)
                category_name = rel_path.split(os.sep)[0] if rel_path != "." else "RAIZ"
                for file in files:
                    if file.lower() == "desktop.ini" or file.startswith("."):
                        continue
                    ext = os.path.splitext(file)[1].lower()
                    if ext in [".jpg", ".png", ".jpeg", ".webp", ".bmp"]:
                        full_p = os.path.join(root, file)
                        final_files.append({
                            "nombre_archivo": file,
                            "nombre_sin_ext": os.path.splitext(file)[0],
                            "extension": ext,
                            "categoria_principal": category_name,
                            "subcarpeta_rel": rel_path,
                            "ruta_completa": full_p
                        })
            self.final_photos = final_files
            for out_p in [BASE_APP_DIR / "db_fotos_final" / "catalogo_fotos_final.json", Path("app_alta_odoo/db_fotos_final/catalogo_fotos_final.json")]:
                if out_p.parent.exists():
                    try:
                        with open(out_p, "w", encoding="utf-8") as f:
                            json.dump(final_files, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

        return {
            "origen": len(self.origen_photos),
            "final": len(self.final_photos)
        }

    def search_photos(self, query: str, category_filter: Optional[str] = None, source: str = "all", limit: int = 60) -> List[Dict]:
        """Busca fotos por nombre y/o categoría con normalización completa sin acentos."""
        if source == "final":
            dataset = self.final_photos
        elif source == "origen" or source == "interior":
            dataset = self.origen_photos
        else:
            dataset = self.final_photos + self.origen_photos

        q_norm = normalizar_busqueda(query)
        results = []
        seen = set()

        for item in dataset:
            nom = item.get("nombre_sin_ext", "")
            nom_norm = normalizar_busqueda(nom)
            arch = item.get("nombre_archivo", "")
            cat = item.get("categoria_principal", "").upper()
            sub = item.get("subcarpeta_rel", "").upper()

            if arch in seen:
                continue

            if category_filter and category_filter.upper() not in cat and category_filter.upper() not in sub:
                continue

            if not q_norm or q_norm in nom_norm or q_norm in normalizar_busqueda(sub):
                seen.add(arch)
                ruta_res = resolver_ruta_foto(item.get("ruta_completa", ""))
                item_copy = dict(item)
                if ruta_res:
                    item_copy["ruta_completa"] = ruta_res
                results.append(item_copy)
                if len(results) >= limit:
                    break

        return results

    def get_photo_by_name(self, filename: str, source: str = "all") -> Optional[Dict]:
        """Busca una foto exacta o normalizada por nombre en catálogo final o interior."""
        if not filename:
            return None

        if source == "final":
            dataset = self.final_photos
        elif source == "interior" or source == "origen":
            dataset = self.origen_photos
        else:
            dataset = self.final_photos + self.origen_photos

        target_norm = normalizar_busqueda(filename)
        if not target_norm:
            return None

        # 1. Búsqueda exacta y normalizada
        for item in dataset:
            nom_arch_norm = normalizar_busqueda(item.get("nombre_archivo", ""))
            nom_sin_norm = normalizar_busqueda(item.get("nombre_sin_ext", ""))
            
            if nom_arch_norm == target_norm or nom_sin_norm == target_norm:
                item_copy = dict(item)
                ruta_res = resolver_ruta_foto(item.get("ruta_completa", ""))
                if ruta_res:
                    item_copy["ruta_completa"] = ruta_res
                    item_copy["existe_local"] = True
                return item_copy

        # 2. Búsqueda por coincidencia parcial si contiene o empieza igual
        for item in dataset:
            nom_sin_norm = normalizar_busqueda(item.get("nombre_sin_ext", ""))
            if nom_sin_norm and (nom_sin_norm == target_norm or target_norm in nom_sin_norm or nom_sin_norm in target_norm):
                item_copy = dict(item)
                ruta_res = resolver_ruta_foto(item.get("ruta_completa", ""))
                if ruta_res:
                    item_copy["ruta_completa"] = ruta_res
                    item_copy["existe_local"] = True
                return item_copy

        return None

    def copy_photo_to_final(self, source_path: str, category_dest: str, new_filename: str) -> str:
        """Copia una foto del origen a la base final en su subcarpeta correspondiente."""
        ruta_res = resolver_ruta_foto(source_path)
        if not ruta_res:
            raise FileNotFoundError(f"Archivo origen no encontrado: {source_path}")

        src = Path(ruta_res)
        dest_folder = PATH_FINAL_FOTOS / category_dest
        dest_folder.mkdir(parents=True, exist_ok=True)

        ext = src.suffix or ".jpg"
        final_filename = new_filename if new_filename.lower().endswith(ext.lower()) else f"{new_filename}{ext}"
        dest_path = dest_folder / final_filename

        shutil.copy2(src, dest_path)
        return str(dest_path)

    @staticmethod
    def verificar_dimensiones_estandar(ancho: int, alto: int) -> Dict[str, Any]:
        """Valida si la imagen cumple con el estándar Odoo de 1254 x 1254 px o si es cuadrada."""
        es_exacto = (ancho == 1254 and alto == 1254)
        es_cuadrada = (ancho == alto and ancho > 0)
        return {
            "es_exacto": es_exacto,
            "es_cuadrada": es_cuadrada,
            "ancho": ancho,
            "alto": alto,
            "mensaje": "🟢 Estándar Odoo (1254x1254)" if es_exacto else ("🟡 Cuadrada pero no 1254px" if es_cuadrada else "⚠️ Requiere ajuste/recorte a 1:1")
        }

photo_service = PhotoService()
