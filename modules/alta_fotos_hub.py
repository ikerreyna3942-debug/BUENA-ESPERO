import os
from typing import Dict, List, Tuple

import streamlit as st
import streamlit.components.v1 as components

from modules.ui_helpers import render_loaded_photos_strip
from services.ai_prompt_service_v7 import ai_prompt_service_v7
from services.sheets_service import BUZON_DRIVE_ID, sheets_service

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff", "jfif", "avif"]

ODOO_DEST_FOLDERS: Dict[str, Tuple[str, str]] = {
    "🛋️ FOTOS MUEBLES": ("10UIhDWLKL0ySmzdcMemA5K5831YozuBa", "MUEBLE"),
    "🪞 FOTOS ACCESORIOS": ("1z-Ne0hBzXIi1dTfJOxtz1kUUPYQQNpTR", "MUEBLE"),
    "🧵 FOTOS TELAS": ("12gsKZVs6rFonOO8CIxokuE73bxhq8tS9", "TELA"),
    "📦 OTROS": ("13inkyy1ZfGn7yD0ceSr6RSMquaA3OBO1", "MUEBLE"),
    "📥 Buzón Odoo": (BUZON_DRIVE_ID, "MUEBLE"),
}

SHEET_TIPOS = ["MUEBLE", "TELA", "MADERA", "SWATCH"]
ODOO_APP_URL = "https://app-1-3y7y.onrender.com/"


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
    ext = ".png" if as_2054_png else (orig_ext.lower() or ".png")

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


def render_alta_fotos_hub() -> None:
    """Módulo unificado y compacto de Alta de Fotos (Odoo Drive + Sheet + Portal Odoo) dentro de la misma app."""
    if "alta_clear_tick" not in st.session_state:
        st.session_state["alta_clear_tick"] = 0
    ak = st.session_state["alta_clear_tick"]

    if "alta_dest_folder" not in st.session_state:
        st.session_state["alta_dest_folder"] = "🛋️ FOTOS MUEBLES"
    if "alta_sheet_tipo" not in st.session_state:
        st.session_state["alta_sheet_tipo"] = "MUEBLE"

    default_stem = str(st.session_state.get("v7_last_photo_stem") or "").strip()

    tab_subir, tab_odoo = st.tabs(["🚀 Subida Rápida (Drive + Sheet)", "📦 Portal Alta de Odoo"])

    with tab_subir:
        with st.container(border=True):
            c_dest, c_tipo, c_nom = st.columns([1.25, 0.85, 1.55], gap="small", vertical_alignment="center")
            with c_dest:
                dest_lbl = st.selectbox(
                    "Destino",
                    list(ODOO_DEST_FOLDERS.keys()),
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
                auto_2054 = st.checkbox("📐 2054×2054 #FFFFFF", value=False, key=f"alta_2054_{ak}")
            with o2:
                reg_sheet = st.checkbox("📊 Registrar en Sheet", value=True, key=f"alta_reg_{ak}")
            with o3:
                if st.button("🗑️ Limpiar", use_container_width=True, key=f"alta_clr_{ak}"):
                    st.session_state["alta_clear_tick"] = ak + 1
                    st.rerun()

            up_files = st.file_uploader(
                "Elegir foto(s)",
                type=IMG_TYPES,
                accept_multiple_files=True,
                key=f"alta_files_{ak}",
                label_visibility="collapsed",
            )

            if up_files:
                thumbs: List[Tuple[str, bytes, str]] = []
                for idx_f, uf in enumerate(up_files, start=1):
                    out_fname, _ = resolve_upload_filename(
                        uf.name, target_stem, idx_f, len(up_files), auto_2054
                    )
                    thumbs.append((out_fname, uf.getvalue(), f"{sheet_tipo}"))
                render_loaded_photos_strip(thumbs[:6], key_prefix=f"alta_{ak}")

                if st.button(
                    f"🚀 Subir {len(up_files)} foto{'s' if len(up_files) != 1 else ''} a Drive + Sheet",
                    type="primary",
                    use_container_width=True,
                    key=f"alta_go_{ak}",
                ):
                    folder_id, _ = ODOO_DEST_FOLDERS[dest_lbl]
                    ok_links: List[Tuple[str, str, bool, str]] = []
                    errs: List[str] = []
                    with st.spinner("Subiendo a Drive (con permiso público por enlace) y registrando en Sheet..."):
                        for idx_f, uf in enumerate(up_files, start=1):
                            raw_bytes = uf.getvalue()
                            out_fname, out_stem = resolve_upload_filename(
                                uf.name, target_stem, idx_f, len(up_files), auto_2054
                            )
                            try:
                                payload_bytes = raw_bytes
                                if auto_2054:
                                    fmt = ai_prompt_service_v7.format_image_2054_white(raw_bytes, target_px=2054)
                                    payload_bytes = fmt["png"]
                                link = sheets_service.upload_image_bytes_to_drive(
                                    payload_bytes, out_fname, folder_id
                                )
                                if not link:
                                    errs.append(f"{out_fname}: no se pudo subir a Drive")
                                    continue
                                fid = sheets_service.extract_drive_id(link)
                                is_pub, perm_msg = sheets_service._last_permission_status.get(
                                    fid, (False, "Permiso no verificado")
                                )
                                if reg_sheet:
                                    sheets_service.register_in_fotos_normalizadas(sheet_tipo, out_stem, link)
                                ok_links.append((out_fname, link, is_pub, perm_msg))
                            except Exception as exc:  # noqa: BLE001
                                errs.append(f"{out_fname}: {exc}")

                    if ok_links:
                        st.success(f"✅ {len(ok_links)} foto(s) subida(s) con nombre exacto.")
                        for nm, lnk, is_pub, p_msg in ok_links:
                            badge_perm = "🌐 Cualquiera con el enlace" if is_pub else f"⚠️ {p_msg}"
                            st.markdown(f"- **{nm}** · {badge_perm} · [Abrir en Drive ↗]({lnk})")
                    if errs:
                        st.error("⚠️ " + " | ".join(errs))

            with st.expander("🔓 Revisar / hacer públicas carpetas de subida (Cualquiera con el enlace)", expanded=False):
                pa, pb = st.columns(2, gap="small")
                with pa:
                    if st.button("🔍 Revisar permisos Odoo", use_container_width=True, key=f"alta_perm_chk_{ak}"):
                        lines = []
                        for lbl_d, (fid_d, _) in ODOO_DEST_FOLDERS.items():
                            info = sheets_service.inspect_drive_item_permissions(fid_d)
                            lines.append(f"- **{lbl_d}**: {info.get('summary', '⚠️')}")
                        st.session_state[f"alta_perm_rep_{ak}"] = "\n".join(lines)
                with pb:
                    if st.button("🌐 Hacer públicas todas", use_container_width=True, type="primary", key=f"alta_perm_fix_{ak}"):
                        lines = []
                        for lbl_d, (fid_d, _) in ODOO_DEST_FOLDERS.items():
                            res_f = sheets_service.repair_folder_public_permissions(fid_d)
                            lines.append(
                                f"- **{lbl_d}**: {'🌐 Pública' if res_f.get('folder_public') else '⚠️ ' + str(res_f.get('folder_msg', ''))} "
                                f"({res_f.get('updated', 0)} fotos actualizadas)"
                            )
                        st.session_state[f"alta_perm_rep_{ak}"] = "\n".join(lines)
                if st.session_state.get(f"alta_perm_rep_{ak}"):
                    st.markdown(st.session_state[f"alta_perm_rep_{ak}"])

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
