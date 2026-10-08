import os
import re
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import io
try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials as UserCredentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
except Exception as e:
    service_account = None
    UserCredentials = None
    build = None
    MediaIoBaseDownload = None
    MediaIoBaseUpload = None
    print(f"[SheetsService] Librerías de Google API no disponibles en este entorno: {e}")

DEFAULT_SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg")
BUZON_DRIVE_ID = "1rwRk-bZtb8m4Hso9pCJE1A0_QiS-rqUQ"
FOTOS_FINAL_DRIVE_ID = "1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B"

class SheetsService:
    BUZON_DRIVE_ID = BUZON_DRIVE_ID
    FOTOS_FINAL_DRIVE_ID = FOTOS_FINAL_DRIVE_ID

    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.service = None
        self.drive_service = None
        self.client_email = ""
        self.spreadsheet_id = DEFAULT_SPREADSHEET_ID
        self.buzon_drive_id = BUZON_DRIVE_ID
        self.fotos_final_drive_id = FOTOS_FINAL_DRIVE_ID
        self.connection_status = "Desconectado"
        self._fn_catalog: Optional[Dict[str, str]] = None
        self._drive_catalog: Optional[Dict[str, str]] = None  # FIX: inicializado para evitar AttributeError
        self._fn_catalogs_by_type: Optional[Dict[str, Dict[str, str]]] = None
        self._drive_link_cache: Dict[str, str] = {}
        self._drive_folder_tree_cache: Dict[str, tuple] = {}
        self._sheet_name_datos_general: Optional[str] = None
        self._sheet_name_fotos_norm: Optional[str] = None
        self._init_service()

    @property
    def connection_ok(self) -> bool:
        """Retorna True si tanto Sheets como Drive están conectados correctamente."""
        return self.service is not None and self.drive_service is not None

    def _init_service(self):
        # 1. Cargar Service Account para Sheets (evita bloqueos de proteccion)
        sa_creds = None
        env_creds = "" # Ignorar variables de entorno que causan error de JWT en Render
        if not env_creds:
            import base64
            env_creds = base64.b64decode("ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAiYW50aWdyYXZpdHktaW50ZWdyYWNpb24iLAogICJwcml2YXRlX2tleV9pZCI6ICI5YTE0OWQ0NjBmZGIyOTFmYjY3NDFjYWUxYmZlZTA3ZDY4ODljNDkwIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tXG5NSUlFdkFJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLWXdnZ1NpQWdFQUFvSUJBUUM5V0dzOUkxYjIzcTNMXG5xMFhNbXRuRTIrRG45WUlEQU5BSzh6OU1FNkZqNHkxSzIrTnZFSXRIRUtjVDRBM0FCZ0VxTHErdjRFQlRtNUhCXG5JOHBWbDNUV2xmSWtpSEY3TStJR0l1OG1SaXE2dlllckw5WmpDLzZnQjkxZ0JMNWc3QmVvTnFsTDRqTDgwTlpuXG5kbTlVaFJObnJpS29QTHo5NWRnTGQ4RVZHTmY4a00vckxpbUVPQ3YyY1hWRTNQRlF3UDNQS2VpS0JDYTI4YnJyXG5FNVdxQUxPZHVOSU9Pcjk4cnlReFRhaVgyZm9uQVhpdXJPZVZ4amVCR0tJc3RTbXJIUGQwdWFtdk85aGRyckgxXG5sY3VqVys1V1hMWXFLMnA0SUZhZEkxYlZLVkhFYjU0ZjVhTWt0K3VRZEIwWU5jdGErcVNHaDdVcjhkTG8vZExiXG5lQzU3NHdlcEFnTUJBQUVDZ2dFQVBodjJWV0Exd3hZSlNXRTlySjl3NXArL2x5Y1R4aHRxb3VUbXN2UlBnTjRBXG51ZWtHSWlUNW9zNkdGOEZya1QwRy9jakJyWDN3YTl5QWc2dlRUNTgyWHJ0aDZmVHQwSjJVdXpHVFkra3BWQWNlXG5yUnNzaG1IbFhLWW55anJVSGlQam9MU0pkUkJXYkZLdXVkS0NNMlhSbHpWcVBlaHFrQmhvZFY2TGNmbXJ3N2RHXG5WZFdVaklvUmFlWitMSHVlT0M2WmdIOXpXUFM5cHVhMVo4SlFzYU9lSTFXdm1ONEhUVjIrR0RzR202TnJlMGxYXG5oZlN6NzB2S0JDUFl5RjNDZUd3RE1BdEY3M3VJNmE4WFlDZXVKWjAxenJ2d2JySGlrak5sTC84azNUVEtpeGhkXG5LMkVJZ25aL0NQL0ZhZEx4bElaN3YvK3hMQ2s0STFtdkR2bWtPcktHNXdLQmdRRGlZTElqbWhoMjlVU3ViUW9JXG5hS0xnd08yQU9QUy9QQzltemUyT0pHR2haSlJHRzVwS0tVSnBBc2czcllqSGN4Rm1hRW5KbEJub0RKOHNqSGZvXG5FNFJSRS9wV0pzTkhndTNmckx0djZEWFIzTWZxekZEbjBRVUM3WkVJOVphQ1E1WmpQWFVmRE44QittTEhJaUlEXG5MUkxReGhXeEQzWWR2TnoybUJDR1JSanJPd0tCZ1FEV0h6SjBZeEhhSzhRcXRudWhpVXlwUFZ1Z2lZRTNrNUpqXG5SNUJDSzlLWjcvclpzTnlDbVZnWnRHVEVObHVSbmJOMXlKdStKbk1MbUpVTlZIakp2b2ZueTd1SW9xaGxvdTdHXG5hOEYxMWkwMXBOZGowbUtQYXVGdmkvWW9UMmkwb0tPWGM0ZFEzUW10WFp6THI2aXNYNmh2aC91SnFNbnhLL3pTXG5JaUx6Q1VMQ2F3S0JnSHpOdUlnK05VeW9EYlJvTXdiTndUWk54dUpSQkVYR0JaQVU2ZW5hanVTdWtieFJEVy9qXG5iVlI5anlwN0JwU0hFTW0zcHk1MTh3NW1udjZ0ZHBIQTZNcldTOFpoV25tN2FpOU5pSXk2cGFsTW9mOEZvM2thXG5XRHYwQTJqQUZMaytUOVBvbHdDR1ZSQS9IV1FSb2xURDdjS2g0bVdhVTVFemhWS0NKV0lSQ0JydkFvR0FYVzIzXG5ZamxvTEw0MEZqOFJxdVp4NE5hNUNFOTNabnlwdjFBV2pnajVGOW95cHBJWlpaTHJjaXZZWEJVcjExbnNXRlIwXG5RSUFlYXN6bEhLL2pGSVJpWUszdzRpbTNPTUhqVmdqbW5UZ2ErZkUzV29NT0ptNElkOWVtVE9oNVUzZFVhbDBxXG5pZ29va3REcC9hWmovdkt1V0J3SmtZTm91aWJyWmZVbk1zeXpxSWtDZ1lCNk1zM3BkM2VZYWNwbENBdGYwV0dXXG5aUUlxNDl6VW1hbWpTTkwyQXI4Y1AxMFU0a2ZSV2V4Z2NyVURQVEYxci9RdnQyRWJIbDgwMW91VksrOTBadmNzXG5ydGt3cGRKSFFNM3VnK3pVUG5iZ0R2dlJpWEs1YXh0UkNTVTRSK2Z2bkFmR29WZmoxNzJFS0ZWZEI1YnBIY1d6XG5SMDVVK21lTW1nWThNamJUSFBZOWZBPT1cbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJwcm95ZWN0by0xQGFudGlncmF2aXR5LWludGVncmFjaW9uLmlhbS5nc2VydmljZWFjY291bnQuY29tIiwKICAiY2xpZW50X2lkIjogIjEwMTE2MjUwNjA0MzM3OTc2OTgyNiIsCiAgImF1dGhfdXJpIjogImh0dHBzOi8vYWNjb3VudHMuZ29vZ2xlLmNvbS9vL29hdXRoMi9hdXRoIiwKICAidG9rZW5fdXJpIjogImh0dHBzOi8vb2F1dGgyLmdvb2dsZWFwaXMuY29tL3Rva2VuIiwKICAiYXV0aF9wcm92aWRlcl94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3Lmdvb2dsZWFwaXMuY29tL29hdXRoMi92MS9jZXJ0cyIsCiAgImNsaWVudF94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3Lmdvb2dsZWFwaXMuY29tL3JvYm90L3YxL21ldGFkYXRhL3g1MDkvcHJveWVjdG8tMSU0MGFudGlncmF2aXR5LWludGVncmFjaW9uLmlhbS5nc2VydmljZWFjY291bnQuY29tIiwKICAidW5pdmVyc2VfZG9tYWluIjogImdvb2dsZWFwaXMuY29tIgp9Cg==").decode('utf-8')
        if env_creds:
            try:
                import json
                cred_dict = json.loads(env_creds) if isinstance(env_creds, str) else env_creds
                if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                self.client_email = cred_dict.get("client_email", "")
                sa_creds = service_account.Credentials.from_service_account_info(
                    cred_dict, scopes=self.scopes
                )
                self.service = build("sheets", "v4", credentials=sa_creds)
                self.drive_service = build("drive", "v3", credentials=sa_creds)
                self.connection_status = f"Conectado SA ({self.client_email})"
            except Exception as e:
                self.sa_error = str(e)
                print(f"[SheetsService] Error Service Account Env: {e}")

        if not sa_creds:
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
                    import json
                    with open(cred_path, "r", encoding="utf-8") as f:
                        self.client_email = json.load(f).get("client_email", "")
                    sa_creds = service_account.Credentials.from_service_account_file(
                        str(cred_path), scopes=self.scopes
                    )
                    self.service = build("sheets", "v4", credentials=sa_creds)
                    self.drive_service = build("drive", "v3", credentials=sa_creds)
                    self.connection_status = f"Conectado SA Local ({self.client_email})"
                except Exception as e:
                    self.sa_error = str(e)
                    print(f"[SheetsService] Error Service Account Archivo: {e}")

        # 2. Cargar OAuth del Usuario para Drive (para registrar copias a su nombre)
        oauth_json = "" # Ignorar variables de entorno que causan error de formato en Render
        if not oauth_json:
            local_oauth = Path(__file__).resolve().parent.parent / "GOOGLE_OAUTH_CREDENTIALS.json"
            if local_oauth.exists():
                try:
                    with open(local_oauth, "r", encoding="utf-8") as f:
                        oauth_json = f.read().strip()
                except Exception as e:
                    pass

        if not oauth_json:
            import base64
            oauth_json = base64.b64decode("ewogICJ0b2tlbiI6ICJ5YTI5LmEwQVgwN0NtdVZvRUtJRXdMRTJYcERnelZTQUtERWo2RTkyTFNVWjBzMkp4LUtGR24yak5UMTFaRGFkTWliVkZrNmJvRUxCX3BEaE82Y1ZqXzlkSnZ1OWRCcVhBSmN3UVkyTWJ3MGl1RkNlT3NKNHNfMjE4VndiMTJhRFVHbWZXR0E5RjlFRTBwQUlSbmFxVjY3eGlmellqSDNYZktxWmJramtNTDRwZDU3UXdmQW9KeFRGY0MtVkd4dlBDN21oOEx2NmhmZ2Rvd2FDZ1lLQWVnU0FSUVNGUUhHWDJNaUdHdTF4SkwzSnEtMXdxcHZPLUdLbXcwMjA2IiwKICAicmVmcmVzaF90b2tlbiI6ICIxLy8wNTY4VkVvNFpiRjE3Q2dZSUFSQUFHQVVTTndGLUw5SXJ5aEprSDFfXzdWRUVvV3pDYjVFR05fNE5JejVjSFByUVJSSG9sX0RQb1ZKRTlySVVIRGdva2NYMGtSZDFpRGR3cXB3IiwKICAidG9rZW5fdXJpIjogImh0dHBzOi8vb2F1dGgyLmdvb2dsZWFwaXMuY29tL3Rva2VuIiwKICAiY2xpZW50X2lkIjogIjIxMDExMTE2MDk1Mi05NGVwM2FkaHJjazVkaTk4MW1tcWtsZzkxdm9hdGNwbi5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbSIsCiAgImNsaWVudF9zZWNyZXQiOiAiR09DU1BYLXAyVkV2M2RrRHR1MHlIOUdCbGlnLVQwandHTkEiLAogICJzY29wZXMiOiBbCiAgICAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vYXV0aC9kcml2ZSIsCiAgICAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vYXV0aC9zcHJlYWRzaGVldHMiCiAgXQp9Cg==").decode("utf-8")

        if oauth_json:
            try:
                import json
                user_info = json.loads(oauth_json)
                user_creds = UserCredentials.from_authorized_user_info(
                    user_info, scopes=self.scopes
                )
                self.drive_service = build("drive", "v3", credentials=user_creds)
                self.service = build("sheets", "v4", credentials=user_creds)
                self.connection_status = "Conectado OAuth (Sheets & Drive)"
                print("[SheetsService] Sheets y Drive conectados exitosamente con OAuth personal (kevin.reyna).")
            except Exception as e:
                print(f"[SheetsService] Error OAuth overrides: {e}")

    def clear_memory_cache(self):
        """Limpia los catálogos en memoria y nombres de pestañas para forzar sincronización fresca."""
        self._fn_catalog = None
        self._drive_catalog = None
        self._fn_catalogs_by_type = None
        self._drive_link_cache.clear()
        self._drive_folder_tree_cache.clear()
        self._sheet_name_datos_general = None
        self._sheet_name_fotos_norm = None

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

    def get_fotos_normalizadas_catalogs(self) -> Dict[str, Dict[str, str]]:
        """Retorna catálogos separados por tipo (MUEBLE, TELA, MADERA, SWATCH) de FOTOS NORMALIZADAS."""
        if hasattr(self, "_fn_catalogs_by_type") and self._fn_catalogs_by_type is not None:
            return self._fn_catalogs_by_type

        cats = {
            "MUEBLE": {},
            "TELA": {},
            "MADERA": {},
            "SWATCH": {}
        }
        if not self.service:
            self._fn_catalogs_by_type = cats
            return cats

        try:
            tab_fn = self.get_fotos_normalizadas_tab_name()
            res = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_fn}'!A4:P"
            ).execute()
            rows = res.get("values", [])
            for r in rows:
                # Mueble (Col B=idx 1, Col D=idx 3)
                if len(r) > 1 and r[1].strip() and len(r) > 3 and r[3].strip():
                    nom = r[1].strip().upper()
                    clean = os.path.splitext(nom)[0].strip()
                    cats["MUEBLE"][nom] = r[3].strip()
                    cats["MUEBLE"][clean] = r[3].strip()

                # Tela (Col F=idx 5, Col H=idx 7)
                if len(r) > 5 and r[5].strip() and len(r) > 7 and r[7].strip():
                    nom = r[5].strip().upper()
                    clean = os.path.splitext(nom)[0].strip()
                    cats["TELA"][nom] = r[7].strip()
                    cats["TELA"][clean] = r[7].strip()

                # Madera (Col J=idx 9, Col L=idx 11)
                if len(r) > 9 and r[9].strip() and len(r) > 11 and r[11].strip():
                    nom = r[9].strip().upper()
                    clean = os.path.splitext(nom)[0].strip()
                    cats["MADERA"][nom] = r[11].strip()
                    cats["MADERA"][clean] = r[11].strip()

                # Swatch (Col N=idx 13, Col P=idx 15)
                if len(r) > 13 and r[13].strip() and len(r) > 15 and r[15].strip():
                    nom = r[13].strip().upper()
                    clean = os.path.splitext(nom)[0].strip()
                    cats["SWATCH"][nom] = r[15].strip()
                    cats["SWATCH"][clean] = r[15].strip()
        except Exception as e:
            print(f"[SheetsService] Error cargando catálogos de FOTOS NORMALIZADAS: {e}")

        self._fn_catalogs_by_type = cats
        return cats

    def get_fotos_normalizadas_catalog(self) -> Dict[str, str]:
        """Compatibilidad: retorna diccionario general de FOTOS NORMALIZADAS priorizando MUEBLES."""
        cats = self.get_fotos_normalizadas_catalogs()
        merged = {}
        for t in ["SWATCH", "MADERA", "TELA", "MUEBLE"]:
            merged.update(cats.get(t, {}))
        self._fn_catalog = merged
        return merged

    def buscar_link_drive_inteligente(self, nombre_foto: str, tipo: str = "MUEBLE") -> str:
        """Busca el enlace de Google Drive para un nombre de foto usando coincidencia exacta y Drive API sin mezclar tipos."""
        if not nombre_foto or not str(nombre_foto).strip() or str(nombre_foto).strip().upper() in ["N/A", "NONE", ""]:
            return ""

        nom = str(nombre_foto).strip()
        n_up = nom.upper()
        n_clean = os.path.splitext(n_up)[0].strip()

        # 1. Búsqueda exacta en catálogo específico según tipo
        cats = self.get_fotos_normalizadas_catalogs()
        tipo_key = "MUEBLE"
        t_upper = tipo.upper()
        if "TELA" in t_upper:
            tipo_key = "TELA"
        elif "MADERA" in t_upper:
            tipo_key = "MADERA"
        elif "SWATCH" in t_upper or "MUESTRA" in t_upper:
            tipo_key = "SWATCH"

        target_cat = cats.get(tipo_key, {})
        if n_up in target_cat:
            return target_cat[n_up]
        if n_clean in target_cat:
            return target_cat[n_clean]

        cache_key = f"{tipo_key}:{n_clean}"
        if cache_key in self._drive_link_cache:
            return self._drive_link_cache[cache_key]

        # 2. Búsqueda directa en Google Drive API por nombre exacto o stem de archivo
        if not self.drive_service:
            return ""

        exact_names = [nom, n_clean] + [f"{n_clean}.{ext}" for ext in ("jpg", "png", "webp")]
        escaped_names = [name.replace("\\", "\\\\").replace("'", "\\'") for name in exact_names]
        exact_clauses = [f"name = '{name}'" for name in escaped_names]
        escaped_name = n_clean.replace("\\", "\\\\").replace("'", "\\'")
        query = (
            "(" + " or ".join(exact_clauses) + f" or name contains '{escaped_name}')"
            " and trashed = false"
        )
        try:
            response = self.drive_service.files().list(
                q=query,
                fields="files(id, name, mimeType)",
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            files = [
                item for item in response.get("files", [])
                if item.get("mimeType") != "application/vnd.google-apps.folder"
            ]
            best_match = next(
                (
                    item for item in files
                    if os.path.splitext(item.get("name", "").strip())[0].upper() == n_clean
                ),
                files[0] if files else None
            )
            if best_match:
                link = f"https://drive.google.com/file/d/{best_match['id']}/view"
                target_cat[n_clean] = link
                target_cat[n_up] = link
                self._drive_link_cache[cache_key] = link
                return link
        except Exception as error:
            print(f"[SheetsService] Error buscando '{nom}' en Drive: {error}")
            return ""

        self._drive_link_cache[cache_key] = ""
        return ""

    def get_drive_file_bytes(self, drive_id: str, raise_on_error: bool = False) -> Optional[bytes]:
        """Descarga el contenido binario de una imagen directamente desde Google Drive API autenticada."""
        if not self.drive_service or not drive_id:
            if raise_on_error:
                raise RuntimeError("Google Drive no está conectado o falta el ID del archivo.")
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
            if raise_on_error:
                raise RuntimeError(f"Falló la descarga autenticada de Drive: {e}") from e
            return None

    def search_drive_images_live(
        self,
        query_text: str,
        limit: int = 30,
        folder_id: str = "",
    ) -> List[Dict[str, str]]:
        """Busca imágenes frescas dentro de una carpeta de Drive y sus subcarpetas."""
        if (
            not self.drive_service
            or not folder_id
            or not query_text
            or not str(query_text).strip()
            or limit <= 0
        ):
            return []
        
        q_str = str(query_text).strip()
        words = [w for w in re.split(r'[\s_\-\.]+', q_str) if len(w) >= 2 and not w.isdigit()]
        if not words:
            return []
            
        escaped_words = [
            w.replace("\\", "\\\\").replace("'", "\\'")
            for w in words[:4]
        ]
        clauses = " and ".join(f"name contains '{word}'" for word in escaped_words)
        folder_mime_type = "application/vnd.google-apps.folder"
        
        try:
            results = []
            seen_ids = set()
            
            # 1. Búsqueda directa ultra-rápida (coincidencia de nombre e imágenes)
            query = f"({clauses}) and trashed = false and (mimeType contains 'image/' or mimeType = 'application/vnd.google-apps.shortcut')"
            response = self.drive_service.files().list(
                q=query,
                pageSize=limit,
                fields="files(id,name,mimeType,webViewLink)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            for file in response.get("files", []):
                file_id = file.get("id")
                if not file_id or file_id in seen_ids:
                    continue
                seen_ids.add(file_id)
                results.append({
                    "id": file_id,
                    "name": file.get("name", ""),
                    "link": file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view",
                })
                if len(results) >= limit:
                    break

            return results
        except Exception as e:
            print(f"[SheetsService] Error buscando imágenes en Drive: {e}")
            raise RuntimeError(
                f"Falló la búsqueda de fotos en FOTOS BASE: {e}"
            ) from e

    
    
    def copy_and_rename_drive_file(self, file_id: str, new_name: str, root_id: str, relative_path: str) -> str:
        if not self.drive_service:
            raise RuntimeError("Google Drive no está conectado.")

        parts = [p for p in relative_path.replace('\\', '/').split('/') if p]
        current_parent = root_id
        for part in parts:
            current_parent = self.get_or_create_drive_folder(current_parent, part)
            if not current_parent:
                raise RuntimeError(f"No se pudo encontrar o crear la carpeta '{part}' en Drive.")

        try:
            escaped_name = new_name.replace("\\", "\\\\").replace("'", "\\'")
            query = f"'{current_parent}' in parents and name='{escaped_name}' and trashed=false"
            page_token = None
            existing_files = []
            while True:
                response = self.drive_service.files().list(
                    q=query,
                    fields='nextPageToken,files(id,name,mimeType,webViewLink,md5Checksum)',
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                existing_files.extend(response.get('files', []))
                page_token = response.get('nextPageToken')
                if page_token:
                    continue
                break

            existing_file = next((
                item for item in existing_files
                if item.get('mimeType') not in (
                    'application/vnd.google-apps.shortcut',
                    'application/vnd.google-apps.folder',
                )
            ), None)

            if existing_file:
                self._drive_link_cache.clear()
                return existing_file.get('webViewLink') or (
                    f"https://drive.google.com/file/d/{existing_file['id']}/view"
                )
            copied = self.drive_service.files().copy(
                fileId=file_id,
                body={'name': new_name, 'parents': [current_parent]},
                supportsAllDrives=True,
                fields='id,webViewLink'
            ).execute()
            if not copied.get('id'):
                raise RuntimeError("Drive no devolvió el ID del archivo copiado.")
            self._drive_link_cache.clear()
            return copied.get('webViewLink') or (
                f"https://drive.google.com/file/d/{copied['id']}/view"
            )
        except Exception as e:
            error_details = str(e)
            error_content = getattr(e, "content", b"")
            if isinstance(error_content, bytes):
                error_details += error_content.decode("utf-8", errors="replace")
            else:
                error_details += str(error_content)
            if "storageQuotaExceeded" in error_details:
                raise RuntimeError(
                    "La cuenta de servicio de Google no tiene cuota para crear "
                    "copias en FOTOS FINAL. Darle más permisos no lo resuelve: "
                    "se necesita autorizar una cuenta de Google con OAuth o "
                    "guardar el destino en una Unidad compartida."
                ) from e
            raise RuntimeError(f"No se pudo copiar '{new_name}' a Google Drive: {e}") from e

    def get_or_create_drive_folder(self, parent_id: str, folder_name: str):
        if not self.drive_service or not parent_id: return None
        query = f"'{parent_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        try:
            res = self.drive_service.files().list(q=query, fields='files(id)', supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            files = res.get('files', [])
            if files:
                return files[0]['id']
            metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = self.drive_service.files().create(body=metadata, fields='id', supportsAllDrives=True).execute()
            return folder.get('id')
        except Exception as e:
            print(f'Error getting/creating folder {folder_name}: {e}')
            return None

    def upload_image_bytes_to_path(self, file_bytes: bytes, filename: str, root_id: str, relative_path: str):
        if not self.drive_service: return None
        parts = [p for p in relative_path.replace('\\', '/').split('/') if p]
        current_parent = root_id
        for part in parts:
            current_parent = self.get_or_create_drive_folder(current_parent, part)
            if not current_parent: return None
        return self.upload_image_bytes_to_drive(file_bytes, filename, current_parent)

    def upload_image_bytes_to_drive(self, file_bytes: bytes, filename: str, folder_id: str) -> Optional[str]:
        """Sube una imagen binaria directamente a una carpeta de Google Drive y retorna su URL oficial."""
        if not self.drive_service or not file_bytes:
            return None
        from googleapiclient.http import MediaIoBaseUpload
        try:
            ext = os.path.splitext(filename)[1].lower().replace(".", "")
            mime = f"image/{ext if ext != 'jpg' else 'jpeg'}"
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=True)
            file_metadata = {
                "name": filename,
                "parents": [folder_id]
            }
            uploaded = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True
            ).execute()
            file_id = uploaded.get("id")
            if file_id:
                self._drive_link_cache.clear()
                try:
                    self.drive_service.permissions().create(
                        fileId=file_id,
                        body={"role": "reader", "type": "anyone"}
                    ).execute()
                except Exception:
                    pass
                link = f"https://drive.google.com/file/d/{file_id}/view"
                stem = os.path.splitext(filename)[0].strip().upper()
                if self._drive_catalog is not None:
                    self._drive_catalog[filename.upper()] = link
                    self._drive_catalog[stem] = link
                if self._fn_catalog is not None:
                    self._fn_catalog[filename.upper()] = link
                    self._fn_catalog[stem] = link
                return link
            return uploaded.get("webViewLink")
        except Exception as e:
            print(f"[SheetsService] Error subiendo imagen a Google Drive ({filename}): {e}")
            return None

    def get_recent_drive_images(self, limit: int = 250) -> List[Dict[str, str]]:
        """Obtiene de inmediato las fotos más recientemente subidas o modificadas en Google Drive (sin llamadas recursivas lentas, ~1 seg)."""
        if not self.drive_service:
            return []
        try:
            res = self.drive_service.files().list(
                q="mimeType contains 'image/' and trashed = false",
                orderBy="modifiedTime desc",
                pageSize=limit,
                fields="files(id, name, webViewLink)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            results = []
            for f in res.get("files", []):
                clean_name = os.path.splitext(f["name"])[0].strip()
                results.append({
                    "id": f["id"],
                    "name": clean_name,
                    "filename": f["name"],
                    "link": f.get("webViewLink") or f"https://drive.google.com/file/d/{f['id']}/view",
                    "subcarpeta": "Drive Nube"
                })
            return results
        except Exception as e:
            print(f"[SheetsService] Error obteniendo fotos recientes de Drive: {e}")
            return []

    def get_drive_folder_files(self, folder_id: str, recursive: bool = True) -> List[Dict[str, str]]:
        """Obtiene la lista de imágenes desde una carpeta específica de Google Drive (con soporte recursivo para subcarpetas)."""
        if not self.drive_service or not folder_id:
            return []
        
        def _scan(f_id: str, sub_label: str = ""):
            items_found = []
            page_token = None
            try:
                while True:
                    res = self.drive_service.files().list(
                        q=f"'{f_id}' in parents and trashed = false",
                        fields="nextPageToken,files(id,name,mimeType)",
                        pageSize=1000,
                        pageToken=page_token,
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
                            mime_type = f.get("mimeType", "")
                            items_found.append({
                                "id": file_id,
                                "name": clean_name,
                                "filename": name,
                                "link": f"https://drive.google.com/file/d/{file_id}/view",
                                "subcarpeta": sub_label,
                                "mimeType": mime_type
                            })
                    page_token = res.get("nextPageToken")
                    if not page_token:
                        break
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

    # =========================================================================
    # OPERACIONES DE BUZÓN (STAGING) Y GESTIÓN DE ARCHIVOS DRIVE (MILESTONE 1)
    # =========================================================================

    def list_buzon_images(self) -> List[Dict[str, Any]]:
        """
        Lista todas las fotos/imágenes presentes en la carpeta Buzón (BUZON_DRIVE_ID).
        Retorna una lista de diccionarios con metadatos: id, name, filename, mimeType,
        webViewLink, link, thumbnailLink, description, createdTime, modifiedTime, size.
        """
        if not self.drive_service:
            print("[SheetsService] Drive service no disponible para listar buzón.")
            return []

        try:
            query = f"'{BUZON_DRIVE_ID}' in parents and trashed = false"
            page_token = None
            image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.heic')
            files_found: List[Dict[str, Any]] = []

            while True:
                response = self.drive_service.files().list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, webViewLink, thumbnailLink, description, createdTime, modifiedTime, size)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()

                for f in response.get("files", []):
                    mime = f.get("mimeType", "")
                    if mime == "application/vnd.google-apps.folder":
                        continue
                    name = f.get("name", "")
                    if mime.startswith("image/") or name.lower().endswith(image_extensions):
                        file_id = f.get("id", "")
                        clean_name = os.path.splitext(name)[0].strip()
                        web_link = f.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
                        files_found.append({
                            "id": file_id,
                            "name": clean_name,
                            "filename": name,
                            "mimeType": mime,
                            "webViewLink": web_link,
                            "link": web_link,
                            "thumbnailLink": f.get("thumbnailLink"),
                            "description": f.get("description", "") or "",
                            "createdTime": f.get("createdTime", "") or "",
                            "modifiedTime": f.get("modifiedTime", "") or "",
                            "size": f.get("size")
                        })

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            files_found.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
            return files_found
        except Exception as e:
            print(f"[SheetsService] Error listando imágenes del buzón: {e}")
            return []

    def upload_image_to_buzon(
        self,
        file_bytes: bytes,
        filename: str,
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Sube una imagen binaria directamente a la carpeta Buzón (BUZON_DRIVE_ID).
        Si se provee metadata (dict), se codifica en JSON y se almacena en el campo description de Drive.
        Retorna el webViewLink del archivo subido o None si ocurre un error.
        """
        if not self.drive_service or not file_bytes:
            return None

        from googleapiclient.http import MediaIoBaseUpload

        try:
            ext = os.path.splitext(filename)[1].lower().replace(".", "")
            mime = f"image/{ext if ext != 'jpg' else 'jpeg'}"
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=True)

            file_metadata: Dict[str, Any] = {
                "name": filename,
                "parents": [BUZON_DRIVE_ID]
            }

            if metadata is not None:
                if isinstance(metadata, dict):
                    file_metadata["description"] = json.dumps(metadata, ensure_ascii=False)
                else:
                    file_metadata["description"] = str(metadata)

            uploaded = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, description",
                supportsAllDrives=True
            ).execute()

            file_id = uploaded.get("id")
            if not file_id:
                return None

            self._drive_link_cache.clear()

            try:
                self.drive_service.permissions().create(
                    fileId=file_id,
                    body={"role": "reader", "type": "anyone"}
                ).execute()
            except Exception:
                pass

            web_link = uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
            return web_link
        except Exception as e:
            print(f"[SheetsService] Error subiendo imagen al buzón ({filename}): {e}")
            return None

    def copy_file_to_buzon(
        self,
        source_drive_id: str,
        filename: str,
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Copia un archivo existente de Drive directamente a la carpeta Buzón (BUZON_DRIVE_ID).
        Si se provee metadata (dict), se codifica en JSON y se almacena en el campo description.
        Retorna el webViewLink del archivo copiado o None si ocurre un error.
        """
        if not self.drive_service or not source_drive_id:
            return None

        try:
            body: Dict[str, Any] = {
                "name": filename,
                "parents": [BUZON_DRIVE_ID]
            }

            if metadata is not None:
                if isinstance(metadata, dict):
                    body["description"] = json.dumps(metadata, ensure_ascii=False)
                else:
                    body["description"] = str(metadata)

            copied = self.drive_service.files().copy(
                fileId=source_drive_id,
                body=body,
                supportsAllDrives=True,
                fields="id, name, webViewLink, description"
            ).execute()

            copied_id = copied.get("id")
            if not copied_id:
                return None

            self._drive_link_cache.clear()

            try:
                self.drive_service.permissions().create(
                    fileId=copied_id,
                    body={"role": "reader", "type": "anyone"}
                ).execute()
            except Exception:
                pass

            web_link = copied.get("webViewLink") or f"https://drive.google.com/file/d/{copied_id}/view"
            return web_link
        except Exception as e:
            print(f"[SheetsService] Error copiando archivo {source_drive_id} al buzón ({filename}): {e}")
            return None

    def move_drive_file(
        self,
        file_id: str,
        source_folder_id: str,
        root_dest_id: str,
        relative_path: str
    ) -> Dict[str, Any]:
        """
        Mueve o transfiere un archivo desde source_folder_id hacia root_dest_id/relative_path.
        1. Crea o resuelve la subcarpeta de destino mediante get_or_create_drive_folder.
        2. Intenta mover el archivo vía files().update(addParents=..., removeParents=...).
        3. Si update falla (ej. permisos entre cuentas o cuota), realiza fallback a copy + delete en origen.
        Retorna un dict con {'id': ..., 'link': ..., 'method': 'move'|'copy_delete', 'folder_id': ...}.
        """
        if not self.drive_service:
            raise RuntimeError("Google Drive no está conectado.")
        if not file_id:
            raise ValueError("file_id no puede ser nulo o vacío.")

        # 1. Resolver o crear la ruta de carpetas de destino
        parts = [p for p in relative_path.replace('\\', '/').split('/') if p]
        current_dest = root_dest_id
        for part in parts:
            current_dest = self.get_or_create_drive_folder(current_dest, part)
            if not current_dest:
                raise RuntimeError(f"No se pudo resolver o crear la subcarpeta '{part}' en destino.")

        # 2. Intentar mover mediante update(addParents, removeParents)
        try:
            update_kwargs: Dict[str, Any] = {
                "fileId": file_id,
                "addParents": current_dest,
                "supportsAllDrives": True,
                "fields": "id, name, webViewLink, parents"
            }
            if source_folder_id:
                update_kwargs["removeParents"] = source_folder_id

            updated = self.drive_service.files().update(**update_kwargs).execute()
            res_id = updated.get("id") or file_id
            link = updated.get("webViewLink") or f"https://drive.google.com/file/d/{res_id}/view"
            self._drive_link_cache.clear()
            return {
                "id": res_id,
                "link": link,
                "method": "move",
                "folder_id": current_dest
            }
        except Exception as move_err:
            print(f"[SheetsService] files().update(addParents) falló ({move_err}). Iniciando fallback copy+delete...")

        # 3. Fallback: Copiar archivo al destino y eliminar el original en origen
        try:
            file_meta = self.drive_service.files().get(
                fileId=file_id,
                fields="id, name, description, mimeType",
                supportsAllDrives=True
            ).execute()
            file_name = file_meta.get("name", "archivo")
            file_desc = file_meta.get("description")

            copy_body: Dict[str, Any] = {
                "name": file_name,
                "parents": [current_dest]
            }
            if file_desc:
                copy_body["description"] = file_desc

            copied = self.drive_service.files().copy(
                fileId=file_id,
                body=copy_body,
                supportsAllDrives=True,
                fields="id, name, webViewLink"
            ).execute()

            new_id = copied.get("id")
            if not new_id:
                raise RuntimeError("Drive no devolvió el ID del archivo copiado en fallback.")

            new_link = copied.get("webViewLink") or f"https://drive.google.com/file/d/{new_id}/view"

            # Eliminar archivo original
            try:
                self.delete_drive_file(file_id)
            except Exception as del_err:
                print(f"[SheetsService] Advertencia eliminando archivo original {file_id}: {del_err}")

            self._drive_link_cache.clear()
            return {
                "id": new_id,
                "link": new_link,
                "method": "copy_delete",
                "folder_id": current_dest
            }
        except Exception as copy_err:
            print(f"[SheetsService] Error en fallback copy+delete de archivo {file_id}: {copy_err}")
            raise RuntimeError(f"Fallo al transferir archivo {file_id} a '{relative_path}': {copy_err}") from copy_err

    def move_buzon_file_to_final(
        self,
        buzon_file_id: str,
        filename: str,
        subcarpeta_destino: str
    ) -> str:
        """
        Helper de conveniencia: transfiere un archivo desde el Buzón hacia FOTOS FINAL.
        Retorna el enlace web de Google Drive del archivo en su destino definitivo.
        """
        result = self.move_drive_file(
            file_id=buzon_file_id,
            source_folder_id=BUZON_DRIVE_ID,
            root_dest_id=FOTOS_FINAL_DRIVE_ID,
            relative_path=subcarpeta_destino
        )
        return result.get("link", "")

    def delete_drive_file(self, file_id: str) -> bool:
        """
        Elimina de forma segura un archivo de Google Drive.
        Intenta borrado permanente vía files().delete(), y si no cuenta con permisos,
        hace fallback enviando el archivo a la papelera (trashed=True).
        Retorna True si la eliminación o descarte tuvo éxito, False en caso contrario.
        """
        if not self.drive_service or not file_id:
            return False

        try:
            self.drive_service.files().delete(
                fileId=file_id,
                supportsAllDrives=True
            ).execute()
            self._drive_link_cache.clear()
            return True
        except Exception as e:
            try:
                self.drive_service.files().update(
                    fileId=file_id,
                    body={"trashed": True},
                    supportsAllDrives=True
                ).execute()
                self._drive_link_cache.clear()
                return True
            except Exception as e2:
                print(f"[SheetsService] Error eliminando archivo en Drive ({file_id}): {e} | {e2}")
                return False



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
                range=f"'{tab_dg}'!A4:AZ",
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

        if products:
            try:
                cache_file = Path(__file__).resolve().parent.parent / "datos_general_cache.json"
                with open(cache_file, "w", encoding="utf-8") as cf:
                    json.dump(products, cf, ensure_ascii=False, indent=2)
            except Exception:
                pass

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

    def register_many_in_fotos_normalizadas(self, photos: List[Dict[str, str]]) -> bool:
        """Registra varios nombres y enlaces con una lectura y una escritura por lote."""
        if not self.service:
            return False

        type_map = {
            "MUEBLE": "MUEBLE",
            "PRODUCTO": "MUEBLE",
            "PRODUCTOS": "MUEBLE",
            "TELA": "TELA",
            "TELAS": "TELA",
            "MADERA": "MADERA",
            "MADERAS": "MADERA",
            "SWATCH": "SWATCH",
            "MUESTRA": "SWATCH",
            "MUESTRAS": "SWATCH",
        }
        columns = {
            "MUEBLE": ("B", "D", 1, 3),
            "TELA": ("F", "H", 5, 7),
            "MADERA": ("J", "L", 9, 11),
            "SWATCH": ("N", "P", 13, 15),
        }
        prepared = []
        for photo in photos:
            name = str(photo.get("nombre", "")).strip()
            if not name:
                continue
            photo_type = type_map.get(str(photo.get("tipo", "")).upper(), "MUEBLE")
            link = str(photo.get("link", "")).strip()
            if not link:
                link = self.buscar_link_drive_inteligente(name, tipo=photo_type)
            prepared.append((photo_type, name, name.upper(), link))

        if not prepared:
            return True

        try:
            tab_fn = self.get_fotos_normalizadas_tab_name()
            response = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{tab_fn}'!A4:P"
            ).execute()
            rows = response.get("values", [])
            existing_rows = {photo_type: {} for photo_type in columns}
            last_rows = {photo_type: 3 for photo_type in columns}

            for offset, row in enumerate(rows):
                sheet_row = offset + 4
                for photo_type, (_, _, name_index, link_index) in columns.items():
                    name = row[name_index].strip() if len(row) > name_index and row[name_index] else ""
                    link = row[link_index].strip() if len(row) > link_index and row[link_index] else ""
                    if name:
                        last_rows[photo_type] = sheet_row
                        existing_rows[photo_type].setdefault(name.upper(), (sheet_row, link))

            updates = []
            for photo_type, name, name_key, link in prepared:
                name_col, link_col, _, _ = columns[photo_type]
                existing = existing_rows[photo_type].get(name_key)
                if existing:
                    row_number, current_link = existing
                    if link and not current_link:
                        updates.append({
                            "range": f"'{tab_fn}'!{link_col}{row_number}",
                            "values": [[link]],
                        })
                        existing_rows[photo_type][name_key] = (row_number, link)
                    continue

                row_number = last_rows[photo_type] + 1
                last_rows[photo_type] = row_number
                existing_rows[photo_type][name_key] = (row_number, link)
                updates.append({
                    "range": f"'{tab_fn}'!{name_col}{row_number}",
                    "values": [[name]],
                })
                if link:
                    updates.append({
                        "range": f"'{tab_fn}'!{link_col}{row_number}",
                        "values": [[link]],
                    })

            if updates:
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"valueInputOption": "USER_ENTERED", "data": updates},
                ).execute()

            for photo_type, name, name_key, link in prepared:
                if not link:
                    continue
                clean_name = os.path.splitext(name_key)[0].strip()
                if self._fn_catalogs_by_type is not None:
                    catalog = self._fn_catalogs_by_type.get(photo_type)
                    if catalog is not None:
                        catalog[name_key] = link
                        catalog[clean_name] = link
                if self._fn_catalog is not None:
                    self._fn_catalog[name_key] = link
                    self._fn_catalog[clean_name] = link
                self._drive_link_cache[f"{photo_type}:{clean_name}"] = link
            return True
        except Exception as error:
            print(f"[SheetsService] Error registrando fotos normalizadas: {error}")
            return False

    def register_in_fotos_normalizadas(self, foto_tipo: str, nombre_foto: str, link_foto: str = "") -> bool:
        """Registra una foto usando el flujo por lotes para conservar compatibilidad."""
        if not nombre_foto or not str(nombre_foto).strip():
            return False
        return self.register_many_in_fotos_normalizadas([{
            "tipo": foto_tipo,
            "nombre": nombre_foto,
            "link": link_foto,
        }])

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
