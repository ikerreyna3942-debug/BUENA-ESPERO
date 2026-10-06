import sys
import os
sys.path.insert(0, os.path.abspath("."))
from io import BytesIO
import services.ai_prompt_service_v4 as s4

service = s4.ai_prompt_service_v4
service.get_api_key = lambda custom=None: ""  # Fast offline fallback

modes = [
    "Solo mueble",
    "Solo Tela",
    "Solo Madera",
    "Tela + Madera",
    "Vistas",
    "Vistas + Tela",
    "Vistas + Tela y Madera",
    "Entorno"
]

print("=== SIMULATION OF PROMPT GENERATION PIPELINE ACROSS MODES IN V4 ===")

for mode in modes:
    print(f"\n--- Testing Mode: '{mode}' ---")
    try:
        # Mock inputs
        m_bytes = [b"dummy_furniture_bytes"]
        m_name = "sofa_test.jpg"
        num_imgs = 1
        tela_bytes = b"dummy_tela_bytes" if "Tela" in mode else None
        madera_bytes = b"dummy_madera_bytes" if "Madera" in mode else None
        fondo_blanco = True
        hd_toggle = False
        
        # Emulate logic from prompt_studio_v4.py lines 240-387
        f_ana = None
        w_ana = None
        m_ana = None
        prompts = {}
        vistas_data = []

        if tela_bytes:
            f_ana = service.analyze_material(tela_bytes, material_type="fabric", api_key="")
        if madera_bytes:
            w_ana = service.analyze_material(madera_bytes, material_type="wood", api_key="")
        elif mode == "Solo mueble":
            m_ana = service.analyze_furniture_for_enhancement(m_bytes, api_key="")
            prompts = service.generate_extraction_prompt(m_name, m_ana)

        if mode in ["Solo Tela", "Solo Madera", "Tela + Madera"]:
            m_ana = service.analyze_furniture_for_enhancement(m_bytes, api_key="")
            mode_map = {"Solo Tela": "fabric_only", "Solo Madera": "wood_only", "Tela + Madera": "dual"}
            prompts = service.generate_material_swap_prompt_v4(
                mode=mode_map[mode],
                furniture_name=m_name,
                fabric_analysis=f_ana,
                wood_analysis=w_ana,
                furniture_analysis=m_ana,
                num_furniture_images=num_imgs,
                fondo_blanco=fondo_blanco,
                hd=hd_toggle
            )
        elif mode == "Vistas":
            m_ana = service.analyze_furniture_for_enhancement(m_bytes, api_key="")
            # Here prompt_studio_v4 line 270 evaluates notas_vistas_usuario which is unbound
            # Let's check if the variable exists:
            try:
                # in prompt_studio_v4, notas_vistas_usuario is evaluated here
                eval("notas_vistas_usuario")
            except NameError as ne:
                raise NameError("In prompt_studio_v4.py line 270: " + str(ne))
        elif mode == "Vistas + Tela":
            # prompt_studio_v4 line 307
            # In prompt_studio_v4, m_ana is never computed (remains None)
            pass
        elif mode == "Vistas + Tela y Madera":
            # prompt_studio_v4 line 343:
            # calls generate_dynamic_gemini_clone_prompt
            res = service.generate_dynamic_gemini_clone_prompt(
                ref_bytes=m_bytes[0],
                view_bytes=b"dummy_view",
                fondo_blanco=fondo_blanco,
                hd=hd_toggle
            )
        elif mode == "Entorno":
            # prompt_studio_v4 line 375 evaluates medidas_usuario and lugar_casa_usuario
            try:
                eval("medidas_usuario")
            except NameError as ne:
                raise NameError("In prompt_studio_v4.py line 375: " + str(ne))

        print(f"Result: SUCCESS")
    except Exception as e:
        print(f"Result: CRASH ({type(e).__name__}: {e})")
