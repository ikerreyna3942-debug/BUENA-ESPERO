import urllib.parse
import requests
import random
import io
import re
from typing import Optional
from PIL import Image

class FreeImageService:
    """
    Servicio integral para generar renders visuales de muebles e interiores.
    Soporta generación gratuita abierta (FLUX / Diffusion) y fallback inteligente.
    """

    @staticmethod
    def clean_prompt_for_diffusion(prompt: str) -> str:
        """
        Limpia, extrae y sintetiza las palabras clave visuales esenciales para motores de difusión (FLUX / SDXL).
        Elimina metadatos, delimitadores de sistema y encabezados extensos.
        """
        if not prompt:
            return "modern luxury furniture piece, isolated on pure white background, 8k product photography"

        # Eliminar bloques de sistema y markdown
        text = re.sub(r'===.*?===', ' ', prompt)
        text = re.sub(r'\[.*?\]', ' ', text)
        text = re.sub(r'SYSTEM:.*?\n', ' ', text)
        text = re.sub(r'TASK:.*?\n', ' ', text)
        text = re.sub(r'Negative Prompt:.*', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'--[a-z0-9]+\s+[^\s]+', ' ', text) # eliminar flags como --ar 1:1 --v 6.1

        lines = text.split("\n")
        cleaned_phrases = []
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("#") or line_str.startswith("```"):
                continue
            cleaned_phrases.append(line_str)

        full_clean = " ".join(cleaned_phrases)
        full_clean = re.sub(r'\s+', ' ', full_clean).strip()

        # Limitar longitud para evitar URLs excesivas
        if len(full_clean) > 350:
            full_clean = full_clean[:350]

        # Garantizar palabras clave de calidad comercial y fondo blanco
        if "white background" not in full_clean.lower():
            full_clean += ", isolated on solid pure white background #FFFFFF"
        if "photography" not in full_clean.lower() and "render" not in full_clean.lower():
            full_clean += ", 8k hyper-realistic commercial studio photography"

        return full_clean

    @classmethod
    def generate_flux_image(
        cls, 
        prompt: str, 
        width: int = 768, 
        height: int = 768, 
        seed: Optional[int] = None,
        custom_key: Optional[str] = None
    ) -> bytes:
        """
        Genera una imagen a partir de un prompt con reintentos y múltiples proveedores de respaldo.
        """
        if seed is None:
            seed = random.randint(1000, 999999)

        prompt_opt = cls.clean_prompt_for_diffusion(prompt)
        prompt_encoded = urllib.parse.quote(prompt_opt)

        endpoints = [
            f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={width}&height={height}&seed={seed}&nologo=true&nofeed=true",
            f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={width}&height={height}&seed={seed}&nologo=true",
            f"https://image.pollinations.ai/prompt/{prompt_encoded}?model=flux&width={width}&height={height}&seed={seed}&nologo=true",
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }

        last_error = ""

        for url in endpoints:
            try:
                response = requests.get(url, headers=headers, timeout=45)
                if response.status_code == 200 and len(response.content) > 2000:
                    img = Image.open(io.BytesIO(response.content))
                    img.verify()
                    return response.content
                elif response.status_code != 200:
                    last_error = f"HTTP {response.status_code}"
            except Exception as e:
                last_error = str(e)
                continue

        raise RuntimeError(
            f"Los servidores comunitarios de FLUX están experimentando alta congestión en este momento ({last_error}). "
            f"Puedes reintentar en unos segundos o abrir directamente el prompt en Google AI Studio o ChatGPT con los botones de abajo."
        )

free_image_service = FreeImageService()
