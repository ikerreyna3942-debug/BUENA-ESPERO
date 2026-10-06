import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import io
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
except Exception as e:
    service_account = None
    build = None
    MediaIoBaseDownload = None
    print(f"[SheetsService] Librerías de Google API no disponibles en este entorno: {e}")

DEFAULT_SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg")

class SheetsService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.service = None
        self.drive_service = None
        self.client_email = ""
        self.spreadsheet_id = DEFAULT_SPREADSHEET_ID
        self.connection_status = "Desconectado"
        self._fn_catalog: Optional[Dict[str, str]] = None
        self._sheet_name_datos_general: Optional[str] = None
        self._sheet_name_fotos_norm: Optional[str] = None
        self._init_service()

    def _init_service(self):
        # 1. Intentar cargar desde variable de entorno GOOGLE_CREDENTIALS_JSON
        env_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if env_creds:
            try:
                if isinstance(env_creds, str):
                    cred_dict = json.loads(env_creds)
                else:
                    cred_dict = env_creds

                if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                    # Asegurar saltos de línea reales en la clave privada
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")

                self.client_email = cred_dict.get("client_email", "")
                creds = service_account.Credentials.from_service_account_info(
                    cred_dict, scopes=self.scopes
                )
                self.service = build("sheets", "v4", credentials=creds)
                self.drive_service = build("drive", "v3", credentials=creds)
                self.connection_status = f"Conectado ({self.client_email})"
                print(f"[SheetsService] Google Sheets & Drive API conectados con Service Account: {self.client_email}")
                return
            except Exception as e:
                print(f"[SheetsService] Error cargando credenciales de entorno: {e}")
                self.connection_status = f"Error entorno: {e}"

        # 2. Buscar credentials.json en rutas relativas comunes
        possible_paths = [
            Path("credentials.json"),
            Path(__file__).resolve().parent.parent.parent / "credentials.json",
            Path(__file__).resolve().parent.parent / "credentials.json",
            Path(r"G:\Mi unidad\PROYECTOS FINALES\ALTA ODOO\Conexiones\credentials.json"),
            Path(r"I:\Mi unidad\PROYECTOS FINALES\ALTA ODOO\Conexiones\credentials.json"),
            Path(r"I:\Mi unidad\PROYECTOS FINALES\ALTA ODOO\credentials.json"),
            Path(r"G:\Mi unidad\PROYECTOS FINALES\ALTA ODOO\credentials.json")
        ]
        cred_path = next((p for p in possible_paths if p.exists()), None)
        if cred_path:
            try:
                with open(cred_path, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
                    self.client_email = c_data.get("client_email", "")

                creds = service_account.Credentials.from_service_account_file(
                    str(cred_path), scopes=self.scopes
                )
                self.service = build("sheets", "v4", credentials=creds)
                self.drive_service = build("drive", "v3", credentials=creds)
                self.connection_status = f"Conectado local ({self.client_email})"
                print(f"[SheetsService] Google Sheets & Drive conectados con archivo local: {cred_path}")
            except Exception as e:
                print(f"[SheetsService] Error inicializando credenciales desde archivo: {e}")
                self.connection_status = f"Error archivo: {e}"

    def get_datos_general_tab_name(self) -> str:
        """Determina dinámicamente el nombre real de la pestaña (ej. 'DATOS GENERAL' o 'DATOS GENERALES')."""
        if self._sheet_name_datos_general:
            return self._sheet_name_datos_general
        if not self.service:
            return "DATOS GENERAL"
        try:
            meta = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id, fields="sheets(properties(title))").execute()
            titles = [s.get('properties', {}).get('title', '').strip() for s in meta.get('sheets', [])]
            for candidate in ["DATOS GENERAL", "DATOS GENERALES"]:
                for t in titles:
                    if t.upper() == candidate.upper():
                        self._sheet_name_datos_general = t
                        return t
            for t in titles:
                if t.upper().startswith("DATOS GENERAL"):
                    self._sheet_name_datos_general = t
                    return t
        except Exception as e:
            print(f"[SheetsService] Aviso al consultar pestañas de la hoja: {e}")
        self._sheet_name_datos_general = "DATOS GENERAL"
        return self._sheet_name_datos_general

    def get_fotos_normalizadas_tab_name(self) -> str:
        """Determina dinámicamente el nombre real de la pestaña de fotos normalizadas."""
        if self._sheet_name_fotos_norm:
            return self._sheet_name_fotos_norm
        if not self.service:
            return "FOTOS NORMALIZADAS"
        try:
            meta = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id, fields="sheets(properties(title))").execute()
            titles = [s.get('properties', {}).get('title', '').strip() for s in meta.get('sheets', [])]
            for candidate in ["FOTOS NORMALIZADAS", "FOTO NORMALIZADAS", "FOTOS NORMALIZADA"]:
                for t in titles:
                    if t.upper() == candidate.upper():
                        self._sheet_name_fotos_norm = t
                        return t
            for t in titles:
                if t.upper().startswith("FOTOS NORMALIZAD"):
                    self._sheet_name_fotos_norm = t
                    return t
        except Exception as e:
            print(f"[SheetsService] Aviso al consultar pestañas de la hoja: {e}")
        self._sheet_name_fotos_norm = "FOTOS NORMALIZADAS"
        return self._sheet_name_fotos_norm

    def get_fotos_normalizadas_catalog(self, force_refresh: bool = False) -> Dict[str, str]:
        """Obtiene el catálogo indexado de fotos registradas en FOTOS NORMALIZADAS para resolución ultrarrápida."""
        if self._fn_catalog is not None and not force_refresh:
            return self._fn_catalog

        catalog = {}
        if not self.service:
            self._fn_catalog = catalog
            return catalog

        try:
            tab_fn = self.get_fotos_normalizadas_tab_name()
            res = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_fn}'!A4:P2000"
            ).execute()
            rows = res.get("values", [])
            for r in rows:
                # Mueble (Col B=idx 1, Col D=idx 3)
                if len(r) > 1 and r[1].strip() and len(r) > 3 and r[3].strip():
                    catalog[r[1].strip().upper()] = r[3].strip()
                # Tela (Col F=idx 5, Col H=idx 7)
                if len(r) > 5 and r[5].strip() and len(r) > 7 and r[7].strip():
                    catalog[r[5].strip().upper()] = r[7].strip()
                # Madera (Col J=idx 9, Col L=idx 11)
                if len(r) > 9 and r[9].strip() and len(r) > 11 and r[11].strip():
                    catalog[r[9].strip().upper()] = r[11].strip()
                # Swatch (Col N=idx 13, Col P=idx 15)
                if len(r) > 13 and r[13].strip() and len(r) > 15 and r[15].strip():
                    catalog[r[13].strip().upper()] = r[15].strip()
        except Exception as e:
            print(f"[SheetsService] Error cargando catálogo de FOTOS NORMALIZADAS: {e}")

        self._fn_catalog = catalog
        return catalog

    def buscar_link_drive_inteligente(self, nombre_foto: str) -> str:
        """Busca el enlace de Google Drive para un nombre de foto usando coincidencia inteligente en catálogo y Drive API."""
        if not nombre_foto or not str(nombre_foto).strip() or str(nombre_foto).strip().upper() in ["N/A", "NONE", ""]:
            return ""

        nom = str(nombre_foto).strip()
        n_up = nom.upper()
        n_clean = os.path.splitext(n_up)[0].strip()

        # 1. Búsqueda exacta en catálogo FOTOS NORMALIZADAS
        catalog = self.get_fotos_normalizadas_catalog()
        if n_up in catalog:
            return catalog[n_up]
        if n_clean in catalog:
            return catalog[n_clean]

        # 2. Búsqueda parcial en catálogo FOTOS NORMALIZADAS
        for k, v in catalog.items():
            if n_clean == k or (len(n_clean) > 4 and (n_clean in k or k in n_clean)):
                return v

        # 3. Búsqueda directa en Google Drive API
        if not self.drive_service:
            return ""

        words = [w for w in re.split(r'[\s_\-\.]+', n_clean) if len(w) > 2 and not w.isdigit()]
        queries = [
            f"name = '{nom}' and trashed = false",
            f"name = '{n_clean}' and trashed = false",
            f"name contains '{n_clean}' and trashed = false"
        ]

        if len(words) >= 2:
            contains_clause = " and ".join([f"name contains '{w}'" for w in words[:3]])
            queries.append(f"{contains_clause} and trashed = false")
        elif len(words) == 1:
            queries.append(f"name contains '{words[0]}' and trashed = false")

        for q in queries:
            try:
                res = self.drive_service.files().list(
                    q=q,
                    fields="files(id, name, mimeType)",
                    pageSize=5,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                files = [f for f in res.get("files", []) if f.get("mimeType") != "application/vnd.google-apps.folder"]
                if files:
                    f_id = files[0]["id"]
                    link_gen = f"https://drive.google.com/file/d/{f_id}/view"
                    # Cachear resultado
                    catalog[n_up] = link_gen
                    return link_gen
            except Exception as e:
                pass

        return ""

    def get_drive_file_bytes(self, drive_id: str) -> Optional[bytes]:
        """Descarga el contenido binario de una imagen directamente desde Google Drive API autenticada."""
        if not self.drive_service or not drive_id:
            return None
        try:
            request = self.drive_service.files().get_media(fileId=drive_id, supportsAllDrives=True)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            return fh.getvalue()
        except Exception as e:
            print(f"[SheetsService] Error descargando archivo de Drive {drive_id}: {e}")
            return None

    def get_drive_folder_files(self, folder_id: str, recursive: bool = True) -> List[Dict[str, str]]:
        """Obtiene la lista de imágenes desde una carpeta específica de Google Drive (con soporte recursivo para subcarpetas)."""
        if not self.drive_service or not folder_id:
            return []
        
        def _scan(f_id: str, sub_label: str = ""):
            items_found = []
            try:
                res = self.drive_service.files().list(
                    q=f"'{f_id}' in parents and trashed = false",
                    fields="files(id, name, mimeType)",
                    pageSize=500,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                for f in res.get("files", []):
                    if f.get("mimeType") == "application/vnd.google-apps.folder":
                        if recursive:
                            items_found.extend(_scan(f.get("id"), f.get("name")))
                    else:
                        name = f.get("name", "")
                        clean_name = os.path.splitext(name)[0].strip()
                        file_id = f.get("id", "")
                        items_found.append({
                            "id": file_id,
                            "name": clean_name,
                            "filename": name,
                            "link": f"https://drive.google.com/file/d/{file_id}/view",
                            "subcarpeta": sub_label
                        })
            except Exception as e:
                print(f"[SheetsService] Error escaneando carpeta {f_id}: {e}")
            return items_found

        all_files = _scan(folder_id)
        seen_ids = set()
        unique_files = []
        for f in all_files:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                unique_files.append(f)
        unique_files.sort(key=lambda x: x["name"].upper())
        return unique_files

    def get_pending_products(self) -> List[Dict[str, Any]]:
        """Obtiene la lista de productos de DATOS GENERAL, clasificando los que no tienen fotos."""
        if not self.service:
            # Cargar desde caché pre-guardado de 1,162 productos
            cache_paths = [
                Path(__file__).resolve().parent.parent / "datos_general_cache.json",
                Path("app_alta_odoo/datos_general_cache.json"),
                Path("datos_general_cache.json")
            ]
            for cp in cache_paths:
                if cp.exists():
                    try:
                        with open(cp, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception as e:
                        print(f"[SheetsService] Error leyendo cache: {e}")
            return []

        tab_dg = self.get_datos_general_tab_name()
        try:
            res = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_dg}'!A4:AZ1200",
                valueRenderOption="FORMATTED_VALUE"
            ).execute()
        except Exception as e:
            print(f"[SheetsService] Error accediendo a {self.spreadsheet_id} con pestaña '{tab_dg}': {e}")
            # Si no tiene permisos o falla conexión, cargar desde cache
            cache_paths = [
                Path(__file__).resolve().parent.parent / "datos_general_cache.json",
                Path("app_alta_odoo/datos_general_cache.json"),
                Path("datos_general_cache.json")
            ]
            for cp in cache_paths:
                if cp.exists():
                    try:
                        with open(cp, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception:
                        pass
            return []

        rows = res.get("values", [])
        products = []

        for idx, row in enumerate(rows):
            fila_num = idx + 4
            sku = row[0] if len(row) > 0 else ""
            nombre_viejo = row[1] if len(row) > 1 else ""

            if not sku and not nombre_viejo:
                continue

            foto_mueble_nom = row[26] if len(row) > 26 else ""
            foto_mueble_link = row[28] if len(row) > 28 else ""
            foto_tela_nom = row[29] if len(row) > 29 else ""
            foto_tela_link = row[31] if len(row) > 31 else ""
            foto_madera_nom = row[32] if len(row) > 32 else ""
            foto_madera_link = row[34] if len(row) > 34 else ""
            foto_swatch_nom = row[35] if len(row) > 35 else ""
            foto_swatch_link = row[37] if len(row) > 37 else ""

            tiene_fotos = bool(foto_mueble_link or foto_tela_link or foto_madera_link or foto_swatch_link or foto_mueble_nom)

            prod_data = {
                "fila": fila_num,
                "sku": sku,
                "nombre_viejo": nombre_viejo,
                "tiene_fotos": tiene_fotos,
                "sin_empaque": {
                    "frente": row[2] if len(row) > 2 else "",
                    "fondo": row[3] if len(row) > 3 else "",
                    "alto": row[4] if len(row) > 4 else "",
                    "diametro": row[5] if len(row) > 5 else "",
                    "piso_asiento": row[6] if len(row) > 6 else "",
                    "peso_kg": row[7] if len(row) > 7 else "",
                    "metro_3": row[8] if len(row) > 8 else ""
                },
                "con_empaque": {
                    "frente": row[9] if len(row) > 9 else "",
                    "fondo": row[10] if len(row) > 10 else "",
                    "alto": row[11] if len(row) > 11 else "",
                    "peso_kg": row[12] if len(row) > 12 else "",
                    "metro_cubico": row[13] if len(row) > 13 else ""
                },
                "proveedor": row[14] if len(row) > 14 else "",
                "categoria": row[15] if len(row) > 15 else "",
                "rama": row[16] if len(row) > 16 else "",
                "precio": row[17] if len(row) > 17 else "",
                "costo": row[18] if len(row) > 18 else "",
                "color_tela": row[21] if len(row) > 21 else "",
                "tamano": row[22] if len(row) > 22 else "",
                "modelo": row[23] if len(row) > 23 else "",
                "tipo_mueble": row[24] if len(row) > 24 else "",
                "nombre_nuevo": row[25] if len(row) > 25 else "",
                "fotos": {
                    "mueble_nombre": foto_mueble_nom,
                    "mueble_link": foto_mueble_link,
                    "tela_nombre": foto_tela_nom,
                    "tela_link": foto_tela_link,
                    "madera_nombre": foto_madera_nom,
                    "madera_link": foto_madera_link,
                    "swatch_nombre": foto_swatch_nom,
                    "swatch_link": foto_swatch_link
                },
                "bultos": row[38] if len(row) > 38 else "",
                "concatenado_sheet": row[40] if len(row) > 40 else "",
                "medidas_sheet": row[51] if len(row) > 51 else ""
            }
            products.append(prod_data)

        return products

    def update_product_row_safe(self, fila: int, data: Dict[str, Any]) -> bool:
        """
        Actualiza de forma 100% segura y directa todas las celdas de entrada manual,
        medidas, categoría, modelo, nombre nuevo, bultos y fotos en DATOS GENERAL,
        respetando estrictamente las columnas con fórmulas de la fila 3 (B, O, Q, R, S, T, U, V, W, AB, AE, AH, AK, AO, etc.).
        """
        if not self.service or fila < 4:
            return False

        tab_dg = self.get_datos_general_tab_name()
        sku_val = data.get("sku", "").strip()
        updates = []
        fotos = data.get("fotos", {})
        se = data.get("sin_empaque", {})
        ce = data.get("con_empaque", {})

        # 1. Medidas Sin Empaque (Cols C a I)
        if se:
            if "frente" in se:
                updates.append({"range": f"'{tab_dg}'!C{fila}", "values": [[str(se["frente"])]]})
            if "fondo" in se:
                updates.append({"range": f"'{tab_dg}'!D{fila}", "values": [[str(se["fondo"])]]})
            if "alto" in se:
                updates.append({"range": f"'{tab_dg}'!E{fila}", "values": [[str(se["alto"])]]})
            if "diametro" in se:
                updates.append({"range": f"'{tab_dg}'!F{fila}", "values": [[str(se["diametro"]) or "n/A"]]})
            if "piso_asiento" in se:
                updates.append({"range": f"'{tab_dg}'!G{fila}", "values": [[str(se["piso_asiento"])]]})
            if "peso_kg" in se:
                updates.append({"range": f"'{tab_dg}'!H{fila}", "values": [[str(se["peso_kg"])]]})
            if "metro_3" in se:
                updates.append({"range": f"'{tab_dg}'!I{fila}", "values": [[str(se["metro_3"])]]})

        # 2. Medidas Con Empaque (Cols J a N)
        if ce:
            if "frente" in ce:
                updates.append({"range": f"'{tab_dg}'!J{fila}", "values": [[str(ce["frente"])]]})
            if "fondo" in ce:
                updates.append({"range": f"'{tab_dg}'!K{fila}", "values": [[str(ce["fondo"])]]})
            if "alto" in ce:
                updates.append({"range": f"'{tab_dg}'!L{fila}", "values": [[str(ce["alto"])]]})
            if "peso_kg" in ce:
                updates.append({"range": f"'{tab_dg}'!M{fila}", "values": [[str(ce["peso_kg"])]]})
            if "metro_cubico" in ce:
                updates.append({"range": f"'{tab_dg}'!N{fila}", "values": [[str(ce["metro_cubico"])]]})

        # 3. Categoría (Col P)
        if "categoria" in data:
            updates.append({"range": f"'{tab_dg}'!P{fila}", "values": [[str(data["categoria"])]]})

        # 4. Modelo (Col X), Tipo de Mueble (Col Y), Nombre Nuevo (Col Z)
        if "modelo" in data:
            updates.append({"range": f"'{tab_dg}'!X{fila}", "values": [[str(data["modelo"])]]})
        if "tipo_mueble" in data:
            updates.append({"range": f"'{tab_dg}'!Y{fila}", "values": [[str(data["tipo_mueble"])]]})
        if "nombre_nuevo" in data:
            updates.append({"range": f"'{tab_dg}'!Z{fila}", "values": [[str(data["nombre_nuevo"])]]})

        # 5. Fotos Mueble (Cols AA, AC)
        if "mueble_nombre" in fotos and fotos["mueble_nombre"]:
            nom_m = fotos["mueble_nombre"]
            lnk_m = fotos.get("mueble_link", "").strip()
            if not lnk_m:
                lnk_m = self.buscar_link_drive_inteligente(nom_m)
                fotos["mueble_link"] = lnk_m
            updates.append({"range": f"'{tab_dg}'!AA{fila}", "values": [[nom_m]]})
            if lnk_m:
                updates.append({"range": f"'{tab_dg}'!AC{fila}", "values": [[lnk_m]]})

        # 6. Fotos Tela (Cols AD, AF)
        if "tela_nombre" in fotos and fotos["tela_nombre"]:
            nom_t = fotos["tela_nombre"]
            lnk_t = fotos.get("tela_link", "").strip()
            if not lnk_t:
                lnk_t = self.buscar_link_drive_inteligente(nom_t)
                fotos["tela_link"] = lnk_t
            updates.append({"range": f"'{tab_dg}'!AD{fila}", "values": [[nom_t]]})
            if lnk_t:
                updates.append({"range": f"'{tab_dg}'!AF{fila}", "values": [[lnk_t]]})

        # 7. Fotos Madera (Cols AG, AI)
        if "madera_nombre" in fotos and fotos["madera_nombre"]:
            nom_md = fotos["madera_nombre"]
            lnk_md = fotos.get("madera_link", "").strip()
            if not lnk_md:
                lnk_md = self.buscar_link_drive_inteligente(nom_md)
                fotos["madera_link"] = lnk_md
            updates.append({"range": f"'{tab_dg}'!AG{fila}", "values": [[nom_md]]})
            if lnk_md:
                updates.append({"range": f"'{tab_dg}'!AI{fila}", "values": [[lnk_md]]})

        # 8. Fotos Swatch (Cols AJ, AL)
        if "swatch_nombre" in fotos and fotos["swatch_nombre"]:
            nom_sw = fotos["swatch_nombre"]
            lnk_sw = fotos.get("swatch_link", "").strip()
            if not lnk_sw:
                lnk_sw = self.buscar_link_drive_inteligente(nom_sw)
                fotos["swatch_link"] = lnk_sw
            updates.append({"range": f"'{tab_dg}'!AJ{fila}", "values": [[nom_sw]]})
            if lnk_sw:
                updates.append({"range": f"'{tab_dg}'!AL{fila}", "values": [[lnk_sw]]})

        # 9. Bultos (Col AM) y SKU (Col A)
        if "bultos" in data:
            updates.append({"range": f"'{tab_dg}'!AM{fila}", "values": [[data["bultos"]]]})
        if sku_val:
            updates.append({"range": f"'{tab_dg}'!A{fila}", "values": [[sku_val]]})

        if updates:
            body = {
                "valueInputOption": "USER_ENTERED",
                "data": updates
            }
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()

        # 10. Actualizar caché local
        try:
            cache_path = Path(__file__).resolve().parent.parent / "datos_general_cache.json"
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    prods = json.load(f)
                for p in prods:
                    if p.get("fila") == fila:
                        if sku_val: p["sku"] = sku_val
                        if "proveedor" in data: p["proveedor"] = data["proveedor"]
                        if "categoria" in data: p["categoria"] = data["categoria"]
                        if "modelo" in data: p["modelo"] = data["modelo"]
                        if "tipo_mueble" in data: p["tipo_mueble"] = data["tipo_mueble"]
                        if "nombre_nuevo" in data: p["nombre_nuevo"] = data["nombre_nuevo"]
                        if "bultos" in data: p["bultos"] = data["bultos"]
                        if "sin_empaque" in data:
                            p["sin_empaque"] = data["sin_empaque"]
                            se_d = data["sin_empaque"]
                            fr = se_d.get("frente", "")
                            fo = se_d.get("fondo", "")
                            al = se_d.get("alto", "")
                            di = se_d.get("diametro", "")
                            if di and di.upper() not in ["", "N/A", "N/D", "0"]:
                                p["medidas_sheet"] = f"{di} CM DIAM"
                            elif fr and fo and al:
                                p["medidas_sheet"] = f"{fr}X{fo}X{al} CM"
                        if "con_empaque" in data: p["con_empaque"] = data["con_empaque"]
                        if "fotos" in data:
                            p["fotos"] = data["fotos"]
                            p["tiene_fotos"] = bool(
                                data["fotos"].get("mueble_link") or 
                                data["fotos"].get("tela_link") or 
                                data["fotos"].get("madera_link") or 
                                data["fotos"].get("swatch_link") or 
                                data["fotos"].get("mueble_nombre")
                            )
                        break
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(prods, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SheetsService] Error actualizando cache local: {e}")

        return True

    def register_in_fotos_normalizadas(self, foto_tipo: str, nombre_foto: str, link_foto: str = "") -> bool:
        """
        Registra una foto en la pestaña FOTOS NORMALIZADAS sin romper estructura ni fórmulas.
        Columnas:
          - Mueble/Producto: B (Nombre) y D (Link) [C tiene fórmula imagen =MAP]
          - Tela:           F (Nombre) y H (Link) [G tiene fórmula imagen =MAP]
          - Madera:         J (Nombre) y L (Link) [K tiene fórmula imagen =MAP]
          - Muestra/Swatch: N (Nombre) y P (Link) [O tiene fórmula imagen =MAP]
        Si el nombre ya existe en la columna correspondiente, no lo duplica.
        """
        if not self.service or not nombre_foto or not str(nombre_foto).strip():
            return False

        col_map = {
            "MUEBLE": ("B", "D"),
            "PRODUCTO": ("B", "D"),
            "PRODUCTOS": ("B", "D"),
            "TELA": ("F", "H"),
            "TELAS": ("F", "H"),
            "MADERA": ("J", "L"),
            "MADERAS": ("J", "L"),
            "SWATCH": ("N", "P"),
            "MUESTRA": ("N", "P"),
            "MUESTRAS": ("N", "P")
        }

        cols = col_map.get(foto_tipo.upper(), ("B", "D"))
        nom_clean = str(nombre_foto).strip()
        n_target = nom_clean.upper()

        # Auto-resolver enlace si viene vacío
        if not link_foto or not str(link_foto).strip():
            link_foto = self.buscar_link_drive_inteligente(nom_clean)
        else:
            link_foto = str(link_foto).strip()

        try:
            tab_fn = self.get_fotos_normalizadas_tab_name()
            res = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_fn}'!{cols[0]}4:{cols[0]}2000"
            ).execute()
            existing_vals = res.get("values", [])
            
            # Verificar si ya está registrada para no duplicar
            last_idx = -1
            for idx, r in enumerate(existing_vals):
                val = r[0].strip().upper() if r and len(r) > 0 and r[0] else ""
                if val:
                    last_idx = idx
                if val == n_target:
                    # Ya está registrada en FOTOS NORMALIZADAS: No colocar ni duplicar
                    return True

            next_row = 4 if last_idx == -1 else (last_idx + 5)

            # Actualizar únicamente nombre y link por separado, sin tocar la columna intermedia de fórmulas (C, G, K, O)
            updates = [
                {"range": f"'{tab_fn}'!{cols[0]}{next_row}", "values": [[nom_clean]]}
            ]
            if link_foto:
                updates.append({"range": f"'{tab_fn}'!{cols[1]}{next_row}", "values": [[link_foto]]})

            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": updates
                }
            ).execute()

            # Actualizar índice en memoria
            if link_foto and self._fn_catalog is not None:
                self._fn_catalog[n_target] = link_foto
                clean_no_ext = os.path.splitext(n_target)[0].strip()
                self._fn_catalog[clean_no_ext] = link_foto

            return True
        except Exception as e:
            print(f"[SheetsService] Error registrando en FOTOS NORMALIZADAS: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Verifica el estado de conexión real con Google Sheets."""
        if not self.service:
            return {
                "ok": False,
                "message": "Servicio no inicializado. Verifica GOOGLE_CREDENTIALS_JSON o credentials.json.",
                "client_email": self.client_email,
                "spreadsheet_id": self.spreadsheet_id
            }
        try:
            res = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            title = res.get("properties", {}).get("title", "Desconocido")
            sheets = [s.get("properties", {}).get("title") for s in res.get("sheets", [])]
            return {
                "ok": True,
                "message": f"Conexión exitosa a Google Sheets: '{title}'",
                "title": title,
                "sheets": sheets,
                "client_email": self.client_email,
                "spreadsheet_id": self.spreadsheet_id
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"Error de acceso: {e}. Recuerda compartir la hoja con '{self.client_email}' como Editor.",
                "client_email": self.client_email,
                "spreadsheet_id": self.spreadsheet_id
            }

sheets_service = SheetsService()
