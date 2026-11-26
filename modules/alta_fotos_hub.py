import os
from typing import Dict, List, Tuple

import streamlit as st
import streamlit.components.v1 as components

from modules.ui_helpers import render_loaded_photos_strip
from services.ai_prompt_service_v7 import ai_prompt_service_v7
from services.sheets_service import BUZON_DRIVE_ID, RENDER_DRIVE_ID, sheets_service

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff", "jfif", "avif"]
DOC_TYPES = ["pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "ppt", "pptx", "zip"]
IMG_AND_DOC_TYPES = IMG_TYPES + DOC_TYPES
_IMG_EXT_SET = {f".{ext.lower()}" for ext in IMG_TYPES}

ODOO_DEST_FOLDERS: Dict[str, Tuple[str, str]] = {
    "🛋️ FOTOS MUEBLES": ("10UIhDWLKL0ySmzdcMemA5K5831YozuBa", "MUEBLE"),
    "🪞 FOTOS ACCESORIOS": ("1z-Ne0hBzXIi1dTfJOxtz1kUUPYQQNpTR", "MUEBLE"),
    "🧵 FOTOS TELAS": ("12gsKZVs6rFonOO8CIxokuE73bxhq8tS9", "TELA"),
    "📦 OTROS": ("13inkyy1ZfGn7yD0ceSr6RSMquaA3OBO1", "MUEBLE"),
    "📥 Buzón Odoo": (BUZON_DRIVE_ID, "MUEBLE"),
}

SHEET_TIPOS = ["MUEBLE", "TELA", "MADERA", "SWATCH"]
ODOO_APP_URL = "https://app-1-3y7y.onrender.com/"


def is_image_filename(filename: str) -> bool:
    """Retorna True si el nombre de archivo corresponde a una imagen soportada."""
    ext = os.path.splitext(str(filename or "").strip())[1].lower()
    return ext in _IMG_EXT_SET


def _format_file_size(size_bytes: int) -> str:
    try:
        sz = int(size_bytes or 0)
    except Exception:
        return ""
    if sz <= 0:
        return ""
    if sz < 1024:
        return f"{sz} B"
    if sz < 1024 * 1024:
        return f"{sz / 1024:.0f} KB"
    return f"{sz / (1024 * 1024):.1f} MB"


def _invalidate_v7_caches_safe() -> None:
    try:
        from modules.prompt_studio_v7 import invalidate_v7_catalog_caches
        invalidate_v7_catalog_caches()
    except Exception:
        pass


def build_dest_folder_options(buzon_active: bool) -> Dict[str, Tuple[str, str]]:
    """Construye destinos de subida evitando usar un Buzón Odoo en papelera."""
    dests: Dict[str, Tuple[str, str]] = {}
    for lbl, (fid, tipo) in ODOO_DEST_FOLDERS.items():
        if fid == BUZON_DRIVE_ID and not buzon_active:
            dests["📥 Buzón Odoo (⚠️ en papelera · usa RENDER)"] = (RENDER_DRIVE_ID, tipo)
        else:
            dests[lbl] = (fid, tipo)
    return dests


def resolve_upload_filename(
    original_file_name: str,
    target_stem: str,
    index: int,
    total_files: int,
    as_2054_png: bool,
) -> Tuple[str, str]:
    """Calcula el nombre exacto de archivo y el nombre base para Sheet conservando el nombre original."""
    orig_base = os.path.basename(str(original_file_name or "foto.png").strip())
    orig_stem, orig_ext = os.path.splitext(orig_base)
    is_img = is_image_filename(orig_base) or not orig_ext
    ext = ".png" if (as_2054_png and is_img) else (orig_ext.lower() or ".png")

    clean_target = os.path.splitext(str(target_stem or "").strip())[0].strip()
    if clean_target and total_files == 1:
        stem = clean_target
    elif clean_target and total_files > 1:
        stem = clean_target if index == 1 else f"{clean_target}_{index}"
    else:
        stem = orig_stem.strip() or f"foto_{index}"

    return f"{stem}{ext}", stem


def _sync_tipo_from_dest() -> None:
    dest_lbl = st.session_state.get("alta_dest_folder", "🛋️ FOTOS MUEBLES")
    _, default_tipo = ODOO_DEST_FOLDERS.get(dest_lbl, ("", "MUEBLE"))
    st.session_state["alta_sheet_tipo"] = default_tipo


def _clear_alta_form(ak: int) -> None:
    """Limpia archivos y nombre exacto SIN reiniciar las casillas 2054px / Registrar en Sheet ni el destino."""
    st.session_state.pop("v7_last_photo_stem", None)
    st.session_state.pop(f"alta_perm_rep_{ak}", None)
    st.session_state.pop(f"alta_name_{ak}", None)
    st.session_state["alta_clear_tick"] = ak + 1
    st.rerun()


def _render_shared_staging_queue(staging_folder_id: str, staging_label: str) -> None:
    """Sección compacta sincronizada en la nube (Drive) para ver fotos y documentos pendientes en todos los dispositivos."""
    def _body() -> None:
        with st.container(border=True):
            q_head, q_ref = st.columns([2.6, 0.9], gap="small", vertical_alignment="center")
            with q_head:
                st.markdown(f"**☁️ Cola compartida (todos tus dispositivos)** · `{staging_label}`")
            with q_ref:
                if st.button("🔄 Actualizar", use_container_width=True, key="alta_queue_refresh"):
                    sheets_service._invalidate_drive_catalog_caches()
                    _invalidate_v7_caches_safe()

            staged_items = sheets_service.list_shared_staging_files(
                folder_id=staging_folder_id,
                max_files=120,
            )
            if not staged_items:
                st.caption("Sin fotos ni documentos en cola compartida todavía.")
                return

            n_imgs = sum(1 for it in staged_items if it.get("kind") == "image")
            n_docs = sum(1 for it in staged_items if it.get("kind") == "document")
            st.caption(
                f"☁️ {len(staged_items)} archivo{'s' if len(staged_items) != 1 else ''} "
                f"({n_imgs} 🖼️ · {n_docs} 📄) visibles en celular, iPad y PC"
            )

            list_h = min(280, max(108, len(staged_items) * 44 + 14))
            with st.container(height=list_h, border=True):
                for idx_q, item in enumerate(staged_items):
                    fid = item.get("id", "")
                    fname = item.get("name", "archivo")
                    kind = item.get("kind", "document")
                    icon = "🖼️" if kind == "image" else "📄"
                    size_lbl = _format_file_size(item.get("size", 0))
                    web_link = item.get("webViewLink") or f"https://drive.google.com/file/d/{fid}/view"
                    safe_nm = fname.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    meta_txt = f" · {size_lbl}" if size_lbl else ""

                    c_info, c_open, c_del = st.columns([2.35, 0.72, 0.48], gap="small", vertical_alignment="center")
                    with c_info:
                        st.markdown(
                            f'<div style="font-size:11.5px;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" '
                            f'title="{safe_nm}">{icon} <b>{safe_nm}</b>'
                            f'<span style="color:#94A3B8;font-size:10px;">{meta_txt}</span></div>',
                            unsafe_allow_html=True,
                        )
                    with c_open:
                        st.markdown(
                            f'<a href="{web_link}" target="_blank" rel="noopener" '
                            f'style="display:inline-block;width:100%;text-align:center;background:#1E293B;'
                            f'border:1px solid #334155;color:#7DD3FC;text-decoration:none;'
                            f'font-size:10.5px;font-weight:600;padding:3px 6px;border-radius:6px;">Abrir ↗</a>',
                            unsafe_allow_html=True,
                        )
                    with c_del:
                        if st.button(
                            "🗑️",
                            key=f"alta_q_del_{fid}_{idx_q}",
                            help=f"Quitar {fname} de la cola",
                            use_container_width=True,
                        ):
                            if sheets_service.trash_drive_file(fid):
                                _invalidate_v7_caches_safe()
                                st.toast(f"🗑️ Quitada de la cola: {fname}")
                                st.rerun()
                            else:
                                st.error(f"No se pudo quitar {fname}")

    if hasattr(st, "fragment"):
        @st.fragment(run_every=10)
        def _frag() -> None:
            _body()

        _frag()
    else:
        _body()


def render_alta_fotos_hub() -> None:
    """Módulo unificado y compacto de Alta de Fotos y Documentos (Drive + Cola Compartida + Sheet + Portal Odoo)."""
    if "alta_clear_tick" not in st.session_state:
        st.session_state["alta_clear_tick"] = 0
    ak = st.session_state["alta_clear_tick"]

    if "alta_staging_folder_id" not in st.session_state:
        st.session_state["alta_staging_folder_id"] = sheets_service.resolve_active_staging_folder_id()
    staging_folder_id = str(st.session_state["alta_staging_folder_id"] or RENDER_DRIVE_ID)
    buzon_active = (staging_folder_id == BUZON_DRIVE_ID)
    dest_folders = build_dest_folder_options(buzon_active)
    dest_keys = list(dest_folders.keys())

    staging_label = "📥 Buzón Odoo" if buzon_active else "📁 RENDER (Buzón en papelera)"

    if st.session_state.get("alta_dest_folder") not in dest_folders:
        st.session_state["alta_dest_folder"] = dest_keys[0]
    if st.session_state.get("alta_sheet_tipo") not in SHEET_TIPOS:
        st.session_state["alta_sheet_tipo"] = "MUEBLE"
    if "alta_2054" not in st.session_state:
        st.session_state["alta_2054"] = False
    if "alta_reg" not in st.session_state:
        st.session_state["alta_reg"] = True

    default_stem = str(st.session_state.get("v7_last_photo_stem") or "").strip()

    tab_subir, tab_odoo = st.tabs(["🚀 Subida Rápida (Drive + Sheet)", "📦 Portal Alta de Odoo"])

    with tab_subir:
        with st.container(border=True):
            c_dest, c_tipo, c_nom = st.columns([1.25, 0.85, 1.55], gap="small", vertical_alignment="center")
            with c_dest:
                dest_lbl = st.selectbox(
                    "Destino",
                    dest_keys,
                    key="alta_dest_folder",
                    on_change=_sync_tipo_from_dest,
                    label_visibility="collapsed",
                )
            with c_tipo:
                sheet_tipo = st.selectbox(
                    "Tipo",
                    SHEET_TIPOS,
                    key="alta_sheet_tipo",
                    label_visibility="collapsed",
                )
            with c_nom:
                target_stem = st.text_input(
                    "Nombre exacto",
                    value=default_stem,
                    placeholder="Nombre exacto (vacío = nombre del archivo)",
                    key=f"alta_name_{ak}",
                    label_visibility="collapsed",
                )

            o1, o2, o3 = st.columns([1.1, 1.15, 0.75], gap="small", vertical_alignment="center")
            with o1:
                auto_2054 = st.checkbox("📐 2054×2054 #FFFFFF", key="alta_2054")
            with o2:
                reg_sheet = st.checkbox("📊 Registrar en Sheet", key="alta_reg")
            with o3:
                if st.button("🗑️ Limpiar", use_container_width=True, key=f"alta_clr_{ak}"):
                    _clear_alta_form(ak)

            up_files = st.file_uploader(
                "Elegir foto(s) o documento(s)",
                type=IMG_AND_DOC_TYPES,
                accept_multiple_files=True,
                key=f"alta_files_{ak}",
                label_visibility="collapsed",
            )

            if up_files:
                thumbs: List[Tuple[str, bytes, str]] = []
                doc_badges: List[str] = []
                for idx_f, uf in enumerate(up_files, start=1):
                    raw_preview = uf.getvalue()
                    out_fname, _ = resolve_upload_filename(
                        uf.name, target_stem, idx_f, len(up_files), auto_2054
                    )
                    if is_image_filename(uf.name):
                        thumbs.append((out_fname, raw_preview, f"{sheet_tipo}"))
                    else:
                        sz_txt = _format_file_size(len(raw_preview))
                        doc_badges.append(f"📄 **{out_fname}**" + (f" ({sz_txt})" if sz_txt else ""))
                if thumbs:
                    render_loaded_photos_strip(thumbs[:6], key_prefix=f"alta_{ak}")
                if doc_badges:
                    st.markdown(" · ".join(doc_badges))

                n_files = len(up_files)
                plural = "s" if n_files != 1 else ""
                b_drive, b_queue = st.columns([1.15, 1.0], gap="small")
                with b_drive:
                    go_drive = st.button(
                        f"🚀 Subir {n_files} archivo{plural} a Drive + Sheet",
                        type="primary",
                        use_container_width=True,
                        key=f"alta_go_{ak}",
                    )
                with b_queue:
                    go_queue = st.button(
                        "☁️ Enviar a cola compartida",
                        use_container_width=True,
                        key=f"alta_queue_send_{ak}",
                        help="Sube a la nube para ver exactamente los mismos archivos en celular, iPad y PC",
                    )

                if go_drive:
                    folder_id, _ = dest_folders[dest_lbl]
                    ok_links: List[Tuple[str, str, bool, str]] = []
                    errs: List[str] = []
                    with st.spinner("Subiendo a Drive (con permiso público por enlace) y registrando en Sheet..."):
                        for idx_f, uf in enumerate(up_files, start=1):
                            raw_bytes = uf.getvalue()
                            file_is_img = is_image_filename(uf.name)
                            out_fname, out_stem = resolve_upload_filename(
                                uf.name, target_stem, idx_f, len(up_files), auto_2054 and file_is_img
                            )
                            try:
                                payload_bytes = raw_bytes
                                if auto_2054 and file_is_img:
                                    fmt = ai_prompt_service_v7.format_image_2054_white(raw_bytes, target_px=2054)
                                    payload_bytes = fmt["png"]
                                if file_is_img:
                                    link = sheets_service.upload_image_bytes_to_drive(
                                        payload_bytes, out_fname, folder_id
                                    )
                                else:
                                    link = sheets_service.upload_file_bytes_to_drive(
                                        payload_bytes, out_fname, folder_id
                                    )
                                if not link:
                                    errs.append(f"{out_fname}: no se pudo subir a Drive")
                                    continue
                                fid = sheets_service.extract_drive_id(link)
                                is_pub, perm_msg = sheets_service._last_permission_status.get(
                                    fid, (False, "Permiso no verificado")
                                )
                                if reg_sheet and file_is_img:
                                    sheets_service.register_in_fotos_normalizadas(sheet_tipo, out_stem, link)
                                ok_links.append((out_fname, link, is_pub, perm_msg))
                            except Exception as exc:  # noqa: BLE001
                                errs.append(f"{out_fname}: {exc}")

                    if ok_links:
                        _invalidate_v7_caches_safe()
                        st.success(f"✅ {len(ok_links)} archivo(s) subido(s) con nombre exacto.")
                        for nm, lnk, is_pub, p_msg in ok_links:
                            badge_perm = "🌐 Cualquiera con el enlace" if is_pub else f"⚠️ {p_msg}"
                            st.markdown(f"- **{nm}** · {badge_perm} · [Abrir en Drive ↗]({lnk})")
                    if errs:
                        st.error("⚠️ " + " | ".join(errs))

                if go_queue:
                    q_ok: List[Tuple[str, str]] = []
                    q_err: List[str] = []
                    with st.spinner("Enviando a la cola compartida en Drive..."):
                        for idx_f, uf in enumerate(up_files, start=1):
                            raw_bytes = uf.getvalue()
                            file_is_img = is_image_filename(uf.name)
                            out_fname, _ = resolve_upload_filename(
                                uf.name, target_stem, idx_f, len(up_files), auto_2054 and file_is_img
                            )
                            try:
                                payload_bytes = raw_bytes
                                if auto_2054 and file_is_img:
                                    fmt = ai_prompt_service_v7.format_image_2054_white(raw_bytes, target_px=2054)
                                    payload_bytes = fmt["png"]
                                link = sheets_service.upload_file_bytes_to_drive(
                                    payload_bytes, out_fname, staging_folder_id
                                )
                                if not link:
                                    q_err.append(f"{out_fname}: no se pudo subir")
                                else:
                                    q_ok.append((out_fname, link))
                            except Exception as exc:  # noqa: BLE001
                                q_err.append(f"{out_fname}: {exc}")

                    if q_ok:
                        _invalidate_v7_caches_safe()
                        st.success(f"☁️ {len(q_ok)} archivo(s) disponibles ahora en todos tus dispositivos.")
                        for nm, lnk in q_ok:
                            st.markdown(f"- **{nm}** · [Abrir en Drive ↗]({lnk})")
                    if q_err:
                        st.error("⚠️ " + " | ".join(q_err))

            with st.expander("🔓 Revisar / hacer públicas carpetas de subida (Cualquiera con el enlace)", expanded=False):
                pa, pb = st.columns(2, gap="small")
                with pa:
                    if st.button("🔍 Revisar permisos Odoo", use_container_width=True, key=f"alta_perm_chk_{ak}"):
                        st.session_state["alta_staging_folder_id"] = sheets_service.resolve_active_staging_folder_id()
                        lines = []
                        for lbl_d, (fid_d, _) in dest_folders.items():
                            info = sheets_service.inspect_drive_item_permissions(fid_d)
                            lines.append(f"- **{lbl_d}**: {info.get('summary', '⚠️')}")
                        st.session_state[f"alta_perm_rep_{ak}"] = "\n".join(lines)
                with pb:
                    if st.button("🌐 Hacer públicas todas", use_container_width=True, type="primary", key=f"alta_perm_fix_{ak}"):
                        lines = []
                        for lbl_d, (fid_d, _) in dest_folders.items():
                            res_f = sheets_service.repair_folder_public_permissions(fid_d)
                            lines.append(
                                f"- **{lbl_d}**: {'🌐 Pública' if res_f.get('folder_public') else '⚠️ ' + str(res_f.get('folder_msg', ''))} "
                                f"({res_f.get('updated', 0)} fotos actualizadas)"
                            )
                        st.session_state[f"alta_perm_rep_{ak}"] = "\n".join(lines)
                if st.session_state.get(f"alta_perm_rep_{ak}"):
                    st.markdown(st.session_state[f"alta_perm_rep_{ak}"])

        _render_shared_staging_queue(staging_folder_id, staging_label)

    with tab_odoo:
        st.markdown(
            f'<div style="display:flex;justify-content:flex-end;margin-bottom:4px;">'
            f'<a href="{ODOO_APP_URL}" target="_blank" rel="noopener" '
            f'style="background:#1E293B;border:1px solid #0284C7;color:#7DD3FC;text-decoration:none;'
            f'font-size:11px;font-weight:600;padding:3px 10px;border-radius:6px;">↗ Abrir Alta de Odoo en pestaña nueva</a>'
            f'</div>',
            unsafe_allow_html=True,
        )
        components.iframe(ODOO_APP_URL, height=760, scrolling=True)
