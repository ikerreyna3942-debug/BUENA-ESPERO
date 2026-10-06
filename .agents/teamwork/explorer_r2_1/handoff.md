# Handoff Report: Requirement R2 (Prompt Engineering & Model Validation)

**Date**: 2026-10-06T07:55:00Z  
**Agent**: Explorer 2 (Explorer R2 - Prompt Engineering & Model Specialist)  
**Target Codebase**: `services/ai_prompt_service_v4.py` and related modules in `BUENA ESPERO`  
**Working Directory**: `C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\.agents\teamwork\explorer_r2_1`

---

## 1. Observation

### Observation 1.1: File Lineage and Diff Between V3 and V4 Services
A character-level diff between `services/ai_prompt_service_v3.py` (38,357 bytes) and `services/ai_prompt_service_v4.py` (38,359 bytes) revealed that `services/ai_prompt_service_v4.py` is an exact clone of `v3`, differing in only one line at the end:
```diff
--- services/ai_prompt_service_v3.py
+++ services/ai_prompt_service_v4.py
@@ -660,1 +660,1 @@
-ai_prompt_service_v3 = AIPromptServiceV3()
+ai_prompt_service_v4 = AIPromptServiceV3()
```
- In `services/ai_prompt_service_v4.py` (line 23), the class name remains `class AIPromptServiceV3:`.
- At line 660: `ai_prompt_service_v4 = AIPromptServiceV3()`.
- The Pydantic output schemas remain `MaterialAnalysisV3` (line 10) and `FurnitureAnalysisV3` (line 16).

---

### Observation 1.2: Method Name Mismatches Triggering `AttributeError`
In `modules/prompt_studio_v4.py`, the UI calls method names ending in `_v4`:
- Line 256:
  ```python
  prompts = ai_prompt_service_v4.generate_material_swap_prompt_v4(
      mode=mode_map[modo_sel],
      ...
  )
  ```
- Line 270:
  ```python
  prompts_vistas = ai_prompt_service_v4.generate_multi_perspective_prompts_v4(
      furniture_name=m_name, ...
  )
  ```
- Line 375:
  ```python
  prompts_min = ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(
      furniture_name=m_name, ...
  )
  ```
However, in `services/ai_prompt_service_v4.py`, these methods are defined with `_v3`:
- Line 176: `def generate_material_swap_prompt_v3(self, ...)`
- Line 299: `def generate_multi_perspective_prompts_v3(self, ...)`
- Line 543: `def generate_minimalist_environment_prompt_v3(self, ...)`

**Verbatim Execution Error**:
```
python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; getattr(ai_prompt_service_v4, 'generate_material_swap_prompt_v4')"
AttributeError: 'AIPromptServiceV3' object has no attribute 'generate_material_swap_prompt_v4'. Did you mean: 'generate_material_swap_prompt_v3'?
```
All three methods fail with `AttributeError` when triggered from `prompt_studio_v4.py`.

---

### Observation 1.3: Unbound / Undefined Variable Crashes in `services/ai_prompt_service_v4.py`

#### A. `NameError: name 'notas_vistas_usuario' is not defined`
In `services/ai_prompt_service_v4.py` lines 393-410:
```python
393: def generate_clone_views_prompt_v3(self, target_name: str, furniture_analysis: Optional[Dict[str, Any]] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
...
409: USER NOTES: {notas_vistas_usuario if notas_vistas_usuario else "None"}
```
- `notas_vistas_usuario` is NOT declared in the parameters of `generate_clone_views_prompt_v3` (line 393).
- **Verbatim Execution Error**:
  ```
  NameError: name 'notas_vistas_usuario' is not defined
  File "services/ai_prompt_service_v4.py", line 409, in generate_clone_views_prompt_v3
  ```

#### B. `NameError: name 'key' is not defined`
In `services/ai_prompt_service_v4.py` lines 427-431:
```python
427: def generate_dynamic_gemini_clone_prompt(self, ref_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
428:     if not key:
429:         fallback = "Please set GEMINI_API_KEY to generate dynamic prompts."
430:         return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}
```
- The statement `key = self.get_api_key(api_key)` was omitted before checking `if not key:`.
- **Verbatim Execution Error**:
  ```
  NameError: name 'key' is not defined
  File "services/ai_prompt_service_v4.py", line 428, in generate_dynamic_gemini_clone_prompt
  ```
- This function is directly invoked by `modules/prompt_studio_v4.py` line 343 whenever the user selects "Vistas + Tela y Madera", leading to an immediate crash.

---

### Observation 1.4: User Input Variables Reception and Injection Trace

Tracing the 4 specified user variables:
`medidas_usuario`, `lugar_casa_usuario`, `tipo_mueble_usuario`, `notas_vistas_usuario`:

1. **`medidas_usuario`**:
   - Signature: Accepted in `generate_minimalist_environment_prompt_v3` (line 550: `medidas_usuario: str = ""`).
   - Injection: Line 632 in `sys_prompt`:
     ```python
     - REAL WORLD MEASUREMENTS: {medidas_usuario if medidas_usuario else "Standard realistic proportions"}
     ```
   - Evaluation: Clean formatting and safe fallback handling when empty or None.
   - Status: Dropped in all other prompt generators.

2. **`lugar_casa_usuario`**:
   - Signature: Accepted in `generate_minimalist_environment_prompt_v3` (line 551: `lugar_casa_usuario: str = ""`).
   - Injection: Line 631 in `sys_prompt`:
     ```python
     - EXACT LOCATION: {lugar_casa_usuario if lugar_casa_usuario else "The natural room for this furniture"}
     ```
   - Evaluation: Clean formatting and safe fallback handling when empty or None.
   - Status: Dropped in all other prompt generators.

3. **`tipo_mueble_usuario`**:
   - Signature: Accepted in `generate_minimalist_environment_prompt_v3` (line 549: `tipo_mueble_usuario: str = ""`).
   - Processing: Lines 568-571:
     ```python
     furn_item = ma.get("furniture_item", furniture_name)
     if tipo_mueble_usuario and tipo_mueble_usuario.strip():
         furn_item = f"{tipo_mueble_usuario.strip()} ({furn_item})"
     ```
   - Injection: Injected into `sys_prompt` as `{furn_item}` at line 621 and line 630.
   - Evaluation: Correctly overrides and augments furniture identification.

4. **`notas_vistas_usuario`**:
   - In `generate_material_swap_prompt_v3` (lines 185, 226, 252, 277):
     * Injected only into `prompt_ai_studio` via `USER NOTES: {notas_vistas_usuario if notas_vistas_usuario else "None"}`.
     * Dropped from `prompt_dalle` and `prompt_mj`.
     * Caller in `prompt_studio_v4.py` (line 256) does not pass this variable.
   - In `generate_multi_perspective_prompts_v3` (lines 305, 342, 354, 356):
     * Injected into `p_ai` (line 342) and `p_dalle` (line 354).
     * Dropped from `p_mj` (line 356).
   - In `generate_clone_views_prompt_v3` (line 409):
     * Injected in f-string, but NOT declared as parameter -> triggers `NameError` crash.
   - In `generate_minimalist_environment_prompt_v3` (line 552):
     * Declared as parameter (`notas_vistas_usuario: str = ""`), BUT **COMPLETELY OMITTED** from `sys_prompt` (lines 553-658). Any view notes supplied by user are ignored and lost!

---

### Observation 1.5: UI Caller (`modules/prompt_studio_v4.py`) Data Flow Failures
Static symbol table analysis (`symtable`) on `modules/prompt_studio_v4.py::render_prompt_studio_v4` showed:
```
Free/global vars used in render_prompt_studio_v4:
['st', ..., 'notas_vistas_usuario', 'medidas_usuario', 'lugar_casa_usuario', ...]
```
- Lines 161-167 capture `tipo_mueble_usuario = st.text_input(...)`.
- `medidas_usuario`, `lugar_casa_usuario`, and `notas_vistas_usuario` have **NO UI widgets** and are never assigned before line 270 and line 375.
- Executing "Vistas" triggers `NameError: name 'notas_vistas_usuario' is not defined`.
- Executing "Entorno" triggers `NameError: name 'medidas_usuario' is not defined`.

---

### Observation 1.6: Gemini Model Configurations & Fallback Mechanism
Inspecting `services/ai_prompt_service_v4.py` lines 38-48:
```python
38: def _call_gemini(self, client, contents, config=None):
39:     """Llama a Gemini con lista de modelos activos y fallback automático."""
40:     models_to_try = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
41:     last_err = None
42:     for m in models_to_try:
43:         try:
44:             return client.models.generate_content(model=m, contents=contents, config=config)
45:         except Exception as e:
46:             last_err = e
47:             continue
48:     raise last_err if last_err else RuntimeError("No se pudo conectar con Gemini API")
```
- Models configured:
  1. Primary: `"gemini-3.5-flash"`
  2. Fallback: `"gemini-3.1-pro-preview"`
- Mechanism: A `for` loop over `models_to_try` wrapped in `try...except Exception as e:` captures any `APIError`, quota exhaustion, rate limit (429), or model-not-found (404), records `last_err`, and attempts the fallback in sequence. If all fail, it raises the last recorded error.
- Compliance: Exactly matches Requirement R2's requested model strings and sequential fallback pattern.

---

## 2. Logic Chain

1. **Step 1 (Lineage verification)**: Comparing `ai_prompt_service_v3.py` with `ai_prompt_service_v4.py` proves `v4` was copied from `v3` without updating internal class and method names.
2. **Step 2 (Interface breakage)**: Because `prompt_studio_v4.py` calls `generate_material_swap_prompt_v4`, `generate_multi_perspective_prompts_v4`, and `generate_minimalist_environment_prompt_v4`, but `ai_prompt_service_v4.py` only defines `_v3` variants, any user click on "GENERAR PROMPTS" in these modes immediately crashes with `AttributeError`.
3. **Step 3 (Internal crashes)**: In `generate_clone_views_prompt_v3`, referencing `notas_vistas_usuario` without declaring it in parameters creates an unavoidable `NameError`. In `generate_dynamic_gemini_clone_prompt`, evaluating `if not key:` before `key = self.get_api_key(api_key)` creates an unavoidable `NameError` whenever "Vistas + Tela y Madera" is run.
4. **Step 4 (Prompt injection integrity)**: In `generate_minimalist_environment_prompt_v3`, while `tipo_mueble_usuario`, `lugar_casa_usuario`, and `medidas_usuario` are cleanly formatted into the prompt with sensible fallbacks, `notas_vistas_usuario` is declared as an argument but never injected into the prompt body, failing prompt completeness.
5. **Step 5 (Caller data binding)**: In `modules/prompt_studio_v4.py`, 3 of the 4 inputs (`medidas_usuario`, `lugar_casa_usuario`, `notas_vistas_usuario`) are absent from the Streamlit UI, so they are not bound in scope when passed to the service layer.
6. **Step 6 (Model configuration)**: The fallback sequence `["gemini-3.5-flash", "gemini-3.1-pro-preview"]` is properly wired into `_call_gemini` with a loop and exception catcher, fulfilling the R2 model configuration requirement.

---

## 3. Caveats

1. **Google Gemini Live API Availability**:
   The model names `gemini-3.5-flash` and `gemini-3.1-pro-preview` specified in the project requirements are preview/hypothetical strings. In production Google AI Studio endpoints, if Google's API returns `404 NOT_FOUND` for these identifiers, the try/except loop will exhaust both models and fall back to the schema defaults in `analyze_material` / `analyze_furniture_for_enhancement`, or output an error string in dynamic prompt generation. It is recommended to include a proven production model (such as `gemini-2.5-flash`) as a 3rd fallback if live API calls are required.
2. **UI Widgets Scope**:
   The fix for missing widgets in `modules/prompt_studio_v4.py` falls under Requirement R1 / frontend routing, but is documented here as an essential upstream requirement for R2 prompt data flow.

---

## 4. Conclusion

The V4 prompt generation logic is **currently BROKEN with multiple severe bugs** that prevent normal operation:
1. **3 Method Name Discrepancies**: `_v4` in caller vs `_v3` in service -> Causes `AttributeError`.
2. **2 Service-layer `NameError` Bugs**:
   - `notas_vistas_usuario` in `generate_clone_views_prompt_v3:409`.
   - `key` in `generate_dynamic_gemini_clone_prompt:428`.
3. **1 Silent Variable Drop**: `notas_vistas_usuario` is accepted in `generate_minimalist_environment_prompt_v3` but never injected into the Gemini prompt template.
4. **Gemini Model Configuration**: Fully configured with `["gemini-3.5-flash", "gemini-3.1-pro-preview"]` and sequential try/except fallback.

### Artifact Provided
A complete, drop-in replacement file resolving all class/method mismatches, fixing all NameErrors, adding full backward compatibility, and cleanly injecting all 4 variables has been created and validated:
`C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO\.agents\teamwork\explorer_r2_1\proposed_ai_prompt_service_v4.py`

---

## 5. Verification Method

### A. Reproduce Existing Bugs
Run from project root `C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO`:
```powershell
# 1. AttributeError on V4 method
python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; getattr(ai_prompt_service_v4, 'generate_material_swap_prompt_v4')"

# 2. NameError on notas_vistas_usuario
python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; ai_prompt_service_v4.generate_clone_views_prompt_v3('sofa')"

# 3. NameError on key
python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; ai_prompt_service_v4.generate_dynamic_gemini_clone_prompt(b'1', b'2')"
```

### B. Verify Proposed Solution
```powershell
# Test proposed file imports, V4 method names, V3 aliases, and bug-free execution:
python -c "import sys; sys.path.insert(0, '.agents/teamwork/explorer_r2_1'); import proposed_ai_prompt_service_v4 as ps; print('V4 methods:', hasattr(ps.ai_prompt_service_v4, 'generate_material_swap_prompt_v4')); print('V3 aliases:', hasattr(ps.ai_prompt_service_v4, 'generate_material_swap_prompt_v3')); res = ps.ai_prompt_service_v4.generate_clone_views_prompt_v4('sofa'); print('generate_clone_views_prompt_v4 SUCCESS');"
```

### C. Invalidation Conditions
This investigation report is invalidated if:
1. `services/ai_prompt_service_v4.py` already implements `generate_material_swap_prompt_v4`, `generate_multi_perspective_prompts_v4`, and `generate_minimalist_environment_prompt_v4`.
2. `generate_dynamic_gemini_clone_prompt` defines `key = self.get_api_key(api_key)` before checking `if not key:`.
3. `generate_clone_views_prompt_v3` receives `notas_vistas_usuario` in its parameter signature.
