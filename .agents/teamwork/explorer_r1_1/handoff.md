# Handoff Report - Explorer R1: UI and Routing Specialist

## 1. Observation

### Obs 1.1: Routing Architecture and Session State Management in `main.py`
- **File**: `C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\main.py`
- **Lines 30–33**:
  ```python
  version = st.sidebar.radio(
      "📌 Versión del Estudio:",
      ["V4 Ultimate (Nuevas Casillas)", "V3 Nivel Dios (Recomendado)", "V2 Optimizado", "V1 Clasica Original"]
  )
  ```
- **Lines 44–51**:
  ```python
  if version == "V4 Ultimate (Nuevas Casillas)":
      render_v4()
  elif version == "V3 Nivel Dios (Recomendado)":
      render_v3()
  elif version == "V2 Optimizado":
      render_v2()
  else:
      render_v1()
  ```
- **Direct observation**: `main.py` performs conditional module rendering based on `st.sidebar.radio`. However, there is zero initialization, isolation, namespacing, or reset logic in `main.py` when transitioning between versions. `st.session_state` is preserved verbatim across version switches.

### Obs 1.2: Session State Key Collisions Across V1, V2, V3, and V4
- **Shared Action Keys**:
  - `btn_clear_studio`: Used in V1 (`modules/prompt_studio_v1.py:155`), V2 (`modules/prompt_studio_v2.py:166`), V3 (`modules/prompt_studio_v3.py:116`), and V4 (`modules/prompt_studio_v4.py:116`).
  - In V1, V3, and V4, clicking this button triggers `st.session_state.clear()`, wiping the entire global session state across all versions.
- **Shared Output Text Area Keys**:
  - `txt_res_g` and `txt_res_d`: Used identically in V1 (`modules/prompt_studio_v1.py:876, 880`), V3 (`modules/prompt_studio_v3.py:481, 499`), and V4 (`modules/prompt_studio_v4.py:481, 499`).
  - `txt_res_m`: Used identically in V3 (`modules/prompt_studio_v3.py:517`) and V4 (`modules/prompt_studio_v4.py:517`).
  - `cp_comp`: Copy button key shared between V3 (`modules/prompt_studio_v3.py:111`) and V4 (`modules/prompt_studio_v4.py:111`).
- **Direct observation**: Streamlit gives precedence to existing values in `st.session_state[key]` over the `value=...` argument of `st.text_area`. If a user generates prompts in V3 and then switches to V4, the text areas in V4 retain or conflict with V3's generated output unless manually wiped. In contrast, V2 namespaced all its keys (`txt_res_g_v2`, `txt_res_d_v2`, `txt_res_f_v2`).
- **Isolated Result Storage**: The primary result dictionary keys are namespaced:
  - V1: `last_studio_result`
  - V2: `last_studio_result_v2`
  - V3: `last_studio_result_v3`
  - V4: `last_studio_result_v4`

### Obs 1.3: Missing User Input Widgets in `modules/prompt_studio_v4.py`
- **File**: `C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\modules\prompt_studio_v4.py`
- **Inspection of target inputs specified in R1**:
  1. `tipo_mueble_usuario`:
     - Initialized at line 161: `tipo_mueble_usuario = ""`
     - Widget created at lines 162–167:
       ```python
       if modo_sel == "Entorno":
           st.markdown("##### 🏷️ Ubicación / Tipo de Mueble (Opcional)")
           tipo_mueble_usuario = st.text_input(
               "Ayuda a la IA especificando el mueble (ej. Silla de comedor, Sofá, Cama) para que lo ubique en su espacio real:", 
               key="txt_tipo_mueble_v4"
           )
       ```
  2. `medidas_usuario`:
     - **Widget**: ZERO occurrences. No widget (`st.text_input` or other) exists in `prompt_studio_v4.py`.
     - **Initialization**: ZERO occurrences. Not defined anywhere before use.
     - **Execution line 375**:
       ```python
       prompts_min = ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(furniture_name=m_name, fabric_analysis=f_ana, furniture_analysis=m_ana, num_furniture_images=num_imgs, tipo_mueble_usuario=tipo_mueble_usuario, medidas_usuario=medidas_usuario, lugar_casa_usuario=lugar_casa_usuario, hd=hd_toggle)
       ```
     - **Runtime Error**: When `modo_sel == "Entorno"`, clicking "⚡ GENERAR PROMPTS" throws:
       `NameError: name 'medidas_usuario' is not defined`
  3. `lugar_casa_usuario`:
     - **Widget**: ZERO occurrences. No widget exists in `prompt_studio_v4.py`.
     - **Initialization**: ZERO occurrences. Not defined anywhere before use.
     - **Execution line 375**: Passed to `generate_minimalist_environment_prompt_v4`.
     - **Runtime Error**: If `medidas_usuario` were resolved, `lugar_casa_usuario` throws:
       `NameError: name 'lugar_casa_usuario' is not defined`
  4. `notas_vistas_usuario`:
     - **Widget**: ZERO occurrences. No widget exists in `prompt_studio_v4.py`.
     - **Initialization**: ZERO occurrences. Not defined anywhere before use.
     - **Execution line 270**:
       ```python
       elif modo_sel == "Vistas":
           progress_holder.info("🛋️ Calculando perspectivas ortogonales 360°...")
           m_ana = ai_prompt_service_v4.analyze_furniture_for_enhancement(m_bytes)
           prompts_vistas = ai_prompt_service_v4.generate_multi_perspective_prompts_v4(furniture_name=m_name, fabric_analysis=f_ana, furniture_analysis=m_ana, fondo_blanco=fondo_blanco, hd=hd_toggle, notas_vistas_usuario=notas_vistas_usuario)
       ```
     - **Runtime Error**: When `modo_sel == "Vistas"`, clicking "⚡ GENERAR PROMPTS" throws:
       `NameError: name 'notas_vistas_usuario' is not defined`
     - **Omission in material swap**: In lines 256–265, `notas_vistas_usuario` is NOT passed to `generate_material_swap_prompt_v4`, despite the underlying method supporting user notes.

### Obs 1.4: Service Layer Method Name Mismatch (Contract Breakdown)
- **File**: `modules/prompt_studio_v4.py` calls:
  - Line 256: `ai_prompt_service_v4.generate_material_swap_prompt_v4(...)`
  - Line 270: `ai_prompt_service_v4.generate_multi_perspective_prompts_v4(...)`
  - Line 375: `ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(...)`
- **File**: `services/ai_prompt_service_v4.py` defines:
  - Line 176: `def generate_material_swap_prompt_v3(self, ...)`
  - Line 299: `def generate_multi_perspective_prompts_v3(self, ...)`
  - Line 543: `def generate_minimalist_environment_prompt_v3(self, ...)`
  - Line 660: `ai_prompt_service_v4 = AIPromptServiceV3()`
- **Command output**:
  ```bash
  python -c "import services.ai_prompt_service_v4 as s; getattr(s.ai_prompt_service_v4, 'generate_material_swap_prompt_v4')"
  # AttributeError: 'AIPromptServiceV3' object has no attribute 'generate_material_swap_prompt_v4'. Did you mean: 'generate_material_swap_prompt_v3'?
  ```
- **Direct observation**: `services/ai_prompt_service_v4.py` is an exact clone of `services/ai_prompt_service_v3.py` where only the bottom instance variable was renamed to `ai_prompt_service_v4 = AIPromptServiceV3()`. The method names were never renamed or aliased to `*_v4`, causing instant `AttributeError` exceptions whenever generation is executed.

### Obs 1.5: UI Display Bug with Uploaded Views (`st_vistas_v4`)
- **File**: `modules/prompt_studio_v4.py`
- **Line 171**:
  ```python
  vistas_up = st.file_uploader(
      "Sube las fotos de las vistas que quieres estandarizar",
      type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
      key=f"st_vistas_v4_{st.session_state.clear_key_v4}",
      accept_multiple_files=True
  )
  ```
- **Lines 412–413**:
  ```python
  if "st_vistas_v4" in st.session_state and st.session_state["st_vistas_v4"]:
      for f in st.session_state["st_vistas_v4"]:
  ```
- **Direct observation**: Because the widget key is dynamically formatted as `f"st_vistas_v4_{st.session_state.clear_key_v4}"` (e.g. `st_vistas_v4_0`), the literal key `"st_vistas_v4"` never exists in `st.session_state`. Lines 412–426 never execute, and uploaded views in Column 2 ("Elementos Cargados") are NEVER rendered.

### Obs 1.6: Upstream Service Bugs in `services/ai_prompt_service_v4.py`
- **File**: `services/ai_prompt_service_v4.py`
- **Line 409 (`generate_clone_views_prompt_v3`)**:
  `USER NOTES: {notas_vistas_usuario if notas_vistas_usuario else "None"}`
  `notas_vistas_usuario` is NOT an argument to `generate_clone_views_prompt_v3(self, target_name: str, furniture_analysis: Optional[Dict[str, Any]] = None, fondo_blanco: bool = True, hd: bool = False)`.
  * Command result: `NameError: name 'notas_vistas_usuario' is not defined`.
- **Line 428 (`generate_dynamic_gemini_clone_prompt`)**:
  `if not key:`
  `key = self.get_api_key(api_key)` was omitted before line 428.
  * Command result: `NameError: name 'key' is not defined`.

### Obs 1.7: Tab 4 ("Razonamiento IA") Encoding and Formatting
- **File**: `modules/prompt_studio_v4.py`
- **Lines 519–523**:
  ```python
  with p_tabs[3]:
      st.caption("?? Este es el razonamiento interno que Gemini us para entender el mueble:")
      st.code(res.get("furniture_analysis", "No hay anlisis disponible"), language="markdown")
      if res.get("fabric_analysis"):
          st.caption("?? Anlisis de la tela:")
          st.code(res.get("fabric_analysis"), language="markdown")
  ```
- **Direct observation**: Non-UTF8 corrupted characters (`??`, `us`, `anlisis`). Furthermore, `furniture_analysis` and `fabric_analysis` are Python dictionaries, not markdown strings. When `res["furniture_analysis"]` is `None` (in modes where `analyze_furniture_for_enhancement` is not called, such as "Vistas + Tela"), `.get("furniture_analysis", default)` evaluates to `None` instead of the fallback string.

---

## 2. Logic Chain

1. **Routing and State in `main.py`**:
   - `main.py` routes via `version = st.sidebar.radio(...)` (Obs 1.1).
   - In Streamlit, all keys stored in `st.session_state` persist across page reruns regardless of which branch of `if/elif/else` is executed.
   - Because `main.py` does not track `previous_version` and does not isolate namespaces, widgets in V1, V3, and V4 sharing identical keys (`txt_res_g`, `txt_res_d`, `txt_res_m`, `btn_clear_studio`) share the same memory slot in `st.session_state` (Obs 1.2).
   - Therefore, switching between V1, V3, and V4 can cause state bleeding, stale prompt text display, or unintentional wipes.

2. **The "Nuevas Casillas" Promise vs Implementation in V4**:
   - The subtitle of V4 in `main.py` is `"V4 Ultimate (Nuevas Casillas)"`.
   - The authoritative requirement R1 mandates:
     "Check `modules/prompt_studio_v4.py` to ensure the new inputs (medidas_usuario, lugar_casa_usuario, tipo_mueble_usuario, notas_vistas_usuario) are correctly collected and passed to the service layer."
   - When inspecting `modules/prompt_studio_v4.py`:
     - Only `tipo_mueble_usuario` was ported from V3 with a widget (`st.text_input` in lines 164–167) and initialized (line 161).
     - `medidas_usuario`, `lugar_casa_usuario`, and `notas_vistas_usuario` were inserted as argument variables in calls on line 270 and line 375, but NO input widgets were ever created to capture them from the user, and NO initialization to default strings `""` was performed (Obs 1.3).
   - Because Python functions evaluate local variable references before executing the function call:
     - Selecting "Vistas" and clicking "GENERAR PROMPTS" evaluates line 270 with unbound `notas_vistas_usuario` -> crashes immediately with `NameError`.
     - Selecting "Entorno" and clicking "GENERAR PROMPTS" evaluates line 375 with unbound `medidas_usuario` -> crashes immediately with `NameError`.
   - The `except Exception as e:` block at line 388 catches this and displays `❌ Error al procesar: name 'notas_vistas_usuario' is not defined` or `name 'medidas_usuario' is not defined` on the frontend, completely blocking prompt generation.

3. **Service Layer Disconnect**:
   - Even if the variables were defined, line 256, line 270, and line 375 invoke `ai_prompt_service_v4.generate_material_swap_prompt_v4`, `generate_multi_perspective_prompts_v4`, and `generate_minimalist_environment_prompt_v4` (Obs 1.4).
   - As proven by AST and runtime inspection, `ai_prompt_service_v4` is an instance of `AIPromptServiceV3` where the methods are still suffixed with `_v3`.
   - Consequently, any generation attempt encounters an unhandled `AttributeError` exception.

4. **Uploaded Views UI Breakdown**:
   - `vistas_up` uploader key is parameterized by `clear_key_v4` (`st_vistas_v4_0`), but the rendering check on line 412 inspects `st.session_state["st_vistas_v4"]` (Obs 1.5).
   - Because the static key `"st_vistas_v4"` is never populated, user-uploaded vista images are never previewed in the UI.

---

## 3. Caveats

1. **Read-Only Constraint**: In accordance with the Explorer role instructions, no source files were modified during this investigation. Verification scripts and logs were created exclusively inside `.agents/teamwork/explorer_r1_1/`.
2. **AI Studio API Key / Quota**: While testing static syntax, parameter names, and AST binding, live Gemini API calls depend on the availability of a valid `GEMINI_API_KEY` (or the default key embedded in `services/ai_prompt_service_v4.py`).
3. **Streamlit Component Execution**: Streamlit headless testing confirmed AST parsing and object attributes. Interactive browser DOM behavior was analyzed via Streamlit's documented execution model for widget state retention.

---

## 4. Conclusion

Requirement R1 currently **FAILS** due to multiple critical bugs in `modules/prompt_studio_v4.py` and `services/ai_prompt_service_v4.py`:

1. **Missing UI Widgets**: 3 out of the 4 required new inputs (`medidas_usuario`, `lugar_casa_usuario`, `notas_vistas_usuario`) do not have UI input widgets in `modules/prompt_studio_v4.py`.
2. **NameError Crashes**: Referencing `notas_vistas_usuario` (line 270) and `medidas_usuario`, `lugar_casa_usuario` (line 375) without initialization causes immediate `NameError` crashes whenever a user attempts to generate prompts in "Vistas" or "Entorno" modes.
3. **AttributeError Crashes**: `modules/prompt_studio_v4.py` calls `generate_material_swap_prompt_v4`, `generate_multi_perspective_prompts_v4`, and `generate_minimalist_environment_prompt_v4`, but `services/ai_prompt_service_v4.py` only defines the `*_v3` methods.
4. **State Bleeding in `main.py`**: `main.py` lacks session state cleanup when switching versions; shared widget keys (`txt_res_g`, `txt_res_d`, `txt_res_m`, `btn_clear_studio`) cause cross-version prompt pollution and global session resets.
5. **View Preview Bug**: `modules/prompt_studio_v4.py:412` fails to display uploaded view images due to checking `"st_vistas_v4"` instead of the active uploader state.

### Actionable Remediation Plan for the Implementer

#### A. In `modules/prompt_studio_v4.py`:
1. **Initialize default values at top of `render_prompt_studio_v4()`**:
   ```python
   tipo_mueble_usuario = ""
   medidas_usuario = ""
   lugar_casa_usuario = ""
   notas_vistas_usuario = ""
   ```
2. **Add UI Widgets in Column 1**:
   - In `modo_sel == "Entorno"` (lines 161–168):
     Add `medidas_usuario = st.text_input("Medidas del mueble (ej. 220x95x80 cm):", key="txt_medidas_v4")`
     Add `lugar_casa_usuario = st.text_input("Habitación / Ubicación (ej. Salón minimalista, Terraza cubierta):", key="txt_lugar_v4")`
   - In `modo_sel in ["Vistas", "Solo Tela", "Solo Madera", "Tela + Madera"]` (or globally as an advanced expander):
     Add `notas_vistas_usuario = st.text_input("Notas adicionales para la IA (ej. Resaltar costuras, patas en nogal oscuro):", key="txt_notas_vistas_v4")`
3. **Align Service Calls**:
   - Pass `notas_vistas_usuario=notas_vistas_usuario` in `generate_material_swap_prompt_v4` (or `_v3`).
   - Call the actual methods existing on `ai_prompt_service_v4` or create aliases.
4. **Fix View Images Preview**:
   - Change line 412 from:
     `if "st_vistas_v4" in st.session_state and st.session_state["st_vistas_v4"]:`
     to:
     `if vistas_up:` and iterate over `vistas_up`.
5. **Namespace Output Text Areas**:
   - Change widget keys to `txt_res_g_v4`, `txt_res_d_v4`, `txt_res_m_v4` to prevent collision with V1 and V3.
6. **Fix Corrupted UTF-8 Characters in Tab 4**:
   - Replace corrupted strings on lines 519 and 522 with proper UTF-8 captions.
   - Format `res["furniture_analysis"]` with `json.dumps(..., indent=2, ensure_ascii=False)` if it is a dictionary.

#### B. In `services/ai_prompt_service_v4.py`:
1. Add method aliases on `AIPromptServiceV3` (or define `AIPromptServiceV4`):
   ```python
   generate_material_swap_prompt_v4 = generate_material_swap_prompt_v3
   generate_multi_perspective_prompts_v4 = generate_multi_perspective_prompts_v3
   generate_minimalist_environment_prompt_v4 = generate_minimalist_environment_prompt_v3
   ```
2. Fix line 409 in `generate_clone_views_prompt_v3`: add `notas_vistas_usuario: str = ""` to the method signature.
3. Fix line 428 in `generate_dynamic_gemini_clone_prompt`: insert `key = self.get_api_key(api_key)` before `if not key:`.

#### C. In `main.py`:
1. Track version switches in `st.session_state`:
   ```python
   if "active_version" not in st.session_state:
       st.session_state.active_version = version
   elif st.session_state.active_version != version:
       st.session_state.active_version = version
       # Optionally clean version-specific keys
   ```

---

## 5. Verification Method

To independently reproduce and verify all findings:

1. **Verify Missing Attributes on `ai_prompt_service_v4`**:
   ```powershell
   python -c "import services.ai_prompt_service_v4 as s; [print(m, hasattr(s.ai_prompt_service_v4, m)) for m in ['generate_material_swap_prompt_v4', 'generate_multi_perspective_prompts_v4', 'generate_minimalist_environment_prompt_v4']]"
   ```
   *Expected output*: `False` for all three methods.

2. **Verify Unbound Variables in `modules/prompt_studio_v4.py`**:
   ```powershell
   python .agents/teamwork/explorer_r1_1/check_ast.py
   ```
   *Expected output*:
   `Var 'medidas_usuario' in render_prompt_studio_v4(): assigned=False, used_at_lines=[375]`
   `Var 'lugar_casa_usuario' in render_prompt_studio_v4(): assigned=False, used_at_lines=[375]`
   `Var 'notas_vistas_usuario' in render_prompt_studio_v4(): assigned=False, used_at_lines=[270]`

3. **Verify Upstream Bugs in `services/ai_prompt_service_v4.py`**:
   ```powershell
   python -c "import services.ai_prompt_service_v4 as s; s.ai_prompt_service_v4.generate_clone_views_prompt_v3('test')"
   # Raises NameError: name 'notas_vistas_usuario' is not defined
   python -c "import services.ai_prompt_service_v4 as s; s.ai_prompt_service_v4.generate_dynamic_gemini_clone_prompt(b'1', b'2')"
   # Raises NameError: name 'key' is not defined
   ```

4. **Verify Session Key Overlap**:
   ```powershell
   python .agents/teamwork/explorer_r1_1/check_sessions.py
   ```
   *Expected output*: Shows shared keys `txt_res_g`, `txt_res_d`, `txt_res_m`, `btn_clear_studio` between V1, V3, and V4.
