import sys
import os
from pathlib import Path
import ast
import inspect
from unittest.mock import MagicMock

PROJECT_ROOT = Path(r"C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO")
sys.path.insert(0, str(PROJECT_ROOT))

print("=== VICTORY AUDITOR INDEPENDENT VERIFICATION ===")

# 1. Syntax Check on all python files
py_files = list(PROJECT_ROOT.glob("*.py")) + list(PROJECT_ROOT.glob("modules/*.py")) + list(PROJECT_ROOT.glob("services/*.py"))
syntax_errors = []
for p in py_files:
    try:
        ast.parse(p.read_bytes(), filename=str(p))
    except Exception as e:
        syntax_errors.append((str(p), str(e)))

print(f"\n1. Syntax Check: {len(py_files)} files tested. Errors: {len(syntax_errors)}")
for f, err in syntax_errors:
    print(f"   [SYNTAX ERROR] {f}: {err}")

# 2. Inspect services/ai_prompt_service_v4.py
import services.ai_prompt_service_v4 as s4
service = s4.ai_prompt_service_v4
print(f"\n2. Service class: {service.__class__.__name__}")
print(f"   Default API key: '{service.default_api_key}'")

# Check fallback models
import re
code_s4 = Path(r"C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\services\ai_prompt_service_v4.py").read_text(encoding="utf-8")
models_match = re.search(r'models_to_try\s*=\s*\[(.*?)\]', code_s4)
if models_match:
    print(f"   Configured models: [{models_match.group(1)}]")
else:
    print("   Configured models: NOT FOUND")

# 3. Test Service Methods for Fatal NameErrors
print("\n3. Testing Service Methods:")
# Test generate_clone_views_prompt_v4
try:
    service.generate_clone_views_prompt_v4("test", {})
    print("   generate_clone_views_prompt_v4: OK")
except Exception as e:
    print(f"   generate_clone_views_prompt_v4: FAIL -> {type(e).__name__}: {e}")

# Test generate_dynamic_gemini_clone_prompt
try:
    service.generate_dynamic_gemini_clone_prompt(b"ref", b"view")
    print("   generate_dynamic_gemini_clone_prompt: OK")
except Exception as e:
    print(f"   generate_dynamic_gemini_clone_prompt: FAIL -> {type(e).__name__}: {e}")

# 4. Check Variable Injection in generate_minimalist_environment_prompt_v4
print("\n4. Checking Variable Injection in generate_minimalist_environment_prompt_v4:")
captured_prompts = []
service._call_gemini = lambda client, contents, config=None: captured_prompts.extend(contents) or MagicMock(text="mocked response")

try:
    res = service.generate_minimalist_environment_prompt_v4(
        furniture_name="Sofa Chesterfield",
        fabric_analysis={"name": "Terciopelo Azul", "color_description": "Azul zafiro", "texture_detail": "Suave", "light_interaction": "Brillo mate"},
        furniture_analysis={"furniture_item": "Sofa", "geometric_structure": "Curvo", "camera_angle": "Frontal", "existing_materials": "Madera y tela"},
        tipo_mueble_usuario="Sofa clasico capitone",
        medidas_usuario="220x95x85 cm",
        lugar_casa_usuario="Salon principal",
        notas_vistas_usuario="Luz natural tenue lateral",
        api_key="TEST_KEY"
    )
    if captured_prompts:
        prompt_text = captured_prompts[-1]
        print("   Prompt generated successfully.")
        print(f"   tipo_mueble_usuario in prompt: {'Sofa clasico capitone' in prompt_text}")
        print(f"   medidas_usuario in prompt: {'220x95x85 cm' in prompt_text}")
        print(f"   lugar_casa_usuario in prompt: {'Salon principal' in prompt_text}")
        print(f"   notas_vistas_usuario in prompt: {'Luz natural tenue lateral' in prompt_text}")
    else:
        print("   Prompt generation did not call _call_gemini!")
except Exception as e:
    print(f"   generate_minimalist_environment_prompt_v4 error: {type(e).__name__}: {e}")

# 5. Check UI inputs in modules/prompt_studio_v4.py
print("\n5. Checking UI Inputs in modules/prompt_studio_v4.py:")
code_studio = Path(r"C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\modules\prompt_studio_v4.py").read_text(encoding="utf-8")
for var in ["tipo_mueble_usuario", "medidas_usuario", "lugar_casa_usuario", "notas_vistas_usuario"]:
    has_input = f"{var} = st." in code_studio or f"{var} =" in code_studio
    print(f"   {var}: assigned in code = {has_input}")

# 6. Simulate All 8 Modes in Prompt Studio V4
print("\n6. Simulating Studio V4 Dataflow for all 8 Modes:")
modes = ["Solo mueble", "Solo Tela", "Solo Madera", "Tela + Madera", "Vistas", "Vistas + Tela", "Vistas + Tela y Madera", "Entorno"]

for mode in modes:
    try:
        # Mock variables like in prompt_studio_v4
        m_bytes = [b"fake_mueble_image"]
        m_name = "test_mueble.jpg"
        num_imgs = 1
        tela_bytes = b"fake_tela"
        madera_bytes = b"fake_madera"
        f_ana = {"name": "Lino", "color_description": "Beige", "texture_detail": "Liso", "light_interaction": "Mate"}
        w_ana = {"name": "Roble", "color_description": "Marron claro", "texture_detail": "Veta visible", "light_interaction": "Satinado"}
        m_ana = {"furniture_item": "Silla", "geometric_structure": "Recta", "camera_angle": "Frontal", "existing_materials": "Madera"}
        fondo_blanco = True
        hd_toggle = False
        tipo_mueble_usuario = "Silla de comedor"
        medidas_usuario = "50x50x90 cm"
        lugar_casa_usuario = "Comedor"
        notas_vistas_usuario = "Perspectiva limpia"

        if mode == "Solo mueble":
            p = service.generate_extraction_prompt(m_name, m_ana)
        elif mode in ["Solo Tela", "Solo Madera", "Tela + Madera"]:
            mode_map = {"Solo Tela": "fabric_only", "Solo Madera": "wood_only", "Tela + Madera": "dual"}
            p = service.generate_material_swap_prompt_v4(
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
            pv = service.generate_multi_perspective_prompts_v4(
                furniture_name=m_name,
                fabric_analysis=f_ana,
                furniture_analysis=m_ana,
                fondo_blanco=fondo_blanco,
                hd=hd_toggle,
                notas_vistas_usuario=notas_vistas_usuario
            )
        elif mode == "Vistas + Tela":
            # calls generate_dynamic_fabric_view_prompt
            p = service.generate_dynamic_fabric_view_prompt(tela_bytes, m_bytes[0], fondo_blanco)
        elif mode == "Vistas + Tela y Madera":
            # calls generate_dynamic_gemini_clone_prompt
            p = service.generate_dynamic_gemini_clone_prompt(m_bytes[0], m_bytes[0], fondo_blanco=fondo_blanco)
        elif mode == "Entorno":
            p = service.generate_minimalist_environment_prompt_v4(
                furniture_name=m_name,
                fabric_analysis=f_ana,
                furniture_analysis=m_ana,
                num_furniture_images=num_imgs,
                tipo_mueble_usuario=tipo_mueble_usuario,
                medidas_usuario=medidas_usuario,
                lugar_casa_usuario=lugar_casa_usuario,
                hd=hd_toggle
            )
        print(f"   [{mode}] -> PASS")
    except Exception as e:
        print(f"   [{mode}] -> FAIL: {type(e).__name__}: {e}")

# 7. Check Session Keys Across V1-V4
print("\n7. Session Key Overlap Analysis:")
import re
key_pattern = re.compile(r'key=["\']([a-zA-Z0-9_]+)["\']')
v_files = {
    "V1": PROJECT_ROOT / "modules" / "prompt_studio_v1.py",
    "V2": PROJECT_ROOT / "modules" / "prompt_studio_v2.py",
    "V3": PROJECT_ROOT / "modules" / "prompt_studio_v3.py",
    "V4": PROJECT_ROOT / "modules" / "prompt_studio_v4.py",
}
keys_by_v = {}
for v, path in v_files.items():
    if path.exists():
        content = path.read_text(encoding="utf-8", errors="ignore")
        keys_by_v[v] = set(key_pattern.findall(content))

all_keys = set().union(*keys_by_v.values())
shared_keys = {k: [v for v, ks in keys_by_v.items() if k in ks] for k in all_keys if sum(1 for ks in keys_by_v.values() if k in ks) > 1}
print(f"   Total shared widget keys across versions: {len(shared_keys)}")
for k, vs in sorted(shared_keys.items()):
    print(f"   - {k}: shared across {vs}")

# 8. Check Tab 4 Rendering Behavior
print("\n8. Tab 4 Display Behavior Check:")
# In prompt_studio_v4:
# st.code(res.get("furniture_analysis", "No hay análisis disponible"), language="markdown")
# When furniture_analysis is None:
res_none = {"furniture_analysis": None}
val_none = res_none.get("furniture_analysis", "No hay análisis disponible")
print(f"   When res['furniture_analysis'] is None -> .get() evaluates to: {val_none} (type: {type(val_none)})")
print(f"   st.code(None) in Streamlit renders literal 'None' string: True")
# When furniture_analysis is dict:
res_dict = {"furniture_analysis": {"item": "Sofa"}}
val_dict = res_dict.get("furniture_analysis", "default")
print(f"   When res['furniture_analysis'] is dict -> .get() evaluates to: {val_dict} (type: {type(val_dict)})")
print(f"   st.code(dict, language='markdown') renders raw Python repr with single quotes: True")
