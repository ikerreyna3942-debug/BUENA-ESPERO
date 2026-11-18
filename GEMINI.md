# Reglas del Proyecto: Estudio IA de Fotografía y Catálogo de Muebles

1. **Interfaz Ultra Limpia, Pequeña y de 1 Sola Línea en Encabezado:**
   - Mantener `initial_sidebar_state="collapsed"`, navegación y controles superiores en **una sola línea horizontal pequeña** con selectores desplegables (`selectbox`), sin listas de radios grandes ni cajas duplicadas de medidas.
   - **Cero texto extra y 3 botones con sentido claro:** mantener únicamente los 3 botones directos (`🚀 <Modo elegido>`, `↘️ 3/4 Derecha`, `🗑️ Borrar`) sin botones de generación sintética de fotos cuando no sea Nano Banana real, y miniaturas de vista previa muy pequeñas (`38×38 px`).
   - **Credenciales siempre integradas:** nunca mostrar campos ni menús de credenciales en la interfaz al usuario.

2. **Comportamiento del Botón Borrar / Limpiar:**
   - Al limpiar el formulario, borrar únicamente fotos cargadas, SKU, medidas, notas y resultados generados.
   - **NUNCA reiniciar ni cambiar** el modo/opción ni las sub-opciones que el usuario tenga seleccionadas actualmente.

3. **Estándar Técnico de Fotografía Comercial y Tapicería:**
   - **Aplicación de Tela en el Casco:** Siempre que se seleccione muestra de tela, exigir cobertura 100% uniforme tanto en **todo el casco tapizado** (respaldo exterior/interior, descansabrazos, faldón/base, laterales) como en los cojines, con calibración de micro-escala (~97% de reducción de macro a distancia real) y 0% cambio de tono, protegiendo patas/bases de madera o metal.
   - **Toma Maestra 3/4 Derecha:** Posición 3/4 mirando hacia la derecha, fondo blanco puro `#FFFFFF` (`RGB 255,255,255`), **0% sombras** (sin sombra de piso, contacto ni reflejo) y salida exacta de **`2054 × 2054 px`**.

4. **Carpeta Única de Muebles (`RENDER`) y Modelos Gemini API:**
   - **Única carpeta de muebles:** usar exclusivamente `I:\Mi unidad\DOC ANIPA\Fotos general\Informacion mia\RENDER` (Google Drive ID `1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX`) para jalar fotos de muebles en V7 (sin menús de carpetas extra).
   - Usar los modelos vigentes de imagen y visión multimodal verificados en la cuenta activa con ejecución en paralelo (`ThreadPoolExecutor`) y caché BFS por lotes en Drive para máxima velocidad, además de diseño micro-compacto adaptable a escritorio y celular (`<= 640px`).
   - Nunca guardar API keys ni credenciales OAuth/Service Account en código fuente versionado; usar variables de entorno o `.env` / `.streamlit/secrets.toml` ignorados en `.gitignore`.
