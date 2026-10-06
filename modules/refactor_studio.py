import os

file_path = r'I:\Mi unidad\PROYECTOS FINALES\APP PORMPT MEJORADO\PROMPRT 2.1\APP-FINAL\modules\prompt_studio_v3.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Change radio button options globally
content = content.replace('"Extraer Mueble (Fondo Blanco)"', '"Solo mueble"')
content = content.replace('"Vistas Ortogonales (360)"', '"Vistas"')
content = content.replace('"Aplicar Tela a Vistas (1x1)"', '"Vistas + Tela"')
content = content.replace('"Clonar Vistas (Color y Tela)"', '"Vistas + Tela y Madera"')
content = content.replace('"Entorno Minimalista"', '"Entorno"')

# Text removals
content = content.replace('"Sube foto(s) del mueble"', '""')
content = content.replace('"Fuente:"', '""')
content = content.replace('"Configura y genera para ver los avisos optimizados."', '""')
content = content.replace(' <span class="studio-badge">Micro-Escala -95%</span>', '')

# Remove HD and tabs
if 'hd_toggle' not in content:
    content = content.replace('fondo_blanco = st.toggle("⬜ Solo mueble", value=True, help="Le ordena a la IA extraer el mueble, preservando color, textura y geometría, colocándolo sobre blanco puro sin sombras ni reflejos.")', 
    '''fondo_blanco = st.toggle("⬜ Solo mueble", value=True, help="Le ordena a la IA extraer el mueble, preservando color, textura y geometría, colocándolo sobre blanco puro sin sombras ni reflejos.")
        hd_toggle = st.toggle("HD", value=False)''')

content = content.replace('p_tabs = st.tabs(["🌟 Google AI Studio", "🤖 DALL-E 3", "⚡ Flux / Midjourney", "🎨 Render Gratis (FLUX.1)", "🕵️ Inspector de Calidad (Quality Gate)"])',
'p_tabs = st.tabs(["🌟 Google AI Studio", "🤖 DALL-E 3", "⚡ Flux / Midjourney"])')

# Find indices and cut
start_idx = content.find('            with p_tabs[3]:')
if start_idx != -1:
    end_idx = content.find('        else:', start_idx)
    if end_idx != -1:
        content = content[:start_idx] + content[end_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
