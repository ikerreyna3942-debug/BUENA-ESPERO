import os
import sys
import re
import io
import requests
import streamlit as st
from pathlib import Path
from PIL import Image

# Agregar directorio al sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from services.sheets_service import sheets_service
from services.photo_service import photo_service
from services.calculator_service import normalizar_texto, calcular_metro_cubico

try:
    st.set_page_config(
        page_title="Alta Odoo - Gestión y Fotos de Muebles",
        page_icon="🛋️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
except Exception:
    pass

# Estilos CSS personalizados (Gris Pizarra / Slate Grey)
st.markdown("""
<style>
    header[data-testid="stHeader"] {
        background-color: #1E293B !important;
    }
    .stApp {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
    }
    label, .stRadio label, .stSelectbox label, .stTextInput label, p, span, div {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #FFFFFF !important;
    }
    .main-title {
        font-size: 24px;
        font-weight: 800;
        background: linear-gradient(135deg, #F59E0B, #FBBF24);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2px;
    }
    .sub-title {
        font-size: 13px;
        color: #CBD5E1 !important;
        margin-bottom: 15px;
    }
    .kpi-box {
        background: #283548;
        border: 1px solid #475569;
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .kpi-num {
        font-size: 22px;
        font-weight: 800;
        color: #FFFFFF !important;
    }
    .kpi-lbl {
        font-size: 11px;
        font-weight: 700;
        color: #E2E8F0 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 2px;
    }
    .product-banner {
        background: #283548;
        border: 1px solid #475569;
        border-left: 4px solid #38BDF8;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 18px;
        color: #FFFFFF !important;
    }
    .photo-meta-card {
        background: #283548;
        border: 1px solid #475569;
        border-radius: 8px;
        padding: 12px 14px;
        margin-top: 8px;
        margin-bottom: 12px;
        font-size: 12px;
        color: #FFFFFF !important;
    }
    .photo-badge-ok {
        background: rgba(16, 185, 129, 0.25);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.5);
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 11px;
        display: inline-block;
        margin-bottom: 8px;
    }
    .photo-badge-pending {
        background: rgba(239, 68, 68, 0.25);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.5);
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 11px;
        display: inline-block;
        margin-bottom: 8px;
    }
    .photo-tag {
        background: #1E293B;
        border: 1px solid #475569;
        color: #38BDF8;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 11px;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def cargar_datos_sheets():
    return sheets_service.get_pending_products()

def extraer_id_drive(url: str) -> str:
    """Extrae el ID de un archivo de Google Drive."""
    if not url:
        return ""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match_id = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if match_id:
        return match_id.group(1)
    return ""

@st.cache_data(show_spinner=False, ttl=300)
def descargar_imagen_drive(drive_id: str):
    """Descarga la imagen de Google Drive usando API autenticada y fallback HTTP."""
    if not drive_id:
        return None
    
    # 1. Intentar con Service Account autenticada (100% confiable)
    try:
        drive_bytes = sheets_service.get_drive_file_bytes(drive_id)
        if drive_bytes and len(drive_bytes) > 500:
            return drive_bytes
    except Exception:
        pass

    # 2. Fallback por URLs de Google Drive
    urls = [
        f"https://drive.google.com/thumbnail?id={drive_id}&sz=w1000",
        f"https://lh3.googleusercontent.com/d/{drive_id}",
        f"https://drive.google.com/uc?export=view&id={drive_id}"
    ]
    for u in urls:
        try:
            r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
        except Exception:
            pass
    return None

def obtener_detalles_foto(nombre_foto: str, link_drive: str):
    """Obtiene metadatos reales y ruta de la imagen local o de Drive."""
    # Si no hay link pero hay nombre, intentar resolver desde catálogo o Drive API
    if (not link_drive or not link_drive.strip()) and nombre_foto:
        link_drive = sheets_service.buscar_link_drive_inteligente(nombre_foto)

    detalles = {
        "existe_local": False,
        "ruta_local": None,
        "bytes_drive": None,
        "dimensiones": "N/D",
        "formato": "N/D",
        "peso_kb": 0.0,
        "categoria": "N/D",
        "status_dimension": "",
        "drive_id": extraer_id_drive(link_drive),
        "tiene_drive": bool(link_drive and link_drive.strip()),
        "link_drive": link_drive or ""
    }

    # 1. Intentar por nombre exacto o normalizado en base final u origen
    if nombre_foto:
        match = photo_service.get_photo_by_name(nombre_foto)
        if match:
            ruta = match.get("ruta_completa", "")
            if ruta and os.path.exists(ruta):
                detalles["existe_local"] = True
                detalles["ruta_local"] = ruta
                detalles["categoria"] = match.get("subcarpeta_rel", match.get("categoria_principal", "Base Final"))
                try:
                    with Image.open(ruta) as img:
                        w, h = img.size
                        detalles["dimensiones"] = f"{w} x {h} px"
                        detalles["formato"] = img.format
                        diag = photo_service.verificar_dimensiones_estandar(w, h)
                        detalles["status_dimension"] = diag["mensaje"]
                    detalles["peso_kb"] = round(os.path.getsize(ruta) / 1024, 1)
                    return detalles
                except Exception:
                    pass

    # 2. Si no hay drive_id explícito pero hay nombre_foto, buscar link inteligente
    if not detalles["drive_id"] and nombre_foto:
        smart_link = sheets_service.buscar_link_drive_inteligente(nombre_foto)
        if smart_link:
            detalles["link_drive"] = smart_link
            detalles["drive_id"] = extraer_id_drive(smart_link)
            detalles["tiene_drive"] = True

    # 3. Si no está en local pero hay Drive ID, descargar bytes
    if detalles["drive_id"]:
        img_bytes = descargar_imagen_drive(detalles["drive_id"])
        if img_bytes:
            detalles["bytes_drive"] = img_bytes
            try:
                with Image.open(io.BytesIO(img_bytes)) as img:
                    w, h = img.size
                    detalles["dimensiones"] = f"{w} x {h} px"
                    detalles["formato"] = img.format
                    diag = photo_service.verificar_dimensiones_estandar(w, h)
                    detalles["status_dimension"] = diag["mensaje"]
                detalles["peso_kb"] = round(len(img_bytes) / 1024, 1)
                detalles["categoria"] = "Google Drive (Nube)"
            except Exception:
                pass

    return detalles

FOLDER_INTERIOR_DRIVE_ID = "1jFGFpOocxQs-Wbq9pMgegB_ard-dUZDr"
FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"
FOLDER_MUESTRAS_DRIVE_ID = "12gsKZVs6rFonOO8CIxokuE73bxhq8tS9"

@st.cache_data(ttl=300)
def cargar_catalogo_drive_exclusivo(folder_id: str):
    """Carga la lista de archivos de una carpeta oficial de Google Drive (con escaneo recursivo de subcarpetas)."""
    return sheets_service.get_drive_folder_files(folder_id, recursive=True)

def renderizar_bloque_drive_exclusivo(titulo_bloque: str, icono: str, col_cols: str, folder_id: str, foto_nom_actual: str, foto_link_actual: str, fila_id: int, key_prefix: str):
    """Renderiza un selector exclusivo desde Google Drive con búsqueda en vivo, previsualización inmediata y nombre de solo lectura."""
    st.markdown(f"##### {icono} {titulo_bloque} ({col_cols})")
    archivos = cargar_catalogo_drive_exclusivo(folder_id)
    
    arch_map = {a["name"].upper(): a for a in archivos}
    opciones = [""] + [a["name"] for a in archivos]
    
    cur_nom_clean = normalizar_texto(foto_nom_actual)
    default_idx = 0
    for idx, a in enumerate(archivos):
        if normalizar_texto(a["name"]) == cur_nom_clean:
            default_idx = idx + 1
            break
            
    st.markdown(f"""
    <div style="background:#0b1120; border:1px solid #1e293b; border-left: 4px solid #38bdf8; border-radius:8px; padding:12px 16px; margin-bottom:14px;">
        <div style="font-weight:800; font-size:13px; color:#38bdf8; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;">
            {icono} CATÁLOGO OFICIAL DE {titulo_bloque.upper()} (GOOGLE DRIVE)
        </div>
    """, unsafe_allow_html=True)
    
    sel_arch = st.selectbox(
        f"Seleccionar {titulo_bloque} (Escribe aquí para buscar):",
        opciones,
        index=default_idx,
        key=f"sb_drive_{key_prefix}_{fila_id}"
    )
    
    if not sel_arch:
        nombre_final = foto_nom_actual
        link_final = foto_link_actual
        file_id_final = extraer_id_drive(foto_link_actual)
    else:
        obj = arch_map.get(sel_arch.upper())
        if obj:
            nombre_final = obj["name"]
            link_final = obj["link"]
            file_id_final = obj["id"]
        else:
            nombre_final = sel_arch
            link_final = ""
            file_id_final = ""
            
    # Previsualización inmediata
    if file_id_final:
        img_bytes = descargar_imagen_drive(file_id_final)
        if img_bytes:
            st.image(img_bytes, caption=f"Vista Previa: {nombre_final}", use_container_width=True)
        else:
            st.info(f"Cargando vista previa de {nombre_final} desde Google Drive...")
    elif nombre_final:
        info = obtener_detalles_foto(nombre_final, link_final)
        if info["existe_local"] and info["ruta_local"]:
            st.image(info["ruta_local"], caption=f"Foto Registrada: {nombre_final}", use_container_width=True)
        elif info["bytes_drive"]:
            st.image(info["bytes_drive"], caption=f"Foto Registrada: {nombre_final}", use_container_width=True)
        else:
            st.info(f"{titulo_bloque} asignado: {nombre_final}")
    else:
        st.info(f"Sin {titulo_bloque.lower()} asignado en el archivo.")
        
    # Ficha Técnica de solo lectura (sin campos editables)
    st.markdown(f"""
    <div class="photo-meta-card">
        <div>📁 <b>Nombre Oficial</b>: <code style="font-size:13px; color:#0284c7; font-weight:700;">{nombre_final or 'Sin asignar'}</code></div>
        <div style="margin-top:6px; color:#64748B; font-size:11px;">🔒 Nombre oficial de Google Drive (no modificable).</div>
    </div>
    """, unsafe_allow_html=True)
    
    if link_final:
        st.markdown(f'<a href="{link_final}" target="_blank" style="text-decoration:none;"><button style="background:#2563EB;color:#FFF;border:none;padding:8px 12px;border-radius:6px;font-weight:600;cursor:pointer;width:100%;margin-top:6px;">🔗 Abrir Foto en Google Drive</button></a>', unsafe_allow_html=True)
        
    st.markdown("</div>", unsafe_allow_html=True)
    return (nombre_final or foto_nom_actual), link_final, None

def renderizar_bloque_foto_completo(titulo_bloque: str, icono: str, foto_nom_actual: str, foto_link_actual: str, lista_opciones: list, key_prefix: str, fila_id: int, sku_prod: str = "", modelo_prod: str = ""):
    """Renderiza el bloque visual completo con los 2 recuadros: SUBIR FOTO y ACTUAL (CAMBIO O MODIFICACIÓN)."""
    st.markdown(f"##### {icono} {titulo_bloque}")
    
    # =========================================================================
    # RECUADRO 1 (ARRIBA): SUBIR FOTO (ALMACÉN FOTOS BASE 1254 x 1254 PX)
    # =========================================================================
    st.markdown("""
    <div style="background:#0b1120; border:1px solid #1e293b; border-left: 4px solid #38bdf8; border-radius:8px; padding:12px 16px; margin-bottom:14px;">
        <div style="font-weight:800; font-size:13px; color:#38bdf8; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;">
            📤 SUBIR FOTO (ALMACÉN FOTOS BASE 1254 x 1254 PX)
        </div>
    """, unsafe_allow_html=True)
    
    # Cargar catálogo de fotos base de manera ultrarrápida (0.001s)
    fotos_origen = photo_service.origen_photos
    opciones_nuevas = [""] + [
        f"{f['nombre_sin_ext']} ({f.get('subcarpeta_rel', 'Interior')})" 
        for f in fotos_origen 
        if f.get("nombre_sin_ext")
    ]

    sel_nueva = st.selectbox(
        f"Elegir Foto Nueva:",
        opciones_nuevas,
        index=0,
        key=f"sb_nueva_{key_prefix}_{fila_id}"
    )

    foto_nueva_nombre = ""
    foto_nueva_link = ""
    ruta_origen_sel = None

    if sel_nueva:
        foto_nueva_nombre = sel_nueva.split(" (")[0].strip()
        with st.spinner("Buscando y cargando vista previa de foto..."):
            info_nueva = obtener_detalles_foto(foto_nueva_nombre, "")
            foto_nueva_link = info_nueva.get("link_drive", "")
            if info_nueva["existe_local"] and info_nueva["ruta_local"]:
                st.image(info_nueva["ruta_local"], caption=f"Foto Nueva: {foto_nueva_nombre} ({info_nueva['dimensiones']})", use_container_width=True)
                ruta_origen_sel = info_nueva["ruta_local"]
            elif info_nueva["bytes_drive"]:
                st.image(info_nueva["bytes_drive"], caption=f"Foto Nueva (Google Drive): {foto_nueva_nombre} ({info_nueva['dimensiones']})", use_container_width=True)
            elif foto_nueva_link:
                st.info(f"Foto encontrada en Google Drive: {foto_nueva_nombre}")

    # Si se seleccionó una foto nueva, colocar su nombre. Si NO se seleccionó foto nueva, dejar el campo VACÍO.
    sugerencia_dest = normalizar_texto(foto_nueva_nombre) if foto_nueva_nombre else ""

    nombre_dest_input = st.text_input(
        f"Nombre de la Foto:",
        value=sugerencia_dest,
        key=f"txt_dest_{key_prefix}_{fila_id}"
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # =========================================================================
    # RECUADRO 2 (ABAJO): ACTUAL (CAMBIO O MODIFICACIÓN)
    # =========================================================================
    st.markdown("""
    <div style="background:#0b1120; border:1px solid #1e293b; border-left: 4px solid #fbbf24; border-radius:8px; padding:12px 16px; margin-bottom:14px;">
        <div style="font-weight:800; font-size:13px; color:#fbbf24; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;">
            📸 ACTUAL (CAMBIO O MODIFICACIÓN) - FOTOS FINAL
        </div>
    """, unsafe_allow_html=True)

    opciones_cat = [""] + lista_opciones
    default_cat_idx = 0
    if foto_nom_actual in lista_opciones:
        default_cat_idx = lista_opciones.index(foto_nom_actual) + 1

    sel_cat = st.selectbox(
        f"📂 Elegir de Catálogo (Base Final) para {titulo_bloque}:",
        opciones_cat,
        index=default_cat_idx,
        key=f"sb_cat_{key_prefix}_{fila_id}"
    )

    if sel_cat:
        nombre_actual_val = sel_cat
    else:
        nombre_actual_val = foto_nom_actual

    nombre_actual_input = st.text_input(
        f"📸 Foto Actual Registrada ({titulo_bloque}):",
        value=nombre_actual_val,
        key=f"txt_nom_act_{key_prefix}_{fila_id}"
    )

    link_input = foto_link_actual
    if not link_input and nombre_actual_val:
        link_input = sheets_service.buscar_link_drive_inteligente(nombre_actual_val)

    # Obtener detalles foto actual (SOLO si hay foto actual en el archivo o elegida de catálogo)
    if nombre_actual_val or link_input:
        info_act = obtener_detalles_foto(nombre_actual_val, link_input)
    else:
        info_act = {
            "existe_local": False,
            "ruta_local": None,
            "bytes_drive": None,
            "dimensiones": "N/D",
            "formato": "N/D",
            "peso_kb": 0.0,
            "categoria": "N/D",
            "status_dimension": "",
            "drive_id": "",
            "tiene_drive": False,
            "link_drive": ""
        }

    if not link_input and info_act.get("link_drive"):
        link_input = info_act["link_drive"]
    if info_act["existe_local"] and info_act["ruta_local"]:
        st.image(info_act["ruta_local"], caption=f"Foto Actual Registrada: {nombre_actual_val} ({info_act['dimensiones']})", use_container_width=True)
    elif info_act["bytes_drive"]:
        st.image(info_act["bytes_drive"], caption=f"Google Drive: {nombre_actual_val or titulo_bloque} ({info_act['dimensiones']})", use_container_width=True)
    else:
        st.info(f"ℹ️ Sin fotografía asignada en el archivo para {titulo_bloque}.")

    # Ficha Técnica
    st.markdown(f"""
    <div class="photo-meta-card">
        <div>📁 <b>Nombre Archivo</b>: <code>{nombre_actual_val or 'Sin asignar'}</code></div>
        <div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:4px;">
            <span class="photo-tag">📐 Dim: {info_act['dimensiones']}</span>
            <span class="photo-tag">🎨 Formato: {info_act['formato']}</span>
            <span class="photo-tag">💾 Peso: {info_act['peso_kb']} KB</span>
            {f'<span class="photo-tag" style="background:#e0f2fe;color:#0369a1;font-weight:700;">{info_act["status_dimension"]}</span>' if info_act.get("status_dimension") else ''}
        </div>
        <div style="margin-top:6px; color:#475569;">📍 <b>Carpeta</b>: <code>{info_act['categoria']}</code></div>
    </div>
    """, unsafe_allow_html=True)

    if link_input:
        st.markdown(f'<a href="{link_input}" target="_blank" style="text-decoration:none;"><button style="background:#2563EB;color:#FFF;border:none;padding:8px 12px;border-radius:6px;font-weight:600;cursor:pointer;width:100%;margin-bottom:6px;">🔗 Abrir Foto en Google Drive</button></a>', unsafe_allow_html=True)
    
    with st.expander("✏️ Ver / Modificar Enlace de Drive"):
        link_input = st.text_input(f"URL Drive ({titulo_bloque}):", value=link_input, key=f"txt_link_{key_prefix}_{fila_id}")

    st.markdown("</div>", unsafe_allow_html=True)

    # El nombre y enlace que se guardará en sheets y fotos final
    nombre_definitivo = nombre_dest_input if (foto_nueva_nombre and nombre_dest_input) else nombre_actual_input
    link_definitivo = foto_nueva_link if (foto_nueva_nombre and foto_nueva_link) else link_input
    return (nombre_definitivo or nombre_actual_input), link_definitivo, ruta_origen_sel

def determinar_subcarpeta_destino_mueble(categoria: str, tipo_mueble: str, nombre_prod: str) -> str:
    """Determina la subcarpeta de destino dentro de FOTOS MUEBLES respetando la estructura existente."""
    texto = f"{categoria} {tipo_mueble} {nombre_prod}".upper()
    if any(k in texto for k in ["COMEDOR", "MESA DE COMEDOR", "MESA COMEDOR", "SILLA DE COMEDOR", "BUFETERA", "TRINCHADOR", "CREDENZA", "COMEDORES"]):
        return r"FOTOS MUEBLES\FOTOS COMEDORES"
    elif any(k in texto for k in ["SALA", "SOFA", "SOFÁ", "LOVE SEAT", "CHAISE", "ESQUINERO", "SALAS"]):
        return r"FOTOS MUEBLES\FOTOS SALAS"
    elif any(k in texto for k in ["RECAMARA", "RECÁMARA", "CAMA", "BURO", "BURÓ", "CABECERA", "RECAMARAS", "RECÁMARAS"]):
        return r"FOTOS MUEBLES\FOTOS RECAMARAS"
    elif "CENTRO" in texto:
        return r"FOTOS MUEBLES\FOTOS MESA DE CENTRO"
    elif "LATERAL" in texto:
        return r"FOTOS MUEBLES\FOTOS MESA LATERALES"
    elif "SILLON" in texto or "OCASIONAL" in texto:
        return r"FOTOS MUEBLES\FOTOS SILLONES"
    elif "AUXILIAR" in texto:
        return r"FOTOS MUEBLES\FOTOS DE AUXILIARES"
    elif any(k in texto for k in ["SOFA CAMA", "SOFÁ CAMA", "FUTON", "FUTTON"]):
        return r"FOTOS MUEBLES\FOTOS SOFÁ CAMA Y FUTTONES"
    return r"FOTOS MUEBLES"

def render_odoo_catalog():
    st.markdown('<div class="main-title">🛋️ ALTA ODOO - GESTIÓN Y FOTOS DE MUEBLES</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Estandarización de fichas técnicas, normalización Odoo y Sección de fotos (1254 x 1254 px)</div>', unsafe_allow_html=True)

    # Cargar datos
    with st.spinner("Sincronizando con Google Sheets..."):
        try:
            productos = cargar_datos_sheets()
        except Exception as e:
            st.error(f"Error al conectar con Google Sheets: {e}")
            productos = []

    if not productos:
        st.warning("No se pudieron cargar productos desde Google Sheets.")
        return

    pendientes = [p for p in productos if not p["tiene_fotos"]]
    con_fotos = [p for p in productos if p["tiene_fotos"]]

    # Catálogos dinámicos
    todos_proveedores = sorted(list(set(p["proveedor"].strip() for p in productos if p["proveedor"].strip())))
    todas_categorias = sorted(list(set(p["categoria"].strip() for p in productos if p["categoria"].strip())))
    todos_tipos = sorted(list(set(p["tipo_mueble"].strip() for p in productos if p["tipo_mueble"].strip())))

    # Métricas superiores
    c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
    with c_kpi1:
        st.markdown(f'<div class="kpi-box"><div class="kpi-num" style="color:#38BDF8;">{len(productos)}</div><div class="kpi-lbl">Total Productos</div></div>', unsafe_allow_html=True)
    with c_kpi2:
        st.markdown(f'<div class="kpi-box"><div class="kpi-num" style="color:#EF4444;">{len(pendientes)}</div><div class="kpi-lbl">⚠️ Pendientes Sin Foto</div></div>', unsafe_allow_html=True)
    with c_kpi3:
        st.markdown(f'<div class="kpi-box"><div class="kpi-num" style="color:#10B981;">{len(con_fotos)}</div><div class="kpi-lbl">✅ Con Fotos Listas</div></div>', unsafe_allow_html=True)
    with c_kpi4:
        st.markdown(f'<div class="kpi-box"><div class="kpi-num" style="color:#A78BFA;">992</div><div class="kpi-lbl">📸 Base Final Fotos</div></div>', unsafe_allow_html=True)

    pct_completado = round((len(con_fotos) / len(productos)) * 100, 1) if productos else 0.0
    st.progress(pct_completado / 100.0, text=f"📊 **Avance del Catálogo**: {pct_completado}% completado ({len(con_fotos)} de {len(productos)} productos listos con fotos)")

    # ==========================================
    # 1. SELECTOR SUPERIOR AL ANCHO DE PANTALLA
    # ==========================================
    st.markdown("#### 🔍 Selección y Búsqueda de Producto")
    col_filtro, col_search, col_reload = st.columns([1.3, 2.3, 0.6])
    
    with col_filtro:
        modo = st.radio("Filtrar estado:", ["⚠️ Pendientes Sin Foto", "📦 Todos los Productos", "✅ Con Fotos"], horizontal=True)

    with col_search:
        texto_busqueda = st.text_input("Buscador por SKU / Nombre Viejo / Modelo / Proveedor:", placeholder="Ej: ARMSHEESQNA01, ATXCAMAUQSREB, SHELBY...")

    with col_reload:
        st.write("")
        st.write("")
        if st.button("🔄 Refrescar"):
            with st.spinner("Escaneando fotos nuevas y sincronizando..."):
                photo_service.rescan_catalogs()
                st.cache_data.clear()
                st.rerun()

    # Búsqueda universal si hay texto
    if texto_busqueda and texto_busqueda.strip():
        q = texto_busqueda.strip().upper()
        lista_filtrada = [
            p for p in productos
            if q in p.get("sku", "").upper() or q in p.get("nombre_viejo", "").upper() or q in p.get("modelo", "").upper() or q in p.get("proveedor", "").upper()
        ]
        if not lista_filtrada:
            st.warning(f"No se encontró ningún producto con '{texto_busqueda}'.")
            return
    else:
        if modo == "⚠️ Pendientes Sin Foto":
            lista_filtrada = pendientes
        elif modo == "✅ Con Fotos":
            lista_filtrada = con_fotos
        else:
            lista_filtrada = productos

    if not lista_filtrada:
        st.warning("No hay productos para mostrar en este filtro.")
        return

    # Selector principal a todo el ancho
    opciones_display = [
        f"Fila {p['fila']:<4} | SKU: {p['sku']:<16} | {p['nombre_viejo']}"
        for p in lista_filtrada
    ]
    
    idx_sel = st.selectbox(
        f"Selecciona un producto para editar ({len(lista_filtrada)} coincidencias):",
        range(len(opciones_display)),
        format_func=lambda i: opciones_display[i]
    )
    
    producto_sel = lista_filtrada[idx_sel]
    fila_sel = producto_sel["fila"]

    # Banner resumen horizontal
    status_foto = "🟢 TIENE FOTOS" if producto_sel["tiene_fotos"] else "🔴 PENDIENTE DE FOTOS"
    st.markdown(f"""
    <div class="product-banner">
        <span style="font-weight: 800; font-size: 15px; color: #0F172A;">Fila {producto_sel['fila']} | SKU: {producto_sel['sku']}</span> &nbsp;·&nbsp; 
        <span style="color: #475569; font-weight: 600;">{producto_sel['nombre_viejo']}</span> &nbsp;·&nbsp; 
        <span style="font-size: 12px; font-weight: 700; color: {'#10B981' if producto_sel['tiene_fotos'] else '#EF4444'};">{status_foto}</span>
    </div>
    """, unsafe_allow_html=True)

    # ==========================================
    # 2. CUERPO PRINCIPAL EN 2 COLUMNAS
    # ==========================================
    col_left, col_right = st.columns([1.0, 1.3])

    with col_left:
        st.subheader("📋 Datos del Producto y Medidas")

        cur_sku = producto_sel.get("sku", "")
        cur_prov = producto_sel.get("proveedor", "").strip()
        cur_cat = producto_sel.get("categoria", "").strip()
        cur_tipo = producto_sel.get("tipo_mueble", "").strip()
        cur_mod = producto_sel.get("modelo", "").strip()
        cur_nn = producto_sel.get("nombre_nuevo", "").strip()

        # Opciones dinámicas para desplegables basadas en el documento
        prov_options = [""] + sorted(list(set(p for p in todos_proveedores if p)))
        if cur_prov and cur_prov not in prov_options: prov_options.append(cur_prov)
        
        cat_options = [""] + sorted(list(set(c for c in todas_categorias if c)))
        if cur_cat and cur_cat not in cat_options: cat_options.append(cur_cat)
        
        tipo_options = [""] + sorted(list(set(t for t in todos_tipos if t)))
        if cur_tipo and cur_tipo not in tipo_options: tipo_options.append(cur_tipo)

        # Proveedor y Categoría
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            p_idx = prov_options.index(cur_prov) if cur_prov in prov_options else 0
            prov_val = st.selectbox("PROVEEDOR (Col O):", prov_options, index=p_idx, key=f"prov_{fila_sel}")
        with c_p2:
            c_idx = cat_options.index(cur_cat) if cur_cat in cat_options else 0
            cat_val = st.selectbox("CATEGORIA (Col P):", cat_options, index=c_idx, key=f"cat_{fila_sel}")

        # Tipo de Mueble y Modelo
        c_t1, c_t2 = st.columns(2)
        with c_t1:
            t_idx = tipo_options.index(cur_tipo) if cur_tipo in tipo_options else 0
            tipo_val = st.selectbox("TIPO DE MUEBLE (Col Y):", tipo_options, index=t_idx, key=f"tipo_{fila_sel}")
        with c_t2:
            modelo_val = st.text_input("MODELO (Col X):", value=cur_mod, key=f"mod_{fila_sel}")

        # Nombre nuevo (Fiel al documento original)
        nombre_nuevo_val = st.text_input("NOMBRE NUEVO (Col Z):", value=cur_nn, key=f"nn_{fila_sel}")

        # Recuadros adicionales abajo de NOMBRE NUEVO (Col Z)
        c_sub1, c_sub2 = st.columns(2)
        with c_sub1:
            st.text_input(
                "NOMBRE ORIGINAL (Col B):",
                value=producto_sel.get("nombre_viejo", ""),
                disabled=True,
                key=f"txt_col_b_{fila_sel}"
            )
        with c_sub2:
            # Obtener valores en vivo de medidas sin empaque
            se = producto_sel.get("sin_empaque", {})
            fr_live = st.session_state.get(f"fr_se_{fila_sel}", str(se.get("frente", ""))).strip()
            fo_live = st.session_state.get(f"fo_se_{fila_sel}", str(se.get("fondo", ""))).strip()
            al_live = st.session_state.get(f"al_se_{fila_sel}", str(se.get("alto", ""))).strip()
            di_live = st.session_state.get(f"di_{fila_sel}", str(se.get("diametro", ""))).strip()

            if di_live and di_live.upper() not in ["", "N/A", "N/D", "0"]:
                medida_calc_live = f"{di_live} CM DIAM"
            elif fr_live and fo_live and al_live:
                medida_calc_live = f"{fr_live}X{fo_live}X{al_live} CM"
            else:
                medida_calc_live = producto_sel.get("medidas_sheet", "") or (f"{fr_live}X{fo_live}X{al_live} CM" if (fr_live or fo_live or al_live) else "")

            # Sincronización reactiva en tiempo real en session_state
            st.session_state[f"txt_medidas_concat_{fila_sel}"] = medida_calc_live

            medidas_concat_val = st.text_input(
                "MEDIDAS (Concatenado Sin Empaque):",
                key=f"txt_medidas_concat_{fila_sel}"
            )

        # Medidas Sin Empaque
        st.markdown("##### 📐 Medidas Sin Empaque (cm)")
        c_se1, c_se2, c_se3 = st.columns(3)
        with c_se1:
            frente_se = st.text_input("Frente (Col C):", value=str(se.get("frente", "")), key=f"fr_se_{fila_sel}")
            diametro = st.text_input("Diámetro (Col F):", value=str(se.get("diametro", "")), key=f"di_{fila_sel}")
        with c_se2:
            fondo_se = st.text_input("Fondo (Col D):", value=str(se.get("fondo", "")), key=f"fo_se_{fila_sel}")
            piso_asiento = st.text_input("Piso-Asiento (Col G):", value=str(se.get("piso_asiento", "")), key=f"pa_{fila_sel}")
        with c_se3:
            alto_se = st.text_input("Alto (Col E):", value=str(se.get("alto", "")), key=f"al_se_{fila_sel}")
            peso_se = st.text_input("Peso KG (Col H):", value=str(se.get("peso_kg", "")), key=f"pe_se_{fila_sel}")

        volumen_se = se.get("metro_3") or calcular_metro_cubico(frente_se, fondo_se, alto_se)
        st.caption(f"Volumen Sin Empaque (Col I): **{volumen_se} m³**")

        # Medidas Con Empaque
        st.markdown("##### 📦 Medidas Con Empaque (cm)")
        ce = producto_sel.get("con_empaque", {})
        c_ce1, c_ce2, c_ce3, c_ce4 = st.columns(4)
        with c_ce1:
            frente_ce = st.text_input("Frente (Emp) (Col J):", value=str(ce.get("frente", "")), key=f"fr_ce_{fila_sel}")
        with c_ce2:
            fondo_ce = st.text_input("Fondo (Emp) (Col K):", value=str(ce.get("fondo", "")), key=f"fo_ce_{fila_sel}")
        with c_ce3:
            alto_ce = st.text_input("Alto (Emp) (Col L):", value=str(ce.get("alto", "")), key=f"al_ce_{fila_sel}")
        with c_ce4:
            peso_ce = st.text_input("Peso (Emp) (Col M):", value=str(ce.get("peso_kg", "")), key=f"pe_ce_{fila_sel}")

        auto_m3 = st.checkbox("Recalcular Metro Cúbico con las medidas actuales", value=False, key=f"chk_m3_{fila_sel}")
        if auto_m3:
            metro_cubico_calc = calcular_metro_cubico(frente_ce, fondo_ce, alto_ce)
        else:
            metro_cubico_calc = ce.get("metro_cubico", "") or calcular_metro_cubico(frente_ce, fondo_ce, alto_ce)

        st.info(f"**Metro Cúbico con Empaque (Col N)**: `{metro_cubico_calc} m³`")
        bultos_val = st.text_input("BULTOS (Col AM):", value=producto_sel.get("bultos", "") or "1 BULTO", key=f"bul_{fila_sel}")

    with col_right:
        # ==========================================
        # 3. SECCIÓN DE FOTOS (1254 x 1254 px)
        # ==========================================
        st.subheader("🖼️ Sección de fotos (1254 x 1254 px)")
        st.caption("Visualiza las fotos asignadas en el archivo con sus metadatos o busca en la base final oficial.")

        fotos_final = photo_service.final_photos
        nombres_muebles = [f["nombre_sin_ext"] for f in fotos_final if "MUEBLE" in f.get("categoria_principal", "")]
        nombres_acabados = [f["nombre_sin_ext"] for f in fotos_final if "MADERA" in f.get("subcarpeta_rel", "") or "MATERIAL" in f.get("subcarpeta_rel", "")]
        nombres_swatch = [f["nombre_sin_ext"] for f in fotos_final if "TELA - MADERA" in f.get("subcarpeta_rel", "")]

        cur_fotos = producto_sel.get("fotos", {})

        tab1, tab2, tab3, tab4 = st.tabs(["1. Mueble", "2. Tela", "3. Madera / Tono", "4. Swatch"])

        # TAB 1: MUEBLE
        with tab1:
            foto_mueble_nom, foto_mueble_link, ruta_nueva_mueble = renderizar_bloque_foto_completo(
                titulo_bloque="Foto Mueble (Cols AA, AC)",
                icono="🪑",
                foto_nom_actual=cur_fotos.get("mueble_nombre", ""),
                foto_link_actual=cur_fotos.get("mueble_link", ""),
                lista_opciones=nombres_muebles,
                key_prefix="mueble",
                fila_id=fila_sel,
                sku_prod=cur_sku,
                modelo_prod=cur_mod
            )

        # TAB 2: TELA (EXCLUSIVO GOOGLE DRIVE)
        with tab2:
            foto_tela_nom, foto_tela_link, ruta_nueva_tela = renderizar_bloque_drive_exclusivo(
                titulo_bloque="Foto Tela",
                icono="🧵",
                col_cols="Cols AD, AF",
                folder_id=FOLDER_TELAS_DRIVE_ID,
                foto_nom_actual=cur_fotos.get("tela_nombre", ""),
                foto_link_actual=cur_fotos.get("tela_link", ""),
                fila_id=fila_sel,
                key_prefix="tela"
            )

        # TAB 3: MADERA / TONO (EXCLUSIVO GOOGLE DRIVE)
        with tab3:
            foto_madera_nom, foto_madera_link, ruta_nueva_madera = renderizar_bloque_drive_exclusivo(
                titulo_bloque="Foto Madera / Tono",
                icono="🪵",
                col_cols="Cols AG, AI",
                folder_id=FOLDER_MADERAS_DRIVE_ID,
                foto_nom_actual=cur_fotos.get("madera_nombre", ""),
                foto_link_actual=cur_fotos.get("madera_link", ""),
                fila_id=fila_sel,
                key_prefix="madera"
            )

        # TAB 4: MUESTRA / SWATCH (EXCLUSIVO GOOGLE DRIVE)
        with tab4:
            foto_swatch_nom, foto_swatch_link, ruta_nueva_swatch = renderizar_bloque_drive_exclusivo(
                titulo_bloque="Foto Muestra / Swatch",
                icono="🎨",
                col_cols="Cols AJ, AL",
                folder_id=FOLDER_MUESTRAS_DRIVE_ID,
                foto_nom_actual=cur_fotos.get("swatch_nombre", ""),
                foto_link_actual=cur_fotos.get("swatch_link", ""),
                fila_id=fila_sel,
                key_prefix="swatch"
            )

        st.markdown("---")

        # ==========================================
        # 4. BOTÓN DE GUARDADO SEGURO
        # ==========================================
        if st.button("💾 OK A TODO - GUARDAR EN GOOGLE SHEETS Y FOTOS NORMALIZADAS", type="primary", use_container_width=True, key=f"btn_save_{fila_sel}"):
            # Resolver enlaces faltantes automáticamente antes de guardar
            lnk_m = foto_mueble_link.strip() or (sheets_service.buscar_link_drive_inteligente(foto_mueble_nom) if foto_mueble_nom else "")
            lnk_t = foto_tela_link.strip() or (sheets_service.buscar_link_drive_inteligente(foto_tela_nom) if foto_tela_nom else "")
            lnk_md = foto_madera_link.strip() or (sheets_service.buscar_link_drive_inteligente(foto_madera_nom) if foto_madera_nom else "")
            lnk_sw = foto_swatch_link.strip() or (sheets_service.buscar_link_drive_inteligente(foto_swatch_nom) if foto_swatch_nom else "")

            datos_guardar = {
                "sku": normalizar_texto(cur_sku),
                "proveedor": prov_val,
                "categoria": cat_val,
                "modelo": normalizar_texto(modelo_val),
                "tipo_mueble": tipo_val,
                "nombre_nuevo": normalizar_texto(nombre_nuevo_val),
                "sin_empaque": {
                    "frente": str(frente_se).strip(),
                    "fondo": str(fondo_se).strip(),
                    "alto": str(alto_se).strip(),
                    "diametro": str(diametro).strip(),
                    "piso_asiento": str(piso_asiento).strip(),
                    "peso_kg": str(peso_se).strip(),
                    "metro_3": str(volumen_se).strip()
                },
                "con_empaque": {
                    "frente": str(frente_ce).strip(),
                    "fondo": str(fondo_ce).strip(),
                    "alto": str(alto_ce).strip(),
                    "peso_kg": str(peso_ce).strip(),
                    "metro_cubico": str(metro_cubico_calc).strip()
                },
                "fotos": {
                    "mueble_nombre": normalizar_texto(foto_mueble_nom),
                    "mueble_link": lnk_m,
                    "tela_nombre": normalizar_texto(foto_tela_nom),
                    "tela_link": lnk_t,
                    "madera_nombre": normalizar_texto(foto_madera_nom),
                    "madera_link": lnk_md,
                    "swatch_nombre": normalizar_texto(foto_swatch_nom),
                    "swatch_link": lnk_sw
                },
                "bultos": normalizar_texto(bultos_val)
            }

            with st.spinner("Guardando en Google Sheets y copiando fotos a Fotos Final..."):
                try:
                    # 1. Copia física de fotos seleccionadas a Fotos Final en su subcarpeta correspondiente
                    if ruta_nueva_mueble and foto_mueble_nom:
                        try:
                            subcarpeta_mueble = determinar_subcarpeta_destino_mueble(cat_val, tipo_val, cur_mod or cur_sku)
                            photo_service.copy_photo_to_final(ruta_nueva_mueble, subcarpeta_mueble, foto_mueble_nom)
                        except Exception as e_cp:
                            st.warning(f"Aviso copia foto mueble: {e_cp}")

                    if ruta_nueva_tela and foto_tela_nom:
                        try:
                            photo_service.copy_photo_to_final(ruta_nueva_tela, "FOTOS TELAS/TELAS", foto_tela_nom)
                        except Exception as e_cp:
                            st.warning(f"Aviso copia foto tela: {e_cp}")

                    if ruta_nueva_madera and foto_madera_nom:
                        try:
                            photo_service.copy_photo_to_final(ruta_nueva_madera, "FOTOS TELAS/MADERAS", foto_madera_nom)
                        except Exception as e_cp:
                            st.warning(f"Aviso copia foto madera: {e_cp}")

                    if ruta_nueva_swatch and foto_swatch_nom:
                        try:
                            photo_service.copy_photo_to_final(ruta_nueva_swatch, "FOTOS TELAS/TELA - MADERA", foto_swatch_nom)
                        except Exception as e_cp:
                            st.warning(f"Aviso copia foto swatch: {e_cp}")

                    # 2. Actualizar DATOS GENERAL de forma segura
                    sheets_service.update_product_row_safe(fila_sel, datos_guardar)

                    # 3. Registrar en FOTOS NORMALIZADAS con sus enlaces resueltos
                    if foto_mueble_nom:
                        sheets_service.register_in_fotos_normalizadas("MUEBLE", foto_mueble_nom, lnk_m)
                    if foto_tela_nom:
                        sheets_service.register_in_fotos_normalizadas("TELA", foto_tela_nom, lnk_t)
                    if foto_madera_nom:
                        sheets_service.register_in_fotos_normalizadas("MADERA", foto_madera_nom, lnk_md)
                    if foto_swatch_nom:
                        sheets_service.register_in_fotos_normalizadas("SWATCH", foto_swatch_nom, lnk_sw)

                    st.success(f"✅ ¡Fila {fila_sel} ({cur_sku}) guardada y copiada a Fotos Final exitosamente! Todas las fórmulas y vistas previas intactas.")
                    st.toast(f"¡Fila {fila_sel} ({cur_sku}) guardada con éxito!", icon="💾")
                    st.cache_data.clear()
                except Exception as err:
                    st.error(f"Error al guardar: {err}")

# Exported module function: render_odoo_catalog
