# Reglas del Proyecto: Estudio IA de Fotografía y Catálogo de Muebles

1. **Interfaz en Encabezado Superior y Adaptable (Cero Menús Verticales Largos):**
   - Mantener `initial_sidebar_state="collapsed"` y la navegación en barra superior horizontal compacta.
   - Usar etiquetas muy cortas (1 a 3 palabras máximo) en menús, modos y botones.
   - Garantizar adaptación responsiva (`max-width: 100%`, `clamp()`, `@media`) para monitor completo, laptop y media pantalla dividida.

2. **Comportamiento del Botón Borrar / Limpiar:**
   - Al limpiar el formulario, borrar únicamente fotos cargadas, SKU, medidas, notas y resultados generados.
   - **NUNCA reiniciar ni cambiar** el modo/opción ni las sub-opciones que el usuario tenga seleccionadas actualmente.

3. **Estándar Técnico de Fotografía Comercial y Tapicería:**
   - **Aplicación de Tela en el Casco:** Siempre que se seleccione muestra de tela, exigir cobertura 100% uniforme tanto en **todo el casco tapizado** (respaldo exterior/interior, descansabrazos, faldón/base, laterales) como en los cojines, con calibración de micro-escala (~97% de reducción de macro a distancia real) y 0% cambio de tono, protegiendo patas/bases de madera o metal.
   - **Toma Maestra 3/4 Derecha:** Posición 3/4 mirando hacia la derecha, fondo blanco puro `#FFFFFF` (`RGB 255,255,255`), **0% sombras** (sin sombra de piso, contacto ni reflejo) y salida exacta de **`2054 × 2054 px`**.

4. **Modelos Gemini API y Seguridad de Credenciales:**
   - Usar los modelos vigentes de imagen y visión multimodal verificados en la cuenta activa (nunca modelos retirados).
   - Nunca guardar API keys ni credenciales OAuth/Service Account en código fuente versionado; usar variables de entorno o `.env` / `.streamlit/secrets.toml` ignorados en `.gitignore`.
