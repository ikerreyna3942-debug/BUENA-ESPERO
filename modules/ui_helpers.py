import base64
from collections import OrderedDict
import gc
import hashlib
import io
import re
import threading
from pathlib import Path
from typing import Optional, Union

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

_CACHE_LOCK = threading.Lock()
_THUMB_CACHE: "OrderedDict[tuple[str, int, int], bytes]" = OrderedDict()
_THUMB_CACHE_BYTES = 0
_THUMB_MAX_ENTRIES = 64
_THUMB_MAX_BYTES = 4 * 1024 * 1024  # 4 MB máximo para miniaturas

_EXACT_COPY_CACHE: "OrderedDict[tuple[str, int], tuple[bytes, str]]" = OrderedDict()
_EXACT_COPY_CACHE_BYTES = 0
_EXACT_COPY_MAX_ENTRIES = 12
_EXACT_COPY_MAX_BYTES = 10 * 1024 * 1024  # 10 MB máximo para copias al portapapeles
_COPY_MAX_DIM = 1600
_COPY_PNG_MAX_DIM = 1400
_COPY_PASSTHROUGH_MAX_BYTES = 1_500_000


def _bytes_sig(raw_bytes: bytes) -> tuple[str, int]:
    """Firma compacta (SHA-1 parcial + tamaño) para cachear sin retener los bytes crudos como llave."""
    n = len(raw_bytes)
    h = hashlib.sha1()
    if n <= 131_072:
        h.update(raw_bytes)
    else:
        h.update(raw_bytes[:65_536])
        h.update(raw_bytes[n // 2 - 16_384 : n // 2 + 16_384])
        h.update(raw_bytes[-32_768:])
    return h.hexdigest(), n


def _safe_exif_orientation(img: Image.Image) -> int:
    try:
        exif = img.getexif()
        if exif:
            return int(exif.get(274, 1) or 1)
    except Exception:
        pass
    return 1


def _apply_orientation_if_needed(img: Image.Image, orientation: int) -> Image.Image:
    if orientation in (None, 1):
        return img
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def _has_real_transparency(img: Image.Image) -> bool:
    try:
        if img.mode in ("RGBA", "LA"):
            alpha = img.getchannel("A")
            ext = alpha.getextrema()
            return bool(ext and ext[0] < 255)
        if img.mode == "P" and "transparency" in img.info:
            rgba = img.convert("RGBA")
            ext = rgba.getchannel("A").getextrema()
            return bool(ext and ext[0] < 255)
    except Exception:
        pass
    return False


def render_copy_button(
    text: str,
    label: str = "📋 Copiar Prompt",
    key: str = "cp",
    extra_link_url: str = "",
    extra_link_label: str = "",
) -> None:
    """Renderiza un botón HTML/JS seguro para copiar texto UTF-8 al portapapeles (con acceso opcional a AI Studio/ChatGPT)."""
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
    extra_html = ""
    if extra_link_url and extra_link_label:
        safe_url = extra_link_url.replace('"', "&quot;")
        safe_extra = (
            extra_link_label.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        extra_html = f"""
        <a href="{safe_url}" target="_blank" rel="noopener" style="
            background:#1e293b;border:1px solid #38bdf8;color:#7dd3fc;
            text-decoration:none;padding:4px 9px;border-radius:6px;
            font-size:11px;font-weight:600;white-space:nowrap;
        ">{safe_extra}</a>
        """

    html_code = f"""
    <style>html, body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}</style>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:2px 0 2px 0;font-family:sans-serif;">
        <button id="{btn_id}" style="
            background:linear-gradient(135deg,#0284c7,#0ea5e9);
            color:#ffffff;border:none;padding:5px 10px;border-radius:6px;
            font-size:11.5px;font-weight:600;line-height:1.25;cursor:pointer;
            max-width:100%;text-align:center;
            box-shadow:0 1px 4px rgba(2,132,199,0.3);transition:transform 0.1s ease;
        ">{safe_label}</button>
        {extra_html}
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
                function tryParentText() {{
                    try {{
                        if (window.parent && window.parent !== window && window.parent.navigator && window.parent.navigator.clipboard && window.parent.navigator.clipboard.writeText) {{
                            return window.parent.navigator.clipboard.writeText(decoded).then(showOk);
                        }}
                    }} catch (ep) {{}}
                    return Promise.reject(new Error("parent_text_unavailable"));
                }}
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    navigator.clipboard.writeText(decoded).then(showOk).catch(function() {{
                        tryParentText().catch(function() {{ fallbackCopy(decoded); }});
                    }});
                }} else {{
                    tryParentText().catch(function() {{ fallbackCopy(decoded); }});
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
    btn_height = 44 if len(label) > 26 else 36
    components.html(html_code, height=btn_height)


def prepare_exact_copy_image_bytes(raw_bytes: bytes) -> tuple[bytes, str]:
    """Prepara la imagen sin recorte ni pérdida de proporción y con límite seguro de RAM/peso para copiar al portapapeles."""
    global _EXACT_COPY_CACHE_BYTES
    if not raw_bytes:
        return b"", "image/png"

    sig = _bytes_sig(raw_bytes)
    with _CACHE_LOCK:
        cached = _EXACT_COPY_CACHE.get(sig)
        if cached is not None:
            _EXACT_COPY_CACHE.move_to_end(sig)
            return cached

    result: tuple[bytes, str] = (raw_bytes, "image/jpeg")
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            fmt = (img.format or "").upper()
            orientation = _safe_exif_orientation(img)
            orig_w, orig_h = img.size
            max_side = max(orig_w, orig_h)

            # Ruta rápida sin decodificar píxeles: conserva bytes exactos cuando la imagen ya es ligera y estándar
            if (
                fmt in ("PNG", "JPEG", "JPG")
                and img.mode in ("RGB", "RGBA")
                and orientation == 1
                and max_side <= _COPY_MAX_DIM
                and len(raw_bytes) <= _COPY_PASSTHROUGH_MAX_BYTES
            ):
                mime = "image/png" if fmt == "PNG" else "image/jpeg"
                result = (raw_bytes, mime)
            else:
                if fmt in ("JPEG", "JPG") and max_side > _COPY_MAX_DIM:
                    try:
                        img.draft("RGB", (_COPY_MAX_DIM * 2, _COPY_MAX_DIM * 2))
                    except Exception:
                        pass

                work = img
                if max(work.size) > _COPY_MAX_DIM * 2:
                    factor = max(2, max(work.size) // (_COPY_MAX_DIM * 2))
                    work = work.reduce(factor)
                if max(work.size) > _COPY_MAX_DIM:
                    work.thumbnail((_COPY_MAX_DIM, _COPY_MAX_DIM), Image.Resampling.LANCZOS)
                if orientation != 1:
                    work = _apply_orientation_if_needed(work, orientation)

                out = io.BytesIO()
                if _has_real_transparency(work):
                    if work.mode != "RGBA":
                        work = work.convert("RGBA")
                    if max(work.size) > _COPY_PNG_MAX_DIM:
                        work.thumbnail((_COPY_PNG_MAX_DIM, _COPY_PNG_MAX_DIM), Image.Resampling.LANCZOS)
                    work.save(out, format="PNG", compress_level=4)
                    result = (out.getvalue(), "image/png")
                else:
                    if work.mode in ("RGBA", "LA", "P"):
                        rgba = work if work.mode == "RGBA" else work.convert("RGBA")
                        bg = Image.new("RGB", rgba.size, (255, 255, 255))
                        bg.paste(rgba, mask=rgba.split()[-1])
                        work = bg
                    elif work.mode != "RGB":
                        work = work.convert("RGB")
                    work.save(out, format="JPEG", quality=92, subsampling=0)
                    result = (out.getvalue(), "image/jpeg")
    except Exception:
        result = (raw_bytes[:_COPY_PASSTHROUGH_MAX_BYTES], "image/jpeg") if len(raw_bytes) > 4_000_000 else (raw_bytes, "image/jpeg")

    if len(raw_bytes) >= 1_500_000:
        gc.collect()

    out_len = len(result[0])
    if out_len <= _EXACT_COPY_MAX_BYTES:
        with _CACHE_LOCK:
            if sig in _EXACT_COPY_CACHE:
                _EXACT_COPY_CACHE_BYTES -= len(_EXACT_COPY_CACHE[sig][0])
                _EXACT_COPY_CACHE.pop(sig, None)
            while (
                _EXACT_COPY_CACHE
                and (
                    len(_EXACT_COPY_CACHE) >= _EXACT_COPY_MAX_ENTRIES
                    or (_EXACT_COPY_CACHE_BYTES + out_len) > _EXACT_COPY_MAX_BYTES
                )
            ):
                _, ev = _EXACT_COPY_CACHE.popitem(last=False)
                _EXACT_COPY_CACHE_BYTES -= len(ev[0])
            _EXACT_COPY_CACHE[sig] = result
            _EXACT_COPY_CACHE_BYTES += out_len
    return result


def make_thumbnail_bytes(raw_bytes: bytes, max_dim: int = 480) -> bytes:
    """Genera una miniatura JPEG optimizada en caché acotada en RAM sin decodificar mapas de bits gigantes."""
    global _THUMB_CACHE_BYTES
    if not raw_bytes:
        return b""

    sig_base = _bytes_sig(raw_bytes)
    cache_key = (sig_base[0], sig_base[1], int(max_dim))
    with _CACHE_LOCK:
        cached = _THUMB_CACHE.get(cache_key)
        if cached is not None:
            _THUMB_CACHE.move_to_end(cache_key)
            return cached

    thumb_out = b""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            fmt = (img.format or "").upper()
            orientation = _safe_exif_orientation(img)
            if fmt in ("JPEG", "JPG") and max(img.size) > max_dim:
                try:
                    img.draft("RGB", (max_dim * 2, max_dim * 2))
                except Exception:
                    pass
            work = img
            if max(work.size) > max_dim * 2:
                factor = max(2, max(work.size) // (max_dim * 2))
                work = work.reduce(factor)
            work.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            if orientation != 1:
                work = _apply_orientation_if_needed(work, orientation)
            if work.mode in ("RGBA", "LA", "P"):
                rgba = work if work.mode == "RGBA" else work.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (245, 245, 245))
                bg.paste(rgba, mask=rgba.split()[-1])
                work = bg
            elif work.mode != "RGB":
                work = work.convert("RGB")
            out = io.BytesIO()
            work.save(out, format="JPEG", quality=80)
            thumb_out = out.getvalue()
    except Exception:
        thumb_out = raw_bytes if len(raw_bytes) <= 512_000 else b""

    if thumb_out and len(thumb_out) <= _THUMB_MAX_BYTES:
        with _CACHE_LOCK:
            if cache_key in _THUMB_CACHE:
                _THUMB_CACHE_BYTES -= len(_THUMB_CACHE[cache_key])
                _THUMB_CACHE.pop(cache_key, None)
            while (
                _THUMB_CACHE
                and (
                    len(_THUMB_CACHE) >= _THUMB_MAX_ENTRIES
                    or (_THUMB_CACHE_BYTES + len(thumb_out)) > _THUMB_MAX_BYTES
                )
            ):
                _, ev = _THUMB_CACHE.popitem(last=False)
                _THUMB_CACHE_BYTES -= len(ev)
            _THUMB_CACHE[cache_key] = thumb_out
            _THUMB_CACHE_BYTES += len(thumb_out)
    return thumb_out


def resolve_copied_photo_filename(label: str, fallback: str = "foto.png") -> str:
    """Devuelve el nombre exacto de archivo que entrega el botón Copiar foto (y el que usará el prompt)."""
    raw = str(label or "").strip().replace("\\", "/")
    base = raw.rsplit("/", 1)[-1].strip() if raw else ""
    if not base:
        base = str(fallback or "foto.png").strip() or "foto.png"
    dl_name = base if "." in base else f"{base}.png"
    clean = dl_name.replace("\\", "_").replace('"', "").replace("'", "").strip()
    return clean or "foto.png"


def render_loaded_photos_strip(
    thumbs: list[tuple[str, bytes, str]],
    key_prefix: str = "v7",
    thumb_px: int = 120,
) -> None:
    """Muestra las fotos que se van a utilizar (+50% más grandes: 120×120 px) con 1 botón debajo de cada foto para copiar la imagen (no texto)."""
    if not thumbs:
        return

    card_blocks: list[str] = []
    js_entries: list[str] = []
    img_px = max(90, int(thumb_px))
    card_w = img_px + 20

    for idx, (lbl, raw_b, badge) in enumerate(thumbs):
        if not raw_b:
            continue
        exact_bytes, exact_mime = prepare_exact_copy_image_bytes(raw_b)
        if not exact_bytes:
            continue
        t_bytes = make_thumbnail_bytes(exact_bytes, max_dim=min(260, max(200, img_px * 2)))
        if not t_bytes:
            continue
        b64_thumb = base64.b64encode(t_bytes).decode("ascii")
        b64_exact = base64.b64encode(exact_bytes).decode("ascii")
        uid = hashlib.md5(f"{key_prefix}_{idx}_{lbl}_{len(raw_b)}".encode("utf-8")).hexdigest()[:8]
        btn_id = f"cpimg_{uid}"
        msg_id = f"cpmsg_{uid}"

        safe_dl = resolve_copied_photo_filename(lbl, fallback=f"foto_{idx + 1}.png")
        clean_lbl = safe_dl
        safe_lbl = clean_lbl.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_title = clean_lbl.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        safe_badge = (badge or "Cargada")[:34].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        js_dl = safe_dl.replace("\\", "\\\\").replace('"', '\\"')

        card_blocks.append(
            f'<div class="thumb-card" title="{safe_badge}: {safe_title}">'
            f'<div class="thumb-img-wrap">'
            f'<img class="thumb-img" src="data:image/jpeg;base64,{b64_thumb}" alt="{safe_title}" />'
            f'</div>'
            f'<span class="thumb-badge">✅ {safe_badge}</span>'
            f'<span class="thumb-name" title="{safe_title}">{safe_lbl}</span>'
            f'<button type="button" id="{btn_id}" class="cp-btn" title="Copiar foto original ({safe_title}) al portapapeles">🖼️ Copiar foto</button>'
            f'<span id="{msg_id}" class="cp-msg"></span>'
            f'</div>'
        )
        js_entries.append(
            f'bindCopy("{btn_id}", "{msg_id}", "data:{exact_mime};base64,{b64_exact}", "{js_dl}");'
        )

    if not card_blocks:
        return

    # Estima filas pensando en móvil (2 tarjetas por fila) para que nunca se recorte la 3.ª foto
    rows_est = max(1, (len(card_blocks) + 1) // 2)
    row_h = img_px + 98
    comp_height = min(460, row_h * rows_est + 16)
    needs_scroll = (row_h * rows_est + 16) > 460

    html_doc = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8" />
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: transparent; padding: 3px 2px; overflow-x: hidden; }}
        .strip {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: stretch;
        }}
        .thumb-card {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            width: {card_w}px;
            max-width: calc(50% - 4px);
            background: #0F172A;
            border: 1px solid #0284C7;
            border-radius: 9px;
            padding: 7px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.38);
        }}
        .thumb-img-wrap {{
            width: {img_px}px;
            height: {img_px}px;
            max-width: 100%;
            border-radius: 7px;
            overflow: hidden;
            background: #020617;
            border: 1px solid #1E293B;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .thumb-img {{
            width: {img_px}px;
            height: {img_px}px;
            max-width: 100%;
            object-fit: cover;
            display: block;
            transition: transform 0.18s ease;
        }}
        .thumb-img:hover {{ transform: scale(1.12); }}
        .thumb-badge {{
            width: 100%;
            font-size: 10px;
            color: #4ADE80;
            font-weight: 700;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .thumb-name {{
            width: 100%;
            font-size: 11px;
            color: #F8FAFC;
            font-weight: 600;
            text-align: center;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .cp-btn {{
            width: 100%;
            background: linear-gradient(135deg, #0284C7, #0EA5E9);
            color: #FFFFFF;
            border: none;
            border-radius: 6px;
            padding: 5px 8px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
            margin-top: 2px;
            box-shadow: 0 1px 4px rgba(2,132,199,0.35);
        }}
        .cp-btn:hover {{ filter: brightness(1.1); }}
        .cp-btn:active {{ transform: scale(0.97); }}
        .cp-btn:disabled {{ opacity: 0.65; cursor: wait; }}
        .cp-msg {{
            width: 100%;
            font-size: 9.5px;
            font-weight: 700;
            color: #4ADE80;
            min-height: 13px;
            line-height: 13px;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
    </style>
    </head>
    <body>
        <div class="strip">{"".join(card_blocks)}</div>
        <script>
        (function() {{
            function decodePngDataUriSync(dataUri) {{
                try {{
                    if (typeof dataUri !== "string" || dataUri.indexOf("data:image/png;base64,") !== 0) return null;
                    var b64 = dataUri.slice("data:image/png;base64,".length);
                    var bin = atob(b64);
                    var bytes = new Uint8Array(bin.length);
                    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    return new Blob([bytes], {{ type: "image/png" }});
                }} catch (e) {{
                    return null;
                }}
            }}

            function dataUriToPngBlob(dataUri) {{
                var directPng = decodePngDataUriSync(dataUri);
                if (directPng) return Promise.resolve(directPng);
                return new Promise(function(resolve, reject) {{
                    var img = new Image();
                    img.onload = function() {{
                        try {{
                            var c = document.createElement("canvas");
                            c.width = img.naturalWidth || img.width;
                            c.height = img.naturalHeight || img.height;
                            var ctx = c.getContext("2d");
                            ctx.drawImage(img, 0, 0);
                            c.toBlob(function(blob) {{
                                if (blob) resolve(blob);
                                else reject(new Error("toBlob failed"));
                            }}, "image/png");
                        }} catch (e) {{ reject(e); }}
                    }};
                    img.onerror = function() {{ reject(new Error("img load failed")); }};
                    img.src = dataUri;
                }});
            }}

            function writePngToWindowClipboard(targetWin, syncBlob, blobPromise, fileName) {{
                return new Promise(function(resolve, reject) {{
                    try {{
                        if (!targetWin || !targetWin.navigator || !targetWin.navigator.clipboard || typeof targetWin.navigator.clipboard.write !== "function" || typeof targetWin.ClipboardItem !== "function") {{
                            reject(new Error("clipboard_image_unavailable"));
                            return;
                        }}
                        if (syncBlob) {{
                            var syncItem = new targetWin.ClipboardItem({{ "image/png": syncBlob }});
                            targetWin.navigator.clipboard.write([syncItem]).then(function() {{ resolve(true); }}, reject);
                            return;
                        }}
                        try {{
                            var promiseItem = new targetWin.ClipboardItem({{ "image/png": blobPromise }});
                            targetWin.navigator.clipboard.write([promiseItem]).then(function() {{ resolve(true); }}, function() {{
                                blobPromise.then(function(resolvedBlob) {{
                                    var fbItem = new targetWin.ClipboardItem({{ "image/png": resolvedBlob }});
                                    return targetWin.navigator.clipboard.write([fbItem]);
                                }}).then(function() {{ resolve(true); }}, reject);
                            }});
                        }} catch (eItem) {{
                            blobPromise.then(function(resolvedBlob) {{
                                var fbItem2 = new targetWin.ClipboardItem({{ "image/png": resolvedBlob }});
                                return targetWin.navigator.clipboard.write([fbItem2]);
                            }}).then(function() {{ resolve(true); }}, reject);
                        }}
                    }} catch (err) {{
                        reject(err);
                    }}
                }});
            }}

            function requestHostBridgeCopyImage(dataUri, fileName) {{
                return new Promise(function(resolve) {{
                    var targets = [];
                    try {{
                        if (window.top && window.top !== window && typeof window.top.postMessage === "function") {{
                            targets.push(window.top);
                        }}
                    }} catch (e1) {{}}
                    try {{
                        if (window.parent && window.parent.parent && window.parent.parent !== window && window.parent.parent !== window.top && typeof window.parent.parent.postMessage === "function") {{
                            targets.push(window.parent.parent);
                        }}
                    }} catch (e2) {{}}
                    if (!targets.length) {{
                        resolve(false);
                        return;
                    }}
                    var reqId = "cpimg_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
                    var done = false;
                    var timer = setTimeout(function() {{
                        if (done) return;
                        done = true;
                        window.removeEventListener("message", onMsg);
                        resolve(false);
                    }}, 1400);
                    function onMsg(ev) {{
                        var d = ev && ev.data;
                        if (!d || d.type !== "CREATA_PROMPTS_COPY_IMAGE_RESULT" || d.requestId !== reqId) return;
                        if (done) return;
                        done = true;
                        clearTimeout(timer);
                        window.removeEventListener("message", onMsg);
                        resolve(Boolean(d.ok));
                    }}
                    window.addEventListener("message", onMsg);
                    var payload = {{
                        type: "CREATA_PROMPTS_COPY_IMAGE",
                        requestId: reqId,
                        dataUri: dataUri,
                        dataUrl: dataUri,
                        fileName: fileName || "foto.png"
                    }};
                    for (var i = 0; i < targets.length; i++) {{
                        try {{ targets[i].postMessage(payload, "*"); }} catch (ePost) {{}}
                    }}
                }});
            }}

            function triggerFallbackDownload(dataUri, fileName) {{
                var a = document.createElement("a");
                a.href = dataUri;
                a.download = fileName || "foto.png";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }}

            function bindCopy(btnId, msgId, dataUri, fileName) {{
                var btn = document.getElementById(btnId);
                var msg = document.getElementById(msgId);
                if (!btn) return;

                var readyPngBlob = null;

                btn.addEventListener("click", async function() {{
                    btn.disabled = true;
                    if (msg) msg.textContent = "Copiando foto...";
                    if (!readyPngBlob) {{
                        readyPngBlob = decodePngDataUriSync(dataUri);
                    }}
                    var activePromise = readyPngBlob
                        ? Promise.resolve(readyPngBlob)
                        : dataUriToPngBlob(dataUri).then(function(b) {{
                            readyPngBlob = b;
                            return b;
                        }});
                    var copiedImage = false;
                    try {{
                        // Nivel 1: Portapapeles directo (ventana actual) — solo imagen PNG, nunca texto
                        try {{
                            await writePngToWindowClipboard(window, readyPngBlob, activePromise, fileName);
                            copiedImage = true;
                        }} catch (eSelf) {{}}

                        // Nivel 2: Documento padre Streamlit del mismo origen (escapa iframe srcdoc sin allow=clipboard-write)
                        if (!copiedImage) {{
                            try {{
                                if (window.parent && window.parent !== window && window.parent.navigator) {{
                                    try {{ if (typeof window.parent.focus === "function") window.parent.focus(); }} catch (eFoc) {{}}
                                    await writePngToWindowClipboard(window.parent, readyPngBlob, activePromise, fileName);
                                    copiedImage = true;
                                }}
                            }} catch (eParent) {{}}
                        }}

                        // Nivel 3: Puente postMessage al host superior (prompts.html / CREATA Suite)
                        if (!copiedImage) {{
                            copiedImage = await requestHostBridgeCopyImage(dataUri, fileName);
                        }}

                        if (copiedImage) {{
                            if (msg) {{
                                msg.textContent = "✅ " + (fileName || "Foto copiada");
                                msg.title = "Foto copiada: " + (fileName || "foto.png");
                            }}
                        }} else {{
                            triggerFallbackDownload(dataUri, fileName);
                            if (msg) {{
                                msg.textContent = "💾 " + (fileName || "Descargada");
                                msg.title = "Foto descargada: " + (fileName || "foto.png");
                            }}
                        }}
                    }} catch (err) {{
                        triggerFallbackDownload(dataUri, fileName);
                        if (msg) {{
                            msg.textContent = "💾 " + (fileName || "Descargada");
                            msg.title = "Foto descargada: " + (fileName || "foto.png");
                        }}
                    }} finally {{
                        btn.disabled = false;
                        setTimeout(function() {{ if (msg) msg.textContent = ""; }}, 3000);
                    }}
                }});
            }}

            {" ".join(js_entries)}
        }})();
        </script>
    </body>
    </html>
    """
    components.html(html_doc, height=comp_height, scrolling=needs_scroll)


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


def load_drive_file_cached(file_id: str) -> Optional[bytes]:
    """Descarga y cachea archivos de Drive en RAM sin envenenar caché con None si falla un intento."""
    if not file_id:
        return None
    from services.sheets_service import sheets_service
    return sheets_service.get_drive_file_bytes(file_id)
