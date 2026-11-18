import base64
import hashlib
import io
import re
from pathlib import Path
from typing import Optional, Union

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps


def render_copy_button(text: str, label: str = "📋 Copiar Prompt", key: str = "cp") -> None:
    """Renderiza un botón HTML/JS seguro para copiar texto UTF-8 al portapapeles."""
    if text is None:
        text = ""
    b64_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", str(key))
    uid = hashlib.md5(f"{safe_key}_{len(text)}".encode("utf-8")).hexdigest()[:8]
    btn_id = f"btn_{safe_key}_{uid}"
    msg_id = f"msg_{safe_key}_{uid}"
    safe_label = (
        label.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    html_code = f"""
    <div style="display:flex;align-items:center;gap:6px;margin:2px 0 4px 0;font-family:sans-serif;">
        <button id="{btn_id}" style="
            background:linear-gradient(135deg,#0284c7,#0ea5e9);
            color:#ffffff;border:none;padding:4px 10px;border-radius:5px;
            font-size:11.5px;font-weight:600;cursor:pointer;
            box-shadow:0 1px 4px rgba(2,132,199,0.3);transition:transform 0.1s ease;
        ">{safe_label}</button>
        <span id="{msg_id}" style="font-size:11px;color:#4ade80;font-weight:600;display:none;">
            ✅ Copiado
        </span>
    </div>
    <script>
    (function() {{
        var btn = document.getElementById("{btn_id}");
        var msg = document.getElementById("{msg_id}");
        if (!btn) return;
        btn.addEventListener("click", function() {{
            try {{
                var binStr = atob("{b64_text}");
                var bytes = new Uint8Array(binStr.length);
                for (var i = 0; i < binStr.length; i++) {{
                    bytes[i] = binStr.charCodeAt(i);
                }}
                var decoded = new TextDecoder("utf-8").decode(bytes);
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    navigator.clipboard.writeText(decoded).then(showOk).catch(function() {{
                        fallbackCopy(decoded);
                    }});
                }} else {{
                    fallbackCopy(decoded);
                }}
            }} catch (e) {{
                console.error("Copy error:", e);
            }}
        }});
        function showOk() {{
            if (msg) {{
                msg.style.display = "inline";
                setTimeout(function() {{ msg.style.display = "none"; }}, 2000);
            }}
        }}
        function fallbackCopy(val) {{
            var ta = document.createElement("textarea");
            ta.value = val;
            ta.style.position = "fixed";
            ta.style.opacity = "0";
            document.body.appendChild(ta);
            ta.select();
            try {{ document.execCommand("copy"); showOk(); }} catch (e) {{}}
            document.body.removeChild(ta);
        }}
    }})();
    </script>
    """
    components.html(html_code, height=32)


@st.cache_data(max_entries=256, show_spinner=False)
def make_thumbnail_bytes(raw_bytes: bytes, max_dim: int = 480) -> bytes:
    """Genera una miniatura JPEG optimizada en caché para evitar saturar memoria/DOM."""
    if not raw_bytes:
        return b""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (245, 245, 245))
                if img.mode == "P":
                    img = img.convert("RGBA")
                alpha = img.split()[-1] if "A" in img.getbands() else None
                bg.paste(img, mask=alpha)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=82, optimize=True)
            return out.getvalue()
    except Exception:
        return raw_bytes


def _extract_bytes(img_data: Union[bytes, bytearray, str, Path, Image.Image, object]) -> Optional[bytes]:
    if img_data is None:
        return None
    if isinstance(img_data, (bytes, bytearray)):
        return bytes(img_data)
    if isinstance(img_data, (str, Path)):
        p = Path(img_data)
        if p.exists() and p.is_file():
            return p.read_bytes()
        return None
    if isinstance(img_data, Image.Image):
        buf = io.BytesIO()
        img_data.save(buf, format="PNG")
        return buf.getvalue()
    if hasattr(img_data, "getvalue"):
        return img_data.getvalue()
    if hasattr(img_data, "read"):
        pos = img_data.tell() if hasattr(img_data, "tell") else None
        data = img_data.read()
        if pos is not None and hasattr(img_data, "seek"):
            img_data.seek(pos)
        return data
    return None


def render_preview_image(
    img_data,
    caption: str = "",
    max_dim: int = 480,
    max_height: Optional[int] = None,
    width: Optional[int] = None,
) -> None:
    """Muestra una miniatura ligera de la imagen para evitar re-serializar MBs en cada rerun."""
    raw = _extract_bytes(img_data)
    if not raw:
        return
    thumb = make_thumbnail_bytes(raw, max_dim=max_dim)
    target_w = width if width is not None else (max_height if max_height is not None else None)
    if target_w is not None:
        st.image(thumb, caption=caption or None, width=target_w)
    else:
        st.image(thumb, caption=caption or None, use_container_width=True)


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def load_drive_file_cached(file_id: str) -> Optional[bytes]:
    """Descarga y cachea archivos de Drive durante 60 minutos para evitar re-descargas por rerun."""
    if not file_id:
        return None
    from services.sheets_service import sheets_service
    return sheets_service.get_drive_file_bytes(file_id)
