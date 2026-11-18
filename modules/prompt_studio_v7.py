import csv
import io
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from modules.sku_banner import render_sku_autofill_bar
from modules.ui_helpers import load_drive_file_cached, render_copy_button, render_preview_image
from services.ai_prompt_service_v7 import (
    ALL_SINGLE_VIEWS,
    MODES,
    ROOM_PRESETS,
    ai_prompt_service_v7,
)
from services.sheets_service import sheets_service

FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"
IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff"]
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

MATERIAL_MODES = {
    "Solo tela": "fabric_only",
    "Solo madera": "wood_only",
    "Tela + madera": "dual",
}

IMAGE_ENGINES = {
    "Nano Banana 2.1 (Rápido)": "gemini-nano-banana-2.1",
    "Nano Banana Pro (Ultra HD)": "gemini-3-pro-image",
}

SYS_PROMPT_COMPORTAMIENTO = (
    "Eres un Director de Arte experto en Fotografía Comercial de Muebles de Lujo. "
    "Priorizas fidelidad 100% en silueta 3D, aplicación exacta de la textura de tela en todo el casco y cojines "
    "a escala real de tejido, vetas naturales de madera y aislamiento impecable en blanco puro #FFFFFF con 0% sombras."
)


def _scan_local_maderas() -> List[Dict[str, str]]:
    app_dir = Path(__file__).resolve().parent.parent
    maderas_dir = app_dir / "muestras_madera"
    items: List[Dict[str, str]] = []
    seen = set()
    if maderas_dir.exists():
        for f in sorted(maderas_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS:
                clean_name = f.stem.replace("_", " ").strip()
                key = clean_name.upper()
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "id": f.name,
                    "name": clean_name,
                    "filename": f.name,
                    "local_path": str(f),
                })
    return items


@st.cache_data(ttl=300, show_spinner=False)
def cargar_maderas_v7(include_drive: bool = True) -> List[Dict[str, str]]:
    local_maderas = _scan_local_maderas()
    seen = {m["name"].upper() for m in local_maderas}
    drive_maderas: List[Dict[str, str]] = []
    if include_drive:
        try:
            if sheets_service.ensure_connected():
                drive_maderas = sheets_service.get_drive_folder_files(FOLDER_MADERAS_DRIVE_ID, recursive=True)
        except Exception:
            drive_maderas = []
    return local_maderas + [m for m in drive_maderas if m["name"].strip().upper() not in seen]


@st.cache_data(ttl=300, show_spinner=False)
def cargar_telas_v7() -> List[Dict[str, str]]:
    try:
        if sheets_service.ensure_connected():
            return sheets_service.get_drive_folder_files(FOLDER_TELAS_DRIVE_ID, recursive=True)
    except Exception:
        pass
    return []


def _read_files(files: Any) -> Tuple[List[bytes], List[str]]:
    if not files:
        return [], []
    lst = files if isinstance(files, list) else [files]
    data: List[bytes] = []
    names: List[str] = []
    for f in lst:
        data.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
        names.append(getattr(f, "name", "foto.jpg"))
    return data, names


def _num(label: str, key: str) -> float:
    return float(st.number_input(label, min_value=0.0, step=1.0, format="%.0f", key=key))


def _resolve_material_selector(
    kind: str,
    ck: int,
    catalog_items: List[Dict[str, str]],
    sku_fallback: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[bytes], str]:
    """Selector compacto: foto subida > catálogo oficial > auto-carga desde SKU."""
    is_wood = kind == "wood"
    icon = "🪵" if is_wood else "🧵"
    short_lbl = "Madera" if is_wood else "Tela (casco)"
    options = [""] + [item["name"] for item in catalog_items]
    sel_name = st.selectbox(
        f"{icon} {short_lbl} ({len(catalog_items)}):",
        options,
        key=f"v7_sb_{kind}_{ck}",
    )
    up_file = st.file_uploader(
        f"Foto {('madera' if is_wood else 'tela')}:",
        type=IMG_TYPES,
        key=f"v7_up_{kind}_{ck}",
        label_visibility="collapsed",
    )

    if up_file:
        return up_file.getvalue(), getattr(up_file, "name", short_lbl)

    if sel_name:
        match = next((x for x in catalog_items if x["name"].upper() == sel_name.upper()), None)
        if match:
            if match.get("local_path") and os.path.exists(match["local_path"]):
                return Path(match["local_path"]).read_bytes(), sel_name
            if match.get("id"):
                loaded = load_drive_file_cached(match["id"])
                if loaded:
                    return loaded, sel_name

    if sku_fallback and sku_fallback.get("bytes"):
        return sku_fallback["bytes"], sku_fallback.get("name", short_lbl)

    return None, ""


def _render_url_box(urls: Dict[str, str], uid_prefix: str) -> None:
    """Muestra URL oficial de Drive y URL directa CDN con botones de copia en 1 clic."""
    view_url = urls.get("drive_view_url", "")
    cdn_url = urls.get("direct_cdn_url", "")
    st.markdown(
        f"<div style='background:rgba(16,185,129,0.12);border:1px solid #10B981;border-radius:7px;"
        f"padding:6px 10px;margin:4px 0;font-size:11.5px;'>"
        f"🔗 <b>URL Drive (Sheets/Odoo):</b> <a href='{view_url}' target='_blank' style='color:#34D399;'>{view_url}</a><br/>"
        f"🖼️ <b>URL Imagen Directa (2054px CDN):</b> <a href='{cdn_url}' target='_blank' style='color:#38BDF8;'>{cdn_url}</a>"
        f"</div>",
        unsafe_allow_html=True,
    )
    u1, u2 = st.columns(2)
    with u1:
        render_copy_button(view_url, label="📋 Copiar URL Drive", key=f"cp_drv_{uid_prefix}")
    with u2:
        render_copy_button(cdn_url, label="📋 Copiar URL Imagen Directa", key=f"cp_cdn_{uid_prefix}")


def _build_zip(res: Dict[str, Any], include_images: bool = False) -> bytes:
    buf = io.BytesIO()
    url_rows: List[List[str]] = []
    mueble_slug = res.get("mueble_name", "mueble")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, it in enumerate(res.get("items", []), start=1):
            guide = it.get("attachment_guide") or []
            guide_txt = "\n".join(f"  - {g}" for g in guide) if guide else "  - Image 1: Foto del mueble"
            body = (
                f"=== ORDEN DE IMÁGENES ===\n{guide_txt}\n\n"
                f"--- GOOGLE AI STUDIO / GEMINI ---\n{it.get('google_ai_studio', '')}\n\n"
                f"--- CHATGPT (DALL-E 3 / GPT IMAGE) ---\n{it.get('chatgpt_dalle3', '')}\n\n"
                f"--- MIDJOURNEY v6.1 ---\n{it.get('midjourney_v6', '')}\n\n"
                "--- CHECKLIST ---\n"
                + "\n".join(f"- {c}" for c in it.get("checklist", []))
            )
            z.writestr(f"prompts/{i:02d}_{it['id']}.txt", body)

            gen_photo = it.get("generated_photo")
            if isinstance(gen_photo, dict) and gen_photo.get("png"):
                fname_png = f"{i:02d}_{mueble_slug}_{it['id']}_2054x2054.png"
                z.writestr(f"fotos_generadas_2054/{fname_png}", gen_photo["png"])
                u_info = gen_photo.get("urls") or {}
                if u_info.get("drive_view_url"):
                    url_rows.append([
                        it.get("label", it["id"]),
                        fname_png,
                        u_info.get("drive_view_url", ""),
                        u_info.get("direct_cdn_url", ""),
                        u_info.get("download_url", ""),
                    ])

        if res.get("master_ais"):
            z.writestr(
                "prompts/00_prompt_maestro_secuencial.txt",
                res["master_ais"]
                + "\n\n====================\n\n"
                + res.get("master_dal", "")
                + "\n\n====================\n\nMIDJOURNEY:\n"
                + res.get("midjourney", ""),
            )

        render_2054 = res.get("render_2054")
        if isinstance(render_2054, dict) and render_2054.get("png") and not any(
            it.get("generated_photo") for it in res.get("items", [])
        ):
            z.writestr(f"fotos_generadas_2054/{mueble_slug}_3_4_derecha_2054x2054.png", render_2054["png"])

        if url_rows:
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["vista", "archivo", "drive_view_url", "direct_cdn_url_2054", "download_url"])
            writer.writerows(url_rows)
            z.writestr("urls_catalogo.csv", csv_buf.getvalue().encode("utf-8-sig"))

        if include_images:
            for idx, (fname, raw) in enumerate(res.get("ref_images", []), start=1):
                safe_name = os.path.basename(fname or f"referencia_{idx}.jpg")
                z.writestr(f"insumos_originales/{idx:02d}_{safe_name}", raw)
    return buf.getvalue()


def _render_item(
    item: Dict[str, Any],
    idx: int,
    ck: int,
    gen_id: int,
    mueble_slug: str,
    sku_code: str,
    dest_drive: str,
) -> None:
    st.markdown(f"**{item['icon']} {item['label']}**")

    # Si esta vista tiene foto generada en 2054×2054, mostrarla arriba con descarga + botón URL Drive
    gen_photo = item.get("generated_photo")
    if isinstance(gen_photo, dict) and gen_photo.get("png"):
        c_img, c_act = st.columns([1.05, 1.15], vertical_alignment="center")
        with c_img:
            st.image(
                gen_photo["jpg"],
                caption=f"{item.get('short_name', item['id'])} · {gen_photo['width']}×{gen_photo['height']} px",
                use_container_width=True,
            )
        with c_act:
            st.success(f"✅ **{gen_photo['width']} × {gen_photo['height']} px** ({gen_photo.get('model', 'IA')})")
            d_p, d_j = st.columns(2)
            fname_base = f"{sku_code or mueble_slug}_{item['id']}_2054x2054"
            with d_p:
                st.download_button(
                    "💾 PNG 2054",
                    data=gen_photo["png"],
                    file_name=f"{fname_base}.png",
                    mime="image/png",
                    use_container_width=True,
                    key=f"v7_it_png_{idx}_{ck}_{gen_id}",
                )
            with d_j:
                st.download_button(
                    "💾 JPG 2054",
                    data=gen_photo["jpg"],
                    file_name=f"{fname_base}.jpg",
                    mime="image/jpeg",
                    use_container_width=True,
                    key=f"v7_it_jpg_{idx}_{ck}_{gen_id}",
                )

            existing_urls = gen_photo.get("urls")
            if existing_urls:
                _render_url_box(existing_urls, f"it_{idx}_{ck}_{gen_id}")
            else:
                if st.button(
                    "🔗 Subir a Drive y Obtener URL",
                    key=f"v7_btn_url_it_{idx}_{ck}_{gen_id}",
                    use_container_width=True,
                ):
                    try:
                        urls = sheets_service.publish_photo_and_get_urls(
                            file_bytes=gen_photo["png"],
                            filename=f"{fname_base}.png",
                            dest=dest_drive,
                            subfolder=sku_code or mueble_slug,
                            metadata={"sku": sku_code, "vista": item["id"], "res": "2054x2054"},
                        )
                        gen_photo["urls"] = urls
                        st.rerun()
                    except Exception as up_err:  # noqa: BLE001
                        st.error(f"❌ Error subiendo a Drive: {up_err}")
    elif item.get("preview_bytes"):
        render_preview_image(item["preview_bytes"], caption=item["label"], max_dim=260)

    guide = item.get("attachment_guide") or []
    if guide:
        bullets = " &nbsp;|&nbsp; ".join(f"<b>{g}</b>" for g in guide)
        st.markdown(
            f"<div style='background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.35);"
            f"border-radius:6px;padding:5px 9px;margin-bottom:6px;font-size:11.5px;color:#E2E8F0;'>"
            f"📎 {bullets}</div>",
            unsafe_allow_html=True,
        )

    with st.expander("📝 Ver / Copiar Prompts de respaldo", expanded=not bool(gen_photo)):
        t_ais, t_dal, t_mj = st.tabs(["🌐 AI Studio / Gemini", "🤖 ChatGPT", "🎨 Midjourney"])
        with t_ais:
            txt = item.get("google_ai_studio", "")
            render_copy_button(
                txt,
                label=f"📋 Copiar ({item.get('short_name', 'AI Studio')})",
                key=f"v7_cp_ais_{idx}_{ck}_{gen_id}",
            )
            st.text_area("AI Studio:", txt, height=180, key=f"v7_ais_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
        with t_dal:
            txt = item.get("chatgpt_dalle3", "")
            render_copy_button(
                txt,
                label=f"📋 Copiar ({item.get('short_name', 'ChatGPT')})",
                key=f"v7_cp_dal_{idx}_{ck}_{gen_id}",
            )
            st.text_area("ChatGPT:", txt, height=170, key=f"v7_dal_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
        with t_mj:
            txt = item.get("midjourney_v6", "")
            render_copy_button(
                txt,
                label=f"📋 Copiar ({item.get('short_name', 'Midjourney')})",
                key=f"v7_cp_mj_{idx}_{ck}_{gen_id}",
            )
            st.text_area("Midjourney:", txt, height=110, key=f"v7_mj_{idx}_{ck}_{gen_id}", label_visibility="collapsed")


def _generate_photos_batch_for_res(
    res: Dict[str, Any],
    mode: str,
    primary_bytes: bytes,
    wood_bytes: Optional[bytes],
    fabric_bytes: Optional[bytes],
    ref_bytes: List[bytes],
    batch_views_files: List[Tuple[str, bytes]],
    white_bg_enabled: bool,
    img_engine: str,
    auto_upload_url: bool,
    dest_drive: str,
    sku_code: str,
    mueble_slug: str,
    status_placeholder: Any,
) -> Optional[str]:
    """Genera las fotos reales en 2054×2054 px para todos los ítems del resultado (con encadenamiento Vista 1 -> Anchor y URL Drive)."""
    items = res.get("items", [])
    if not items:
        return "No hay ítems para renderizar."

    anchor_vista1_bytes: Optional[bytes] = None
    first_error: Optional[str] = None
    total = len(items)

    for idx, it in enumerate(items, start=1):
        vid = it.get("id", f"vista_{idx}")
        status_placeholder.info(f"🎨 Generando foto {idx}/{total}: **{it.get('short_name', vid)}** en 2054×2054 px...")

        is_env = vid == "vista_entorno_cliente"
        pure_white = (not is_env) and (white_bg_enabled or mode in ("catalogo", "plano", "extraer", "vista_34_der_2054"))

        if mode in ("vistas_tela", "clonar_color") and idx - 1 < len(batch_views_files):
            # En modos lote: Image 1 es la muestra/referencia, Image 2 es la vista objetivo
            ref_master = fabric_bytes if mode == "vistas_tela" else primary_bytes
            target_view_bytes = batch_views_files[idx - 1][1]
            img_out, err = ai_prompt_service_v7.generate_catalog_photo(
                prompt_text=it.get("google_ai_studio", ""),
                primary_bytes=ref_master or target_view_bytes,
                wood_bytes=target_view_bytes if ref_master else None,
                pure_white_border=white_bg_enabled,
                preferred_image_model=img_engine,
            )
        else:
            use_anc = anchor_vista1_bytes if (it.get("needs_anchor") and anchor_vista1_bytes) else None
            img_out, err = ai_prompt_service_v7.generate_catalog_photo(
                prompt_text=it.get("google_ai_studio", ""),
                primary_bytes=primary_bytes,
                wood_bytes=wood_bytes,
                fabric_bytes=fabric_bytes,
                ref_bytes=ref_bytes,
                anchor_bytes=use_anc,
                pure_white_border=pure_white,
                preferred_image_model=img_engine,
            )

        if img_out:
            if vid == "vista_frontal" and anchor_vista1_bytes is None:
                anchor_vista1_bytes = img_out["png"]
            if auto_upload_url:
                try:
                    fname_up = f"{sku_code or mueble_slug}_{vid}_2054x2054.png"
                    urls = sheets_service.publish_photo_and_get_urls(
                        file_bytes=img_out["png"],
                        filename=fname_up,
                        dest=dest_drive,
                        subfolder=sku_code or mueble_slug,
                        metadata={"sku": sku_code, "vista": vid, "res": "2054x2054"},
                    )
                    img_out["urls"] = urls
                except Exception as up_e:  # noqa: BLE001
                    print(f"[StudioV7] Aviso subiendo a Drive ({vid}): {up_e}")
            it["generated_photo"] = img_out
        else:
            first_error = err
            # Si es error de autenticación/API key filtrada, detener de inmediato para no repetir llamadas fallidas
            if err and any(k in err.upper() for k in ("BLOQUEADA", "FILTRADA", "403", "NO ES VÁLIDA", "NO HAY GEMINI_API_KEY")):
                break

    return first_error


def render_prompt_studio_v7() -> None:
    if "clear_key_v7" not in st.session_state:
        st.session_state.clear_key_v7 = 0
    ck = st.session_state.clear_key_v7

    st.markdown(
        """
<style>
/* Diseño horizontal compacto y 100% adaptable a cualquier tamaño de pantalla */
.stButton > button {
    white-space: normal !important;
    font-size: clamp(11.5px, 0.9vw, 13px) !important;
    font-weight: 600 !important;
    height: auto !important;
    min-height: 36px !important;
    padding: 5px 10px !important;
}
div[role="radiogroup"][aria-orientation="horizontal"] {
    gap: 5px !important;
    flex-wrap: wrap !important;
}
div[role="radiogroup"][aria-orientation="horizontal"] > label {
    background: #1E293B !important;
    border: 1px solid #475569 !important;
    border-radius: 999px !important;
    padding: 2px 10px !important;
    margin: 0 !important;
    font-size: clamp(11px, 0.85vw, 12.5px) !important;
}
section[data-testid="stFileUploaderDropzone"] {
    padding: 6px 10px !important;
    min-height: 54px !important;
}
section[data-testid="stFileUploaderDropzone"] small {
    display: none !important;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.45rem !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # =====================================================================
    # ENCABEZADO SUPERIOR DE MODO, MOTOR DE FOTOS/URL Y BORRAR
    # =====================================================================
    with st.container(border=True):
        top_modes, top_cfg, top_role, top_clear = st.columns([3.7, 0.95, 0.75, 0.6], vertical_alignment="center")
        with top_modes:
            mode_labels = list(MODES.values())
            if st.session_state.get("v7_keep_mode") not in mode_labels:
                st.session_state["v7_keep_mode"] = mode_labels[0]
            mode_label = st.radio(
                "Modo:",
                mode_labels,
                horizontal=True,
                key="v7_keep_mode",
                label_visibility="collapsed",
            )
            mode = next(k for k, v in MODES.items() if v == mode_label)

        with top_cfg:
            has_active_key = bool(ai_prompt_service_v7.get_api_key())
            lbl_cfg = "⚙️ Motor & URL" if has_active_key else "🔑 API & URL"
            with st.popover(lbl_cfg, use_container_width=True):
                st.markdown("**🔑 Gemini API Key (Fotos directas IA)**")
                custom_k = st.text_input(
                    "Pega tu GEMINI_API_KEY nueva (AI Studio):",
                    value=st.session_state.get("v7_custom_api_key", ""),
                    type="password",
                    placeholder="AIzaSy...",
                    key="v7_keep_apikey_input",
                )
                if custom_k.strip() != st.session_state.get("v7_custom_api_key", ""):
                    st.session_state["v7_custom_api_key"] = custom_k.strip()
                if st.button("💾 Guardar llave en .env local (no sube a Git)", use_container_width=True, key="v7_save_env"):
                    if custom_k.strip():
                        env_file = Path(__file__).resolve().parent.parent / ".env"
                        env_file.write_text(f"GEMINI_API_KEY={custom_k.strip()}\n", encoding="utf-8")
                        st.success("✅ Guardada en .env local.")
                    else:
                        st.warning("Pega primero una llave válida.")

                eng_labels = list(IMAGE_ENGINES.keys())
                if st.session_state.get("v7_keep_engine") not in eng_labels:
                    st.session_state["v7_keep_engine"] = eng_labels[0]
                eng_sel = st.radio("Motor fotográfico:", eng_labels, key="v7_keep_engine")
                img_engine = IMAGE_ENGINES[eng_sel]

                st.markdown("---")
                st.markdown("**☁️ Publicación con URL (Google Drive)**")
                auto_upload_url = st.toggle(
                    "Subir fotos automáticamente y dar URL",
                    value=True,
                    key="v7_keep_autourl",
                )
                dest_lbl = st.radio(
                    "Carpeta Drive:",
                    ["📥 Buzón Staging", "📁 Fotos Final (por SKU)"],
                    horizontal=True,
                    key="v7_keep_drivedest",
                )
                dest_drive = "final" if "Final" in dest_lbl else "buzon"

        img_engine = IMAGE_ENGINES.get(
            st.session_state.get("v7_keep_engine", list(IMAGE_ENGINES.keys())[0]),
            "gemini-nano-banana-2.1",
        )
        auto_upload_url = bool(st.session_state.get("v7_keep_autourl", True))
        dest_drive = "final" if "Final" in str(st.session_state.get("v7_keep_drivedest", "")) else "buzon"

        with top_role:
            render_copy_button(SYS_PROMPT_COMPORTAMIENTO, label="🧠 Rol IA", key=f"v7_comp_{ck}")

        with top_clear:
            if st.button("🗑️ Borrar", use_container_width=True, key="v7_btn_clear"):
                # Limpia insumos, SKU, medidas, notas y resultados SIN mover la opción ni configuración activa
                clear_prefixes = (
                    "v7_result",
                    "v7_render_2054",
                    "v7_sku_assets_",
                    "v7_w_",
                    "v7_h_",
                    "v7_d_",
                    "v7_diam_",
                    "v7_med_src_",
                    "v7_notas_",
                    "v7_sb_",
                    "v7_up_",
                    "v7_mueble_",
                    "v7_batch_",
                    "v7_clone_",
                    "v7_ref_",
                    "v7_ext2054_",
                    "sku_",
                    "field_",
                )
                for k in [k for k in list(st.session_state.keys()) if k.startswith(clear_prefixes)]:
                    del st.session_state[k]
                st.session_state.clear_key_v7 = ck + 1
                st.rerun()

        vista_id = "vista_3_4_derecha"
        material_mode = "fabric_only"
        lugar_casa = ""

        if mode == "vista_suelta":
            view_opts = {k: v["label"] for k, v in ALL_SINGLE_VIEWS.items()}
            view_labels = list(view_opts.values())
            if st.session_state.get("v7_keep_vista") not in view_labels:
                st.session_state["v7_keep_vista"] = view_opts["vista_3_4_derecha"]
            vsel = st.radio("Ángulo:", view_labels, horizontal=True, key="v7_keep_vista", label_visibility="collapsed")
            vista_id = next(k for k, v in view_opts.items() if v == vsel)
        elif mode == "material":
            mat_labels = list(MATERIAL_MODES.keys())
            if st.session_state.get("v7_keep_matmode") not in mat_labels:
                st.session_state["v7_keep_matmode"] = mat_labels[0]
            msel = st.radio("Material:", mat_labels, horizontal=True, key="v7_keep_matmode", label_visibility="collapsed")
            material_mode = MATERIAL_MODES[msel]

        if mode in ("catalogo", "entorno") or (mode == "vista_suelta" and vista_id == "vista_entorno_cliente"):
            room_opts = ROOM_PRESETS + ["Otra"]
            if st.session_state.get("v7_keep_room") not in room_opts:
                st.session_state["v7_keep_room"] = room_opts[0]
            r_col1, r_col2 = st.columns([2.2, 1.8], vertical_alignment="center")
            with r_col1:
                room_preset = st.radio("🏡 Espacio:", room_opts, horizontal=True, key="v7_keep_room", label_visibility="collapsed")
            with r_col2:
                if room_preset == "Otra":
                    lugar_casa = st.text_input(
                        "Espacio:",
                        placeholder="Ej: Sala minimalista",
                        key="v7_keep_room_custom",
                        label_visibility="collapsed",
                    )
                else:
                    lugar_casa = room_preset

        # Fila 2 del encabezado: SKU + Auto-carga Drive + Medidas + Toggles
        sku = render_sku_autofill_bar("v7", inline_header=True)
        sku_code = (sku.get("sku") or "").strip().upper()
        tipo = sku["tipo_mueble"]
        medidas = sku["medidas"]
        sku_loaded = sku.get("data_loaded") or {}

        # Botón opcional para jalar fotos registradas del SKU directamente desde Google Drive
        has_sku_media = any(
            sku_loaded.get(f) for f in ("foto_mueble_nom", "foto_tela_nom", "foto_madera_nom")
        )
        if has_sku_media:
            if st.button(
                f"📥 Traer fotos del SKU {sku_code} desde Drive",
                key=f"v7_pull_sku_drive_{ck}",
            ):
                with st.spinner("Descargando fotos del SKU desde Google Drive..."):
                    st.session_state[f"v7_sku_assets_{ck}"] = sheets_service.fetch_sku_assets_from_drive(sku_loaded)

        sku_assets = st.session_state.get(f"v7_sku_assets_{ck}") or {}

        src_key = f"v7_med_src_{ck}"
        if src_key not in st.session_state or st.session_state[src_key] != medidas:
            d_init = ai_prompt_service_v7.parse_dimensions(tipo, medidas)
            st.session_state[f"v7_w_{ck}"] = float(d_init["width_cm"] or 0)
            st.session_state[f"v7_h_{ck}"] = float(d_init["height_cm"] or 0)
            st.session_state[f"v7_d_{ck}"] = float(d_init["depth_cm"] or 0)
            st.session_state[f"v7_diam_{ck}"] = float(d_init["diam_cm"] or 0)
            st.session_state[src_key] = medidas

        d1, d2, d3, d4, d5, d6 = st.columns([0.85, 0.85, 0.85, 0.85, 1.0, 1.0], vertical_alignment="bottom")
        with d1:
            w = _num("Ancho cm", f"v7_w_{ck}")
        with d2:
            h = _num("Alto cm", f"v7_h_{ck}")
        with d3:
            d_ = _num("Fondo cm", f"v7_d_{ck}")
        with d4:
            diam = _num("Diám. cm", f"v7_diam_{ck}")
        with d5:
            white_bg_enabled = st.toggle("⬜ Fondo blanco", value=True, key="v7_keep_whitebg")
        with d6:
            classic_num = st.toggle("🔙 Num. clásica", value=False, key="v7_keep_classic")

        medidas_final = ai_prompt_service_v7.compose_dimensions_text(w, d_, h, diam)

    # =====================================================================
    # PANEL PRINCIPAL ADAPTATIVO (IZQUIERDA: INSUMOS | DERECHA: FOTOS + URLS)
    # =====================================================================
    m_bytes: List[bytes] = []
    m_names: List[str] = []
    r_bytes: List[bytes] = []
    r_names: List[str] = []
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""

    col_work, col_out = st.columns([1.12, 1.38], gap="medium")

    with col_work:
        with st.container(border=True):
            if mode == "vistas_tela":
                u1, u2 = st.columns(2)
                with u1:
                    up_views = st.file_uploader(
                        "🖼️ Vistas del mueble:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_batch_views_{ck}",
                    )
                    vb, vn = _read_files(up_views)
                    batch_views_files = list(zip(vn, vb))
                with u2:
                    fabric_bytes, fabric_name = _resolve_material_selector(
                        "fabric", ck, cargar_telas_v7(), sku_fallback=sku_assets.get("tela")
                    )
            elif mode == "clonar_color":
                u1, u2 = st.columns(2)
                with u1:
                    up_ref_color = st.file_uploader(
                        "🎨 Foto maestra (color):",
                        type=IMG_TYPES,
                        accept_multiple_files=False,
                        key=f"v7_clone_ref_{ck}",
                    )
                    m_bytes, m_names = _read_files(up_ref_color)
                with u2:
                    up_views = st.file_uploader(
                        "🖼️ Vistas objetivo:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_clone_targets_{ck}",
                    )
                    vb, vn = _read_files(up_views)
                    batch_views_files = list(zip(vn, vb))
            else:
                u_m, u_f, u_w = st.columns(3)
                with u_m:
                    up_mueble = st.file_uploader(
                        "🛋️ Foto mueble:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_mueble_{ck}",
                    )
                    m_bytes, m_names = _read_files(up_mueble)
                    if not m_bytes and sku_assets.get("mueble", {}).get("bytes"):
                        m_bytes = [sku_assets["mueble"]["bytes"]]
                        m_names = [sku_assets["mueble"]["filename"]]
                with u_f:
                    if mode != "material" or material_mode in ("fabric_only", "dual"):
                        fabric_bytes, fabric_name = _resolve_material_selector(
                            "fabric", ck, cargar_telas_v7(), sku_fallback=sku_assets.get("tela")
                        )
                with u_w:
                    if mode != "material" or material_mode in ("wood_only", "dual"):
                        wood_bytes, wood_name = _resolve_material_selector(
                            "wood", ck, cargar_maderas_v7(), sku_fallback=sku_assets.get("madera")
                        )

            n_col, ref_col = st.columns([2.2, 1.0], vertical_alignment="bottom")
            with n_col:
                notas = st.text_input(
                    "📝 Notas:",
                    key=f"v7_notas_{ck}",
                    placeholder="Opcional: detalles de casco, costuras o madera...",
                )
            with ref_col:
                if mode not in ("vistas_tela", "clonar_color", "plano"):
                    with st.popover("📐 Ángulos extra", use_container_width=True):
                        up_ref = st.file_uploader(
                            "Referencias extra:",
                            type=IMG_TYPES,
                            accept_multiple_files=True,
                            key=f"v7_ref_{ck}",
                        )
                        r_bytes, r_names = _read_files(up_ref)

            # Botones de acción directa: 1) 3/4 Derecha 2054×2054 + URL | 2) Hacer Fotos IA del Modo | 3) Solo Prompts
            b_34, b_foto_mode, b_prompts = st.columns([1.35, 1.1, 0.75])
            with b_34:
                btn_34_2054 = st.button(
                    "↘️ 3/4 Derecha · 2054×2054 + URL",
                    type="primary",
                    use_container_width=True,
                    key=f"v7_btn_34_2054_{ck}",
                )
            with b_foto_mode:
                btn_make_photos = st.button(
                    "📸 Hacer Foto(s)",
                    use_container_width=True,
                    key=f"v7_btn_photos_{ck}",
                )
            with b_prompts:
                go = st.button(
                    "📝 Prompts",
                    use_container_width=True,
                    key=f"v7_btn_go_{ck}",
                )

            thumbs: List[Tuple[str, bytes]] = []
            for nm, raw in zip(m_names[:2], m_bytes[:2]):
                thumbs.append((f"🛋️ {nm}", raw))
            if fabric_bytes:
                thumbs.append((f"🧵 {fabric_name or 'Tela'}", fabric_bytes))
            if wood_bytes:
                thumbs.append((f"🪵 {wood_name or 'Madera'}", wood_bytes))
            for vn, vb in batch_views_files[:2]:
                thumbs.append((f"🖼️ {vn}", vb))

            if thumbs:
                t_cols = st.columns(len(thumbs))
                for tc, (lbl, raw_b) in zip(t_cols, thumbs):
                    with tc:
                        render_preview_image(raw_b, caption=lbl, max_dim=170)

        # ------------------------------------------------------------------ ACCIÓN 1: BOTÓN 3/4 DERECHA · 2054×2054 + URL
        if btn_34_2054:
            target_furn_bytes = m_bytes or ([batch_views_files[0][1]] if batch_views_files else [])
            target_furn_names = m_names or ([batch_views_files[0][0]] if batch_views_files else [])
            if not target_furn_bytes:
                st.error("⚠️ Sube primero la foto del mueble (o tráela por SKU).")
            else:
                status = st.empty()
                try:
                    name = sku_code or (target_furn_names[0].rsplit(".", 1)[0] if target_furn_names else "Mueble")
                    notas_ia = "\n".join(
                        p
                        for p in [
                            f"Tipo de mueble: {tipo}" if tipo else "",
                            f"Medidas exactas: {medidas_final}" if medidas_final else "",
                            notas.strip(),
                        ]
                        if p
                    )
                    has_key = bool(ai_prompt_service_v7.get_api_key())
                    status.info("⏳ Analizando casco, tela y geometría...")

                    f_ana = ai_prompt_service_v7.analyze_furniture_for_enhancement(
                        furniture_bytes=target_furn_bytes,
                        reference_bytes=r_bytes,
                        wood_bytes=[wood_bytes] if wood_bytes else None,
                        fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                        notas_usuario=notas_ia,
                    )
                    w_ana = (
                        ai_prompt_service_v7.analyze_material(wood_bytes, material_type="wood", sample_name=wood_name)
                        if wood_bytes
                        else None
                    )
                    t_ana = (
                        ai_prompt_service_v7.analyze_material(
                            fabric_bytes, material_type="fabric", sample_name=fabric_name
                        )
                        if fabric_bytes
                        else None
                    )

                    res = ai_prompt_service_v7.build_34_derecha_2054_prompts(
                        furniture_name=name,
                        furniture_analysis=f_ana,
                        wood_analysis=w_ana,
                        fabric_analysis=t_ana,
                        notas_usuario=notas.strip(),
                        tipo_mueble=tipo,
                        medidas_texto=medidas_final,
                        wood_label=wood_name,
                        fabric_label=fabric_name,
                        has_reference_imgs=bool(r_bytes),
                        classic_numbering=classic_num,
                    )

                    render_2054 = None
                    img_err = None
                    if has_key:
                        status.info("🎨 Generando fotografía 3/4 Derecha en 2054×2054 px (#FFFFFF, 0% sombras)...")
                        render_2054, img_err = ai_prompt_service_v7.generate_catalog_photo(
                            prompt_text=res["items"][0]["google_ai_studio"],
                            primary_bytes=target_furn_bytes[0],
                            wood_bytes=wood_bytes,
                            fabric_bytes=fabric_bytes,
                            ref_bytes=r_bytes,
                            pure_white_border=True,
                            preferred_image_model=img_engine,
                        )
                        if render_2054:
                            if auto_upload_url:
                                status.info("☁️ Subiendo foto 2054×2054 a Google Drive y creando URL pública...")
                                try:
                                    urls = sheets_service.publish_photo_and_get_urls(
                                        file_bytes=render_2054["png"],
                                        filename=f"{name}_3_4_derecha_2054x2054.png",
                                        dest=dest_drive,
                                        subfolder=sku_code or name,
                                        metadata={"sku": sku_code, "vista": "3_4_derecha", "res": "2054x2054"},
                                    )
                                    render_2054["urls"] = urls
                                except Exception as up_e:  # noqa: BLE001
                                    print(f"[StudioV7] Aviso subiendo a Drive: {up_e}")
                            res["items"][0]["generated_photo"] = render_2054

                    ref_imgs: List[Tuple[str, bytes]] = list(zip(target_furn_names, target_furn_bytes))
                    if wood_bytes:
                        ref_imgs.append((f"madera_{wood_name or 'muestra'}.jpg", wood_bytes))
                    if fabric_bytes:
                        ref_imgs.append((f"tela_{fabric_name or 'muestra'}.jpg", fabric_bytes))

                    gen_key = f"v7_gen_id_{ck}"
                    gen_id = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[gen_key] = gen_id
                    res["gen_id"] = gen_id
                    res["mueble_name"] = name
                    res["analysis"] = f_ana
                    res["wood_analysis"] = w_ana
                    res["fabric_analysis"] = t_ana
                    res["ref_images"] = ref_imgs
                    res["render_2054"] = render_2054
                    res["image_error"] = img_err
                    st.session_state["v7_result"] = res
                    if render_2054:
                        st.session_state["v7_render_2054"] = render_2054
                        status.success("✅ ¡Foto 2054×2054 y URL listas!")
                    elif img_err:
                        status.warning(f"⚠️ Prompt listo. {img_err}")
                    else:
                        status.success("✅ ¡Prompt 3/4 Derecha · 2054×2054 listo!")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error: {e}")

        # ------------------------------------------------------------------ ACCIÓN 2 & 3: HACER FOTOS IA DEL MODO / SOLO PROMPTS
        if btn_make_photos or go:
            err = None
            if mode == "vistas_tela":
                if not batch_views_files:
                    err = "⚠️ Sube al menos una vista del mueble."
                elif not fabric_bytes:
                    err = "⚠️ Selecciona o sube la muestra de tela."
            elif mode == "clonar_color":
                if not m_bytes:
                    err = "⚠️ Sube la foto maestra con el color correcto."
                elif not batch_views_files:
                    err = "⚠️ Sube al menos una vista a recolorear."
            else:
                if not m_bytes:
                    err = "⚠️ Sube la foto del mueble (o tráela por SKU)."
                elif mode == "material" and material_mode in ("wood_only", "dual") and not wood_bytes:
                    err = "⚠️ Selecciona o sube muestra de madera."
                elif mode == "material" and material_mode in ("fabric_only", "dual") and not fabric_bytes:
                    err = "⚠️ Selecciona o sube muestra de tela."

            if err:
                st.error(err)
            else:
                status = st.empty()
                try:
                    name = sku_code or (
                        m_names[0].rsplit(".", 1)[0]
                        if m_names
                        else (batch_views_files[0][0].rsplit(".", 1)[0] if batch_views_files else "Mueble")
                    )
                    notas_ia = "\n".join(
                        p
                        for p in [
                            f"Tipo de mueble: {tipo}" if tipo else "",
                            f"Medidas exactas: {medidas_final}" if medidas_final else "",
                            notas.strip(),
                        ]
                        if p
                    )

                    has_key = bool(ai_prompt_service_v7.get_api_key())
                    status.info("⏳ Analizando con Gemini..." if has_key else "🧩 Construyendo prompts...")

                    f_ana: Dict[str, Any] = {}
                    w_ana: Optional[Dict[str, Any]] = None
                    t_ana: Optional[Dict[str, Any]] = None

                    if mode not in ("vistas_tela", "clonar_color"):
                        f_ana = ai_prompt_service_v7.analyze_furniture_for_enhancement(
                            furniture_bytes=m_bytes,
                            reference_bytes=r_bytes,
                            wood_bytes=[wood_bytes] if wood_bytes else None,
                            fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                            notas_usuario=notas_ia,
                        )
                    if wood_bytes:
                        w_ana = ai_prompt_service_v7.analyze_material(
                            wood_bytes, material_type="wood", sample_name=wood_name
                        )
                    if fabric_bytes:
                        t_ana = ai_prompt_service_v7.analyze_material(
                            fabric_bytes, material_type="fabric", sample_name=fabric_name
                        )

                    batch_ref = fabric_bytes if mode == "vistas_tela" else (m_bytes[0] if mode == "clonar_color" else None)

                    res = ai_prompt_service_v7.build_prompts(
                        mode=mode,
                        furniture_name=name,
                        furniture_analysis=f_ana,
                        wood_analysis=w_ana,
                        fabric_analysis=t_ana,
                        notas_usuario=notas.strip(),
                        tipo_mueble=tipo,
                        medidas_texto=medidas_final,
                        lugar_casa=lugar_casa,
                        vista_id=vista_id,
                        material_mode=material_mode,
                        wood_label=wood_name,
                        fabric_label=fabric_name,
                        has_reference_imgs=bool(r_bytes),
                        white_bg_enabled=white_bg_enabled,
                        classic_numbering=classic_num,
                        batch_ref_bytes=batch_ref,
                        batch_views=batch_views_files,
                    )

                    img_err_batch = None
                    if btn_make_photos:
                        prim = m_bytes[0] if m_bytes else (batch_views_files[0][1] if batch_views_files else b"")
                        img_err_batch = _generate_photos_batch_for_res(
                            res=res,
                            mode=mode,
                            primary_bytes=prim,
                            wood_bytes=wood_bytes,
                            fabric_bytes=fabric_bytes,
                            ref_bytes=r_bytes,
                            batch_views_files=batch_views_files,
                            white_bg_enabled=white_bg_enabled,
                            img_engine=img_engine,
                            auto_upload_url=auto_upload_url,
                            dest_drive=dest_drive,
                            sku_code=sku_code,
                            mueble_slug=name,
                            status_placeholder=status,
                        )

                    ref_imgs = list(zip(m_names, m_bytes))
                    if wood_bytes:
                        ref_imgs.append((f"madera_{wood_name or 'muestra'}.jpg", wood_bytes))
                    if fabric_bytes:
                        ref_imgs.append((f"tela_{fabric_name or 'muestra'}.jpg", fabric_bytes))
                    for vn, vb in batch_views_files:
                        ref_imgs.append((vn, vb))
                    for rn, rb in zip(r_names, r_bytes):
                        ref_imgs.append((rn, rb))

                    gen_key = f"v7_gen_id_{ck}"
                    gen_id = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[gen_key] = gen_id
                    res["gen_id"] = gen_id
                    res["mueble_name"] = name
                    res["analysis"] = f_ana
                    res["wood_analysis"] = w_ana
                    res["fabric_analysis"] = t_ana
                    res["ref_images"] = ref_imgs
                    res["image_error"] = img_err_batch
                    st.session_state.pop("v7_render_2054", None)
                    st.session_state["v7_result"] = res

                    rendered_count = sum(1 for it in res.get("items", []) if it.get("generated_photo"))
                    if btn_make_photos and rendered_count > 0:
                        status.success(f"✅ ¡{rendered_count} foto(s) 2054×2054 y URLs generadas!")
                    elif img_err_batch:
                        status.warning(f"⚠️ Prompts listos. {img_err_batch}")
                    else:
                        status.success("✅ ¡Prompts listos!")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error: {e}")

    # ------------------------------------------------------------------ COLUMNA DERECHA: FOTOS GENERADAS, URLS Y PROMPTS
    with col_out:
        with st.container(border=True):
            res = st.session_state.get("v7_result")
            if not res:
                st.caption(
                    "👈 Sube la foto (o cárgala por SKU) y pulsa **↘️ 3/4 Derecha · 2054×2054 + URL** o **📸 Hacer Foto(s)**."
                )
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")

            if res.get("image_error"):
                st.warning(res["image_error"])

            head_res, head_chk, head_zip = st.columns([1.4, 0.9, 1.1], vertical_alignment="center")
            with head_res:
                st.markdown(f"**✨ {mueble_slug}**")
            with head_chk:
                inc_imgs = st.checkbox("Insumos en .zip", value=True, key=f"v7_zip_imgs_{ck}")
            with head_zip:
                st.download_button(
                    "📦 Kit Fotos + URLs (.zip)",
                    data=_build_zip(res, include_images=inc_imgs),
                    file_name=f"kit_v7_{res.get('mode')}_{mueble_slug}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"v7_dl_{ck}_{gen_id}",
                )

            # Herramienta universal: Ajustar cualquier imagen a 2054×2054 #FFFFFF + Subir a Drive con URL
            any_rendered = any(it.get("generated_photo") for it in res.get("items", []))
            with st.expander(
                "📐 Ajustar foto externa a 2054×2054 (#FFFFFF) y crear URL en Drive",
                expanded=(res.get("mode") == "vista_34_der_2054" and not any_rendered),
            ):
                ext_up = st.file_uploader(
                    "Sube cualquier render para convertirlo a 2054×2054 px exactos (#FFFFFF) y obtener su URL:",
                    type=IMG_TYPES,
                    key=f"v7_ext2054_{ck}_{gen_id}",
                    label_visibility="collapsed",
                )
                if ext_up:
                    fmt_img = ai_prompt_service_v7.format_image_2054_white(ext_up.getvalue(), target_px=2054)
                    c_p, c_j, c_u = st.columns(3)
                    with c_p:
                        st.download_button(
                            "💾 PNG 2054×2054",
                            data=fmt_img["png"],
                            file_name=f"{mueble_slug}_2054x2054.png",
                            mime="image/png",
                            use_container_width=True,
                            key=f"v7_ext_png_{ck}_{gen_id}",
                        )
                    with c_j:
                        st.download_button(
                            "💾 JPG 2054×2054",
                            data=fmt_img["jpg"],
                            file_name=f"{mueble_slug}_2054x2054.jpg",
                            mime="image/jpeg",
                            use_container_width=True,
                            key=f"v7_ext_jpg_{ck}_{gen_id}",
                        )
                    with c_u:
                        if st.button(
                            "🔗 Subir y dar URL",
                            use_container_width=True,
                            key=f"v7_ext_url_btn_{ck}_{gen_id}",
                        ):
                            try:
                                st.session_state[f"v7_ext_urls_{ck}_{gen_id}"] = sheets_service.publish_photo_and_get_urls(
                                    file_bytes=fmt_img["png"],
                                    filename=f"{sku_code or mueble_slug}_2054x2054.png",
                                    dest=dest_drive,
                                    subfolder=sku_code or mueble_slug,
                                    metadata={"sku": sku_code, "res": "2054x2054"},
                                )
                            except Exception as e_up:  # noqa: BLE001
                                st.error(f"❌ Error Drive: {e_up}")
                    ext_urls = st.session_state.get(f"v7_ext_urls_{ck}_{gen_id}")
                    if ext_urls:
                        _render_url_box(ext_urls, f"ext_{ck}_{gen_id}")

            items = res.get("items", [])
            if len(items) > 1:
                tabs = st.tabs([f"{i['icon']} {i['short_name']}" for i in items])
                for idx, (tab, item) in enumerate(zip(tabs, items)):
                    with tab:
                        _render_item(item, idx, ck, gen_id, mueble_slug, sku_code, dest_drive)
            elif items:
                _render_item(items[0], 0, ck, gen_id, mueble_slug, sku_code, dest_drive)
