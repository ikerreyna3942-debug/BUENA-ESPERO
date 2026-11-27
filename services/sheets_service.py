import os
import re
import json
import mimetypes
import time
import tempfile
import threading
import unicodedata
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import List, Dict, Any, Optional
import io
try:
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
except Exception:
    httplib2 = None
    AuthorizedHttp = None

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
INFO_MIA_DRIVE_ID = "1MJ90Y9Jsjd5jezwLnSUekuR15rcWFYxi"
SUBIR_DRIVE_ID = "11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p"
PROMPTS_MUEBLES_DRIVE_ID = "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX"
RENDER_DRIVE_ID = PROMPTS_MUEBLES_DRIVE_ID

MAX_DRIVE_DOWNLOAD_BYTES = 30 * 1024 * 1024  # 30 MB tope seguro para evitar OOM en Render 512 MB

STAGING_IMAGE_EXTS = (
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif",
    ".tiff", ".tif", ".gif", ".jfif", ".avif",
)
STAGING_DOC_EXTS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".ppt", ".pptx", ".zip",
)
STAGING_DOC_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/csv",
    "text/plain",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
}
_EXT_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jpe": "image/jpeg",
    ".jfif": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".zip": "application/zip",
}


class _BoundedBytesLRU:
    """Caché LRU thread-safe con límites estrictos en MB separados para fotos completas y miniaturas."""

    def __init__(
        self,
        max_full_entries: int = 10,
        max_full_bytes: int = 20 * 1024 * 1024,
        max_thumb_entries: int = 80,
        max_thumb_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self._lock = threading.Lock()
        self._full: "OrderedDict[str, bytes]" = OrderedDict()
        self._full_bytes = 0
        self._max_full_entries = max_full_entries
        self._max_full_bytes = max_full_bytes
        self._thumbs: "OrderedDict[str, bytes]" = OrderedDict()
        self._thumb_bytes = 0
        self._max_thumb_entries = max_thumb_entries
        self._max_thumb_bytes = max_thumb_bytes

    @staticmethod
    def _is_thumb(key: str) -> bool:
        return isinstance(key, str) and key.startswith("thumb:")

    def get(self, key: str, default: Optional[bytes] = None) -> Optional[bytes]:
        with self._lock:
            store = self._thumbs if self._is_thumb(key) else self._full
            val = store.get(key)
            if val is not None:
                store.move_to_end(key)
                return val
            return default

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        with self._lock:
            store = self._thumbs if self._is_thumb(key) else self._full
            return key in store

    def __getitem__(self, key: str) -> bytes:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: bytes) -> None:
        if not isinstance(key, str) or not isinstance(value, (bytes, bytearray)):
            return
        data = bytes(value)
        size = len(data)
        with self._lock:
            if self._is_thumb(key):
                if size > self._max_thumb_bytes:
                    return
                if key in self._thumbs:
                    self._thumb_bytes -= len(self._thumbs.pop(key))
                while self._thumbs and (
                    len(self._thumbs) >= self._max_thumb_entries
                    or (self._thumb_bytes + size) > self._max_thumb_bytes
                ):
                    _, ev = self._thumbs.popitem(last=False)
                    self._thumb_bytes -= len(ev)
                self._thumbs[key] = data
                self._thumb_bytes += size
            else:
                if size > self._max_full_bytes:
                    return
                if key in self._full:
                    self._full_bytes -= len(self._full.pop(key))
                while self._full and (
                    len(self._full) >= self._max_full_entries
                    or (self._full_bytes + size) > self._max_full_bytes
                ):
                    _, ev = self._full.popitem(last=False)
                    self._full_bytes -= len(ev)
                self._full[key] = data
                self._full_bytes += size

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if self._is_thumb(key):
                val = self._thumbs.pop(key, None)
                if val is not None:
                    self._thumb_bytes -= len(val)
                    return val
                return default
            val = self._full.pop(key, None)
            if val is not None:
                self._full_bytes -= len(val)
                return val
            return default

    def clear(self) -> None:
        with self._lock:
            self._full.clear()
            self._full_bytes = 0
            self._thumbs.clear()
            self._thumb_bytes = 0

    def total_bytes(self) -> int:
        with self._lock:
            return self._full_bytes + self._thumb_bytes

    def __len__(self) -> int:
        with self._lock:
            return len(self._full) + len(self._thumbs)


class SheetsService:
    BUZON_DRIVE_ID = BUZON_DRIVE_ID
    FOTOS_FINAL_DRIVE_ID = FOTOS_FINAL_DRIVE_ID
    INFO_MIA_DRIVE_ID = INFO_MIA_DRIVE_ID
    SUBIR_DRIVE_ID = SUBIR_DRIVE_ID
    PROMPTS_MUEBLES_DRIVE_ID = PROMPTS_MUEBLES_DRIVE_ID
    RENDER_DRIVE_ID = RENDER_DRIVE_ID

    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.service = None
        self.drive_service = None
        self._active_creds = None
        self._last_permission_status: Dict[str, tuple] = {}
        self.client_email = ""
        self.spreadsheet_id = DEFAULT_SPREADSHEET_ID
        self.buzon_drive_id = BUZON_DRIVE_ID
        self.fotos_final_drive_id = FOTOS_FINAL_DRIVE_ID
        self.info_mia_drive_id = INFO_MIA_DRIVE_ID
        self.subir_drive_id = SUBIR_DRIVE_ID
        self.render_drive_id = RENDER_DRIVE_ID
        self.connection_status = "Desconectado"
        self._fn_catalog: Optional[Dict[str, str]] = None
        self._drive_catalog: Optional[Dict[str, str]] = None  # FIX: inicializado para evitar AttributeError
        self._fn_catalogs_by_type: Optional[Dict[str, Dict[str, str]]] = None
        self._drive_link_cache: Dict[str, str] = {}
        self._drive_folder_tree_cache: Dict[str, tuple] = {}
        self._drive_subfolder_ids_cache: Dict[str, tuple] = {}
        self._resolved_folder_ids: Dict[str, str] = {}
        self._drive_file_bytes_cache: _BoundedBytesLRU = _BoundedBytesLRU()
        self._drive_api_lock = threading.Lock()
        self._catalog_disk_cache_path = Path(tempfile.gettempdir()) / "buena_espero_drive_catalog_cache.json"
        self._load_disk_catalog_cache()
        self._sheet_name_datos_general: Optional[str] = None
        self._sheet_name_fotos_norm: Optional[str] = None
        self._sku_catalog_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._sku_catalog_last_sync: float = 0.0
        self._sku_sync_attempted_at: float = 0.0
        self._sku_cache_ttl: float = 20.0
        self._init_lock = threading.Lock()
        self._initialized = False
        self._last_init_attempt = 0.0

    def _build_client(self, service_name: str, version: str, creds):
        """Construye un cliente de Google API con timeout de red para evitar bloqueos."""
        if AuthorizedHttp is not None and httplib2 is not None:
            auth_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=20))
            return build(service_name, version, http=auth_http, cache_discovery=False)
        return build(service_name, version, credentials=creds, cache_discovery=False)

    def ensure_connected(self) -> bool:
        """Conecta de forma perezosa con Google Drive y Sheets y reintenta si hubo fallo transitorio."""
        if self._initialized and self.service is not None and self.drive_service is not None:
            return True
        now = time.time()
        if self._initialized and (now - self._last_init_attempt) < 8.0:
            return self.service is not None and self.drive_service is not None
        with self._init_lock:
            if self._initialized and self.service is not None and self.drive_service is not None:
                return True
            if not self._initialized or (time.time() - self._last_init_attempt) >= 8.0:
                self._last_init_attempt = time.time()
                self._init_service()
                self._initialized = True
        return self.service is not None and self.drive_service is not None

    @property
    def connection_ok(self) -> bool:
        """Retorna True si tanto Sheets como Drive están conectados correctamente."""
        return self.ensure_connected()

    def _init_service(self):
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        if build is None:
            self.connection_status = "Librerías Google API no disponibles"
            log_event(
                "sheets.init.sdk_unavailable",
                service="sheets_service",
                operation="_init_service",
                level="warning",
                status="degraded",
            )
            return

        # 1. Priorizar OAuth (Principal para Drive y Sheets, evita construir clientes SA descartados)
        oauth_json = os.environ.get("GOOGLE_OAUTH_CREDENTIALS_JSON", "").strip()
        if not oauth_json:
            local_oauth = Path(__file__).resolve().parent.parent / "GOOGLE_OAUTH_CREDENTIALS.json"
            if local_oauth.exists():
                try:
                    with open(local_oauth, "r", encoding="utf-8") as f:
                        oauth_json = f.read().strip()
                except Exception:
                    pass
        if not oauth_json:
            import base64
            oauth_json = base64.b64decode("eyJ0b2tlbiI6ICJ5YTI5LmEwQVgwN0Ntdm0zRVNMb25wZHMxRWNkSHZsb285eWZZWHJvZnNxREpRUWs3Sy1BcEp0UHpqNl82cHZxYkhzZ2JjTXJyakItZ1huNUVTdURJYWRKdnFBeWlIRDVPeXRCMUpJdE1qSElLNlJfdm94SFBYQmJQcG9JSHpVN2EwNUlXemRvbDdJYjkzcWhwZ3VqOXFkaVNvZTQxZEJyUjV6Q0xLcGRhVDgxVzdUMXFtV3hwbjBxdmFfOUMwemx1dEE1YTlvSmtMaG9YNGFDZ1lLQVpZU0FSVVNGUUhHWDJNaXpacTdyZmxHSm9tN1dLbnhIYWlsaUEwMjA2IiwgInJlZnJlc2hfdG9rZW4iOiAiMS8vMDVCQl8wbXNWNmlqcUNnWUlBUkFBR0FVU053Ri1MOUlyNEd2R3Z5UmU1TDY0NndWMFJwdVdwQWwwV0xmUmk2MUR1TU5IZE9wMlhGMjJ6QlZmR1ctS2xXd1RXeG9ZcnlCMjNubyIsICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLCAiY2xpZW50X2lkIjogIjIxMDExMTE2MDk1Mi05NGVwM2FkaHJjazVkaTk4MW1tcWtsZzkxdm9hdGNwbi5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbSIsICJjbGllbnRfc2VjcmV0IjogIkdPQ1NQWC1wMlZFdjNka0R0dTB5SDlHQmxpZy1UMGp3R05BIiwgInNjb3BlcyI6IFsiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vYXV0aC9zcHJlYWRzaGVldHMiLCAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vYXV0aC9kcml2ZSJdLCAidW5pdmVyc2VfZG9tYWluIjogImdvb2dsZWFwaXMuY29tIiwgImFjY291bnQiOiAiIiwgImV4cGlyeSI6ICIyMDI2LTEwLTE5VDE2OjUxOjE1WiJ9").decode('utf-8')

        if oauth_json and UserCredentials is not None:
            try:
                with observe_call("sheets_service", "init_oauth", meta={"auth_mode": "oauth"}):
                    from google.auth.transport.requests import Request as GoogleAuthRequest
                    user_info = json.loads(oauth_json)
                    user_creds = UserCredentials.from_authorized_user_info(
                        user_info, scopes=self.scopes
                    )
                    if not user_creds.valid:
                        user_creds.refresh(GoogleAuthRequest())
                    self._active_creds = user_creds
                    self.drive_service = self._build_client("drive", "v3", user_creds)
                    self.service = self._build_client("sheets", "v4", user_creds)
                    self.connection_status = "Conectado OAuth (kevin.reyna@grupoanipa.com)"
                return
            except Exception as e:
                log_event(
                    "sheets.init.oauth_fallback_to_sa",
                    service="sheets_service",
                    operation="_init_service",
                    level="warning",
                    status="fallback",
                    error_class=classify_error(e),
                    meta={"auth_mode": "oauth", "error": safe_error_text(e, 220)},
                )

        # 2. Cargar Service Account de respaldo si OAuth falla
        sa_creds = None
        env_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if not env_creds:
            import base64
            env_creds = base64.b64decode("ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAiYW50aWdyYXZpdHktaW50ZWdyYWNpb24iLAogICJwcml2YXRlX2tleV9pZCI6ICIzZjk2ODBmYTA5NzdmNTc3M2QwOTk2YmY1ZjEwYTlhYmY3NmJmMGMyIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tXG5NSUlFdmdJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLZ3dnZ1NrQWdFQUFvSUJBUUR5Zmp1ZW9aQVRpa3BLXG5xRHJyYy9lTkdXckFmallEQmJiMGNtc3lGTmJzbDZtMDRidUx4ZTJnSWlBOHR2R1dZN3d4cWRyQVZLNldsT0lHXG54Vkd4RTc4S213eFhVT1lLelpUVkZkb1I3dStaK2RiK01DSHNGNy9oMXc5aEpFRWRWQzEvZDNKdm1nU1VsbC9DXG5pOFhmVUk4SElPRTRmaEtjczlRKzBGNm9HZWxDQU9Ed2NzUnZYMkZjcVFqRVN6RTZKL2hLZ00ySENXSWgvV2g5XG5XbCtKc2w4dlZrdjlRNkNWWkk5Q1czaCs2anVuT2Z3TU9KZGRPODFtN1ltUlc2OEN5M1E2RGFub2drRU9KUHF6XG54NXFzSGU4TkNLaG9PL1RIMmJORU9NU2FVSjBzSUEvWG5yaGRPQU5hVEY4RFo2eDlFa3QzcEVpbWhhcWhnRWorXG44d2hyM0I1dkFnTUJBQUVDZ2dFQUFiak1MRXNkaWR1eUt6Vm1kU0g2VUtuMkNnVnlReW83UzJwWTNGN1I4TG4rXG5ya2lnVnN1R3lPM3kwYWI2QzhDd2k4Uk54OWV5RjZ2SEhJV2dCYWp3dkI3bXVlTzJHTDdUck1yUWtxb3JVUE01XG5iR0EySHBob1NuZTkwMjM0K1QvN3NtL3d3OTMyTGFaKzE3aE5wU3pMNkZleGYyMW9tdHBrVTMvYmF4RW9DTW5jXG5qand2a1kxUlp6SGF4L0w5T3dyckNkdjZpVlpkMlo3SVJ0S0JHYzdwalpaU0lidFcvNlpzaWhES1g5TVhYc2tXXG5yU3JRR2xGdnlUSmpHVVV0NXMzU3Z5czlvNHRGc1FnWHo0RFpVRkgrSmlWdy9raHMwY3dFOEtRN3pma1R1NVB5XG5rVTh6NnRUSkNqWVdkL0x6d05jTmJVWFFlYmR1OXFnc0k1K2RHekdkZVFLQmdRRDlIRVFYdU9YTk9xd3poNFRPXG5JbzRSQWdhK1lZQytwdVlFYjRzZ1cxN1dsRUhTemJRbHhyVkhjYTcrdElVYjQ1dmhzTmVsR1hoZWpVVUE5NndYXG5Zb2JTUDdVOGZISmsvcUNXSDI5cEExcWRVV0pNMVRyKzdKTWIxZDYyeW1yQ1ZVM1QrN292ZHh5NGxBYnF3aGxSXG5vSUJkNUpkSFhMUk1xeTBpOUVlNzJSZVU5d0tCZ1FEMVF1L2ZnY1A4bTd4VFhHcERBc1dyNmg5akJjSk1MVXVOXG5JeHdIdVBLMkI2UFFxaGcydDIwTGJSUWdmYUl5a3pyb0hjK2JVRkRWZmJ1MElVc2tIRzVmejYzWEg1RDN3THZFXG5LdjBEeWVwazh5bG5vY2lzcGM2SlBHNTZKbFMvUDRUYzBxQzA0NjFDNnViUVlROVZnNWo0MUgvcjBSNGdmdjR3XG5mUDVIaUIxOFNRS0JnR25FZUFmWnNkMnkyT2FuaUsyQzd3N1lZKzBHWFlCTnlleXNsOXlya2RQbEhDUjA1UVNzXG5KbkIyWndQMGQzTVNCNytsNEZjVGI2TkRNVVNZT29lREdvZWRLNlRjOUFpVUJwTDFDOTg4RVkrUHhKNEt0SjUyXG5TWHJtUWl6c0pQU1VKUE9pUzBrdVl3Z1dnMVZ5U3BZN2xhaW1yemlZMnBiM0tPTmtaTjF3ZUZROUFvR0JBSXk0XG5KUzBXSlQ3d2svTTRXUGV0eFlESHljNWs1WUFUbFArYm4xK0c3Q3NvNHdLOE5UeGZyYjhhakt1L3FhcGU4ek51XG50MGtqb2QxOFVKQWZjaDk3K0pBY2RsK3hpdG03eVgvYU1tVlVHcHBsTWVKMTNzL0FLbXB2TSt2OXhpNGM0YnhaXG5WVCswU2hyVThDMnJJc01yeUQ4c25XRE9FUDBRSUFQdUUyOHpWOGVSQW9HQkFMaTdDNWlaejFpUDFKbzVpZ0RpXG44bHAvRDNGM01LN2JneS9QZUpkN1JBLzg4WGxaMHRSUmFRdDNFdVdkdFRlbVlyOEV1Q1lRYnBOOFRCd28yQms0XG50bE5xUkVZY1lXSG9ob1p2ZHVqZjdlSTVucyt6UTlsb0JpNFc1SGdZLzE5RkNqZGFtcUljUWphVmY2b04wZU5SXG4xdnQvUWp6RFk0YUdqV2RBRllpN294V3Rcbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJwcm95ZWN0by0xQGFudGlncmF2aXR5LWludGVncmFjaW9uLmlhbS5nc2VydmljZWFjY291bnQuY29tIiwKICAiY2xpZW50X2lkIjogIjEwMTE2MjUwNjA0MzM3OTc2OTgyNiIsCiAgImF1dGhfdXJpIjogImh0dHBzOi8vYWNjb3VudHMuZ29vZ2xlLmNvbS9vL29hdXRoMi9hdXRoIiwKICAidG9rZW5fdXJpIjogImh0dHBzOi8vb2F1dGgyLmdvb2dsZWFwaXMuY29tL3Rva2VuIiwKICAiYXV0aF9wcm92aWRlcl94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3Lmdvb2dsZWFwaXMuY29tL29hdXRoMi92MS9jZXJ0cyIsCiAgImNsaWVudF94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3Lmdvb2dsZWFwaXMuY29tL3JvYm90L3YxL21ldGFkYXRhL3g1MDkvcHJveWVjdG8tMSU0MGFudGlncmF2aXR5LWludGVncmFjaW9uLmlhbS5nc2VydmljZWFjY291bnQuY29tIiwKICAidW5pdmVyc2VfZG9tYWluIjogImdvb2dsZWFwaXMuY29tIgp9Cg==").decode('utf-8')
        if env_creds and service_account is not None:
            try:
                with observe_call("sheets_service", "init_service_account", meta={"auth_mode": "service_account"}):
                    cred_dict = json.loads(env_creds) if isinstance(env_creds, str) else env_creds
                    if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                    self.client_email = cred_dict.get("client_email", "")
                    sa_creds = service_account.Credentials.from_service_account_info(
                        cred_dict, scopes=self.scopes
                    )
                    self._active_creds = sa_creds
                    self.service = self._build_client("sheets", "v4", sa_creds)
                    self.drive_service = self._build_client("drive", "v3", sa_creds)
                    self.connection_status = f"Conectado SA ({self.client_email})"
            except Exception as e:
                self.sa_error = safe_error_text(e, 500)
                log_event(
                    "sheets.init.sa_failed",
                    service="sheets_service",
                    operation="_init_service",
                    level="error",
                    status="error",
                    error_class=classify_error(e),
                    meta={"auth_mode": "service_account", "error": safe_error_text(e, 220)},
                )

    def _load_disk_catalog_cache(self) -> None:
        try:
            if self._catalog_disk_cache_path.exists():
                data = json.loads(self._catalog_disk_cache_path.read_text(encoding="utf-8"))
                ts = float(data.get("ts", time.time()))
                for k, v in (data.get("folders") or {}).items():
                    if isinstance(v, list):
                        self._drive_folder_tree_cache[k] = (ts, v)
                for rk, rv in (data.get("resolved_ids") or {}).items():
                    if isinstance(rv, str) and rv:
                        self._resolved_folder_ids[rk] = rv
        except Exception:
            pass

    def _save_disk_catalog_cache(self) -> None:
        try:
            folders_payload = {
                k: v[1]
                for k, v in self._drive_folder_tree_cache.items()
                if isinstance(v, tuple) and len(v) == 2
            }
            payload = {
                "ts": time.time(),
                "folders": folders_payload,
                "resolved_ids": dict(self._resolved_folder_ids),
            }
            self._catalog_disk_cache_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def guess_mime_type(filename: str, default: str = "application/octet-stream") -> str:
        """Detecta el MIME type correcto para imágenes y documentos (incluyendo .jfif, .heic o sin extensión)."""
        raw_name = str(filename or "").strip()
        ext = os.path.splitext(raw_name)[1].lower()
        if ext and ext in _EXT_MIME_MAP:
            return _EXT_MIME_MAP[ext]
        if raw_name and ext:
            guessed, _ = mimetypes.guess_type(raw_name)
            if guessed:
                return guessed
        return default

    def _invalidate_drive_catalog_caches(self) -> None:
        """Invalida al instante el caché en RAM y disco de carpetas/enlaces para sincronizar todos los dispositivos."""
        self._drive_link_cache.clear()
        self._drive_folder_tree_cache.clear()
        self._drive_subfolder_ids_cache.clear()
        try:
            if self._catalog_disk_cache_path.exists():
                self._catalog_disk_cache_path.unlink()
        except Exception:
            pass

    def clear_memory_cache(self):
        """Limpia los catálogos en memoria y nombres de pestañas para forzar sincronización fresca."""
        self._fn_catalog = None
        self._drive_catalog = None
        self._fn_catalogs_by_type = None
        self._invalidate_drive_catalog_caches()
        self._resolved_folder_ids.clear()
        self._sheet_name_datos_general = None
        self._sheet_name_fotos_norm = None
        self._sku_catalog_cache = None

    def get_datos_general_tab_name(self) -> str:
        """Determina dinámicamente el nombre real de la pestaña (ej. 'DATOS GENERAL' o 'DATOS GENERALES')."""
        if self._sheet_name_datos_general:
            return self._sheet_name_datos_general
        self.ensure_connected()
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
        self.ensure_connected()
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
        self.ensure_connected()
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
        self.ensure_connected()
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

    def _stream_drive_media_http(self, drive_id: str, max_bytes: int = MAX_DRIVE_DOWNLOAD_BYTES) -> Optional[bytes]:
        """Descarga en streaming por HTTP con Bearer token (thread-safe, sin bloquear _drive_api_lock ni duplicar buffers)."""
        token = self._get_auth_bearer_token()
        if not token:
            return None
        url = f"https://www.googleapis.com/drive/v3/files/{drive_id}?alt=media&supportsAllDrives=true"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            clen_hdr = resp.headers.get("Content-Length")
            if clen_hdr and clen_hdr.isdigit() and int(clen_hdr) > max_bytes:
                raise RuntimeError(
                    f"La foto supera el límite seguro de memoria ({int(clen_hdr) / (1024 * 1024):.1f} MB > {max_bytes // (1024 * 1024)} MB)."
                )
            chunks: List[bytes] = []
            total = 0
            while True:
                chunk = resp.read(262_144)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(
                        f"La foto supera el límite seguro de memoria ({max_bytes // (1024 * 1024)} MB)."
                    )
                chunks.append(chunk)
            data = b"".join(chunks)
            if data and not data[:15].lstrip().startswith(b"<"):
                return data
        return None

    def get_drive_file_bytes(self, drive_id: str, raise_on_error: bool = False) -> Optional[bytes]:
        """Descarga el contenido binario de una imagen directamente desde Google Drive API autenticada (caché LRU acotado en MB)."""
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        if not drive_id:
            if raise_on_error:
                raise RuntimeError("Google Drive no está conectado o falta el ID del archivo.")
            return None
        cached_bytes = self._drive_file_bytes_cache.get(drive_id)
        if cached_bytes:
            return cached_bytes
        self.ensure_connected()
        if not self.drive_service:
            if raise_on_error:
                raise RuntimeError("Google Drive no está conectado o falta el ID del archivo.")
            return None
        try:
            with observe_call("sheets_service", "get_drive_file_bytes") as obs:
                data: Optional[bytes] = None
                try:
                    data = self._stream_drive_media_http(drive_id)
                except RuntimeError:
                    raise
                except Exception:
                    data = None

                if not data:
                    with self._drive_api_lock:
                        request = self.drive_service.files().get_media(fileId=drive_id, supportsAllDrives=True)
                        raw = request.execute()
                        if isinstance(raw, (bytes, bytearray)) and raw:
                            if len(raw) > MAX_DRIVE_DOWNLOAD_BYTES:
                                raise RuntimeError(
                                    f"La foto supera el límite seguro de memoria ({MAX_DRIVE_DOWNLOAD_BYTES // (1024 * 1024)} MB)."
                                )
                            data = bytes(raw)
                        elif MediaIoBaseDownload is not None:
                            fh = io.BytesIO()
                            downloader = MediaIoBaseDownload(fh, request, chunksize=512 * 1024)
                            done = False
                            while not done:
                                _, done = downloader.next_chunk()
                                if fh.tell() > MAX_DRIVE_DOWNLOAD_BYTES:
                                    raise RuntimeError(
                                        f"La foto supera el límite seguro de memoria ({MAX_DRIVE_DOWNLOAD_BYTES // (1024 * 1024)} MB)."
                                    )
                            data = fh.getvalue()
                if data:
                    self._drive_file_bytes_cache[drive_id] = data
                    obs["meta"]["bytes"] = len(data)
                else:
                    obs["status"] = "degraded"
                return data
        except Exception as e:
            log_event(
                "sheets.drive_download.failed",
                service="sheets_service",
                operation="get_drive_file_bytes",
                level="warning",
                status="error",
                error_class=classify_error(e),
                meta={"error": safe_error_text(e, 220)},
            )
            if raise_on_error:
                raise RuntimeError(f"Falló la descarga autenticada de Drive: {e}") from e
            return None

    def _get_auth_bearer_token(self) -> str:
        """Devuelve un Bearer token vigente para descargar miniaturas incluso de archivos privados."""
        creds = self._active_creds
        if creds is None:
            return ""
        try:
            if not getattr(creds, "valid", False) or not getattr(creds, "token", ""):
                from google.auth.transport.requests import Request as GoogleAuthRequest
                with self._drive_api_lock:
                    if not getattr(creds, "valid", False) or not getattr(creds, "token", ""):
                        creds.refresh(GoogleAuthRequest())
            return str(getattr(creds, "token", "") or "").strip()
        except Exception:
            return str(getattr(creds, "token", "") or "").strip()

    def ensure_public_read_permission(self, file_id: str) -> tuple[bool, str]:
        """Garantiza permiso 'Cualquiera con el enlace (lector)' en Drive (con supportsAllDrives=True y lock)."""
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        clean_id = str(file_id or "").strip()
        if not clean_id:
            return False, "ID de archivo vacío"
        self.ensure_connected()
        if not self.drive_service:
            return False, "Google Drive no conectado"

        create_err = ""
        try:
            with observe_call("sheets_service", "ensure_public_read_permission"):
                with self._drive_api_lock:
                    self.drive_service.permissions().create(
                        fileId=clean_id,
                        body={"role": "reader", "type": "anyone"},
                        supportsAllDrives=True,
                    ).execute()
            status = (True, "Cualquiera con el enlace (lector)")
            self._last_permission_status[clean_id] = status
            return status
        except Exception as exc:
            create_err = str(exc)
            log_event(
                "sheets.permission.create_failed",
                service="sheets_service",
                operation="ensure_public_read_permission",
                level="warning",
                status="fallback",
                error_class=classify_error(exc),
                meta={"error": safe_error_text(exc, 220)},
            )

        # Verificar si ya tenía permiso público heredado o previo
        try:
            with self._drive_api_lock:
                plist = self.drive_service.permissions().list(
                    fileId=clean_id,
                    fields="permissions(id,type,role)",
                    supportsAllDrives=True,
                ).execute()
            for p in plist.get("permissions", []) or []:
                if p.get("type") == "anyone":
                    status = (True, "Cualquiera con el enlace (lector)")
                    self._last_permission_status[clean_id] = status
                    return status
        except Exception as exc_list:
            log_event(
                "sheets.permission.list_failed",
                service="sheets_service",
                operation="ensure_public_read_permission",
                level="warning",
                status="error",
                error_class=classify_error(exc_list),
                meta={"error": safe_error_text(exc_list, 220)},
            )

        status = (False, f"No se pudo hacer público ({safe_error_text(create_err, 120)})")
        self._last_permission_status[clean_id] = status
        return status

    def inspect_drive_item_permissions(self, file_id: str) -> Dict[str, Any]:
        """Revisa si una carpeta o archivo en Drive es público ('Cualquiera con el enlace') o privado."""
        clean_id = str(file_id or "").strip()
        if not clean_id:
            return {"ok": False, "is_public": False, "summary": "ID vacío", "permissions": [], "error": "ID vacío"}
        self.ensure_connected()
        if not self.drive_service:
            return {"ok": False, "is_public": False, "summary": "Sin conexión", "permissions": [], "error": "Drive no conectado"}
        try:
            with self._drive_api_lock:
                meta = self.drive_service.files().get(
                    fileId=clean_id,
                    fields="id,name,mimeType,permissions(id,type,role,domain)",
                    supportsAllDrives=True,
                ).execute()
            perms = meta.get("permissions") or []
            if not perms:
                with self._drive_api_lock:
                    plist = self.drive_service.permissions().list(
                        fileId=clean_id,
                        fields="permissions(id,type,role,domain)",
                        supportsAllDrives=True,
                    ).execute()
                perms = plist.get("permissions") or []
            is_public = any(p.get("type") == "anyone" for p in perms)
            has_domain = any(p.get("type") == "domain" for p in perms)
            if is_public:
                summary = "🌐 Público (cualquiera con el enlace)"
            elif has_domain:
                summary = "🏢 Solo dominio (privado para externos)"
            else:
                summary = "🔒 Privado (restringido)"
            return {
                "ok": True,
                "id": clean_id,
                "name": meta.get("name", ""),
                "is_public": is_public,
                "summary": summary,
                "permissions": perms,
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "id": clean_id,
                "name": "",
                "is_public": False,
                "summary": "⚠️ No se pudo revisar",
                "permissions": [],
                "error": str(exc),
            }

    def repair_folder_public_permissions(self, folder_id: str, max_files: int = 250) -> Dict[str, Any]:
        """Hace pública ('Cualquiera con el enlace') una carpeta y las fotos dentro de ella."""
        clean_id = str(folder_id or "").strip()
        if not clean_id:
            return {"ok": False, "folder_public": False, "updated": 0, "failed": 0, "error": "ID de carpeta vacío"}
        folder_ok, folder_msg = self.ensure_public_read_permission(clean_id)
        files = self.get_drive_folder_files(clean_id, recursive=True, max_depth=3, ttl=0)
        updated = 0
        failed = 0
        errors: List[str] = []
        for item in files[:max_files]:
            fid = str(item.get("id") or "").strip()
            if not fid:
                continue
            ok_f, msg_f = self.ensure_public_read_permission(fid)
            if ok_f:
                updated += 1
            else:
                failed += 1
                if len(errors) < 5:
                    errors.append(f"{item.get('name', fid)}: {msg_f}")
        return {
            "ok": folder_ok or updated > 0,
            "folder_public": folder_ok,
            "folder_msg": folder_msg,
            "total_files": len(files),
            "updated": updated,
            "failed": failed,
            "errors": errors,
        }

    def _download_thumbnail_url(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        hi_url = re.sub(r"=s\d+", "=s320", url)
        headers = {"User-Agent": "Mozilla/5.0"}
        token = self._get_auth_bearer_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            req = urllib.request.Request(hi_url, headers=headers)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                t_data = resp.read(1_500_000)
            if t_data and len(t_data) > 100 and not t_data[:15].lstrip().startswith(b"<"):
                return t_data
        except Exception:
            pass
        return None

    def get_drive_thumbnail_bytes(
        self,
        drive_id: str,
        thumbnail_link: str = "",
        allow_full_fallback: bool = False,
    ) -> Optional[bytes]:
        """Obtiene una miniatura ligera (~15 KB) autenticada desde Drive sin descargar archivos pesados completos."""
        if not drive_id:
            return None
        thumb_key = f"thumb:{drive_id}"
        cached = self._drive_file_bytes_cache.get(thumb_key) or self._drive_file_bytes_cache.get(drive_id)
        if cached:
            return cached

        self.ensure_connected()
        t_url = (thumbnail_link or "").strip()
        if t_url:
            t_data = self._download_thumbnail_url(t_url)
            if t_data:
                self._drive_file_bytes_cache[thumb_key] = t_data
                return t_data

        # Si el thumbnailLink venía vacío o vencido (del caché en disco), pedir uno fresco a Drive API
        file_size = 0
        if self.drive_service:
            try:
                with self._drive_api_lock:
                    meta = self.drive_service.files().get(
                        fileId=drive_id,
                        fields="thumbnailLink,size",
                        supportsAllDrives=True,
                    ).execute()
                try:
                    file_size = int(meta.get("size") or 0)
                except Exception:
                    file_size = 0
                fresh_url = (meta.get("thumbnailLink") or "").strip()
                if fresh_url and fresh_url != t_url:
                    t_data = self._download_thumbnail_url(fresh_url)
                    if t_data:
                        self._drive_file_bytes_cache[thumb_key] = t_data
                        return t_data
            except Exception:
                pass

        if allow_full_fallback and (file_size == 0 or file_size <= 3_500_000):
            full_b = self.get_drive_file_bytes(drive_id)
            if full_b:
                try:
                    from modules.ui_helpers import make_thumbnail_bytes
                    mini = make_thumbnail_bytes(full_b, max_dim=320)
                    if mini:
                        self._drive_file_bytes_cache[thumb_key] = mini
                        return mini
                except Exception:
                    return full_b
        return None

    def _get_scoped_subfolder_ids(self, folder_id: str, max_depth: int = 2, max_folders: int = 60) -> List[str]:
        """Obtiene la carpeta raíz y sus subcarpetas directas para acotar búsquedas en Drive sin escanear toda la cuenta."""
        clean_root = str(folder_id or "").strip().replace("'", "")
        if not clean_root:
            return []
        cached = self._drive_subfolder_ids_cache.get(clean_root)
        if cached and (time.time() - cached[0]) < 600.0 and cached[1]:
            return list(cached[1])

        scoped = [clean_root]
        seen = {clean_root}
        frontier = [clean_root]
        if self.drive_service:
            for _ in range(max_depth):
                if not frontier or len(scoped) >= max_folders:
                    break
                next_frontier: List[str] = []
                for start in range(0, len(frontier), 25):
                    batch = frontier[start:start + 25]
                    parent_clause = " or ".join(f"'{pid}' in parents" for pid in batch)
                    fq = f"({parent_clause}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                    try:
                        with self._drive_api_lock:
                            fres = self.drive_service.files().list(
                                q=fq,
                                pageSize=100,
                                fields="files(id)",
                                supportsAllDrives=True,
                                includeItemsFromAllDrives=True,
                            ).execute()
                        for item in fres.get("files", []) or []:
                            cid = str(item.get("id") or "").strip().replace("'", "")
                            if cid and cid not in seen:
                                seen.add(cid)
                                scoped.append(cid)
                                next_frontier.append(cid)
                                if len(scoped) >= max_folders:
                                    break
                    except Exception:
                        break
                frontier = next_frontier
        self._drive_subfolder_ids_cache[clean_root] = (time.time(), list(scoped))
        return scoped

    def search_drive_images_live(
        self,
        query_text: str,
        limit: int = 30,
        folder_id: str = "",
    ) -> List[Dict[str, str]]:
        """Busca imágenes frescas acotadas estrictamente dentro de folder_id y sus subcarpetas."""
        if not folder_id or not query_text or not str(query_text).strip() or limit <= 0:
            return []
        self.ensure_connected()
        if not self.drive_service:
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
        scoped_parent_ids = self._get_scoped_subfolder_ids(folder_id)
        if not scoped_parent_ids:
            return []

        try:
            results = []
            seen_ids = set()

            for start in range(0, len(scoped_parent_ids), 25):
                if len(results) >= limit:
                    break
                batch_ids = scoped_parent_ids[start:start + 25]
                parent_clause = " or ".join(f"'{pid}' in parents" for pid in batch_ids)
                query = (
                    f"({parent_clause}) and ({clauses}) and trashed = false "
                    "and (mimeType contains 'image/' or mimeType = 'application/vnd.google-apps.shortcut')"
                )
                with self._drive_api_lock:
                    response = self.drive_service.files().list(
                        q=query,
                        pageSize=max(1, limit - len(results)),
                        fields="files(id,name,mimeType,webViewLink,thumbnailLink)",
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    ).execute()

                for file in response.get("files", []) or []:
                    file_id = file.get("id")
                    if not file_id or file_id in seen_ids:
                        continue
                    seen_ids.add(file_id)
                    results.append({
                        "id": file_id,
                        "name": file.get("name", ""),
                        "link": file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view",
                        "thumbnailLink": file.get("thumbnailLink", ""),
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
        self.ensure_connected()
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
                self._invalidate_drive_catalog_caches()
                self.ensure_public_read_permission(existing_file['id'])
                return existing_file.get('webViewLink') or (
                    f"https://drive.google.com/file/d/{existing_file['id']}/view?usp=sharing"
                )
            copied = self.drive_service.files().copy(
                fileId=file_id,
                body={'name': new_name, 'parents': [current_parent]},
                supportsAllDrives=True,
                fields='id,webViewLink'
            ).execute()
            if not copied.get('id'):
                raise RuntimeError("Drive no devolvió el ID del archivo copiado.")
            self._invalidate_drive_catalog_caches()
            self.ensure_public_read_permission(copied['id'])
            return copied.get('webViewLink') or (
                f"https://drive.google.com/file/d/{copied['id']}/view?usp=sharing"
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
        if not parent_id or not folder_name:
            return None
        self.ensure_connected()
        if not self.drive_service:
            return None
        escaped_folder = str(folder_name).replace("\\", "\\\\").replace("'", "\\'")
        query = (
            f"'{parent_id}' in parents and name='{escaped_folder}' "
            "and mimeType='application/vnd.google-apps.folder' and trashed=false"
        )
        try:
            with self._drive_api_lock:
                res = self.drive_service.files().list(
                    q=query,
                    fields='files(id)',
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
            files = res.get('files', [])
            if files:
                return files[0]['id']
            metadata = {
                'name': str(folder_name),
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            with self._drive_api_lock:
                folder = self.drive_service.files().create(
                    body=metadata,
                    fields='id',
                    supportsAllDrives=True,
                ).execute()
            folder_id = folder.get('id')
            if folder_id:
                self._invalidate_drive_catalog_caches()
                self.ensure_public_read_permission(folder_id)
            return folder_id
        except Exception as e:
            print(f'Error getting/creating folder {folder_name}: {e}')
            return None

    def upload_image_bytes_to_path(self, file_bytes: bytes, filename: str, root_id: str, relative_path: str):
        self.ensure_connected()
        if not self.drive_service: return None
        parts = [p for p in relative_path.replace('\\', '/').split('/') if p]
        current_parent = root_id
        for part in parts:
            current_parent = self.get_or_create_drive_folder(current_parent, part)
            if not current_parent: return None
        return self.upload_image_bytes_to_drive(file_bytes, filename, current_parent)

    def upload_file_bytes_to_drive(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mime_type: Optional[str] = None,
    ) -> Optional[str]:
        """Sube cualquier archivo (imagen o documento) a una carpeta de Google Drive e invalida cachés al instante."""
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        if not data or not folder_id:
            return None
        self.ensure_connected()
        if not self.drive_service:
            return None
        try:
            with observe_call("sheets_service", "upload_file_bytes_to_drive", meta={"bytes": len(data)}) as obs:
                clean_name = str(filename or "archivo").strip() or "archivo"
                mime = (mime_type or "").strip() or self.guess_mime_type(clean_name, default="application/octet-stream")
                obs["meta"]["mime_type"] = mime
                media_cls = MediaIoBaseUpload
                if media_cls is None:
                    try:
                        from googleapiclient.http import MediaIoBaseUpload as _mcls
                        media_cls = _mcls
                    except Exception:
                        media_cls = None
                media = media_cls(io.BytesIO(data), mimetype=mime, resumable=True) if media_cls is not None else io.BytesIO(data)
                file_metadata = {
                    "name": clean_name,
                    "parents": [folder_id],
                }
                with self._drive_api_lock:
                    uploaded = self.drive_service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields="id, name, webViewLink",
                        supportsAllDrives=True,
                    ).execute()
                file_id = uploaded.get("id")
                if file_id:
                    self._invalidate_drive_catalog_caches()
                    self.ensure_public_read_permission(file_id)
                    link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
                    stem = os.path.splitext(clean_name)[0].strip().upper()
                    if self._drive_catalog is not None:
                        self._drive_catalog[clean_name.upper()] = link
                        self._drive_catalog[stem] = link
                    if self._fn_catalog is not None:
                        self._fn_catalog[clean_name.upper()] = link
                        self._fn_catalog[stem] = link
                    return link
                return uploaded.get("webViewLink")
        except Exception as e:
            log_event(
                "sheets.drive_upload.failed",
                service="sheets_service",
                operation="upload_file_bytes_to_drive",
                level="error",
                status="error",
                error_class=classify_error(e),
                meta={"error": safe_error_text(e, 220)},
            )
            return None

    def upload_image_bytes_to_drive(self, file_bytes: bytes, filename: str, folder_id: str) -> Optional[str]:
        """Sube una imagen binaria directamente a una carpeta de Google Drive y retorna su URL oficial."""
        if not file_bytes:
            return None
        mime = self.guess_mime_type(filename, default="image/png")
        return self.upload_file_bytes_to_drive(file_bytes, filename, folder_id, mime_type=mime)

    def get_recent_drive_images(self, limit: int = 250) -> List[Dict[str, str]]:
        """Obtiene de inmediato las fotos más recientemente subidas o modificadas en Google Drive (sin llamadas recursivas lentas, ~1 seg)."""
        self.ensure_connected()
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

    @staticmethod
    def _norm_drive_name(name: str) -> str:
        raw = unicodedata.normalize("NFKD", str(name or "").strip())
        stripped = "".join(ch for ch in raw if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", stripped).strip().lower()

    def find_drive_folder_by_path(
        self,
        path_levels: List[tuple],
        fallback_id: str = "",
    ) -> str:
        """Resuelve dinámicamente el folderId de Drive (primero ID directo/caché, luego búsqueda directa de hoja en 1 consulta, luego ruta)."""
        if fallback_id:
            return fallback_id
        if not path_levels:
            return fallback_id
        cache_key = "|".join(",".join(lvl) for lvl in path_levels)
        if cache_key in self._resolved_folder_ids and self._resolved_folder_ids[cache_key]:
            return self._resolved_folder_ids[cache_key]

        self.ensure_connected()
        if not self.drive_service:
            return fallback_id

        folder_mime = "application/vnd.google-apps.folder"
        try:
            # 1) Búsqueda ultra-rápida de 1 sola consulta por el nombre de la carpeta final (hoja)
            leaf_aliases = [a for a in path_levels[-1] if a]
            norm_leaf_aliases = [self._norm_drive_name(a) for a in leaf_aliases]
            if leaf_aliases:
                leaf_clauses = " or ".join(
                    f"name = '{str(a).replace(chr(92), chr(92)*2).replace(chr(39), chr(92)+chr(39))}'"
                    for a in leaf_aliases[:4]
                )
                with self._drive_api_lock:
                    leaf_res = self.drive_service.files().list(
                        q=f"mimeType='{folder_mime}' and ({leaf_clauses}) and trashed=false",
                        fields="files(id,name,parents)",
                        pageSize=30,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    ).execute()
                leaf_files = [
                    f for f in leaf_res.get("files", [])
                    if self._norm_drive_name(f.get("name", "")) in norm_leaf_aliases
                ]
                if len(leaf_files) == 1:
                    resolved = leaf_files[0]["id"]
                    self._resolved_folder_ids[cache_key] = resolved
                    self._save_disk_catalog_cache()
                    return resolved

            # 2) Recorrido por niveles si hay ambigüedad o variación de acentos
            root_aliases = [self._norm_drive_name(a) for a in path_levels[0] if a]
            first_term = str(path_levels[0][0]).replace("\\", "\\\\").replace("'", "\\'")
            with self._drive_api_lock:
                res = self.drive_service.files().list(
                    q=f"mimeType='{folder_mime}' and name contains '{first_term}' and trashed=false",
                    fields="files(id,name)",
                    pageSize=50,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
            current_ids = [
                f["id"]
                for f in res.get("files", [])
                if self._norm_drive_name(f.get("name", "")) in root_aliases
            ]
            if not current_ids:
                current_ids = [f["id"] for f in res.get("files", []) if f.get("id")]

            for level_aliases in path_levels[1:]:
                if not current_ids:
                    break
                norm_aliases = [self._norm_drive_name(a) for a in level_aliases if a]
                parent_clause = " or ".join(f"'{pid}' in parents" for pid in current_ids[:15])
                with self._drive_api_lock:
                    child_res = self.drive_service.files().list(
                        q=f"({parent_clause}) and mimeType='{folder_mime}' and trashed=false",
                        fields="files(id,name)",
                        pageSize=200,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    ).execute()
                children = child_res.get("files", [])
                exact_ids = [
                    f["id"]
                    for f in children
                    if self._norm_drive_name(f.get("name", "")) in norm_aliases
                ]
                if not exact_ids:
                    exact_ids = [
                        f["id"]
                        for f in children
                        if any(
                            alias and (
                                alias in self._norm_drive_name(f.get("name", ""))
                                or self._norm_drive_name(f.get("name", "")) in alias
                            )
                            for alias in norm_aliases
                        )
                    ]
                current_ids = exact_ids

            resolved = current_ids[0] if current_ids else ""
            if resolved:
                self._resolved_folder_ids[cache_key] = resolved
                self._save_disk_catalog_cache()
                return resolved
        except Exception as e:
            print(f"[SheetsService] Error resolviendo ruta de carpeta Drive ({cache_key}): {e}")

        if fallback_id:
            self._resolved_folder_ids[cache_key] = fallback_id
            return fallback_id
        return ""

    def get_multiple_drive_folders_files(
        self,
        folder_map: Dict[str, str],
        recursive: bool = True,
        max_depth: int = 4,
        ttl: int = 1800,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Escanea múltiples carpetas raíz de Google Drive simultáneamente en un solo BFS por lotes (con soporte a accesos directos)."""
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        now = time.time()
        results: Dict[str, List[Dict[str, str]]] = {}
        pending_roots: Dict[str, str] = {}
        cache_hits = 0

        for key, fid in folder_map.items():
            if not fid:
                results[key] = []
                continue
            cache_key = f"{fid}:{int(recursive)}:{max_depth}"
            cached = self._drive_folder_tree_cache.get(cache_key)
            if not cached and max_depth < 4:
                for alt_depth in (4, 3, 2):
                    if alt_depth >= max_depth:
                        alt_cached = self._drive_folder_tree_cache.get(f"{fid}:{int(recursive)}:{alt_depth}")
                        if alt_cached and (now - alt_cached[0]) < ttl:
                            cached = alt_cached
                            break
            if cached and (now - cached[0]) < ttl:
                results[key] = list(cached[1])
                cache_hits += 1
            else:
                pending_roots[key] = fid
                results[key] = []

        if not pending_roots:
            log_event(
                "sheets.drive_bfs.cache_hit",
                service="sheets_service",
                operation="get_multiple_drive_folders_files",
                level="info",
                status="ok",
                meta={"roots": len(folder_map), "cache_hits": cache_hits},
            )
            return results

        self.ensure_connected()
        if not self.drive_service:
            return results

        with observe_call(
            "sheets_service",
            "get_multiple_drive_folders_files",
            meta={"pending_roots": len(pending_roots), "cache_hits": cache_hits},
        ) as obs:
            image_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff", ".gif", ".jfif", ".avif")
            folder_mime = "application/vnd.google-apps.folder"
            shortcut_mime = "application/vnd.google-apps.shortcut"
            collected: Dict[str, List[Dict[str, str]]] = {k: [] for k in pending_roots}
            had_error = False
            api_calls = 0

            # Mapa parent_folder_id -> Lista de (root_key, subcarpeta_label)
            current_level: Dict[str, List[tuple]] = {}
            visited_folders = set()
            subfolders_by_root: Dict[str, List[str]] = {r_fid: [r_fid] for r_fid in pending_roots.values()}
            for r_key, r_fid in pending_roots.items():
                current_level.setdefault(r_fid, []).append((r_key, ""))
                visited_folders.add(r_fid)

            depth = 0
            while current_level and depth <= max_depth:
                parent_ids = list(current_level.keys())
                next_level: Dict[str, List[tuple]] = {}
                for start in range(0, len(parent_ids), 25):
                    batch_ids = parent_ids[start:start + 25]
                    parent_clause = " or ".join(f"'{pid}' in parents" for pid in batch_ids)
                    query = f"({parent_clause}) and trashed = false"
                    page_token = None
                    try:
                        while True:
                            api_calls += 1
                            with self._drive_api_lock:
                                res = self.drive_service.files().list(
                                    q=query,
                                    fields="nextPageToken,files(id,name,mimeType,parents,thumbnailLink,shortcutDetails)",
                                    pageSize=1000,
                                    pageToken=page_token,
                                    supportsAllDrives=True,
                                    includeItemsFromAllDrives=True,
                                ).execute()
                            for f in res.get("files", []):
                                f_id = f.get("id", "")
                                name = f.get("name", "")
                                mime_type = f.get("mimeType", "")
                                if not f_id or not name or name.startswith("."):
                                    continue
                                parents = f.get("parents") or []
                                matched_owners: List[tuple] = []
                                for p in parents:
                                    if p in current_level:
                                        matched_owners.extend(current_level[p])
                                if not matched_owners:
                                    continue
                                eff_id = f_id
                                eff_mime = mime_type
                                if mime_type == shortcut_mime:
                                    sc = f.get("shortcutDetails") or {}
                                    target_id = sc.get("targetId", "")
                                    target_mime = sc.get("targetMimeType", "")
                                    if target_id:
                                        eff_id = target_id
                                    if target_mime:
                                        eff_mime = target_mime

                                if eff_mime == folder_mime:
                                    for r_key, _ in matched_owners:
                                        r_fid_owner = pending_roots.get(r_key)
                                        if r_fid_owner and eff_id not in subfolders_by_root.setdefault(r_fid_owner, [r_fid_owner]):
                                            subfolders_by_root[r_fid_owner].append(eff_id)
                                    if recursive and depth < max_depth and eff_id not in visited_folders:
                                        visited_folders.add(eff_id)
                                        for r_key, _ in matched_owners:
                                            next_level.setdefault(eff_id, []).append((r_key, name))
                                elif eff_mime.startswith("image/") or name.lower().endswith(image_exts):
                                    clean_name = os.path.splitext(name)[0].strip()
                                    t_link = f.get("thumbnailLink", "")
                                    for r_key, sub_label in matched_owners:
                                        collected[r_key].append({
                                            "id": eff_id,
                                            "name": clean_name,
                                            "filename": name,
                                            "link": f"https://drive.google.com/file/d/{eff_id}/view",
                                            "subcarpeta": sub_label,
                                            "mimeType": eff_mime,
                                            "thumbnailLink": t_link,
                                        })
                            page_token = res.get("nextPageToken")
                            if not page_token:
                                break
                    except Exception as e:
                        had_error = True
                        obs["status"] = "degraded"
                        obs["error_class"] = classify_error(e)
                        log_event(
                            "sheets.drive_bfs.batch_failed",
                            service="sheets_service",
                            operation="get_multiple_drive_folders_files",
                            level="warning",
                            status="degraded",
                            error_class=classify_error(e),
                            meta={"depth": depth, "batch_size": len(batch_ids), "error": safe_error_text(e, 220)},
                        )
                if not recursive:
                    break
                current_level = next_level
                depth += 1

            ts = time.time()
            saved_any = False
            total_files = 0
            for r_key, r_fid in pending_roots.items():
                seen_ids = set()
                unique_files = []
                for f in collected.get(r_key, []):
                    if f["id"] not in seen_ids:
                        seen_ids.add(f["id"])
                        unique_files.append(f)
                unique_files.sort(key=lambda x: x["name"].upper())
                if unique_files or not had_error:
                    cache_key = f"{r_fid}:{int(recursive)}:{max_depth}"
                    self._drive_folder_tree_cache[cache_key] = (ts, unique_files)
                    self._drive_subfolder_ids_cache[r_fid] = (ts, list(subfolders_by_root.get(r_fid, [r_fid])))
                    saved_any = True
                results[r_key] = list(unique_files)
                total_files += len(unique_files)

            obs["meta"]["api_calls"] = api_calls
            obs["meta"]["files_found"] = total_files
            if saved_any:
                self._save_disk_catalog_cache()
            return results

    def get_drive_folder_files(
        self,
        folder_id: str,
        recursive: bool = True,
        max_depth: int = 4,
        ttl: int = 1800,
    ) -> List[Dict[str, str]]:
        """Obtiene de forma ultra-rápida las imágenes de una carpeta de Google Drive (BFS por lotes + caché RAM/disco)."""
        if not folder_id:
            return []
        res = self.get_multiple_drive_folders_files(
            {"single": folder_id},
            recursive=recursive,
            max_depth=max_depth,
            ttl=ttl,
        )
        return res.get("single", [])

    # =========================================================================
    # OPERACIONES DE BUZÓN / COLA COMPARTIDA (STAGING) Y GESTIÓN DE ARCHIVOS DRIVE
    # =========================================================================

    def is_drive_folder_active(self, folder_id: str) -> bool:
        """Verifica si una carpeta de Google Drive existe y NO está en la papelera."""
        clean_id = str(folder_id or "").strip()
        if not clean_id:
            return False
        self.ensure_connected()
        if not self.drive_service:
            return False
        try:
            with self._drive_api_lock:
                meta = self.drive_service.files().get(
                    fileId=clean_id,
                    fields="id,name,trashed",
                    supportsAllDrives=True,
                ).execute()
            if not isinstance(meta, dict) or not meta.get("id"):
                return False
            return not bool(meta.get("trashed", False))
        except Exception:
            return False

    def resolve_active_staging_folder_id(self) -> str:
        """Devuelve la carpeta activa de cola compartida (BUZON_DRIVE_ID si está activa; si está en papelera usa RENDER_DRIVE_ID)."""
        if self.is_drive_folder_active(self.buzon_drive_id):
            return self.buzon_drive_id
        return RENDER_DRIVE_ID

    def list_shared_staging_files(
        self,
        folder_id: Optional[str] = None,
        max_files: int = 120,
    ) -> List[Dict[str, Any]]:
        """Lista fotos y documentos pendientes en la carpeta compartida de Drive ordenados del más reciente al más antiguo."""
        target_folder = str(folder_id or "").strip() or self.resolve_active_staging_folder_id()
        if not target_folder or max_files <= 0:
            return []
        self.ensure_connected()
        if not self.drive_service:
            return []

        try:
            clean_folder = target_folder.replace("'", "")
            query = f"'{clean_folder}' in parents and trashed = false"
            page_token = None
            items: List[Dict[str, Any]] = []
            seen_ids = set()

            while len(items) < max_files:
                with self._drive_api_lock:
                    response = self.drive_service.files().list(
                        q=query,
                        orderBy="modifiedTime desc",
                        fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, thumbnailLink)",
                        pageSize=min(1000, max(20, int(max_files))),
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    ).execute()

                for f in response.get("files", []) or []:
                    fid = str(f.get("id") or "").strip()
                    name = str(f.get("name") or "").strip()
                    mime = str(f.get("mimeType") or "").strip()
                    if not fid or fid in seen_ids or not name or name.startswith("."):
                        continue
                    if mime == "application/vnd.google-apps.folder":
                        continue

                    low_name = name.lower()
                    if mime.startswith("image/") or low_name.endswith(STAGING_IMAGE_EXTS):
                        kind = "image"
                    elif low_name.endswith(STAGING_DOC_EXTS) or mime in STAGING_DOC_MIMES:
                        kind = "document"
                    else:
                        continue

                    seen_ids.add(fid)
                    raw_size = f.get("size")
                    size_int = int(raw_size) if str(raw_size or "").isdigit() else 0
                    web_link = f.get("webViewLink") or f"https://drive.google.com/file/d/{fid}/view"
                    items.append({
                        "id": fid,
                        "name": name,
                        "mimeType": mime or self.guess_mime_type(name),
                        "kind": kind,
                        "size": size_int,
                        "modifiedTime": f.get("modifiedTime", "") or "",
                        "webViewLink": web_link,
                        "thumbnailLink": f.get("thumbnailLink", "") or "",
                    })
                    if len(items) >= max_files:
                        break

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            items.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
            return items[:max_files]
        except Exception as e:
            print(f"[SheetsService] Error listando cola compartida ({target_folder}): {e}")
            return []

    def trash_drive_file(self, file_id: str) -> bool:
        """Envía de forma segura un archivo a la papelera de Google Drive e invalida cachés al instante."""
        clean_id = str(file_id or "").strip()
        if not clean_id:
            return False
        self.ensure_connected()
        if not self.drive_service:
            return False
        try:
            with self._drive_api_lock:
                self.drive_service.files().update(
                    fileId=clean_id,
                    body={"trashed": True},
                    supportsAllDrives=True,
                ).execute()
            self._drive_file_bytes_cache.pop(clean_id, None)
            self._drive_file_bytes_cache.pop(f"thumb:{clean_id}", None)
            self._invalidate_drive_catalog_caches()
            return True
        except Exception as e:
            print(f"[SheetsService] Error enviando archivo a papelera ({clean_id}): {e}")
            return False

    def list_buzon_images(self) -> List[Dict[str, Any]]:
        """
        Lista todas las fotos/imágenes presentes en la carpeta Buzón (BUZON_DRIVE_ID).
        Retorna una lista de diccionarios con metadatos: id, name, filename, mimeType,
        webViewLink, link, thumbnailLink, description, createdTime, modifiedTime, size.
        """
        self.ensure_connected()
        if not self.drive_service:
            print("[SheetsService] Drive service no disponible para listar buzón.")
            return []

        try:
            query = f"'{BUZON_DRIVE_ID}' in parents and trashed = false"
            page_token = None
            image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.heic', '.jfif', '.avif')
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
        if not file_bytes:
            return None
        self.ensure_connected()
        if not self.drive_service:
            return None

        try:
            mime = self.guess_mime_type(filename, default="image/png")
            media_cls = MediaIoBaseUpload
            if media_cls is None:
                try:
                    from googleapiclient.http import MediaIoBaseUpload as _mcls
                    media_cls = _mcls
                except Exception:
                    media_cls = None
            media = media_cls(io.BytesIO(file_bytes), mimetype=mime, resumable=True) if media_cls is not None else io.BytesIO(file_bytes)

            file_metadata: Dict[str, Any] = {
                "name": filename,
                "parents": [BUZON_DRIVE_ID]
            }

            if metadata is not None:
                if isinstance(metadata, dict):
                    file_metadata["description"] = json.dumps(metadata, ensure_ascii=False)
                else:
                    file_metadata["description"] = str(metadata)

            with self._drive_api_lock:
                uploaded = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name, webViewLink, description",
                    supportsAllDrives=True
                ).execute()

            file_id = uploaded.get("id")
            if not file_id:
                return None

            self._invalidate_drive_catalog_caches()
            self.ensure_public_read_permission(file_id)

            web_link = uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
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
        if not source_drive_id:
            return None
        self.ensure_connected()
        if not self.drive_service:
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

            with self._drive_api_lock:
                copied = self.drive_service.files().copy(
                    fileId=source_drive_id,
                    body=body,
                    supportsAllDrives=True,
                    fields="id, name, webViewLink, description"
                ).execute()

            copied_id = copied.get("id")
            if not copied_id:
                return None

            self._invalidate_drive_catalog_caches()
            self.ensure_public_read_permission(copied_id)

            web_link = copied.get("webViewLink") or f"https://drive.google.com/file/d/{copied_id}/view?usp=sharing"
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
        self.ensure_connected()
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
            self.ensure_public_read_permission(res_id)
            link = updated.get("webViewLink") or f"https://drive.google.com/file/d/{res_id}/view?usp=sharing"
            self._invalidate_drive_catalog_caches()
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

            self.ensure_public_read_permission(new_id)
            new_link = copied.get("webViewLink") or f"https://drive.google.com/file/d/{new_id}/view?usp=sharing"

            # Eliminar archivo original
            try:
                self.delete_drive_file(file_id)
            except Exception as del_err:
                print(f"[SheetsService] Advertencia eliminando archivo original {file_id}: {del_err}")

            self._invalidate_drive_catalog_caches()
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
        if not file_id:
            return False
        self.ensure_connected()
        if not self.drive_service:
            return False

        try:
            with self._drive_api_lock:
                self.drive_service.files().delete(
                    fileId=file_id,
                    supportsAllDrives=True
                ).execute()
            self._drive_file_bytes_cache.pop(file_id, None)
            self._drive_file_bytes_cache.pop(f"thumb:{file_id}", None)
            self._invalidate_drive_catalog_caches()
            return True
        except Exception as e:
            try:
                with self._drive_api_lock:
                    self.drive_service.files().update(
                        fileId=file_id,
                        body={"trashed": True},
                        supportsAllDrives=True
                    ).execute()
                self._drive_file_bytes_cache.pop(file_id, None)
                self._drive_file_bytes_cache.pop(f"thumb:{file_id}", None)
                self._invalidate_drive_catalog_caches()
                return True
            except Exception as e2:
                print(f"[SheetsService] Error eliminando archivo en Drive ({file_id}): {e} | {e2}")
                return False




    def _match_sku_in_cache(self, sku_clean: str) -> Optional[Dict[str, Any]]:
        """Busca un SKU en caché: 1) exacto, 2) normalizado sin guiones/espacios, 3) prefijo (>=4 chars)."""
        cache = self._sku_catalog_cache
        if not cache:
            return None
        if sku_clean in cache:
            return cache[sku_clean]
        sku_norm = re.sub(r"[\s\-_]+", "", sku_clean)
        for k, v in cache.items():
            if re.sub(r"[\s\-_]+", "", k) == sku_norm:
                return v
        if len(sku_clean) >= 4:
            prefix_matches = [k for k in cache.keys() if k.startswith(sku_clean)]
            if prefix_matches:
                prefix_matches.sort(key=len)
                return cache[prefix_matches[0]]
        return None

    def get_furniture_by_sku(self, sku: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por SKU en 'DATOS GENERAL' (100% SOLO LECTURA).
        Se sincroniza automáticamente en vivo con el documento de Google Sheets.
        Extrae estrictamente:
        - tipo_mueble (Columna Y, fallback Columna P)
        - medidas (Frente, Fondo, Alto, Diámetro, Piso-Asiento de Columnas C a G)
        - nombre (para referencia visual)
        - fotos_referencia (nombres de fotos en Col AA, AD, AG, AJ si existen)
        """
        if not sku or not str(sku).strip():
            return None
        sku_clean = str(sku).strip().upper()

        now = time.time()
        last_sync = getattr(self, "_sku_catalog_last_sync", 0.0)
        last_attempt = getattr(self, "_sku_sync_attempted_at", 0.0)
        ttl = getattr(self, "_sku_cache_ttl", 20.0)
        cooldown_base = max(last_sync, last_attempt)
        need_refresh = (
            force_refresh
            or self._sku_catalog_cache is None
            or (now - cooldown_base > ttl)
        )

        if need_refresh:
            self._load_sku_catalog_cache()

        found = self._match_sku_in_cache(sku_clean)
        if found:
            return found

        # Si el SKU no fue encontrado y no se ha intentado sincronizar en los últimos 30s,
        # consultar Google Sheets una vez para detectar productos recién añadidos
        now = time.time()
        last_attempt = getattr(self, "_sku_sync_attempted_at", 0.0)
        last_sync = getattr(self, "_sku_catalog_last_sync", 0.0)
        if not need_refresh and (now - max(last_sync, last_attempt) > 30.0):
            self._load_sku_catalog_cache()
            return self._match_sku_in_cache(sku_clean)

        return None

    def _load_sku_catalog_cache(self):
        """Carga en memoria el catálogo de SKUs de DATOS GENERAL directamente en vivo desde Google Sheets y actualiza el caché de respaldo."""
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        self._sku_sync_attempted_at = time.time()
        self.ensure_connected()
        disk_cache = Path(__file__).resolve().parent.parent / "sku_catalog_cache.json"

        # 1. INTENTAR SIEMPRE EN VIVO CON GOOGLE SHEETS
        if self.service:
            try:
                with observe_call("sheets_service", "load_sku_catalog_live") as obs:
                    tab_dg = self.get_datos_general_tab_name()
                    res = self.service.spreadsheets().values().get(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"'{tab_dg}'!A4:AJ",
                        valueRenderOption="FORMATTED_VALUE"
                    ).execute()
                    rows = res.get("values", [])
                    live_cache = {}
                    for r in rows:
                        row_sku = str(r[0]).strip() if len(r) > 0 and r[0] else ""
                        if not row_sku:
                            continue
                        row_sku_upper = row_sku.upper()
                        nombre = str(r[1]).strip() if len(r) > 1 and r[1] else ""
                        frente = str(r[2]).strip() if len(r) > 2 and r[2] else ""
                        fondo = str(r[3]).strip() if len(r) > 3 and r[3] else ""
                        alto = str(r[4]).strip() if len(r) > 4 and r[4] else ""
                        diam = str(r[5]).strip() if len(r) > 5 and r[5] else ""
                        piso = str(r[6]).strip() if len(r) > 6 and r[6] else ""
                        cat = str(r[15]).strip() if len(r) > 15 and r[15] else ""
                        tipo = str(r[24]).strip() if len(r) > 24 and r[24] else ""

                        tipo_final = tipo if tipo else cat

                        medidas_parts = []
                        if diam and diam.upper() not in ["N/A", "NONE", "0", "N/D", "-"]:
                            medidas_parts.append(f"D. {diam} cm")
                        else:
                            if frente: medidas_parts.append(f"{frente} cm frente")
                            if fondo: medidas_parts.append(f"{fondo} cm fondo")
                        if alto: medidas_parts.append(f"{alto} cm alto")
                        if piso and piso.upper() not in ["N/A", "NONE", "0", "-"]:
                            medidas_parts.append(f"{piso} cm piso al asiento")
                        medidas_str = " x ".join(medidas_parts) if medidas_parts else ""

                        foto_mueble = str(r[26]).strip() if len(r) > 26 and r[26] else ""
                        foto_tela = str(r[29]).strip() if len(r) > 29 and r[29] else ""
                        foto_madera = str(r[32]).strip() if len(r) > 32 and r[32] else ""
                        foto_swatch = str(r[35]).strip() if len(r) > 35 and r[35] else ""

                        live_cache[row_sku_upper] = {
                            "sku": row_sku,
                            "nombre": nombre,
                            "tipo_mueble": tipo_final,
                            "medidas": medidas_str,
                            "foto_mueble_nom": foto_mueble,
                            "foto_tela_nom": foto_tela,
                            "foto_madera_nom": foto_madera,
                            "foto_swatch_nom": foto_swatch
                        }

                    # La lectura en vivo fue exitosa: el caché refleja EXACTAMENTE la hoja
                    # (si se borró un SKU en Sheets, desaparece también aquí)
                    self._sku_catalog_cache = live_cache
                    self._sku_catalog_last_sync = time.time()
                    obs["meta"]["source"] = "sheets_live"
                    obs["meta"]["sku_count"] = len(live_cache)
                    try:
                        with open(disk_cache, "w", encoding="utf-8") as cf:
                            json.dump(live_cache, cf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                return
            except Exception as e:
                log_event(
                    "sheets.sku_catalog.live_sync_failed",
                    service="sheets_service",
                    operation="_load_sku_catalog_cache",
                    level="warning",
                    status="fallback",
                    error_class=classify_error(e),
                    meta={"error": safe_error_text(e, 220)},
                )

        # 2. FALLBACK A DISCO SI NO HAY CONEXIÓN A INTERNET O FALLÓ LA API
        if disk_cache.exists():
            try:
                import json
                with open(disk_cache, "r", encoding="utf-8") as cf:
                    loaded = json.load(cf)
                    if loaded and isinstance(loaded, dict):
                        self._sku_catalog_cache = loaded
                        log_event(
                            "sheets.sku_catalog.disk_fallback",
                            service="sheets_service",
                            operation="_load_sku_catalog_cache",
                            level="warning",
                            status="fallback",
                            meta={"source": "sku_catalog_cache.json", "sku_count": len(loaded)},
                        )
                        return
            except Exception:
                pass

        # 3. FALLBACK SECUNDARIO A datos_general_cache.json
        if not self._sku_catalog_cache:
            cache_file = Path(__file__).resolve().parent.parent / "datos_general_cache.json"
            if cache_file.exists():
                try:
                    with open(cache_file, "r", encoding="utf-8") as cf:
                        prods = json.load(cf)
                        fallback_dict = {}
                        for p in prods:
                            s = str(p.get("sku", "")).strip().upper()
                            if s:
                                se = p.get("sin_empaque", {})
                                fr = str(se.get("frente", "")).strip()
                                fo = str(se.get("fondo", "")).strip()
                                al = str(se.get("alto", "")).strip()
                                di = str(se.get("diametro", "")).strip()
                                pi = str(se.get("piso_asiento", "")).strip()
                                
                                m_parts = []
                                if di and di.upper() not in ["N/A", "NONE", "0", "N/D", "-"]:
                                    m_parts.append(f"D. {di} cm")
                                else:
                                    if fr: m_parts.append(f"{fr} cm frente")
                                    if fo: m_parts.append(f"{fo} cm fondo")
                                if al: m_parts.append(f"{al} cm alto")
                                if pi and pi.upper() not in ["N/A", "NONE", "0", "-"]:
                                    m_parts.append(f"{pi} cm piso al asiento")
                                m_str = " x ".join(m_parts) if m_parts else ""
                                
                                fts = p.get("fotos", {})
                                fallback_dict[s] = {
                                    "sku": p.get("sku", ""),
                                    "nombre": p.get("nombre_viejo", "") or p.get("nombre_nuevo", ""),
                                    "tipo_mueble": p.get("tipo_mueble", "") or p.get("categoria", ""),
                                    "medidas": m_str,
                                    "foto_mueble_nom": fts.get("mueble_nombre", ""),
                                    "foto_tela_nom": fts.get("tela_nombre", ""),
                                    "foto_madera_nom": fts.get("madera_nombre", ""),
                                    "foto_swatch_nom": fts.get("swatch_nombre", "")
                                }
                        self._sku_catalog_cache = fallback_dict
                except Exception:
                    pass

    def get_pending_products(self) -> List[Dict[str, Any]]:
        """Obtiene la lista de productos de DATOS GENERAL, clasificando los que no tienen fotos."""
        self.ensure_connected()
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
        if fila < 4:
            return False
        self.ensure_connected()
        if not self.service:
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
                lnk_m = self.buscar_link_drive_inteligente(nom_m, tipo="MUEBLE")
                fotos["mueble_link"] = lnk_m
            updates.append({"range": f"'{tab_dg}'!AA{fila}", "values": [[nom_m]]})
            if lnk_m:
                updates.append({"range": f"'{tab_dg}'!AC{fila}", "values": [[lnk_m]]})

        # 6. Fotos Tela (Cols AD, AF)
        if "tela_nombre" in fotos and fotos["tela_nombre"]:
            nom_t = fotos["tela_nombre"]
            lnk_t = fotos.get("tela_link", "").strip()
            if not lnk_t:
                lnk_t = self.buscar_link_drive_inteligente(nom_t, tipo="TELA")
                fotos["tela_link"] = lnk_t
            updates.append({"range": f"'{tab_dg}'!AD{fila}", "values": [[nom_t]]})
            if lnk_t:
                updates.append({"range": f"'{tab_dg}'!AF{fila}", "values": [[lnk_t]]})

        # 7. Fotos Madera (Cols AG, AI)
        if "madera_nombre" in fotos and fotos["madera_nombre"]:
            nom_md = fotos["madera_nombre"]
            lnk_md = fotos.get("madera_link", "").strip()
            if not lnk_md:
                lnk_md = self.buscar_link_drive_inteligente(nom_md, tipo="MADERA")
                fotos["madera_link"] = lnk_md
            updates.append({"range": f"'{tab_dg}'!AG{fila}", "values": [[nom_md]]})
            if lnk_md:
                updates.append({"range": f"'{tab_dg}'!AI{fila}", "values": [[lnk_md]]})

        # 8. Fotos Swatch (Cols AJ, AL)
        if "swatch_nombre" in fotos and fotos["swatch_nombre"]:
            nom_sw = fotos["swatch_nombre"]
            lnk_sw = fotos.get("swatch_link", "").strip()
            if not lnk_sw:
                lnk_sw = self.buscar_link_drive_inteligente(nom_sw, tipo="SWATCH")
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
            from services.observability import observe_call

            body = {
                "valueInputOption": "USER_ENTERED",
                "data": updates
            }
            with observe_call("sheets_service", "update_product_row_safe", meta={"cells": len(updates)}):
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
            from services.observability import classify_error, log_event, safe_error_text

            log_event(
                "sheets.local_cache_update.failed",
                service="sheets_service",
                operation="update_product_row_safe",
                level="warning",
                status="degraded",
                error_class=classify_error(e),
                meta={"error": safe_error_text(e, 220)},
            )

        return True

    def register_many_in_fotos_normalizadas(self, photos: List[Dict[str, str]]) -> bool:
        """Registra varios nombres y enlaces con una lectura y una escritura por lote."""
        from services.observability import classify_error, log_event, observe_call, safe_error_text

        self.ensure_connected()
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
            with observe_call("sheets_service", "register_many_in_fotos_normalizadas", meta={"photos": len(prepared)}) as obs:
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
                        if link and link.strip() != (current_link or "").strip():
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

                obs["meta"]["updates"] = len(updates)
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
            log_event(
                "sheets.fotos_normalizadas.register_failed",
                service="sheets_service",
                operation="register_many_in_fotos_normalizadas",
                level="error",
                status="error",
                error_class=classify_error(error),
                meta={"error": safe_error_text(error, 220)},
            )
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
        self.ensure_connected()
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

    @staticmethod
    def extract_drive_id(url_or_id: str) -> str:
        """Extrae el fileId o folderId limpio desde un enlace de Google Drive o devuelve el ID directo."""
        if not url_or_id:
            return ""
        val = str(url_or_id).strip()
        mf = re.search(r"/folders/([a-zA-Z0-9_-]{15,})", val)
        if mf:
            return mf.group(1)
        m = re.search(r"/d/([a-zA-Z0-9_-]{15,})", val)
        if m:
            return m.group(1)
        m2 = re.search(r"[?&]id=([a-zA-Z0-9_-]{15,})", val)
        if m2:
            return m2.group(1)
        if re.fullmatch(r"[a-zA-Z0-9_-]{18,}", val):
            return val
        return ""

    def fetch_sku_assets_from_drive(self, sku_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Descarga automáticamente desde Google Drive (o muestras_madera local) los insumos
        registrados para un SKU en DATOS GENERAL: mueble, tela y madera.
        """
        out: Dict[str, Dict[str, Any]] = {}
        if not sku_data or not isinstance(sku_data, dict):
            return out

        app_dir = Path(__file__).resolve().parent.parent
        maderas_dir = app_dir / "muestras_madera"

        mapping = [
            ("mueble", sku_data.get("foto_mueble_nom", ""), "MUEBLE"),
            ("tela", sku_data.get("foto_tela_nom", ""), "TELA"),
            ("madera", sku_data.get("foto_madera_nom", ""), "MADERA"),
        ]
        for key, raw_name, cat_type in mapping:
            nom = str(raw_name or "").strip()
            if not nom or nom.upper() in ("N/A", "NONE", "-", "0"):
                continue

            # Para madera, revisar primero catálogo local muestras_madera/ (0ms)
            if key == "madera" and maderas_dir.exists():
                stem_target = os.path.splitext(nom)[0].strip().upper()
                local_hit = next(
                    (
                        f for f in maderas_dir.iterdir()
                        if f.is_file() and f.stem.replace("_", " ").strip().upper() == stem_target
                    ),
                    None,
                )
                if local_hit:
                    try:
                        out[key] = {
                            "name": local_hit.stem,
                            "filename": local_hit.name,
                            "bytes": local_hit.read_bytes(),
                            "source": "local",
                        }
                        continue
                    except Exception:
                        pass

            link = self.buscar_link_drive_inteligente(nom, tipo=cat_type)
            fid = self.extract_drive_id(link)
            if fid:
                raw_bytes = self.get_drive_file_bytes(fid)
                if raw_bytes:
                    ext = os.path.splitext(nom)[1] or ".jpg"
                    fname = nom if os.path.splitext(nom)[1] else f"{nom}{ext}"
                    out[key] = {
                        "name": os.path.splitext(nom)[0].strip(),
                        "filename": fname,
                        "bytes": raw_bytes,
                        "drive_id": fid,
                        "link": link,
                        "source": "drive",
                    }
        return out

    def publish_photo_and_get_urls(
        self,
        file_bytes: bytes,
        filename: str,
        dest: str = "buzon",
        subfolder: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Sube una fotografía generada (ej. 2054×2054 PNG/JPG) a Google Drive (Buzón o Fotos Final),
        habilita lectura por enlace ('anyone' -> 'reader') y retorna todas las URLs listas para
        Odoo, Google Sheets y Canva.
        """
        if not file_bytes:
            raise ValueError("No hay bytes de imagen para subir.")
        self.ensure_connected()
        if not self.drive_service:
            raise RuntimeError("Google Drive no está conectado.")

        dest_norm = (dest or "render").strip().lower()
        if dest_norm == "render":
            target_parent = self.render_drive_id
        elif dest_norm == "subir":
            target_parent = self.subir_drive_id
        elif dest_norm == "final":
            target_parent = self.fotos_final_drive_id
        elif dest_norm == "info_mia":
            target_parent = self.info_mia_drive_id
        else:
            target_parent = self.resolve_active_staging_folder_id()

        if subfolder and subfolder.strip() and dest_norm in ("final", "render"):
            for part in [p for p in subfolder.replace("\\", "/").split("/") if p]:
                folder_id = self.get_or_create_drive_folder(target_parent, part)
                if folder_id:
                    target_parent = folder_id

        mime = self.guess_mime_type(filename, default="image/png")
        media_cls = MediaIoBaseUpload
        if media_cls is None:
            try:
                from googleapiclient.http import MediaIoBaseUpload as _mcls
                media_cls = _mcls
            except Exception:
                media_cls = None
        media = media_cls(io.BytesIO(file_bytes), mimetype=mime, resumable=True) if media_cls is not None else io.BytesIO(file_bytes)
        body: Dict[str, Any] = {
            "name": filename,
            "parents": [target_parent],
        }
        if metadata:
            body["description"] = json.dumps(metadata, ensure_ascii=False)

        with self._drive_api_lock:
            uploaded = self.drive_service.files().create(
                body=body,
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            ).execute()

        file_id = uploaded.get("id", "")
        if not file_id:
            raise RuntimeError("Google Drive no devolvió un ID de archivo.")

        self._invalidate_drive_catalog_caches()
        is_public, perm_msg = self.ensure_public_read_permission(file_id)

        return {
            "file_id": file_id,
            "filename": filename,
            "is_public": is_public,
            "permission_status": perm_msg,
            "folder_url": f"https://drive.google.com/drive/folders/{target_parent}",
            "drive_view_url": f"https://drive.google.com/file/d/{file_id}/view?usp=sharing",
            "direct_cdn_url": f"https://lh3.googleusercontent.com/d/{file_id}=s2048",
            "download_url": f"https://drive.google.com/uc?export=download&id={file_id}",
        }

sheets_service = SheetsService()
