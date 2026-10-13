import io
import zipfile
from typing import List, Tuple, Dict, Any
from PIL import Image
import numpy as np

def split_catalog_strip(
    image_bytes: bytes,
    min_width_px: int = 40,
    white_threshold: int = 240,
    padding_pct: float = 0.08
) -> List[Dict[str, Any]]:
    """
    Detecta automáticamente cada mueble aislado en una tira/hoja horizontal sobre fondo blanco
    y recorta cada vista como una imagen individual centrada en fondo blanco puro (#FFFFFF).
    """
    orig_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = orig_img.size
    arr = np.array(orig_img)

    # Identificar píxeles no blancos
    is_white = np.all(arr >= white_threshold, axis=2)
    col_has_obj = np.any(~is_white, axis=0)

    # Segmentar columnas horizontales contiguas
    segments: List[Tuple[int, int]] = []
    in_seg = False
    start = 0
    for i, has_obj in enumerate(col_has_obj):
        if has_obj and not in_seg:
            in_seg = True
            start = i
        elif not has_obj and in_seg:
            in_seg = False
            if (i - start) >= min_width_px:
                segments.append((start, i))
    if in_seg and (w - start) >= min_width_px:
        segments.append((start, w))

    if not segments:
        return []

    cropped_results = []
    for idx, (x_start, x_end) in enumerate(segments, start=1):
        # Encontrar los límites verticales exactos del mueble dentro del segmento
        seg_mask = is_white[:, x_start:x_end]
        row_has_obj = np.any(~seg_mask, axis=1)
        nonzero_rows = np.where(row_has_obj)[0]

        if len(nonzero_rows) == 0:
            continue

        y_start = max(0, int(nonzero_rows[0]))
        y_end = min(h, int(nonzero_rows[-1]))

        # Recortar el objeto
        crop_box = (x_start, y_start, x_end, y_end)
        obj_crop = orig_img.crop(crop_box)
        obj_w, obj_h = obj_crop.size

        # Crear un lienzo cuadrado o proporcional limpio con margen blanco
        pad_x = int(obj_w * padding_pct)
        pad_y = int(obj_h * padding_pct)
        pad = max(pad_x, pad_y, 24)

        canvas_w = obj_w + (pad * 2)
        canvas_h = obj_h + (pad * 2)

        final_img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
        final_img.paste(obj_crop, (pad, pad))

        buf = io.BytesIO()
        final_img.save(buf, format="PNG", quality=95)
        out_bytes = buf.getvalue()

        cropped_results.append({
            "index": idx,
            "filename": f"vista_{idx}_separada.png",
            "bytes": out_bytes,
            "image": final_img,
            "width": canvas_w,
            "height": canvas_h
        })

    return cropped_results

def create_zip_from_cropped(crops: List[Dict[str, Any]], base_name: str = "mueble") -> bytes:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zf:
        for c in crops:
            idx = c.get("index", 1)
            fname = f"{base_name}_{c.get('filename', f'vista_{idx}.png')}"
            zf.writestr(fname, c["bytes"])
    return zip_buf.getvalue()
