# Handoff Report: Reviewer 1 (Independent Code Reviewer & Adversarial Critic)

- **Date**: 2026-10-06T08:10:00Z
- **Role**: Reviewer & Adversarial Critic
- **Target Files**:
  - `main.py`
  - `modules/prompt_studio_v4.py`
  - `services/ai_prompt_service_v4.py`
- **Working Directory**: `C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\.agents\teamwork\reviewer_1`
- **Review Verdict**: **REQUEST_CHANGES**
- **Overall Risk Assessment**: **CRITICAL**

---

## Review Summary

**Verdict**: **REQUEST_CHANGES**

The codebase is **NOT ready for production or deployment**. While certain components of `services/ai_prompt_service_v4.py` were recently renamed from `_v3` to `_v4`, the prompt generation pipeline remains critically broken with multiple fatal runtime crashes (`NameError`), missing UI widgets, silent dropping of user input, cross-version session state collisions, and defective rendering in Tab 4 ("Razonamiento IA").

---

## 1. Observation

### Obs 1.1: Verification of Requirement R1 (UI, Routing & Session State)
1. **Session State Bleeding in `main.py`**:
   - **File**: `main.py:30-51`
   - **Direct Observation**:
     ```python
     version = st.sidebar.radio(
         "📌 Versión del Estudio:",
         ["V4 Ultimate (Nuevas Casillas)", "V3 Nivel Dios (Recomendado)", "V2 Optimizado", "V1 Clasica Original"]
     )
     if version == "V4 Ultimate (Nuevas Casillas)":
         render_v4()
     elif version == "V3 Nivel Dios (Recomendado)":
         render_v3()
     elif version == "V2 Optimizado":
         render_v2()
     else:
         render_v1()
     ```
     `main.py` performs conditional routing without any session state reset, version change listener, or namespace isolation.
   - **Key Collision Scan**:
     Using AST and regex analysis (`analyze_keys.py`), the following widget and session state keys are shared across versions:
     - `btn_clear_studio` -> Shared across `['V1', 'V2', 'V3', 'V4']`. Clicking this button executes `st.session_state.clear()`, wiping the global session state across all versions.
     - `txt_res_g` -> Shared across `['V1', 'V3', 'V4']` (`modules/prompt_studio_v1.py:978`, `modules/prompt_studio_v3.py:494`, `modules/prompt_studio_v4.py:481`).
     - `txt_res_d` -> Shared across `['V1', 'V3', 'V4']` (`modules/prompt_studio_v1.py:1000`, `modules/prompt_studio_v3.py:512`, `modules/prompt_studio_v4.py:499`).
     - `txt_res_m` -> Shared across `['V3', 'V4']` (`modules/prompt_studio_v3.py:530`, `modules/prompt_studio_v4.py:517`).
     - `cp_comp` -> Shared across `['V3', 'V4']` (`modules/prompt_studio_v3.py:111`, `modules/prompt_studio_v4.py:111`).
   - **Impact**: Streamlit binds text areas to existing keys in `st.session_state`. Generating prompts in V3 and navigating to V4 displays stale prompts from V3 in V4's UI text areas or causes session bleeding.

2. **Missing UI Widgets and `NameError` in `modules/prompt_studio_v4.py`**:
   - **File**: `modules/prompt_studio_v4.py`
   - **Symbol Table Analysis (`symtable` & AST)** in `render_prompt_studio_v4`:
     - `tipo_mueble_usuario`: `assigned=True`, `loaded=True` (Widget created at lines 164–167 when `modo_sel == "Entorno"`).
     - `medidas_usuario`: `assigned=False`, `loaded=True` (Loaded on line 375, never assigned).
     - `lugar_casa_usuario`: `assigned=False`, `loaded=True` (Loaded on line 375, never assigned).
     - `notas_vistas_usuario`: `assigned=False`, `loaded=True` (Loaded on line 270, never assigned).
   - **Verbatim Code at Line 270 (Mode "Vistas")**:
     ```python
     prompts_vistas = ai_prompt_service_v4.generate_multi_perspective_prompts_v4(furniture_name=m_name, fabric_analysis=f_ana, furniture_analysis=m_ana, fondo_blanco=fondo_blanco, hd=hd_toggle, notas_vistas_usuario=notas_vistas_usuario)
     ```
     Runtime evaluation throws: `NameError: name 'notas_vistas_usuario' is not defined`.
   - **Verbatim Code at Line 375 (Mode "Entorno")**:
     ```python
     prompts_min = ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(furniture_name=m_name, fabric_analysis=f_ana, furniture_analysis=m_ana, num_furniture_images=num_imgs, tipo_mueble_usuario=tipo_mueble_usuario, medidas_usuario=medidas_usuario, lugar_casa_usuario=lugar_casa_usuario, hd=hd_toggle)
     ```
     Runtime evaluation throws: `NameError: name 'medidas_usuario' is not defined`.
   - **Widget Verification**: Zero occurrences of `st.text_input` or any other input widget for `medidas_usuario`, `lugar_casa_usuario`, or `notas_vistas_usuario` exist in `modules/prompt_studio_v4.py`.

3. **Uploaded Views UI Preview Bug**:
   - **Line 171**: `vistas_up = st.file_uploader(..., key=f"st_vistas_v4_{st.session_state.clear_key_v4}", accept_multiple_files=True)`
   - **Line 412**: `if "st_vistas_v4" in st.session_state and st.session_state["st_vistas_v4"]:`
   - Because the widget key is parameterized dynamically (`st_vistas_v4_0`), the key `"st_vistas_v4"` never exists in `st.session_state`. Lines 412–427 never execute, and uploaded view photos are never displayed in Column 2 ("Elementos Cargados").

---

### Obs 1.2: Verification of Requirement R2 (Prompt Engineering & Model Validation)
1. **Method Naming and Class Structure in `services/ai_prompt_service_v4.py`**:
   - **Direct Observation**: At `services/ai_prompt_service_v4.py:23`, the class is defined as `class AIPromptServiceV4:`, and line 660 instantiates `ai_prompt_service_v4 = AIPromptServiceV4()`.
   - The primary methods are now named with `_v4`:
     - Line 176: `def generate_material_swap_prompt_v4(...)`
     - Line 299: `def generate_multi_perspective_prompts_v4(...)`
     - Line 393: `def generate_clone_views_prompt_v4(...)`
     - Line 543: `def generate_minimalist_environment_prompt_v4(...)`
   - Therefore, calling these methods no longer raises `AttributeError: ... has no attribute '..._v4'`. However, NO backward compatibility aliases (`_v3`) exist on the instance.

2. **NameError on `key` in `generate_dynamic_gemini_clone_prompt`**:
   - **Lines 427–430**:
     ```python
     def generate_dynamic_gemini_clone_prompt(self, ref_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
         if not key:
             fallback = "Please set GEMINI_API_KEY to generate dynamic prompts."
             return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}
     ```
   - Variable `key` is referenced on line 428 without prior definition (`key = self.get_api_key(api_key)` was omitted).
   - **Empirical Execution Result**:
     ```
     generate_dynamic_gemini_clone_prompt: FAILED -> NameError: name 'key' is not defined
     ```
   - Invoking mode "Vistas + Tela y Madera" immediately crashes.

3. **NameError on `notas_vistas_usuario` in `generate_clone_views_prompt_v4`**:
   - **Line 393**:
     ```python
     def generate_clone_views_prompt_v4(self, target_name: str, furniture_analysis: Optional[Dict[str, Any]] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
     ```
   - **Line 409**:
     ```python
     USER NOTES: {notas_vistas_usuario if notas_vistas_usuario else "None"}
     ```
   - `notas_vistas_usuario` is NOT declared in the parameter list.
   - **Empirical Execution Result**:
     ```
     generate_clone_views_prompt_v4: FAILED -> NameError: name 'notas_vistas_usuario' is not defined
     ```

4. **Dropped Variable in `generate_minimalist_environment_prompt_v4`**:
   - **Line 552**: `notas_vistas_usuario: str = ""` is received as an argument.
   - **Lines 620–638**: In `sys_prompt`, `lugar_casa_usuario` (line 631) and `medidas_usuario` (line 632) are injected, but `notas_vistas_usuario` is **completely omitted**. Any view notes supplied by the user are silently discarded.

5. **Gemini Model Configuration and Fallback Cascade**:
   - **Lines 40–48**:
     ```python
     def _call_gemini(self, client, contents, config=None):
         models_to_try = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
         last_err = None
         for m in models_to_try:
             try:
                 return client.models.generate_content(model=m, contents=contents, config=config)
             except Exception as e:
                 last_err = e
                 continue
         raise last_err if last_err else RuntimeError("No se pudo conectar con Gemini API")
     ```
   - Models configured: Primary `"gemini-3.5-flash"`, secondary fallback `"gemini-3.1-pro-preview"`.
   - The sequential fallback loop functions as intended. In live testing with the embedded default key, Google AI Studio returned `429 RESOURCE_EXHAUSTED` (Free Tier input token limit reached), properly triggering the exception handler and graceful fallback string.

---

### Obs 1.3: Verification of Requirement R3 (Output Generation & Tab 4 "Razonamiento IA")
1. **Extraction and Pipeline Failure**:
   - Because modes "Vistas", "Vistas + Tela y Madera", and "Entorno" crash on `NameError`, execution enters `except Exception as e:` at line 388:
     ```python
     progress_holder.error(f"❌ Error al procesar: {str(e)}")
     ```
   - Line 378 (`st.session_state["last_studio_result_v4"] = {...}`) is never executed.
   - Therefore, Column 3 remains at line 525 (`st.info("Configura y genera para ver los prompts optimizados.")`), and Tab 4 is **never rendered**.

2. **Rendering when `furniture_analysis` is `None`**:
   - In mode "Vistas + Tela", `m_ana` is never computed (initialized as `None` at line 238 and never assigned).
   - In `last_studio_result_v4`, `"furniture_analysis": None`.
   - In Tab 4 (line 520):
     `st.code(res.get("furniture_analysis", "No hay análisis disponible"), language="markdown")`
   - Because the key `"furniture_analysis"` exists in `res`, `res.get(...)` returns `None`.
   - `st.code(None)` stringifies `None` to `"None"`. It renders a code box displaying the literal word `None`, rather than the user-friendly default string `"No hay análisis disponible"`.

3. **Rendering when `furniture_analysis` is a Dictionary**:
   - In modes where `analyze_furniture_for_enhancement` runs (e.g. "Solo mueble"), `furniture_analysis` is a Python dictionary (`FurnitureAnalysisV4.model_dump()`).
   - `st.code(dict, language="markdown")` stringifies the dictionary using Python's `str()`, displaying raw unformatted dictionary syntax with single quotes:
     `{'furniture_item': '...', 'camera_angle': '...', ...}`.
   - It is neither formatted JSON nor readable markdown.

4. **Omission of `wood_analysis`**:
   - When wood is analyzed in modes "Solo Madera" and "Tela + Madera", `res["wood_analysis"]` is saved, but Tab 4 lines 518–523 only display `furniture_analysis` and `fabric_analysis`. `wood_analysis` is completely omitted.

5. **Character Encoding**:
   - Lines 519 and 522 contain corrupted non-ASCII characters: `st.caption("?? Este es el razonamiento interno que Gemini us para entender el mueble:")` and `st.caption("?? Anlisis de la tela:")`.

---

## 2. Logic Chain

1. **Routing and State**:
   - `main.py` switches versions without resetting or namespacing `st.session_state`.
   - Because `txt_res_g`, `txt_res_d`, `txt_res_m`, and `btn_clear_studio` are shared across V1, V3, and V4, switching between versions causes stale prompt bleeding and accidental global wipes.
2. **Missing UI Inputs**:
   - Requirement R1 explicitly mandated collecting `medidas_usuario`, `lugar_casa_usuario`, `tipo_mueble_usuario`, and `notas_vistas_usuario`.
   - In `modules/prompt_studio_v4.py`, widgets exist only for `tipo_mueble_usuario`. No widgets exist for `medidas_usuario`, `lugar_casa_usuario`, or `notas_vistas_usuario`.
   - When lines 270 and 375 attempt to pass these variables, Python fails to resolve them in local or module scope, immediately throwing `NameError`.
3. **Service Layer Defects**:
   - In `generate_clone_views_prompt_v4`, line 409 references `notas_vistas_usuario` which is not in the parameter list -> crashes with `NameError`.
   - In `generate_dynamic_gemini_clone_prompt`, line 428 evaluates `if not key:` without defining `key` -> crashes with `NameError`.
   - In `generate_minimalist_environment_prompt_v4`, `notas_vistas_usuario` is accepted in the signature but dropped from the prompt body.
4. **End-to-End Breakdown**:
   - As a direct consequence of the NameErrors in modes "Vistas", "Vistas + Tela y Madera", and "Entorno", execution aborts before `st.session_state["last_studio_result_v4"]` is saved.
   - Therefore, prompt generation fails and Tab 4 "Razonamiento IA" never renders in these modes.
   - In modes where generation does run, Tab 4 displays raw Python dict strings or literal `"None"`, omitting wood analysis and displaying corrupted UTF-8 captions.

---

## 3. Findings

### [Critical] Finding 1: Fatal NameErrors Crashing Prompt Studio V4
- **What**: Referencing undeclared variables in `modules/prompt_studio_v4.py` and `services/ai_prompt_service_v4.py` causes immediate fatal crashes.
- **Where**:
  - `modules/prompt_studio_v4.py:270` (`notas_vistas_usuario`)
  - `modules/prompt_studio_v4.py:375` (`medidas_usuario`, `lugar_casa_usuario`)
  - `services/ai_prompt_service_v4.py:409` (`notas_vistas_usuario`)
  - `services/ai_prompt_service_v4.py:428` (`key`)
- **Why**: Blocks prompt generation entirely in modes "Vistas", "Vistas + Tela y Madera", and "Entorno", displaying error banners on the UI.
- **Suggestion**:
  - In `modules/prompt_studio_v4.py`: Add UI widgets (`st.text_input`) and initialize defaults `""` for all four variables.
  - In `services/ai_prompt_service_v4.py:393`: Add `notas_vistas_usuario: str = ""` to the method signature of `generate_clone_views_prompt_v4`.
  - In `services/ai_prompt_service_v4.py:428`: Add `key = self.get_api_key(api_key)` before `if not key:`.

### [Critical] Finding 2: Missing UI Widgets for Mandated Inputs (R1)
- **What**: 3 out of 4 new inputs specified in Requirement R1 (`medidas_usuario`, `lugar_casa_usuario`, `notas_vistas_usuario`) have no UI input widgets in `modules/prompt_studio_v4.py`.
- **Where**: `modules/prompt_studio_v4.py:161-215`
- **Why**: Users cannot input measurements, room locations, or perspective notes, violating Requirement R1.
- **Suggestion**: Add `st.text_input` widgets for `medidas_usuario` and `lugar_casa_usuario` in mode "Entorno", and for `notas_vistas_usuario` in perspective/views modes.

### [Major] Finding 3: Silently Dropped User Notes in Service Layer (R2)
- **What**: `notas_vistas_usuario` is accepted in `generate_minimalist_environment_prompt_v4` but omitted from the prompt template body (`sys_prompt`).
- **Where**: `services/ai_prompt_service_v4.py:552, 620-638`
- **Why**: User-specified view notes are discarded and never reach Gemini.
- **Suggestion**: Inject `- USER VIEW NOTES: {notas_vistas_usuario}` into `sys_prompt` when present.

### [Major] Finding 4: Cross-Version Session State Collisions and Bleeding (R1)
- **What**: Shared session keys (`txt_res_g`, `txt_res_d`, `txt_res_m`, `btn_clear_studio`) cause state contamination across V1, V3, and V4, and `st.session_state.clear()` wipes all version states globally.
- **Where**: `main.py:30-51`, `modules/prompt_studio_v4.py:116, 481, 499, 517`
- **Why**: Navigating between versions retains stale prompts from previous versions; clearing studio in one version destroys user session in others.
- **Suggestion**: Namespace all keys in V4 (`txt_res_g_v4`, `txt_res_d_v4`, `txt_res_m_v4`, `btn_clear_studio_v4`). Implement version-change detection in `main.py`.

### [Major] Finding 5: Defective Rendering and Omissions in Tab 4 "Razonamiento IA" (R3)
- **What**: Displays literal string `"None"` when `furniture_analysis` is `None`; displays raw Python dictionary syntax `{'item': ...}` when populated; completely omits `wood_analysis`; contains corrupted UTF-8 captions.
- **Where**: `modules/prompt_studio_v4.py:518-524`
- **Why**: Produces unreadable output that fails acceptance criteria for AI reasoning visualization.
- **Suggestion**: Use `st.json()` for dictionaries, format with markdown text, display fallback caption when `None`, include `wood_analysis`, and repair UTF-8 encoding.

### [Minor] Finding 6: Uploaded Views Preview Bug
- **What**: `modules/prompt_studio_v4.py:412` checks `st.session_state["st_vistas_v4"]` while the uploader key is parameterized as `st_vistas_v4_0`.
- **Where**: `modules/prompt_studio_v4.py:171, 412`
- **Why**: Uploaded vista images are never previewed in Column 2 ("Elementos Cargados").
- **Suggestion**: Change check to `if vistas_up:` and iterate over `vistas_up`.

---

## 4. Adversarial Critic Challenge Report

### Challenge Summary
**Overall Risk Assessment**: **CRITICAL**

### Challenges

#### Challenge 1: Local Variable Binding in Streamlit Execution Model
- **Assumption Challenged**: Streamlit scripts run top-to-bottom and can rely on conditional variable assignment.
- **Attack Scenario**: User selects "Vistas" or "Entorno" without touching optional inputs. Streamlit re-runs script from line 1. Code attempts to call service methods passing variables that were never bound in any branch.
- **Blast Radius**: Unhandled `NameError` caught by broad `except Exception`, displaying red error banners, halting prompt generation, and leaving the results state empty.
- **Mitigation**: Always initialize variables to safe default values (`tipo_mueble_usuario = ""`, `medidas_usuario = ""`, `lugar_casa_usuario = ""`, `notas_vistas_usuario = ""`) at the top of `render_prompt_studio_v4()`.

#### Challenge 2: Graceful Degradation under Gemini API 429 Quota Exhaustion
- **Assumption Challenged**: Calls to Gemini API will always succeed with the embedded key.
- **Attack Scenario**: Under high traffic or free-tier exhaustion, Gemini returns `429 RESOURCE_EXHAUSTED` (as observed during our live test).
- **Blast Radius**: If exceptions are not trapped cleanly with fallback schemas, the UI crashes.
- **Mitigation**: The current try/except block in `_call_gemini` and default Pydantic dumps provide good fallbacks, but adding a proven production fallback model (e.g. `gemini-2.5-flash`) ensures resilience.

#### Challenge 3: Shared Widget State Contamination
- **Assumption Challenged**: Users will use only one version per session.
- **Attack Scenario**: User tests a prompt in V3, switches to V4 to compare the new inputs. Because `txt_res_g` already exists in `st.session_state`, Streamlit binds V4's text area to V3's string.
- **Blast Radius**: User copies V3 prompts thinking they were generated by V4.
- **Mitigation**: Use version-specific keys (`txt_res_g_v4`, `txt_res_d_v4`, `txt_res_m_v4`).

### Stress Test Results

| Mode / Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|
| Mode: "Solo mueble" | Generate prompts & display analysis | Prompts generated successfully; Tab 4 displays raw Python dict | **PARTIAL** |
| Mode: "Solo Tela" | Material swap generation | Prompts generated; Tab 4 shows fabric analysis | **PASS** |
| Mode: "Solo Madera" | Wood swap generation | Prompts generated; Tab 4 omits wood analysis | **PARTIAL** |
| Mode: "Tela + Madera" | Dual swap generation | Prompts generated; Tab 4 omits wood analysis | **PARTIAL** |
| Mode: "Vistas" | Multi-perspective prompt generation | Crashes: `NameError: name 'notas_vistas_usuario' is not defined` | **FAIL** |
| Mode: "Vistas + Tela" | View recoloring generation | Prompts generated; Tab 4 displays literal `"None"` | **PARTIAL** |
| Mode: "Vistas + Tela y Madera" | Dynamic clone prompt generation | Crashes: `NameError: name 'key' is not defined` | **FAIL** |
| Mode: "Entorno" | Minimalist environment prompt generation | Crashes: `NameError: name 'medidas_usuario' is not defined` | **FAIL** |
| Method: `generate_clone_views_prompt_v4` | Clone views prompt generation | Crashes: `NameError: name 'notas_vistas_usuario' is not defined` | **FAIL** |

---

## 5. Integrity Check

- **Hardcoded Test Results**: None found in codebase.
- **Facade Implementations**: None found. Implementation uses genuine `google-genai` SDK and Pydantic structured output models.
- **Shortcuts / Bypassed Work**: None detected.
- **Self-Certifying Claims**: The Explorer reports accurately identified the primary defects, though `services/ai_prompt_service_v4.py` was partially renamed to `_v4` between the explorer reports and this review. Independent verification confirmed all underlying logical bugs and runtime crashes.

---

## 6. Caveats

- **No Caveats**: All findings and observations were independently reproduced using AST symbol tables, non-destructive script simulations, and live test executions against the codebase. No production source files were modified during this review.

---

## 7. Conclusion

The application `BUENA ESPERO` currently **FAILS** the acceptance criteria outlined in `ORIGINAL_REQUEST.md`:
1. **The V4 prompt generation logic is NOT correct or bug-free**: 3 primary modes crash immediately on `NameError`, and service methods contain uninitialized variables.
2. **User inputs do NOT reliably reach the Gemini prompt**: `medidas_usuario`, `lugar_casa_usuario`, and `notas_vistas_usuario` lack UI widgets, and `notas_vistas_usuario` is dropped inside `generate_minimalist_environment_prompt_v4`.
3. **Session state collides across versions**: Shared widget keys cause prompt bleed and accidental session clearing.
4. **AI Reasoning in Tab 4 is defective**: Displays raw dict strings or `"None"`, omits wood analysis, and has corrupted text encoding.

**Recommendation**: **REQUEST_CHANGES** — An implementer must resolve the critical and major findings documented above before this codebase can be approved.

---

## 8. Verification Method

To independently reproduce all findings from the project root (`C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO`):

1. **Verify Missing Variables in `prompt_studio_v4.py`**:
   ```powershell
   python -c "import ast; tree = ast.parse(open('modules/prompt_studio_v4.py', encoding='utf-8-sig').read()); [print(node.name, [(n.id, isinstance(n.ctx, ast.Store)) for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in ['medidas_usuario', 'notas_vistas_usuario']]) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'render_prompt_studio_v4']"
   ```
   *Expected output*: `isinstance(n.ctx, ast.Store)` is `False` for both variables (only loaded, never assigned).

2. **Verify Service-Layer NameErrors**:
   ```powershell
   python -c "import sys; sys.path.insert(0, '.'); import services.ai_prompt_service_v4 as s; s.ai_prompt_service_v4.generate_clone_views_prompt_v4('test')"
   # Raises: NameError: name 'notas_vistas_usuario' is not defined

   python -c "import sys; sys.path.insert(0, '.'); import services.ai_prompt_service_v4 as s; s.ai_prompt_service_v4.generate_dynamic_gemini_clone_prompt(b'1', b'2')"
   # Raises: NameError: name 'key' is not defined
   ```

3. **Verify Pipeline Simulation Across All 8 Modes**:
   ```powershell
   python .agents/teamwork/reviewer_1/simulate_pipeline.py
   ```
   *Expected output*: Shows crashes on modes 'Vistas', 'Vistas + Tela y Madera', and 'Entorno'.

4. **Verify Session Key Collisions Across V1-V4**:
   ```powershell
   python .agents/teamwork/reviewer_1/analyze_keys.py
   ```
   *Expected output*: Lists shared keys `btn_clear_studio`, `txt_res_g`, `txt_res_d`, `txt_res_m`, `cp_comp`.

### Invalidation Conditions
This report is invalidated only if:
1. All four variables (`medidas_usuario`, `lugar_casa_usuario`, `tipo_mueble_usuario`, `notas_vistas_usuario`) have dedicated UI widgets in `modules/prompt_studio_v4.py` and are initialized at function entry.
2. `services/ai_prompt_service_v4.py:428` defines `key = self.get_api_key(api_key)` before checking `if not key:`.
3. `services/ai_prompt_service_v4.py:393` includes `notas_vistas_usuario: str = ""` in `generate_clone_views_prompt_v4`.
4. `generate_minimalist_environment_prompt_v4` injects `notas_vistas_usuario` into `sys_prompt`.
5. All widget keys in V4 are properly namespaced.
