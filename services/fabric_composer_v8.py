"""
Motor V8 de Física Textil, Calibración CIELAB +30% y Lienzo Maestro de Escala (100% Pillow puro).

Implementa los 4 pilares técnicos de Estudio IA V8 sin dependencias externas (sin numpy/scipy/cv2)
y con huella de memoria acotada (< 10 MB RAM, compatible con Render 512 MB):
  1. extract_clean_swatch_roi_v8: extracción genérica y determinista de regiones limpias con
     relieve real de figuras (descartando sombras diagonales de doblez y esquinas con etiquetas/parches).
  2. calibrate_fabric_lightness_v8: aplanado homomórfico de viñeteo macro + curva perceptual C¹
     Soft-Knee +30% en CIELAB + preservación de micro-relieve entre figuras + tope sRGB <= 243
     (protegiendo el recorte #FFFFFF >= 245 de format_image_2054_white).
  3. analyze_fabric_multitone_v8: análisis policromático a escala motivo (~6x6 px) en CIELAB
     extrayendo hasta 7 familias cromáticas de figuras/hebras, periodo espacial por autocorrelación
     y alternancia multitono entre sub-regiones.
  4. compute_v8_tile_px, make_toroidal_seamless_tile_v8 y build_v8_conditioning_canvas: síntesis de
     mosaico continuo sin costuras (81 a 289 baldosas reducidas en lienzo 1280x1280) adaptado al
     ancho físico del mueble, con el mueble alejado (~58%) al centro y halo/marco aislador #FFFFFF.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import io
import math
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

try:
    from PIL import ImageCms
    _HAS_IMAGECMS = True
except Exception:
    ImageCms = None  # type: ignore[assignment]
    _HAS_IMAGECMS = False


_CMS_LOCK = threading.Lock()
_RGB_TO_LAB_TRANSFORM: Any = None
_LAB_TO_RGB_TRANSFORM: Any = None
_CMS_INIT_FAILED = False

_CANVAS_CACHE_LOCK = threading.Lock()
_CANVAS_CACHE: "OrderedDict[str, V8ConditioningArtifacts]" = OrderedDict()
_CANVAS_CACHE_MAX_ENTRIES = 6
_CANVAS_CACHE_MAX_BYTES = 12 * 1024 * 1024
_CANVAS_CACHE_BYTES = 0


def _get_cms_transforms() -> Tuple[Any, Any]:
    """Obtiene y cachea a nivel módulo las transformaciones C de littlecms2 (sRGB <-> LAB)."""
    global _RGB_TO_LAB_TRANSFORM, _LAB_TO_RGB_TRANSFORM, _CMS_INIT_FAILED
    if _RGB_TO_LAB_TRANSFORM is not None and _LAB_TO_RGB_TRANSFORM is not None:
        return _RGB_TO_LAB_TRANSFORM, _LAB_TO_RGB_TRANSFORM
    if _CMS_INIT_FAILED or not _HAS_IMAGECMS:
        return None, None
    with _CMS_LOCK:
        if _RGB_TO_LAB_TRANSFORM is not None and _LAB_TO_RGB_TRANSFORM is not None:
            return _RGB_TO_LAB_TRANSFORM, _LAB_TO_RGB_TRANSFORM
        try:
            srgb_prof = ImageCms.createProfile("sRGB")
            lab_prof = ImageCms.createProfile("LAB")
            _RGB_TO_LAB_TRANSFORM = ImageCms.buildTransform(srgb_prof, lab_prof, "RGB", "LAB")
            _LAB_TO_RGB_TRANSFORM = ImageCms.buildTransform(lab_prof, srgb_prof, "LAB", "RGB")
            return _RGB_TO_LAB_TRANSFORM, _LAB_TO_RGB_TRANSFORM
        except Exception:
            _CMS_INIT_FAILED = True
            return None, None


# Pre-inicializa los perfiles ICC en C una sola vez al importar el módulo
_get_cms_transforms()


class _DictAccessMixin:
    """Permite acceso tanto por atributo como estilo diccionario (.get / [key] / .to_dict)."""

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        if hasattr(type(self), "mosaic_only_png"):
            d["mosaic_only_png"] = getattr(self, "mosaic_only_png")
        return d

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def keys(self):
        return self.to_dict().keys()


@dataclass
class SwatchROIV8(_DictAccessMixin):
    crop: Image.Image
    bbox: Tuple[int, int, int, int]
    source_size: Tuple[int, int]
    score: float
    relief_energy: float
    quad_mean_spread: float
    quad_std_spread: float
    min_rgb: int
    raw_min_rgb: int = 0
    raw_quad_mean_spread: float = 0.0
    secondary_crop: Optional[Image.Image] = None
    secondary_bbox: Optional[Tuple[int, int, int, int]] = None


@dataclass
class FabricMultitoneReportV8(_DictAccessMixin):
    mean_rgb: Tuple[int, int, int]
    mean_hex: str
    extrema_rgb: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]
    stddev_rgb: Tuple[float, float, float]
    bands: List[Dict[str, Any]] = field(default_factory=list)
    has_multitone_alternation: bool = False
    motif_period_px: float = 14.0
    color_description: str = ""
    pattern_and_figures: str = ""
    texture_detail: str = ""
    light_interaction: str = "Soft matte textile"


@dataclass(init=False)
class V8ConditioningArtifacts(_DictAccessMixin):
    canvas_png: bytes
    calibrated_swatch_png: bytes
    canvas_size: Tuple[int, int]
    tile_px: int
    grid_count: int
    total_tiles: int
    furn_scale: float
    isolation_mode: str
    halo_or_frame_px: int
    roi_bbox: Tuple[int, int, int, int]
    canvas_filename: str
    calibrated_swatch_filename: str
    mosaic_filename: str
    multitone_report: FabricMultitoneReportV8
    canvas_image: Optional[Image.Image] = None
    calibrated_swatch_image: Optional[Image.Image] = None
    seamless_tile_image: Optional[Image.Image] = None

    def __init__(
        self,
        canvas_png: bytes,
        calibrated_swatch_png: bytes,
        mosaic_only_png: Optional[bytes] = None,
        canvas_size: Tuple[int, int] = (1280, 1280),
        tile_px: int = 86,
        grid_count: int = 15,
        total_tiles: int = 225,
        furn_scale: float = 0.58,
        isolation_mode: str = "alpha_halo",
        halo_or_frame_px: int = 15,
        roi_bbox: Tuple[int, int, int, int] = (0, 0, 0, 0),
        canvas_filename: str = "",
        calibrated_swatch_filename: str = "",
        mosaic_filename: str = "",
        multitone_report: Optional[FabricMultitoneReportV8] = None,
        canvas_image: Optional[Image.Image] = None,
        calibrated_swatch_image: Optional[Image.Image] = None,
        seamless_tile_image: Optional[Image.Image] = None,
        _mosaic_source_image: Optional[Image.Image] = None,
    ) -> None:
        self.canvas_png = canvas_png
        self.calibrated_swatch_png = calibrated_swatch_png
        self._mosaic_only_png_cache: Optional[bytes] = mosaic_only_png
        self._mosaic_source_image: Optional[Image.Image] = _mosaic_source_image
        self.canvas_size = canvas_size
        self.tile_px = tile_px
        self.grid_count = grid_count
        self.total_tiles = total_tiles
        self.furn_scale = furn_scale
        self.isolation_mode = isolation_mode
        self.halo_or_frame_px = halo_or_frame_px
        self.roi_bbox = roi_bbox
        self.canvas_filename = canvas_filename
        self.calibrated_swatch_filename = calibrated_swatch_filename
        self.mosaic_filename = mosaic_filename
        self.multitone_report = multitone_report  # type: ignore[assignment]
        self.canvas_image = canvas_image
        self.calibrated_swatch_image = calibrated_swatch_image
        self.seamless_tile_image = seamless_tile_image

    @property
    def mosaic_only_png(self) -> bytes:
        global _CANVAS_CACHE_BYTES
        if self._mosaic_only_png_cache is None:
            src = self._mosaic_source_image
            if src is not None:
                mw, mh = src.size
                mos_small = (
                    src.resize((768, 768), Image.Resampling.BILINEAR)
                    if max(mw, mh) > 768
                    else src
                )
                buf = io.BytesIO()
                mos_small.save(buf, format="PNG", compress_level=1)
                self._mosaic_only_png_cache = buf.getvalue()
                self._mosaic_source_image = None
            else:
                self._mosaic_only_png_cache = b""
            with _CANVAS_CACHE_LOCK:
                if _CANVAS_CACHE:
                    _CANVAS_CACHE_BYTES = sum(v.approx_bytes() for v in _CANVAS_CACHE.values())
        return self._mosaic_only_png_cache

    @mosaic_only_png.setter
    def mosaic_only_png(self, value: Optional[bytes]) -> None:
        self._mosaic_only_png_cache = value

    def approx_bytes(self) -> int:
        mos_sz = (
            len(self._mosaic_only_png_cache)
            if self._mosaic_only_png_cache is not None
            else (262_144 if self._mosaic_source_image is not None else 0)
        )
        return len(self.canvas_png) + len(self.calibrated_swatch_png) + mos_sz


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    ri = max(0, min(255, int(round(r))))
    gi = max(0, min(255, int(round(g))))
    bi = max(0, min(255, int(round(b))))
    return f"#{ri:02X}{gi:02X}{bi:02X}"


def _srgb_to_lab_tuple(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Conversión puntual sRGB (0..255) -> CIELAB D65 exacta para clasificación de parches."""
    def _lin(c: float) -> float:
        v = max(0.0, min(1.0, c / 255.0))
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    rl, gl, bl = _lin(r), _lin(g), _lin(b)
    x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / 0.95047
    y = (0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl) / 1.00000
    z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) / 1.08883

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.00885645 else (7.787037 * t + 16.0 / 116.0)

    fx, fy, fz = _f(x), _f(y), _f(z)
    l_star = 116.0 * fy - 16.0
    a_star = 500.0 * (fx - fy)
    b_star = 200.0 * (fy - fz)
    return l_star, a_star, b_star


def _bytes_digest(*chunks: bytes) -> str:
    h = hashlib.sha1()
    for ch in chunks:
        if not ch:
            h.update(b"\x00")
            continue
        n = len(ch)
        h.update(n.to_bytes(8, "little", signed=False))
        if n <= 65_536:
            h.update(ch)
        else:
            h.update(ch[:24_576])
            h.update(ch[n // 2 - 8_192 : n // 2 + 8_192])
            h.update(ch[-24_576:])
    return h.hexdigest()


def _clean_stem(name: str, fallback: str) -> str:
    raw = os.path.basename(str(name or "").strip().replace("\\", "/"))
    stem = os.path.splitext(raw)[0].strip() if raw else ""
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem).strip(" ._")
    if stem.endswith("_V8_LIENZO_ESCALA"):
        stem = stem[: -len("_V8_LIENZO_ESCALA")]
    elif stem.endswith("_V8_LUZ30"):
        stem = stem[: -len("_V8_LUZ30")]
    elif stem.endswith("_V8_MOSAICO"):
        stem = stem[: -len("_V8_MOSAICO")]
    return stem or fallback


def make_v8_canvas_filename(furniture_name: str = "") -> str:
    return f"{_clean_stem(furniture_name, 'mueble')}_V8_LIENZO_ESCALA.png"


def make_v8_swatch_filename(fabric_name: str = "") -> str:
    return f"{_clean_stem(fabric_name, 'tela')}_V8_LUZ30.png"


def make_v8_mosaic_filename(fabric_name: str = "") -> str:
    return f"{_clean_stem(fabric_name, 'tela')}_V8_MOSAICO.png"


def _open_rgb_safe(raw_bytes: bytes, max_decode_side: int = 2048) -> Image.Image:
    with Image.open(io.BytesIO(raw_bytes)) as src:
        img = ImageOps.exif_transpose(src)
        if max(img.size) > max_decode_side * 2:
            factor = max(2, max(img.size) // (max_decode_side * 2))
            img = img.reduce(factor)
        if max(img.size) > max_decode_side:
            img = img.copy()
            img.thumbnail((max_decode_side, max_decode_side), Image.Resampling.LANCZOS)
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            return bg
        if img.mode != "RGB":
            return img.convert("RGB")
        return img.copy()


def _boxes_overlap_ratio(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = float((ix1 - ix0) * (iy1 - iy0))
    area_a = float(max(1, (a[2] - a[0]) * (a[3] - a[1])))
    area_b = float(max(1, (b[2] - b[0]) * (b[3] - b[1])))
    return inter / min(area_a, area_b)


def _hist_percentile(hist: List[int], total: int, q: float) -> int:
    if total <= 0:
        return 0
    target = max(1, int(math.ceil(total * q)))
    acc = 0
    for idx, cnt in enumerate(hist):
        acc += cnt
        if acc >= target:
            return idx
    return 255


def extract_clean_swatch_roi_v8(sample_bytes: bytes) -> SwatchROIV8:
    """
    Extrae de forma 100% genérica y guiada por imagen el mejor parche cuadrado interior limpio
    (~0.20..0.25 * min(W,H)), descartando bordes (~4%), la esquina inferior derecha de riesgo
    de etiquetas/marcas (x1 > 0.75*W y y1 > 0.80*H), y cualquier sombra/pliegue diagonal,
    premiando la energía real de figuras en relieve a escala motivo (~3-14 px).
    """
    if not sample_bytes:
        raise ValueError("sample_bytes vacío al extraer ROI de muestra de tela.")

    src = _open_rgb_safe(sample_bytes, max_decode_side=1600)
    W, H = src.size
    min_side = min(W, H)

    if min_side < 40:
        sm_im = src.filter(ImageFilter.GaussianBlur(radius=1.0)) if min_side >= 8 else src
        min_sm = min(e[0] for e in sm_im.getextrema())
        min_raw = min(e[0] for e in src.getextrema())
        return SwatchROIV8(
            crop=src.copy(),
            bbox=(0, 0, W, H),
            source_size=(W, H),
            score=1.0,
            relief_energy=float(sum(ImageStat.Stat(src).stddev) / 3.0),
            quad_mean_spread=0.0,
            quad_std_spread=0.0,
            min_rgb=int(min_sm),
            raw_min_rgb=int(min_raw),
            raw_quad_mean_spread=0.0,
        )

    # Escala de análisis rápida (<= 384 px) para mantener < 60 ms en muestras 1024x1024+
    scale = min(1.0, 384.0 / float(max(W, H)))
    w = max(32, int(round(W * scale)))
    h = max(32, int(round(H * scale)))
    work = src.resize((w, h), Image.Resampling.BILINEAR) if scale < 1.0 else src
    l_im = work.convert("L")

    # Energía pasa-banda a escala de figuras/motivos (~3-14 px a 1024px)
    r_fine = max(0.65, 1.0 * scale)
    r_coarse = max(2.2, 6.5 * scale)
    gf = l_im.filter(ImageFilter.GaussianBlur(radius=r_fine))
    gc = l_im.filter(ImageFilter.GaussianBlur(radius=r_coarse))
    relief_map = ImageChops.lighter(ImageChops.subtract(gf, gc), ImageChops.subtract(gc, gf))

    # Detector de surco/sombra macro de doblez (más ancho que un valle individual entre hilos)
    gm_narrow = l_im.filter(ImageFilter.GaussianBlur(radius=max(2.2, 9.0 * scale)))
    gm_wide = l_im.filter(ImageFilter.GaussianBlur(radius=max(7.5, 28.0 * scale)))
    crease_trough = ImageChops.subtract(gm_wide, gm_narrow)
    crease_ridge = ImageChops.subtract(gm_narrow, gm_wide)

    # Malla exacta 20x20 por promedio de caja en C: cada celda = 5% del ancho/alto
    G = 20 if min_side >= 120 else 12
    l_grid = l_im.resize((G, G), Image.Resampling.BOX).tobytes()
    r_grid = relief_map.resize((G, G), Image.Resampling.BOX).tobytes()
    c_grid = crease_trough.resize((G, G), Image.Resampling.BOX).tobytes()
    cr_grid = crease_ridge.resize((G, G), Image.Resampling.BOX).tobytes()

    if G == 20:
        win_cells = (4, 5)  # 4/20 = 0.20, 5/20 = 0.25
        margin_c = 1        # 1/20 = 5% (>= 4% borde exterior excluido)
    else:
        win_cells = (4, 5)
        margin_c = 1

    G1 = G + 1
    ps_l = [0.0] * (G1 * G1)
    ps_r = [0.0] * (G1 * G1)
    ps_xl = [0.0] * (G1 * G1)
    ps_yl = [0.0] * (G1 * G1)
    for yy in range(G):
        ro = yy * G
        pro = yy * G1
        npro = (yy + 1) * G1
        rl = rr = rxl = ryl = 0.0
        for xx in range(G):
            lv = float(l_grid[ro + xx])
            rv = float(r_grid[ro + xx])
            rl += lv
            rr += rv
            rxl += xx * lv
            ryl += yy * lv
            ps_l[npro + xx + 1] = ps_l[pro + xx + 1] + rl
            ps_r[npro + xx + 1] = ps_r[pro + xx + 1] + rr
            ps_xl[npro + xx + 1] = ps_xl[pro + xx + 1] + rxl
            ps_yl[npro + xx + 1] = ps_yl[pro + xx + 1] + ryl

    dx_cell = [0.0] * (G * G)
    dy_cell = [0.0] * (G * G)
    for yy in range(G):
        ro = yy * G
        for xx in range(G - 1):
            dx_cell[ro + xx] = float(l_grid[ro + xx]) - float(l_grid[ro + xx + 1])
        if yy + 1 < G:
            nro = (yy + 1) * G
            for xx in range(G):
                dy_cell[ro + xx] = float(l_grid[ro + xx]) - float(l_grid[nro + xx])

    prelim: List[Tuple[float, Tuple[int, int, int, int], float, float, float, float, int]] = []
    for gw in win_cells:
        if G - 2 * margin_c < gw:
            continue
        hw = max(1, gw // 2)
        n_cells = gw * gw
        qn = hw * hw
        cx_rel = (gw - 1) * 0.5
        hw_rel = (hw - 1) * 0.5
        sxx = float(gw * sum((i - cx_rel) ** 2 for i in range(gw))) or 1.0
        nx_span = G - gw + 1

        c_rmax = [0] * (G * nx_span)
        cr_rmax = [0] * (G * nx_span)
        dx_rmin = [0.0] * (G * nx_span)
        dx_rmax = [0.0] * (G * nx_span)
        dy_rmin = [0.0] * (G * nx_span)
        dy_rmax = [0.0] * (G * nx_span)
        for yy in range(G):
            ro = yy * G
            bo = yy * nx_span
            for gx in range(nx_span):
                sl_c = c_grid[ro + gx : ro + gx + gw]
                sl_cr = cr_grid[ro + gx : ro + gx + gw]
                c_rmax[bo + gx] = max(sl_c)
                cr_rmax[bo + gx] = max(sl_cr)
                sl_dx = dx_cell[ro + gx : ro + gx + gw - 1]
                dx_rmin[bo + gx] = min(sl_dx)
                dx_rmax[bo + gx] = max(sl_dx)
                if yy + 1 < G:
                    sl_dy = dy_cell[ro + gx : ro + gx + gw]
                    dy_rmin[bo + gx] = min(sl_dy)
                    dy_rmax[bo + gx] = max(sl_dy)

        for gy in range(margin_c, G - margin_c - gw + 1):
            gy1 = gy + gw
            for gx in range(margin_c, G - margin_c - gw + 1):
                gx1 = gx + gw
                # Excluir esquina inferior derecha propensa a etiquetas/marcas de agua
                if min_side >= 96 and (gx1 > int(0.75 * G) and gy1 > int(0.80 * G)):
                    continue

                i00 = gy * G1 + gx
                i01 = gy * G1 + gx1
                i10 = gy1 * G1 + gx
                i11 = gy1 * G1 + gx1
                l_sum = ps_l[i11] - ps_l[i01] - ps_l[i10] + ps_l[i00]
                r_sum = ps_r[i11] - ps_r[i01] - ps_r[i10] + ps_r[i00]

                c_max = 0
                cr_max = 0
                mn_dx = 1e9
                mx_dx = -1e9
                mn_dy = 1e9
                mx_dy = -1e9
                for yy in range(gy, gy1):
                    idx_r = yy * nx_span + gx
                    if c_rmax[idx_r] > c_max:
                        c_max = c_rmax[idx_r]
                    if cr_rmax[idx_r] > cr_max:
                        cr_max = cr_rmax[idx_r]
                    if dx_rmin[idx_r] < mn_dx:
                        mn_dx = dx_rmin[idx_r]
                    if dx_rmax[idx_r] > mx_dx:
                        mx_dx = dx_rmax[idx_r]
                    if yy + 1 < gy1:
                        if dy_rmin[idx_r] < mn_dy:
                            mn_dy = dy_rmin[idx_r]
                        if dy_rmax[idx_r] > mx_dy:
                            mx_dy = dy_rmax[idx_r]

                mean_l = l_sum / n_cells
                r_mean = r_sum / n_cells

                # Ajuste de plano suave de iluminación para separar caída gradual de luz vs sombra de doblez
                cx0 = gx + cx_rel
                cy0 = gy + cx_rel
                sum_xl = ps_xl[i11] - ps_xl[i01] - ps_xl[i10] + ps_xl[i00]
                sum_yl = ps_yl[i11] - ps_yl[i01] - ps_yl[i10] + ps_yl[i00]
                bx_s = (sum_xl - cx0 * l_sum) / sxx
                by_s = (sum_yl - cy0 * l_sum) / sxx

                q_raw: List[float] = []
                q_det: List[float] = []
                q_rel: List[float] = []
                for qy in (gy, gy + gw - hw):
                    qy1 = qy + hw
                    qcy = qy + hw_rel
                    for qx in (gx, gx + gw - hw):
                        qx1 = qx + hw
                        qcx = qx + hw_rel
                        qi00 = qy * G1 + qx
                        qi01 = qy * G1 + qx1
                        qi10 = qy1 * G1 + qx
                        qi11 = qy1 * G1 + qx1
                        qm_r = (ps_l[qi11] - ps_l[qi01] - ps_l[qi10] + ps_l[qi00]) / qn
                        qr_v = (ps_r[qi11] - ps_r[qi01] - ps_r[qi10] + ps_r[qi00]) / qn
                        q_pred = mean_l + bx_s * (qcx - cx0) + by_s * (qcy - cy0)
                        q_raw.append(qm_r)
                        q_det.append(qm_r - q_pred)
                        q_rel.append(qr_v)

                max_step_det = max(
                    abs(mx_dx + bx_s),
                    abs(mn_dx + bx_s),
                    abs(mx_dy + by_s),
                    abs(mn_dy + by_s),
                )

                qm_raw = max(q_raw) - min(q_raw)
                qm_det = max(q_det) - min(q_det)
                qr_sp = max(q_rel) - min(q_rel)

                penalty = (
                    1.0
                    + (max(0.0, qm_det - 2.2) / 2.4) ** 2
                    + (max(0.0, qm_raw - 14.0) / 4.0) ** 2
                    + (max(0.0, qr_sp - 1.25) / 0.90) ** 2
                    + (max(0.0, float(c_max) - 3.5) / 1.6) ** 2
                    + (max(0.0, float(cr_max) - 10.0) / 3.0) ** 2
                    + (max(0.0, max_step_det - 12.5) / 3.0) ** 2
                )
                p_score = ((r_mean + 0.5) ** 2.2) / penalty

                x0 = max(0, min(W - 8, int(round(gx * W / float(G)))))
                y0 = max(0, min(H - 8, int(round(gy * H / float(G)))))
                side_px = max(8, min(W - x0, H - y0, int(round(gw * min_side / float(G)))))
                x1 = x0 + side_px
                y1 = y0 + side_px
                if min_side >= 96 and (x1 > int(0.75 * W) and y1 > int(0.80 * H)):
                    continue

                prelim.append((p_score, (x0, y0, x1, y1), r_mean, qm_det, qm_raw, qr_sp, c_max))

    if not prelim:
        m_px = max(0, int(round(0.05 * min_side)))
        s_px = max(16, min(W - 2 * m_px, H - 2 * m_px, int(round(0.5 * min_side))))
        box_fb = (m_px, m_px, m_px + s_px, m_px + s_px)
        crop_fb = src.crop(box_fb)
        sm_fb = crop_fb.filter(ImageFilter.GaussianBlur(radius=1.5))
        return SwatchROIV8(
            crop=crop_fb,
            bbox=box_fb,
            source_size=(W, H),
            score=1.0,
            relief_energy=1.0,
            quad_mean_spread=0.0,
            quad_std_spread=0.0,
            min_rgb=int(min(e[0] for e in sm_fb.getextrema())),
            raw_min_rgb=int(min(e[0] for e in crop_fb.getextrema())),
        )

    prelim.sort(key=lambda r: r[0], reverse=True)

    # Refinamiento exacto en píxeles sobre los 5 mejores candidatos (< 5 ms total)
    finalists: List[Tuple[float, Tuple[int, int, int, int], float, float, float, float, int, int]] = []
    seen_boxes = set()

    for p_score, bx, r_mean, qm_det, qm_raw, _qr_sp, _c_max in prelim[:5]:
        if bx in seen_boxes:
            continue
        seen_boxes.add(bx)
        sub_rgb = src.crop(bx)
        sub_sm = sub_rgb.filter(ImageFilter.GaussianBlur(radius=1.5)) if min_side >= 64 else sub_rgb
        sub_l = sub_rgb.convert("L")
        sw, sh = sub_l.size
        hw, hh = max(1, sw // 2), max(1, sh // 2)

        # Aplanar iluminación lenta dentro del parche para medir uniformidad real de textura
        sub_vig = sub_l.filter(ImageFilter.GaussianBlur(radius=max(8, sw // 4)))
        mean_sub = int(round(ImageStat.Stat(sub_l).mean[0]))
        sub_flat = ImageChops.subtract(sub_l, sub_vig, scale=1.0, offset=mean_sub)

        q_stats = [
            ImageStat.Stat(sub_flat.crop((qx, qy, qx + hw, qy + hh)))
            for qy in (0, sh - hh)
            for qx in (0, sw - hw)
        ]
        qm_exact = max(s.mean[0] for s in q_stats) - min(s.mean[0] for s in q_stats)
        qstd_exact = max(s.stddev[0] for s in q_stats) - min(s.stddev[0] for s in q_stats)

        hist_sm = sub_sm.convert("L").histogram()
        tot_px = sw * sh
        p01_l = _hist_percentile(hist_sm, tot_px, 0.01)
        p05_l = _hist_percentile(hist_sm, tot_px, 0.05)
        p50_l = _hist_percentile(hist_sm, tot_px, 0.50)
        p99_l = _hist_percentile(hist_sm, tot_px, 0.99)
        sm_min_l = next((i for i, c in enumerate(hist_sm) if c > 0), p01_l)

        # Penaliza únicamente colas oscuras ASIMÉTRICAS (sombras de doblez), nunca el relieve 3D simétrico de figuras
        upper_reach = max(8.0, float(p99_l - p50_l))
        lower_reach = float(p50_l - p01_l)
        dark_asym = max(0.0, lower_reach - 1.40 * upper_reach - 8.0) + max(0.0, float(p05_l - sm_min_l) - 20.0)
        exact_pen = (
            1.0
            + (max(0.0, qm_exact - 3.5) / 2.6) ** 2
            + (max(0.0, qstd_exact - 1.8) / 1.3) ** 2
            + (dark_asym / 5.0) ** 2
        )
        final_score = p_score / exact_pen
        min_sm_rgb = int(min(e[0] for e in sub_sm.getextrema()))
        min_raw_rgb = int(min(e[0] for e in sub_rgb.getextrema()))
        finalists.append((
            final_score,
            bx,
            float(r_mean),
            float(qm_exact),
            float(qstd_exact),
            float(qm_raw),
            min_sm_rgb,
            min_raw_rgb,
        ))

    finalists.sort(key=lambda r: r[0], reverse=True)
    win = finalists[0]
    win_crop = src.crop(win[1])

    sec_crop: Optional[Image.Image] = None
    sec_box: Optional[Tuple[int, int, int, int]] = None
    for cand in finalists[1:]:
        if _boxes_overlap_ratio(win[1], cand[1]) < 0.25 and cand[0] >= 0.35 * win[0]:
            sec_box = cand[1]
            sec_crop = src.crop(sec_box)
            break

    return SwatchROIV8(
        crop=win_crop,
        bbox=win[1],
        source_size=(W, H),
        score=round(win[0], 4),
        relief_energy=round(win[2], 4),
        quad_mean_spread=round(win[3], 4),
        quad_std_spread=round(win[4], 4),
        min_rgb=win[6],
        raw_min_rgb=win[7],
        raw_quad_mean_spread=round(win[5], 4),
        secondary_crop=sec_crop,
        secondary_bbox=sec_box,
    )


_CEIL_LUTS_CACHE: Dict[Tuple[int, int], Tuple[List[int], List[int]]] = {}


def _apply_ratio_preserving_rgb_ceiling(
    rgb_img: Image.Image,
    max_rgb: int = 243,
    knee_rgb: Optional[int] = None,
) -> Image.Image:
    """
    Tope suave post-LAB en C puro (ImageChops + LUTs cacheadas, < 1.2 ms) preservando las
    razones R:G:B (0° giro de matiz) y garantizando max(R, G, B) <= max_rgb (<= 243).
    """
    ceil_v = max(180, min(254, int(max_rgb)))
    rc, gc, bc = rgb_img.split()
    max_ch = ImageChops.lighter(ImageChops.lighter(rc, gc), bc)
    hi_obs = max_ch.getextrema()[1]
    if knee_rgb is None and hi_obs <= ceil_v:
        return rgb_img
    knee = max(1, min(ceil_v - 1, int(knee_rgb))) if knee_rgb is not None else max(170, ceil_v - 11)
    if hi_obs <= knee:
        return rgb_img

    lut_key = (ceil_v, knee)
    luts = _CEIL_LUTS_CACHE.get(lut_key)
    if luts is None:
        span = float(max(1, ceil_v - knee))
        denom_top = float(max(1, 255 - knee))
        gain_lut = [255] * 256
        for m in range(knee + 1, 256):
            dm = float(m - knee)
            t = dm / denom_top
            m_target = float(knee) + span * (t / (1.0 + 0.18 * (1.0 - t)))
            if m_target > float(ceil_v):
                m_target = float(ceil_v)
            g_byte = int((m_target * 255.0) / float(m) + 0.5)
            while g_byte > 0 and ((m * g_byte + 128) // 255) > ceil_v:
                g_byte -= 1
            gain_lut[m] = max(0, min(255, g_byte))
        hard_ceil_lut = [i if i <= ceil_v else ceil_v for i in range(256)] * 3
        luts = (gain_lut, hard_ceil_lut)
        _CEIL_LUTS_CACHE[lut_key] = luts

    gain_lut, hard_ceil_lut = luts
    gain_im = max_ch.point(gain_lut)
    scaled = Image.merge(
        "RGB",
        (
            ImageChops.multiply(rc, gain_im),
            ImageChops.multiply(gc, gain_im),
            ImageChops.multiply(bc, gain_im),
        ),
    )
    return scaled.point(hard_ceil_lut)


def calibrate_fabric_lightness_v8(
    img: Image.Image,
    boost: float = 0.30,
    max_rgb: int = 243,
) -> Image.Image:
    """
    Calibra la luminosidad perceptual de la tela un +30% por defecto en CIELAB:
      - Aplana viñeteo macro de cámara en L* alrededor de la media global.
      - Descompone L_flat en base local suave (r=10) y micro-relieve 3D de figuras (R_128).
      - Aplica curva multiplicativa C¹-continua con hombro racional (L*_knee=82.5, L*_ceil=94.8).
      - Re-inyecta el micro-relieve local preservando >= 85% del contraste entre figuras incluso en
        telas claras marfil y manteniendo oscuras las telas azul marino / carbón.
      - Aplica compensación isotrópica sutil de croma en a*, b* (0.0° de giro de tono).
      - Cierra con tope suave sRGB preservador de matiz max(R, G, B) <= max_rgb (243).
    """
    if img is None:
        raise ValueError("Se requiere una imagen PIL válida en calibrate_fabric_lightness_v8.")

    rgb_in = img.convert("RGB") if img.mode != "RGB" else img.copy()
    w, h = rgb_in.size
    eff_boost = max(-0.50, min(1.00, float(boost)))
    ceil_rgb = max(180, min(254, int(max_rgb)))

    if abs(eff_boost) < 1e-6:
        return _apply_ratio_preserving_rgb_ceiling(rgb_in, max_rgb=ceil_rgb)

    rgb2lab, lab2rgb = _get_cms_transforms()

    if rgb2lab is not None and lab2rgb is not None:
        lab = ImageCms.applyTransform(rgb_in, rgb2lab)
        l_ch, a_ch, b_ch = lab.split()

        mean_l_byte = ImageStat.Stat(l_ch).mean[0]
        mean_l_star = (mean_l_byte / 255.0) * 100.0

        # 1. Aplanado homomórfico de caída lenta de iluminación macro (offset = media global)
        if min(w, h) >= 32:
            rad_vig = max(16, min(w, h) // 5)
            l_vig = l_ch.filter(ImageFilter.GaussianBlur(radius=rad_vig))
            l_flat = ImageChops.subtract(l_ch, l_vig, scale=1.0, offset=int(round(mean_l_byte)))
        else:
            l_flat = l_ch

        # 2. Descomposición en base local (r=10) + micro-relieve 3D entre figuras (R_128)
        rad_base = min(10, max(2, min(w, h) // 6))
        l_base = l_flat.filter(ImageFilter.GaussianBlur(radius=rad_base))
        r_128 = ImageChops.subtract(l_flat, l_base, scale=1.0, offset=128)

        # 3. Curva C¹ Soft-Knee en L* (0..100)
        # Si la tela ya es muy clara (mean L* > 86), centramos el techo para dejar margen de relieve bajo RGB 243
        l_knee = 84.0
        l_ceil = 96.5 if mean_l_star <= 86.0 else 92.8
        span = max(2.0, l_ceil - l_knee)
        lut_l: List[int] = []
        for bv in range(256):
            l_star = (bv / 255.0) * 100.0
            x = (1.0 + eff_boost) * l_star
            if x <= l_knee:
                l_new = x
            else:
                dx = x - l_knee
                l_new = l_knee + (span * dx) / (span + dx)
            lut_l.append(max(0, min(255, int(round((l_new / 100.0) * 255.0)))))

        l_lifted = l_base.point(lut_l)

        # 4. Re-inyección del relieve local entre figuras (~94% perceptual, compensando hombro sRGB en tonos claros)
        if mean_l_star >= 85.0:
            rel_gain = 1.18
        elif mean_l_star >= 62.0:
            rel_gain = 1.10
        else:
            rel_gain = 0.96
        lut_r = [max(0, min(255, int(round(128.0 + rel_gain * (i - 128.0))))) for i in range(256)]
        l_out = ImageChops.add(l_lifted, r_128.point(lut_r), scale=1.0, offset=-128)

        # 5. Compensación isotrópica sutil de croma alrededor de 128 (exactamente 0.0° de giro de matiz)
        chroma_gain = 1.0 + 0.24 * max(0.0, eff_boost)
        lut_ab = [max(0, min(255, int(round(128.0 + chroma_gain * (i - 128.0))))) for i in range(256)]
        a_out = a_ch.point(lut_ab)
        b_out = b_ch.point(lut_ab)

        rgb_cal = ImageCms.applyTransform(Image.merge("LAB", (l_out, a_out, b_out)), lab2rgb)
        return _apply_ratio_preserving_rgb_ceiling(rgb_cal, max_rgb=ceil_rgb)

    # Fallback puro Pillow en luminancia linealizada si littlecms2 no estuviera disponible
    lut_fb: List[int] = []
    knee_s = 212.0
    ceil_s = float(ceil_rgb)
    span_s = max(4.0, ceil_s - knee_s)
    for v in range(256):
        x = (1.0 + eff_boost * 0.85) * float(v)
        if x <= knee_s:
            vn = x
        else:
            dx = x - knee_s
            vn = knee_s + (span_s * dx) / (span_s + dx)
        lut_fb.append(max(0, min(ceil_rgb, int(round(vn)))))
    lifted = rgb_in.point(lut_fb * 3)
    return _apply_ratio_preserving_rgb_ceiling(lifted, max_rgb=ceil_rgb)


def _estimate_motif_period_px(gray_img: Image.Image) -> float:
    """Estima el periodo espacial de las figuras/hilos (en px) mediante autocorrelación 1D horizontal y vertical."""
    w, h = gray_img.size
    side = min(96, w, h)
    if side < 24:
        return 12.0
    ox = (w - side) // 2
    oy = (h - side) // 2
    sub = gray_img.crop((ox, oy, ox + side, oy + side))
    sub_s = sub.filter(ImageFilter.GaussianBlur(radius=0.8))
    buf = sub_s.tobytes()
    mean_v = sum(buf) / float(len(buf))
    centered = [float(b) - mean_v for b in buf]
    var_pix = sum(v * v for v in centered) / float(len(centered))
    if var_pix < 1e-3:
        return 12.0

    max_lag = min(36, side // 3)
    ac_x: List[float] = [1.0] * (max_lag + 1)
    ac_y: List[float] = [1.0] * (max_lag + 1)

    for lag in range(1, max_lag + 1):
        sx = 0.0
        nx = 0
        for yy in range(0, side, 4):
            ro = yy * side
            for xx in range(0, side - lag, 2):
                sx += centered[ro + xx] * centered[ro + xx + lag]
                nx += 1
        ac_x[lag] = (sx / nx) / var_pix if nx else 0.0

        sy = 0.0
        ny = 0
        for yy in range(0, side - lag, 2):
            ro = yy * side
            ro2 = (yy + lag) * side
            for xx in range(0, side, 4):
                sy += centered[ro + xx] * centered[ro2 + xx]
                ny += 1
        ac_y[lag] = (sy / ny) / var_pix if nx else 0.0

    def _first_repeat_lag(ac: List[float]) -> Optional[float]:
        dipped = False
        for k in range(2, len(ac) - 1):
            if ac[k] <= 0.12:
                dipped = True
            if dipped and k >= 5 and ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] > -0.05:
                return float(k)
        # Si cae monótonamente, usar el doble del primer cruce por <= 0.05
        for k in range(2, len(ac)):
            if ac[k] <= 0.05:
                return float(max(6, min(36, k * 2)))
        return None

    px = _first_repeat_lag(ac_x)
    py = _first_repeat_lag(ac_y)
    if px and py:
        return round(min(px, py) * 0.65 + max(px, py) * 0.35, 2)
    return round(px or py or 14.0, 2)


def _describe_calibrated_base_tone(r_v: float, g_v: float, b_v: float) -> Tuple[str, str]:
    lum_v = 0.299 * r_v + 0.587 * g_v + 0.114 * b_v
    ch_v = max(r_v, g_v, b_v) - min(r_v, g_v, b_v)
    wm_v = r_v - b_v
    if ch_v < 18:
        if lum_v >= 212:
            if wm_v >= 2.5:
                return (
                    "marfil-avena luminoso cálido",
                    "luminous warm ivory-oatmeal",
                )
            return ("blanco marfil piedra luminoso", "luminous alabaster-ivory")
        if lum_v >= 182:
            return (
                ("crema avena natural claro", "light warm oatmeal-cream")
                if wm_v >= 3.0
                else ("gris perla lino claro", "light pearl-linen grey")
            )
        if lum_v >= 135:
            return ("piedra greige medio", "medium stone-greige")
        if lum_v >= 75:
            return ("gris grafito / carbón", "charcoal grey")
        return ("antracita oscuro", "deep anthracite")

    if r_v >= g_v and r_v >= b_v:
        if (r_v - g_v) >= 34:
            return ("terracota / arcilla cálida", "warm terracotta / clay")
        if lum_v >= 195:
            return ("crema arena / camello suave luminoso", "luminous sand-cream / soft camel")
        if lum_v >= 145:
            return ("arena cálido / avena tostada", "warm toasted sand / oatmeal")
        return ("tabaco / caramelo cálido", "warm cognac / camel")
    if g_v >= r_v and g_v >= b_v:
        return ("verde salvia / oliva natural", "natural sage / olive green")
    return (
        ("azul marino profundo", "deep navy blue")
        if lum_v < 120
        else ("azul pizarra suave", "soft slate blue")
    )


def analyze_fabric_multitone_v8(
    calibrated_roi: Image.Image,
    raw_bytes: Optional[bytes] = None,
    sample_name: str = "",
) -> FabricMultitoneReportV8:
    """
    Muestrea parches a escala motivo (~6x6 px) sobre el ROI calibrado (+30%), convierte a CIELAB
    y extrae el espectro policromático de hasta 7 familias de figuras/hebras, el periodo espacial
    de motivo y la alternancia espacial multitono.
    """
    _ = raw_bytes
    if calibrated_roi is None:
        raise ValueError("calibrated_roi requerido en analyze_fabric_multitone_v8.")

    rgb = calibrated_roi.convert("RGB") if calibrated_roi.mode != "RGB" else calibrated_roi
    w, h = rgb.size
    st_rgb = ImageStat.Stat(rgb)
    mr, mg, mb = st_rgb.mean
    sr, sg, sb = st_rgb.stddev
    mean_rgb_t = (int(round(mr)), int(round(mg)), int(round(mb)))
    mean_hex = _rgb_to_hex(mr, mg, mb)
    extrema = rgb.getextrema()
    clean_lbl = _clean_stem(sample_name, "Muestra de Tela").replace("_", " ")
    lower_lbl = clean_lbl.lower()

    motif_period = _estimate_motif_period_px(rgb.convert("L"))

    # Malla de parches a escala figura (~6x6 px)
    patch_px = 6 if min(w, h) >= 72 else max(2, min(w, h) // 12)
    gw = max(6, min(48, w // patch_px))
    gh = max(6, min(48, h // patch_px))
    patch_rgb_im = rgb.resize((gw, gh), Image.Resampling.BOX)
    raw_p = patch_rgb_im.tobytes()

    rgb2lab, _ = _get_cms_transforms()
    if rgb2lab is not None:
        lab_patch = ImageCms.applyTransform(patch_rgb_im, rgb2lab)
        l_b, a_b, b_b = [ch.tobytes() for ch in lab_patch.split()]
    else:
        l_b = a_b = b_b = None

    patches: List[Tuple[int, int, int, float, float, float]] = []
    n_p = gw * gh
    for idx in range(n_p):
        off = idx * 3
        pr, pg, pb = raw_p[off], raw_p[off + 1], raw_p[off + 2]
        if l_b is not None and a_b is not None and b_b is not None:
            l_st = (float(l_b[idx]) / 255.0) * 100.0
            a_st = float(a_b[idx]) - 128.0
            b_st = float(b_b[idx]) - 128.0
        else:
            l_st, a_st, b_st = _srgb_to_lab_tuple(pr, pg, pb)
        patches.append((pr, pg, pb, l_st, a_st, b_st))

    max_std = max(sr, sg, sb)
    max_span_rgb = max(e[1] - e[0] for e in extrema)
    es_base, en_base = _describe_calibrated_base_tone(mr, mg, mb)

    # Caso sintético 100% monocromo plano
    if max_std < 1.1 and max_span_rgb <= 4:
        l0, a0, b0 = _srgb_to_lab_tuple(mr, mg, mb)
        mono_band = {
            "id": "solid_uniform",
            "name": "Tono Uniforme Sólido",
            "name_en": "Solid Uniform Tone",
            "share_pct": 100.0,
            "hex": mean_hex,
            "rgb": mean_rgb_t,
            "lab": (round(l0, 2), round(a0, 2), round(b0, 2)),
            "role": "Tejido continuo monocromático sin variación multitono entre figuras",
        }
        return FabricMultitoneReportV8(
            mean_rgb=mean_rgb_t,
            mean_hex=mean_hex,
            extrema_rgb=extrema,
            stddev_rgb=(round(sr, 2), round(sg, 2), round(sb, 2)),
            bands=[mono_band],
            has_multitone_alternation=False,
            motif_period_px=motif_period,
            color_description=(
                f"{es_base} ({en_base}) pre-calibrado V8 +30% en tono sólido uniforme {mean_hex} "
                f"(RGB {mean_rgb_t[0]},{mean_rgb_t[1]},{mean_rgb_t[2]})"
            ),
            pattern_and_figures="Unpatterned uniform monochrome textile surface",
            texture_detail="clean uniform woven upholstery textile with subtle micro-thread grain",
            light_interaction="Soft matte textile",
        )

    l_sorted = sorted(p[3] for p in patches)
    a_sorted = sorted(p[4] for p in patches)
    b_sorted = sorted(p[5] for p in patches)

    def _q(arr: List[float], qv: float) -> float:
        pos = max(0, min(len(arr) - 1, int(round((len(arr) - 1) * qv))))
        return arr[pos]

    l_p10 = _q(l_sorted, 0.10)
    l_p88 = _q(l_sorted, 0.88)
    a_med = _q(a_sorted, 0.50)
    b_med = _q(b_sorted, 0.50)
    a_p84 = _q(a_sorted, 0.84)
    b_p88 = _q(b_sorted, 0.88)
    b_p62 = _q(b_sorted, 0.62)
    b_p20 = _q(b_sorted, 0.20)

    bucket_specs = [
        (
            "ivory_crowns",
            "Crestas Luminosas de Figura",
            "Bright Raised Figure Crowns",
            "Cimas de las figuras en relieve que captan la luz de estudio",
        ),
        (
            "warm_camel_yarns",
            "Hebras Cálidas Camel / Arena",
            "Warm Camel / Toasted Sand Yarns",
            "Figuras e hilos cálidos dorados/arena distribuidos de forma orgánica",
        ),
        (
            "oatmeal_figures",
            "Figuras Cuerpo Avena / Crema",
            "Warm Oatmeal Figure Body",
            "Cuerpo cálido principal de las figuras tejidas en relieve",
        ),
        (
            "rosy_taupe_accents",
            "Acentos Subtono Taupe-Rosado",
            "Soft Rosy-Taupe Slub Accents",
            "Matiz cálido sutil en hebras alternas que enriquece el patrón",
        ),
        (
            "neutral_stone_ground",
            "Matriz Piedra / Lino Neutro",
            "Neutral Stone / Linen Matrix",
            "Base orgánica equilibrada de entrelazado principal",
        ),
        (
            "cool_silver_threads",
            "Contra-Hilos Ceniza / Plata Frío",
            "Cool Silver-Ash Counter-Threads",
            "Contra-hilos frescos minerales que evitan dominante amarilla",
        ),
        (
            "deep_figure_valleys",
            "Valles de Relieve entre Figuras",
            "Deep Inter-Figure Relief Valleys",
            "Contorno y micro-sombra 3D entre figura y figura",
        ),
    ]
    buckets: Dict[str, List[Tuple[int, int, int, float, float, float]]] = {b[0]: [] for b in bucket_specs}

    for p in patches:
        _, _, _, ls, as_, bs = p
        if ls >= l_p88 and (l_p88 - l_p10) >= 1.8:
            buckets["ivory_crowns"].append(p)
        elif ls <= l_p10 and (l_p88 - l_p10) >= 1.8:
            buckets["deep_figure_valleys"].append(p)
        elif bs >= max(b_med + 0.9, b_p88):
            buckets["warm_camel_yarns"].append(p)
        elif as_ >= max(a_med + 0.45, a_p84):
            buckets["rosy_taupe_accents"].append(p)
        elif bs <= min(b_med - 0.55, b_p20):
            buckets["cool_silver_threads"].append(p)
        elif bs >= max(b_med + 0.15, b_p62):
            buckets["oatmeal_figures"].append(p)
        else:
            buckets["neutral_stone_ground"].append(p)

    bands: List[Dict[str, Any]] = []
    for bid, name_es, name_en, role_txt in bucket_specs:
        pts = buckets[bid]
        if not pts:
            continue
        share = (len(pts) * 100.0) / float(n_p)
        if share < 0.4:
            continue
        ar = sum(x[0] for x in pts) / len(pts)
        ag = sum(x[1] for x in pts) / len(pts)
        ab = sum(x[2] for x in pts) / len(pts)
        al = sum(x[3] for x in pts) / len(pts)
        aa = sum(x[4] for x in pts) / len(pts)
        abb = sum(x[5] for x in pts) / len(pts)
        rgb_t = (int(round(ar)), int(round(ag)), int(round(ab)))
        bands.append({
            "id": bid,
            "name": name_es,
            "name_en": name_en,
            "share_pct": round(share, 1),
            "hex": _rgb_to_hex(ar, ag, ab),
            "rgb": rgb_t,
            "lab": (round(al, 2), round(aa, 2), round(abb, 2)),
            "role": role_txt,
        })

    # Detector de alternancia multitono espacial (tanto entre figuras vecinas como a meso-escala)
    adj_color_diffs: List[float] = []
    for yy in range(gh):
        for xx in range(gw - 1):
            p1 = patches[yy * gw + xx]
            p2 = patches[yy * gw + xx + 1]
            de = math.sqrt((p1[3] - p2[3]) ** 2 + (p1[4] - p2[4]) ** 2 + (p1[5] - p2[5]) ** 2)
            adj_color_diffs.append(de)
    mean_adj_de = (sum(adj_color_diffs) / len(adj_color_diffs)) if adj_color_diffs else 0.0
    l_span_80 = _q(l_sorted, 0.90) - _q(l_sorted, 0.10)
    b_span_80 = _q(b_sorted, 0.90) - _q(b_sorted, 0.10)
    distinct_hexes = {b["hex"] for b in bands}

    has_multitone = bool(
        len(distinct_hexes) >= 3
        and (l_span_80 >= 3.2 or b_span_80 >= 1.4 or mean_adj_de >= 1.8)
    )

    band_snippets_es = [
        f"{b['name']} {b['hex']} (RGB {b['rgb'][0]},{b['rgb'][1]},{b['rgb'][2]}, {b['share_pct']}%)"
        for b in bands[:7]
    ]
    band_snippets_en = [
        f"{b['name_en']} {b['hex']} (RGB {b['rgb'][0]},{b['rgb'][1]},{b['rgb'][2]}, {b['share_pct']}%)"
        for b in bands[:7]
    ]

    if any(w in lower_lbl for w in ("terciopelo", "velvet")):
        tex_detail = "plush directional velvet pile with subtle multi-tone micro-nap"
        light_desc = "Directional velvet sheen"
    elif any(w in lower_lbl for w in ("pana", "corduroy")):
        tex_detail = "distinct parallel ribbed corduroy wales with tactile pile relief"
        light_desc = "Soft matte textile"
    elif any(w in lower_lbl for w in ("lino", "linen")):
        tex_detail = "crisp natural slubbed multi-yarn linen basketweave with tactile thread relief"
        light_desc = "Soft matte textile"
    else:
        tex_detail = (
            "raised 3D pebbled bouclé-chenille woven figures and organic multi-yarn slubs over tight recessed interstitial valleys"
        )
        light_desc = "Soft matte textile"

    color_desc = (
        f"tejido policromático pre-calibrado V8 (+30% claridad de estudio, media {mean_hex} / "
        f"RGB {mean_rgb_t[0]},{mean_rgb_t[1]},{mean_rgb_t[2]} — {es_base} / {en_base}) con {len(bands)} bandas de tonos "
        f"alternados entre figuras: " + "; ".join(band_snippets_es)
    )
    pattern_desc = (
        f"Polychromatic 3D raised organic woven figures (spatial motif period ~{motif_period:.1f} px in swatch ROI) "
        f"alternating {len(bands)} distinct yarn color families ({'; '.join(band_snippets_en)}) — "
        f"NEVER render as a flat single-color paint fill"
    )

    return FabricMultitoneReportV8(
        mean_rgb=mean_rgb_t,
        mean_hex=mean_hex,
        extrema_rgb=extrema,
        stddev_rgb=(round(sr, 2), round(sg, 2), round(sb, 2)),
        bands=bands,
        has_multitone_alternation=has_multitone,
        motif_period_px=motif_period,
        color_description=color_desc,
        pattern_and_figures=pattern_desc,
        texture_detail=tex_detail,
        light_interaction=light_desc,
    )


_V8_WIDTH_CATEGORY_KEYWORDS: Tuple[str, ...] = (
    "seccional",
    "modular",
    "esquinera",
    "sala en l",
    "loveseat",
    "love seat",
    "sofa cama",
    "sofá cama",
    "sofa",
    "sofá",
    "sala",
    "cama",
    "bed",
    "cabecera",
    "headboard",
    "comedor",
    "dining",
    "credenza",
    "aparador",
    "buffet",
    "banca",
    "bench",
    "pie de cama",
    "sillon",
    "sillón",
    "butaca",
    "poltrona",
    "individual",
    "armchair",
    "silla",
    "chair",
    "banco",
    "taburete",
    "stool",
    "buro",
    "buró",
)

_V8_GENERIC_AI_FURNITURE_PHRASES: Tuple[str, ...] = (
    "attached photo",
    "exact subject",
    "reference photo",
    "reference image",
    "upholstered seating piece",
    "contemporary upholstered seating",
    "architectural table",
    "architectural storage",
    "material / textile texture swatch",
    "flat close-up material",
    "mueble mostrado",
    "foto adjunta",
    "imagen adjunta",
    "sujeto exacto",
)

_V8_GENERIC_NAME_STEMS = frozenset(
    {
        "",
        "mueble",
        "furniture",
        "furniture piece",
        "foto",
        "imagen",
        "image",
        "vista",
        "muestra",
        "referencia",
        "referencia_color",
    }
)


def _has_v8_specific_width_hint(text: str) -> bool:
    raw = (text or "").strip().lower()
    if not raw:
        return False
    if re.search(
        r"(?<![a-z0-9.])([0-9]+(?:\.[0-9]+)?)\s*(?:cm)?\s*(?:frente|ancho|largo|width|diam|di[aá]metro)",
        raw,
    ):
        return True
    if re.search(r"(?:frente|ancho|largo|width|d\.|diam\.?)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)", raw):
        return True
    if re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)", raw):
        return True
    norm = raw.replace("_", " ").replace("-", " ")
    return any(k in norm for k in _V8_WIDTH_CATEGORY_KEYWORDS)


def clean_v8_ai_furniture_item(ai_furniture_item: str = "") -> str:
    """Descarta placeholders genéricos de Vision/fallback para no eclipsar el nombre real del mueble."""
    raw = str(ai_furniture_item or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    if low in _V8_GENERIC_NAME_STEMS:
        return ""
    if any(p in low for p in _V8_GENERIC_AI_FURNITURE_PHRASES):
        return ""
    return raw


def _clean_v8_name_stem(val: str = "") -> str:
    base = os.path.basename(str(val or "").strip())
    stem = os.path.splitext(base)[0].strip() if base else ""
    low = stem.lower()
    if not stem or low in _V8_GENERIC_NAME_STEMS:
        return ""
    if re.fullmatch(r"(?:mueble|vista|foto|imagen|image|muestra)_[0-9]+", low):
        return ""
    return stem


def resolve_v8_furniture_type_hint(
    tipo_mueble: str = "",
    ai_furniture_item: str = "",
    furniture_name: str = "",
    primary_filename: str = "",
) -> str:
    """
    Resuelve de forma determinista la pista de categoría/tipo del mueble en V8 para que la tira 76x76,
    build_prompts, build_34_derecha_2054_prompts y el ZIP produzcan exactamente el mismo w_cm y total_tiles:
      - Si `tipo_mueble` explícito no es genérico, lo prioriza (añadiendo el nombre del archivo solo si
        `tipo_mueble` carece de categoría de ancho específica y no es muestra plana).
      - Filtra placeholders genéricos de `ai_furniture_item` ("exact subject shown in the attached photo",
        "contemporary upholstered seating piece", etc.) para que jamás tapen a `furniture_name`/`primary_filename`.
    """
    tipo_clean = clean_v8_ai_furniture_item(tipo_mueble)
    ai_clean = clean_v8_ai_furniture_item(ai_furniture_item)

    name_tokens: List[str] = []
    seen_low = set()
    for cand in (_clean_v8_name_stem(furniture_name), _clean_v8_name_stem(primary_filename)):
        if cand and cand.lower() not in seen_low:
            seen_low.add(cand.lower())
            name_tokens.append(cand)
    name_hint = " ".join(name_tokens).strip()

    if tipo_clean:
        low_tipo = tipo_clean.lower()
        if _has_v8_specific_width_hint(tipo_clean) or any(s in low_tipo for s in ("swatch", "muestra", "sample")):
            return tipo_clean
        return f"{tipo_clean} {name_hint}".strip() if name_hint else tipo_clean

    if name_hint and _has_v8_specific_width_hint(name_hint):
        return name_hint
    if ai_clean:
        return f"{ai_clean} {name_hint}".strip() if name_hint else ai_clean
    return name_hint


def infer_furniture_width_cm_v8(
    furniture_width_cm: Optional[float] = None,
    furniture_type: str = "",
    medidas_texto: str = "",
) -> float:
    """Infiere el ancho físico del mueble (cm) a partir de medidas explícitas o categoría."""
    if furniture_width_cm is not None and float(furniture_width_cm) > 5.0:
        return float(furniture_width_cm)

    txt = f"{furniture_type or ''} {medidas_texto or ''}".lower()
    m_w = re.search(
        r"(?<![a-z0-9.])([0-9]+(?:\.[0-9]+)?)\s*(?:cm)?\s*(?:frente|ancho|largo|width|diam|di[aá]metro)",
        txt,
    )
    if m_w:
        val = float(m_w.group(1))
        if val > 5.0:
            return val
    m_after = re.search(r"(?:frente|ancho|largo|width|d\.|diam\.?)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)", txt)
    if m_after:
        val = float(m_after.group(1))
        if val > 5.0:
            return val
    m_trip = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)", txt)
    if m_trip:
        val = float(m_trip.group(1))
        if val > 5.0:
            return val

    norm_txt = txt.replace("_", " ").replace("-", " ")
    if any(k in norm_txt for k in ("seccional", "modular", "esquinera", "sala en l")):
        return 250.0
    if any(k in norm_txt for k in ("loveseat", "love seat", "sofa cama", "sofá cama")):
        return 165.0
    if any(k in norm_txt for k in ("sofa", "sofá", "sala")):
        return 220.0
    if any(k in norm_txt for k in ("cama", "bed", "cabecera", "headboard")):
        return 190.0
    if any(k in norm_txt for k in ("comedor", "dining")):
        return 200.0
    if any(k in norm_txt for k in ("credenza", "aparador", "buffet")):
        return 180.0
    if any(k in norm_txt for k in ("banca", "bench", "pie de cama")):
        return 130.0
    if any(k in norm_txt for k in ("sillon", "sillón", "butaca", "poltrona", "individual", "armchair")):
        return 85.0
    if any(k in norm_txt for k in ("silla", "chair", "banco", "taburete", "stool", "buro", "buró")):
        return 55.0
    return 160.0


def compute_v8_tile_px(
    canvas_px: int = 1280,
    furniture_width_cm: Optional[float] = None,
    furniture_type: str = "",
    motif_period_px: float = 14.0,
    roi_px: int = 240,
    furn_scale: float = 0.58,
) -> Tuple[int, int]:
    """
    Calcula (tile_px, grid_n) en un lienzo canvas_px (1280) con el mueble alejado a furn_scale (~0.58):
      - grid_n está estrictamente acotado en [9, 17] -> total_tiles = grid_n^2 en [81, 289].
      - Estrictamente monótono respecto al ancho del mueble: muebles más anchos reciben más baldosas
        y tile_px menor (tile_px(220cm) < tile_px(165cm) < tile_px(85cm) < tile_px(55cm)).
    """
    _ = motif_period_px, roi_px
    c_px = max(512, int(canvas_px))
    f_sc = max(0.35, min(0.85, float(furn_scale)))
    w_cm = infer_furniture_width_cm_v8(furniture_width_cm=furniture_width_cm, furniture_type=furniture_type)

    # Mapeo físico monótono: 50 cm -> grid 9 (81 tiles), 85 cm -> grid 11 (121), 165 cm -> grid 14 (196), 220 cm -> grid 17 (289)
    w_clamped = max(45.0, min(260.0, w_cm))
    scale_adj = 0.58 / f_sc
    norm_w = max(0.0, (w_clamped * scale_adj - 50.0) / (225.0 - 50.0))
    grid_f = 9.0 + 8.0 * (norm_w ** 0.85)
    grid_n = max(9, min(17, int(round(grid_f))))
    tile_px = int(math.ceil(float(c_px) / float(grid_n)))
    return tile_px, grid_n


def make_toroidal_seamless_tile_v8(
    calibrated_roi: Image.Image,
    tile_px: int,
    max_rgb: int = 243,
) -> Image.Image:
    """
    Sintetiza una baldosa tile_px x tile_px sin costuras visibles:
      1) Aplana cualquier gradiente residual de borde a borde sobre el ROI calibrado.
      2) Redimensiona con LANCZOS a (tile_px + ov, tile_px + ov) con ov = max(10, tile_px // 4).
      3) Aplica UnsharpMask suave para preservar nitidez de micro-figuras (~2-3 px).
      4) Mezcla toroidalmente las franjas de traslape en X y Y con rampa alfa coseno alzado
         0.5 * (1 - cos(pi * (t + 0.5) / ov)), de modo que el borde derecho empata al pixel
         con el borde izquierdo y el inferior con el superior (0% líneas de cuadrícula).
      5) Asegura max(R, G, B) <= max_rgb (243).
    """
    if calibrated_roi is None:
        raise ValueError("calibrated_roi requerido en make_toroidal_seamless_tile_v8.")

    t_px = max(16, int(tile_px))
    ov = max(10, t_px // 4)
    ext_px = t_px + ov

    base = calibrated_roi.convert("RGB") if calibrated_roi.mode != "RGB" else calibrated_roi.copy()
    bw, bh = base.size
    if min(bw, bh) >= 32:
        # Eliminar cualquier pendiente residual de muy baja frecuencia antes del traslape toroidal
        rad_flat = max(10, min(bw, bh) // 3)
        chs = base.split()
        flat_chs = []
        for ch in chs:
            m_ch = int(round(ImageStat.Stat(ch).mean[0]))
            low = ch.filter(ImageFilter.GaussianBlur(radius=rad_flat))
            flat_chs.append(ImageChops.subtract(ch, low, scale=1.0, offset=m_ch))
        base = Image.merge("RGB", tuple(flat_chs))

    work = base.resize((ext_px, ext_px), Image.Resampling.LANCZOS)
    work = work.filter(ImageFilter.UnsharpMask(radius=0.75, percent=42, threshold=2))

    ramp_vals = [
        max(0, min(255, int(round(255.0 * 0.5 * (1.0 - math.cos(math.pi * (t + 0.5) / float(ov)))))))
        for t in range(ov)
    ]

    # Mezcla toroidal en X -> tamaño (t_px, ext_px)
    mask_x_row = Image.frombytes("L", (ov, 1), bytes(ramp_vals))
    mask_x = mask_x_row.resize((ov, ext_px), Image.Resampling.NEAREST)
    left_x = work.crop((0, 0, ov, ext_px))
    right_x = work.crop((t_px, 0, ext_px, ext_px))
    blended_x = Image.composite(left_x, right_x, mask_x)
    tile_x = Image.new("RGB", (t_px, ext_px))
    tile_x.paste(blended_x, (0, 0))
    tile_x.paste(work.crop((ov, 0, t_px, ext_px)), (ov, 0))

    # Mezcla toroidal en Y -> tamaño (t_px, t_px)
    mask_y_col = Image.frombytes("L", (1, ov), bytes(ramp_vals))
    mask_y = mask_y_col.resize((t_px, ov), Image.Resampling.NEAREST)
    top_y = tile_x.crop((0, 0, t_px, ov))
    bot_y = tile_x.crop((0, t_px, t_px, ext_px))
    blended_y = Image.composite(top_y, bot_y, mask_y)
    tile_xy = Image.new("RGB", (t_px, t_px))
    tile_xy.paste(blended_y, (0, 0))
    tile_xy.paste(tile_x.crop((0, ov, t_px, t_px)), (0, ov))

    return _apply_ratio_preserving_rgb_ceiling(tile_xy, max_rgb=max_rgb)


_STUDIO_WHITE_MIN_LUT: List[int] = [255 if i >= 244 else 0 for i in range(256)]
_STUDIO_WHITE_CHROMA_LUT: List[int] = [255 if i <= 10 else 0 for i in range(256)]


def _extract_studio_cutout_mask(furn_src: Image.Image) -> Optional[Tuple[Image.Image, Image.Image]]:
    """
    Si la foto del mueble tiene canal alfa transparente real O fondo exterior blanco de estudio
    uniforme (verificando esquinas + anillo perimetral >= 244 para jamás confundir muros beige),
    devuelve (furn_rgb, fg_mask_L). En caso contrario devuelve None (escena de cuarto/taller).
    """
    w, h = furn_src.size
    if w < 16 or h < 16:
        return None

    # 1. Revisar transparencia real RGBA / LA / P
    if furn_src.mode in ("RGBA", "LA") or (furn_src.mode == "P" and "transparency" in furn_src.info):
        rgba = furn_src.convert("RGBA")
        alpha = rgba.getchannel("A")
        ext_a = alpha.getextrema()
        if ext_a and ext_a[0] < 235:
            corners_a = [
                alpha.getpixel((0, 0)),
                alpha.getpixel((w - 1, 0)),
                alpha.getpixel((0, h - 1)),
                alpha.getpixel((w - 1, h - 1)),
            ]
            if sum(1 for a in corners_a if a < 64) >= 2:
                bg_white = Image.new("RGB", (w, h), (255, 255, 255))
                bg_white.paste(rgba.convert("RGB"), mask=alpha)
                fg_mask = alpha.point([255 if i >= 24 else 0 for i in range(256)])
                return bg_white, fg_mask

    rgb = furn_src.convert("RGB") if furn_src.mode != "RGB" else furn_src

    # 2. Construir mapa binario de blanco de estudio en C (< 0.5 ms) y validar esquinas + perímetro
    det_scale = min(1.0, 320.0 / float(max(w, h)))
    dw = max(16, int(round(w * det_scale)))
    dh = max(16, int(round(h * det_scale)))
    small = rgb.resize((dw, dh), Image.Resampling.BILINEAR) if det_scale < 1.0 else rgb

    r_ch, g_ch, b_ch = small.split()
    min_c = ImageChops.darker(ImageChops.darker(r_ch, g_ch), b_ch)
    max_c = ImageChops.lighter(ImageChops.lighter(r_ch, g_ch), b_ch)
    chroma = ImageChops.subtract(max_c, min_c)
    cand = ImageChops.darker(
        min_c.point(_STUDIO_WHITE_MIN_LUT),
        chroma.point(_STUDIO_WHITE_CHROMA_LUT),
    )
    cand_b = cand.tobytes()

    # Verificar las 4 esquinas (bloques 3x3)
    white_corners = 0
    for cy0, cx0 in ((0, 0), (0, dw - 3), (dh - 3, 0), (dh - 3, dw - 3)):
        cnt_w = (
            (cand_b[cy0 * dw + cx0 : cy0 * dw + cx0 + 3].count(255))
            + (cand_b[(cy0 + 1) * dw + cx0 : (cy0 + 1) * dw + cx0 + 3].count(255))
            + (cand_b[(cy0 + 2) * dw + cx0 : (cy0 + 2) * dw + cx0 + 3].count(255))
        )
        if cnt_w >= 6:
            white_corners += 1
    if white_corners < 3:
        return None

    # Verificar cobertura del borde exterior (>= 65%)
    top_w = cand_b[:dw].count(255)
    bot_w = cand_b[(dh - 1) * dw : dh * dw].count(255)
    side_w = 0
    for yy in range(1, dh - 1):
        ro = yy * dw
        if cand_b[ro] == 255:
            side_w += 1
        if cand_b[ro + dw - 1] == 255:
            side_w += 1
    perim_len = 2 * dw + 2 * (dh - 2)
    if ((top_w + bot_w + side_w) / float(max(1, perim_len))) < 0.65:
        return None

    # Flood-fill exterior 4-conexo por segmentos usando memchr/memset en C (< 3 ms)
    fw2, fh2 = dw + 4, dh + 4
    framed = Image.new("L", (fw2, fh2), 0)
    white_ring = Image.new("L", (dw + 2, dh + 2), 255)
    white_ring.paste(cand, (1, 1))
    framed.paste(white_ring, (1, 1))

    buf = bytearray(framed.tobytes())
    fg_buf = bytearray(b"\xff" * (fw2 * fh2))
    zeros = b"\x00" * fw2

    r1_s = fw2 + 1
    r1_e = fw2 + dw + 3
    buf[r1_s:r1_e] = zeros[: dw + 2]
    fg_buf[r1_s:r1_e] = zeros[: dw + 2]
    stack = [(1, dw + 3, 1)]

    while stack:
        lx, rx, y = stack.pop()
        for ny in (y - 1, y + 1):
            if ny <= 0 or ny >= fh2 - 1:
                continue
            roff = ny * fw2
            s_pos = (buf.rfind(0, roff, roff + lx) + 1) if buf[roff + lx] == 255 else (roff + lx)
            r_lim = roff + rx
            pos = buf.find(255, s_pos, r_lim)
            while pos != -1:
                end = buf.find(0, pos)
                span = end - pos
                buf[pos:end] = zeros[:span]
                fg_buf[pos:end] = zeros[:span]
                stack.append((pos - roff, end - roff, ny))
                if end >= r_lim:
                    break
                pos = buf.find(255, end, r_lim)

    fg_small = Image.frombytes("L", (fw2, fh2), bytes(fg_buf)).crop((2, 2, 2 + dw, 2 + dh))
    tot_s = dw * dh
    bg_count = fg_small.histogram()[0]
    bg_ratio = bg_count / float(tot_s)
    if bg_ratio < 0.12 or bg_ratio > 0.94:
        return None

    fg_full = fg_small.resize((w, h), Image.Resampling.BILINEAR) if (dw, dh) != (w, h) else fg_small
    fg_full = fg_full.filter(ImageFilter.GaussianBlur(radius=0.8))
    return rgb.copy(), fg_full


def _dilate_mask_fast(mask_l: Image.Image, radius_px: int) -> Image.Image:
    """
    Dilata una máscara L por radius_px (12-18 px) en < 3 ms mediante filtro Gaussiano separable O(W*H)
    seguido de umbral suave con borde anti-aliasing de 1.5 px (disco euclidiano exacto sin esquinas cuadradas).
    """
    r_px = max(1, int(radius_px))
    sigma = max(1.0, float(r_px) * 0.56)
    blurred = mask_l.filter(ImageFilter.GaussianBlur(radius=sigma))
    # En el borde de un semiplano a distancia r_px con sigma = 0.56*r_px (z = 1.785), el valor Gaussiano es ~9.5/255
    lo, hi = 7.0, 16.0
    lut = []
    for v in range(256):
        if v <= lo:
            lut.append(0)
        elif v >= hi:
            lut.append(255)
        else:
            lut.append(int(round(255.0 * (v - lo) / (hi - lo))))
    return blurred.point(lut)


def build_v8_conditioning_canvas(
    furniture_bytes: bytes,
    fabric_bytes: bytes,
    sample_name: str = "",
    furniture_name: str = "",
    furniture_width_cm: Optional[float] = None,
    furniture_type: str = "",
    boost: float = 0.30,
    canvas_px: int = 1280,
    furn_scale: float = 0.58,
) -> V8ConditioningArtifacts:
    """
    Construye el Lienzo Maestro de Escala V8 (<mueble>_V8_LIENZO_ESCALA.png, 1280x1280 px):
      1) Extrae parche limpio con figuras (extract_clean_swatch_roi_v8) y calibra +30% (<=243).
      2) Sintetiza baldosa sin costuras (make_toroidal_seamless_tile_v8) escalada físicamente al
         ancho del mueble y tapiza el 100% del fondo con 81 a 289 repeticiones reducidas.
      3) Aleja el mueble al ~58% en el centro con halo blanco puro #FFFFFF (12-18 px si es corte
         blanco/RGBA) o marco separador #FFFFFF (10-14 px si tiene fondo de cuarto/taller).
      4) Cachea en LRU acotada por SHA-1 (< 12 MB RAM) para respuesta instantánea en UI.
    """
    global _CANVAS_CACHE_BYTES
    if not furniture_bytes:
        raise ValueError("furniture_bytes vacío en build_v8_conditioning_canvas.")
    if not fabric_bytes:
        raise ValueError("fabric_bytes vacío en build_v8_conditioning_canvas.")

    c_px = max(512, min(1600, int(canvas_px)))
    f_sc = max(0.40, min(0.75, float(furn_scale)))
    eff_w_cm = infer_furniture_width_cm_v8(furniture_width_cm=furniture_width_cm, furniture_type=furniture_type)

    canvas_fname = make_v8_canvas_filename(furniture_name)
    swatch_fname = make_v8_swatch_filename(sample_name)
    mosaic_fname = make_v8_mosaic_filename(sample_name)

    cache_key = _bytes_digest(
        furniture_bytes,
        fabric_bytes,
        f"{c_px}|{f_sc:.3f}|{eff_w_cm:.1f}|{boost:.3f}|{canvas_fname}|{swatch_fname}".encode("utf-8"),
    )
    with _CANVAS_CACHE_LOCK:
        hit = _CANVAS_CACHE.get(cache_key)
        if hit is not None:
            _CANVAS_CACHE.move_to_end(cache_key)
            return hit

    # 1. Extraer ROI limpio + calibrar +30% + analizar espectro multitono
    roi = extract_clean_swatch_roi_v8(fabric_bytes)
    cal_roi = calibrate_fabric_lightness_v8(roi.crop, boost=boost, max_rgb=243)
    mt_report = analyze_fabric_multitone_v8(cal_roi, raw_bytes=fabric_bytes, sample_name=sample_name)

    # 2. Calcular tamaño físico de baldosa y construir mosaico 1280x1280 (81..289 baldosas)
    tile_px, grid_n = compute_v8_tile_px(
        canvas_px=c_px,
        furniture_width_cm=eff_w_cm,
        furniture_type=furniture_type,
        motif_period_px=mt_report.motif_period_px,
        roi_px=min(cal_roi.size),
        furn_scale=f_sc,
    )
    total_tiles = grid_n * grid_n
    seamless_tile = make_toroidal_seamless_tile_v8(cal_roi, tile_px=tile_px, max_rgb=243)

    mosaic_img = Image.new("RGB", (c_px, c_px))
    for gy in range(grid_n):
        py = gy * tile_px
        if py >= c_px:
            break
        for gx in range(grid_n):
            px = gx * tile_px
            if px >= c_px:
                break
            mosaic_img.paste(seamless_tile, (px, py))

    # 3. Alejar mueble (~58% de canvas_px) y aislar con halo/marco blanco #FFFFFF
    with Image.open(io.BytesIO(furniture_bytes)) as f_raw:
        furn_oriented = ImageOps.exif_transpose(f_raw)
        max_furn_px = max(128, int(round(c_px * f_sc)))
        fw0, fh0 = furn_oriented.size
        scale_f = min(max_furn_px / float(max(1, fw0)), max_furn_px / float(max(1, fh0)))
        fw = max(32, int(round(fw0 * scale_f)))
        fh = max(32, int(round(fh0 * scale_f)))
        furn_scaled = furn_oriented.resize((fw, fh), Image.Resampling.LANCZOS)

    canvas_img = mosaic_img.copy()
    ox = (c_px - fw) // 2
    oy = (c_px - fh) // 2

    cutout = _extract_studio_cutout_mask(furn_scaled)
    if cutout is not None:
        furn_rgb, fg_mask = cutout
        halo_px = max(12, min(18, int(round(c_px * 0.012))))
        pad = halo_px * 2 + 4
        padded_mask = Image.new("L", (fw + 2 * pad, fh + 2 * pad), 0)
        padded_mask.paste(fg_mask, (pad, pad))
        halo_mask = _dilate_mask_fast(padded_mask, radius_px=halo_px)

        white_patch = Image.new("RGB", halo_mask.size, (255, 255, 255))
        hx = ox - pad
        hy = oy - pad
        cx0 = max(0, hx)
        cy0 = max(0, hy)
        cx1 = min(c_px, hx + halo_mask.size[0])
        cy1 = min(c_px, hy + halo_mask.size[1])
        if cx1 > cx0 and cy1 > cy0:
            sub_halo = halo_mask.crop((cx0 - hx, cy0 - hy, cx1 - hx, cy1 - hy))
            sub_white = white_patch.crop((0, 0, cx1 - cx0, cy1 - cy0))
            canvas_img.paste(sub_white, (cx0, cy0), mask=sub_halo)

        canvas_img.paste(furn_rgb, (ox, oy), mask=fg_mask)
        iso_mode = "alpha_halo"
        iso_px = halo_px
    else:
        furn_rgb = furn_scaled.convert("RGB") if furn_scaled.mode != "RGB" else furn_scaled
        frame_px = max(10, min(14, int(round(c_px * 0.0095))))
        fx0 = max(0, ox - frame_px)
        fy0 = max(0, oy - frame_px)
        fx1 = min(c_px, ox + fw + frame_px)
        fy1 = min(c_px, oy + fh + frame_px)
        white_box = Image.new("RGB", (fx1 - fx0, fy1 - fy0), (255, 255, 255))
        canvas_img.paste(white_box, (fx0, fy0))
        canvas_img.paste(furn_rgb, (ox, oy))
        iso_mode = "white_frame"
        iso_px = frame_px

    # 4. Codificar artefactos PNG sin pérdida con compress_level=1 (< 35 ms y < 1.2 MB);
    #    mosaic_only_png se codifica perezosamente (@property) solo en reintentos de borde.
    buf_canvas = io.BytesIO()
    canvas_img.save(buf_canvas, format="PNG", compress_level=1)
    canvas_png = buf_canvas.getvalue()
    if len(canvas_png) > 1_450_000:
        buf_canvas = io.BytesIO()
        canvas_img.save(buf_canvas, format="PNG", compress_level=4)
        canvas_png = buf_canvas.getvalue()

    swatch_out = cal_roi
    if min(swatch_out.size) < 256:
        swatch_out = swatch_out.resize((256, 256), Image.Resampling.LANCZOS)
        swatch_out = _apply_ratio_preserving_rgb_ceiling(swatch_out, max_rgb=243)
    buf_sw = io.BytesIO()
    swatch_out.save(buf_sw, format="PNG", compress_level=1)
    swatch_png = buf_sw.getvalue()

    artifacts = V8ConditioningArtifacts(
        canvas_png=canvas_png,
        calibrated_swatch_png=swatch_png,
        mosaic_only_png=None,
        canvas_size=canvas_img.size,
        tile_px=tile_px,
        grid_count=grid_n,
        total_tiles=total_tiles,
        furn_scale=f_sc,
        isolation_mode=iso_mode,
        halo_or_frame_px=iso_px,
        roi_bbox=roi.bbox,
        canvas_filename=canvas_fname,
        calibrated_swatch_filename=swatch_fname,
        mosaic_filename=mosaic_fname,
        multitone_report=mt_report,
        canvas_image=canvas_img,
        calibrated_swatch_image=swatch_out,
        seamless_tile_image=seamless_tile,
        _mosaic_source_image=mosaic_img,
    )

    entry_sz = artifacts.approx_bytes()
    if entry_sz <= _CANVAS_CACHE_MAX_BYTES:
        with _CANVAS_CACHE_LOCK:
            _CANVAS_CACHE.pop(cache_key, None)
            _CANVAS_CACHE_BYTES = sum(v.approx_bytes() for v in _CANVAS_CACHE.values())
            while _CANVAS_CACHE and (
                len(_CANVAS_CACHE) >= _CANVAS_CACHE_MAX_ENTRIES
                or (_CANVAS_CACHE_BYTES + entry_sz) > _CANVAS_CACHE_MAX_BYTES
            ):
                _CANVAS_CACHE.popitem(last=False)
                _CANVAS_CACHE_BYTES = sum(v.approx_bytes() for v in _CANVAS_CACHE.values())
            _CANVAS_CACHE[cache_key] = artifacts
            _CANVAS_CACHE_BYTES = sum(v.approx_bytes() for v in _CANVAS_CACHE.values())

    return artifacts


def compose_view_with_precomputed_tile_v8(
    view_bytes: bytes,
    seamless_tile: Image.Image,
    tile_px: int,
    grid_n: int,
    view_name: str = "",
    canvas_px: int = 1280,
    furn_scale: float = 0.58,
) -> Tuple[str, bytes, Image.Image]:
    """
    Construye rápidamente (< 35 ms) un lienzo V8 por vista para lotes (vistas_tela),
    reutilizando la baldosa continua ya pre-calibrada +30%.
    """
    c_px = max(512, min(1600, int(canvas_px)))
    f_sc = max(0.40, min(0.75, float(furn_scale)))
    mosaic_img = Image.new("RGB", (c_px, c_px))
    for gy in range(grid_n):
        py = gy * tile_px
        if py >= c_px:
            break
        for gx in range(grid_n):
            px = gx * tile_px
            if px >= c_px:
                break
            mosaic_img.paste(seamless_tile, (px, py))

    with Image.open(io.BytesIO(view_bytes)) as v_raw:
        v_oriented = ImageOps.exif_transpose(v_raw)
        max_furn_px = max(128, int(round(c_px * f_sc)))
        fw0, fh0 = v_oriented.size
        scale_f = min(max_furn_px / float(max(1, fw0)), max_furn_px / float(max(1, fh0)))
        fw = max(32, int(round(fw0 * scale_f)))
        fh = max(32, int(round(fh0 * scale_f)))
        furn_scaled = v_oriented.resize((fw, fh), Image.Resampling.LANCZOS)

    ox = (c_px - fw) // 2
    oy = (c_px - fh) // 2
    cutout = _extract_studio_cutout_mask(furn_scaled)
    if cutout is not None:
        furn_rgb, fg_mask = cutout
        halo_px = max(12, min(18, int(round(c_px * 0.012))))
        pad = halo_px * 2 + 4
        padded_mask = Image.new("L", (fw + 2 * pad, fh + 2 * pad), 0)
        padded_mask.paste(fg_mask, (pad, pad))
        halo_mask = _dilate_mask_fast(padded_mask, radius_px=halo_px)
        white_patch = Image.new("RGB", halo_mask.size, (255, 255, 255))
        hx, hy = ox - pad, oy - pad
        cx0, cy0 = max(0, hx), max(0, hy)
        cx1, cy1 = min(c_px, hx + halo_mask.size[0]), min(c_px, hy + halo_mask.size[1])
        if cx1 > cx0 and cy1 > cy0:
            sub_halo = halo_mask.crop((cx0 - hx, cy0 - hy, cx1 - hx, cy1 - hy))
            sub_white = white_patch.crop((0, 0, cx1 - cx0, cy1 - cy0))
            mosaic_img.paste(sub_white, (cx0, cy0), mask=sub_halo)
        mosaic_img.paste(furn_rgb, (ox, oy), mask=fg_mask)
    else:
        furn_rgb = furn_scaled.convert("RGB") if furn_scaled.mode != "RGB" else furn_scaled
        frame_px = max(10, min(14, int(round(c_px * 0.0095))))
        fx0, fy0 = max(0, ox - frame_px), max(0, oy - frame_px)
        fx1, fy1 = min(c_px, ox + fw + frame_px), min(c_px, oy + fh + frame_px)
        mosaic_img.paste(Image.new("RGB", (fx1 - fx0, fy1 - fy0), (255, 255, 255)), (fx0, fy0))
        mosaic_img.paste(furn_rgb, (ox, oy))

    out_buf = io.BytesIO()
    mosaic_img.save(out_buf, format="PNG", compress_level=1)
    canvas_png = out_buf.getvalue()
    if len(canvas_png) > 1_450_000:
        out_buf = io.BytesIO()
        mosaic_img.save(out_buf, format="PNG", compress_level=4)
        canvas_png = out_buf.getvalue()
    return make_v8_canvas_filename(view_name), canvas_png, mosaic_img


def clear_v8_composer_cache() -> None:
    """Limpia el caché LRU de artefactos V8."""
    global _CANVAS_CACHE_BYTES
    with _CANVAS_CACHE_LOCK:
        _CANVAS_CACHE.clear()
        _CANVAS_CACHE_BYTES = 0
