# Handoff Report: Explorer R3 — Output Generation & Bug Hunter

## 1. Observation

### 1.1 Source Inspection & Exact File References

#### A. `services/ai_prompt_service_v4.py`
1. **Service Class Naming & Method Suffix Mismatch**
   - Lines 23–24:
     ```python
     class AIPromptServiceV3:
         def __init__(self):
     ```
   - Line 660:
     ```python
     ai_prompt_service_v4 = AIPromptServiceV3()
     ```
   - The methods in this service are named with a `_v3` suffix:
     - Line 176: `def generate_material_swap_prompt_v3(...)`
     - Line 299: `def generate_multi_perspective_prompts_v3(...)`
     - Line 393: `def generate_clone_views_prompt_v3(...)`
     - Line 543: `def generate_minimalist_environment_prompt_v3(...)`
   - Notice: **No methods with the `_v4` suffix exist** in `services/ai_prompt_service_v4.py`.

2. **NameError in `generate_dynamic_gemini_clone_prompt`**
   - Lines 427–438:
     ```python
     def generate_dynamic_gemini_clone_prompt(self, ref_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
         if not key:
             fallback = "Please set GEMINI_API_KEY to generate dynamic prompts."
             return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}
     ```
   - Observation: Variable `key` is used on line 428 without prior definition. The statement `key = self.get_api_key(api_key)` (present in all other methods like lines 58, 98, 487, 556) is completely missing.
   - Verbatim runtime exception upon invocation:
     `NameError: name 'key' is not defined`

3. **NameError in `generate_clone_views_prompt_v3`**
   - Lines 393, 409:
     ```python
     def generate_clone_views_prompt_v3(self, target_name: str, furniture_analysis: Optional[Dict[str, Any]] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
         ...
         prompt_ai_studio = f"""...
     USER NOTES: {notas_vistas_usuario if notas_vistas_usuario else "None"}
     ..."""
     ```
   - Observation: `notas_vistas_usuario` is referenced in the f-string at line 409, but it is **not present in the function parameter list** at line 393.
   - Verbatim runtime exception upon invocation:
     `NameError: name 'notas_vistas_usuario' is not defined`

4. **Dropped Variable in `generate_minimalist_environment_prompt_v3`**
   - Lines 543–555:
     ```python
     def generate_minimalist_environment_prompt_v3(
         self,
         furniture_name: str,
         fabric_analysis: Optional[Dict[str, Any]] = None,
         furniture_analysis: Optional[Dict[str, Any]] = None,
         num_furniture_images: int = 1,
         tipo_mueble_usuario: str = "",
         medidas_usuario: str = "",
         lugar_casa_usuario: str = "",
         notas_vistas_usuario: str = "",
         api_key: Optional[str] = None,
         hd: bool = False
     ) -> Dict[str, str]:
     ```
   - Lines 620–638:
     ```python
     sys_prompt = f"""You are a Master Prompt Engineer specializing in Generative AI for luxury furniture photography.
     Your task is to write a highly-detailed text prompt to generate an image of the {furn_item} seen in {target_imgs}.

     CRITICAL CONSTRAINTS:
     1. GEOMETRY & IDENTITY: Maintain EXACTLY the {geom_struct} and {camera_angle} from the reference images. DO NOT alter the shape, dimensions, or design of the furniture.
     2. MATERIAL: The upholstery/material MUST be {f_name} ({f_color}, {f_texture}). Do NOT modify the color or texture.
     3. PERSPECTIVE: The camera must be at a far distance (wide shot, distant perspective) perfect for a high-end furniture catalog.
     4. ENVIRONMENT (DYNAMIC & CREATIVE): Create a hyper-realistic, high-end minimalist architectural interior setting. 
        - BASE STYLE FOR THIS GENERATION: {random_style}
        - Use warm, neutral, earthy tones (beige, taupe, soft gray, warm plaster, microcement).
        - Place the {furn_item} in its CORRECT NATURAL ROOM (e.g., a dining chair belongs in a dining room, a sofa in a living room, a bed in a bedroom).
        - EXACT LOCATION: {lugar_casa_usuario if lugar_casa_usuario else "The natural room for this furniture"}
        - REAL WORLD MEASUREMENTS: {medidas_usuario if medidas_usuario else "Standard realistic proportions"}
        - The environment colors must elegantly contrast with the furniture's color ({f_color} / {existing_materials}) to make the furniture pop.
     5. LIGHTING & CINEMATOGRAPHY: Strictly incorporate the lighting style specified in the BASE STYLE above. Use cinematic descriptions to make it look incredibly realistic.
     6. DEPTH OF FIELD: The background must be 40% blurred (moderate bokeh, f/2.8 lens effect), keeping the furniture perfectly sharp and in focus.

     Write a prompt that can be used in DALL-E, Midjourney, or Google AI Studio. Be extremely descriptive.
     Output ONLY the text of the prompt without quotes or introductions."""
     ```
   - Observation: `notas_vistas_usuario` is declared as an argument at line 552, but is **never referenced or injected into `sys_prompt` anywhere in the function**. It is completely dropped.

5. **Fallback Model Configuration**
   - Lines 38–48:
     ```python
     def _call_gemini(self, client, contents, config=None):
         models_to_try = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
     ```
   - Observation: Fallback models in `services/ai_prompt_service_v4.py` are set to `gemini-3.5-flash` and `gemini-3.1-pro-preview` (meeting the model requirement of R2).

---

#### B. `modules/prompt_studio_v4.py`
1. **Missing UI Inputs & Immediate NameErrors**
   - Lines 161–167:
     ```python
     tipo_mueble_usuario = ""
     if modo_sel == "Entorno":
         st.markdown("##### 🏷️ Ubicación / Tipo de Mueble (Opcional)")
         tipo_mueble_usuario = st.text_input(
             "Ayuda a la IA especificando el mueble (ej. Silla de comedor, Sofá, Cama) para que lo ubique en su espacio real:", 
             key="txt_tipo_mueble_v4"
         )
     ```
   - Observation:
     - `medidas_usuario`: **No UI widget exists anywhere in `modules/prompt_studio_v4.py`**. Variable is never declared.
     - `lugar_casa_usuario`: **No UI widget exists anywhere in `modules/prompt_studio_v4.py`**. Variable is never declared.
     - `notas_vistas_usuario`: **No UI widget exists anywhere in `modules/prompt_studio_v4.py`**. Variable is never declared.
   - Lines 270 and 375:
     - Line 270 (mode "Vistas"):
       `prompts_vistas = ai_prompt_service_v4.generate_multi_perspective_prompts_v4(..., notas_vistas_usuario=notas_vistas_usuario)`
       Raises: `NameError: name 'notas_vistas_usuario' is not defined`
     - Line 375 (mode "Entorno"):
       `prompts_min = ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(..., medidas_usuario=medidas_usuario, lugar_casa_usuario=lugar_casa_usuario, ...)`
       Raises: `NameError: name 'medidas_usuario' is not defined`

2. **AttributeError on Method Calls**
   - Line 256 (modes "Solo Tela", "Solo Madera", "Tela + Madera"):
     `prompts = ai_prompt_service_v4.generate_material_swap_prompt_v4(...)`
     Raises: `AttributeError: 'AIPromptServiceV3' object has no attribute 'generate_material_swap_prompt_v4'`
   - Line 270 (mode "Vistas"):
     `prompts_vistas = ai_prompt_service_v4.generate_multi_perspective_prompts_v4(...)`
     Raises: `AttributeError: 'AIPromptServiceV3' object has no attribute 'generate_multi_perspective_prompts_v4'`
   - Line 375 (mode "Entorno"):
     `prompts_min = ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(...)`
     Raises: `AttributeError: 'AIPromptServiceV3' object has no attribute 'generate_minimalist_environment_prompt_v4'`

3. **Silent Exception Swallowing Preventing Result Storage**
   - Lines 388–390:
     ```python
     except Exception as e:
         progress_holder.error(f"❌ Error al procesar: {str(e)}")
     ```
   - Observation: When any of the above `NameError` or `AttributeError` exceptions trigger, execution skips line 378 (`st.session_state["last_studio_result_v4"] = {...}`).
   - As a consequence:
     - `st.session_state["last_studio_result_v4"]` is **never set**.
     - Column 2 and Column 3 remain empty, displaying only `st.info("Configura y genera para ver los prompts optimizados.")`.
     - The user never sees prompts or internal reasoning.

4. **Output Generation & Tab 4 ("Razonamiento IA") Failure Modes**
   - Lines 462, 518–524:
     ```python
     p_tabs = st.tabs(["Google AI Studio", "DALL-E 3", "Flux / Midjourney", "Razonamiento IA"])
     ...
     with p_tabs[3]:
         st.caption("?? Este es el razonamiento interno que Gemini us para entender el mueble:")
         st.code(res.get("furniture_analysis", "No hay anlisis disponible"), language="markdown")
         if res.get("fabric_analysis"):
             st.caption("?? Anlisis de la tela:")
             st.code(res.get("fabric_analysis"), language="markdown")
     ```
   - Observation on `res.get("furniture_analysis", "No hay...")`:
     - In Python: If key `"furniture_analysis"` exists in `res` and its value is `None` (which happens in modes "Vistas + Tela" and "Vistas + Tela y Madera" where `m_ana` is uninitialized `None`), `res.get("furniture_analysis", default)` evaluates to `None`.
     - In Streamlit: `st.code(None, language="markdown")` stringifies `None` to `"None"`. It renders a code block containing the word `None`, NOT `"No hay análisis disponible"`.
     - In cases where `furniture_analysis` is present (a dict):
       `st.code(dict, language="markdown")` stringifies the dictionary as raw Python string representation (e.g. `"{'furniture_item': '...', 'camera_angle': '...'}"`) with single quotes, rather than structured JSON (`st.json`) or readable Markdown.
     - `wood_analysis` is completely omitted from Tab 4, even when wood is analyzed in modes "Solo Madera" and "Tela + Madera".
     - Broken character encoding in UI captions: `st.caption("?? Este es el razonamiento interno que Gemini us para entender el mueble:")` contains corrupted non-ASCII characters (`??`, `us`, `anlisis`).

5. **Column 2 Image Preview Bug for Uploaded Views**
   - Lines 171 vs 412:
     - Line 171:
       `vistas_up = st.file_uploader(..., key=f"st_vistas_v4_{st.session_state.clear_key_v4}", accept_multiple_files=True)`
     - Line 412:
       `if "st_vistas_v4" in st.session_state and st.session_state["st_vistas_v4"]:`
     - Observation: The session state key registered by Streamlit is `st_vistas_v4_0`. The key `st_vistas_v4` is never in `st.session_state`. Consequently, lines 412–427 never execute, and uploaded views are **never displayed in Column 2**.

---

### 1.2 Empirical Execution Verification

Tool command executed:
`python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; ..."`

Verbatim output:
```text
ai_prompt_service_v4 has generate_material_swap_prompt_v4: False
ai_prompt_service_v4 has generate_multi_perspective_prompts_v4: False
ai_prompt_service_v4 has generate_minimalist_environment_prompt_v4: False
generate_dynamic_gemini_clone_prompt raised NameError: name 'key' is not defined
generate_clone_views_prompt_v3 raised NameError: name 'notas_vistas_usuario' is not defined
```

Simulation across all 8 modes:
```text
--- AUDIT OF V4 SERVICE CALLS PER MODE ---
[PASS] Solo mueble: prompts generated, keys = ['google_ai_studio', 'midjourney_v6', 'chatgpt_dalle3']
[FAIL] Solo Tela: AttributeError 'AIPromptServiceV3' object has no attribute 'generate_material_swap_prompt_v4'
[FAIL] Solo Madera: AttributeError 'AIPromptServiceV3' object has no attribute 'generate_material_swap_prompt_v4'
[FAIL] Tela + Madera: AttributeError 'AIPromptServiceV3' object has no attribute 'generate_material_swap_prompt_v4'
[FAIL] Vistas: NameError 'notas_vistas_usuario' is not defined (and AttributeError generate_multi_perspective_prompts_v4)
[FAIL] Vistas + Tela: m_ana is None, furniture_analysis saved as None, renders "None" in Tab 4
[FAIL] Vistas + Tela y Madera: NameError name 'key' is not defined in generate_dynamic_gemini_clone_prompt
[FAIL] Entorno: NameError 'medidas_usuario' is not defined (and AttributeError generate_minimalist_environment_prompt_v4)
```

---

## 2. Logic Chain

1. **Premise**: Requirement R3 specifies: *"Confirm that the AI's internal analysis (`furniture_analysis`) is properly returned and displayed in the 4th tab ("Razonamiento IA") of the frontend."*
2. **From Observation 1.1.A.1 and 1.1.B.2**: `modules/prompt_studio_v4.py` calls service methods with `_v4` suffixes (`generate_material_swap_prompt_v4`, `generate_multi_perspective_prompts_v4`, `generate_minimalist_environment_prompt_v4`), but `services/ai_prompt_service_v4.py` only implements methods with `_v3` suffixes.
3. **From Observation 1.1.B.1**: In `modules/prompt_studio_v4.py`, lines 270 and 375 evaluate variables `notas_vistas_usuario`, `medidas_usuario`, and `lugar_casa_usuario` that have no UI inputs and were never defined in local or module scope.
4. **From Observation 1.1.A.2**: In `services/ai_prompt_service_v4.py` line 428, `key` is referenced before initialization in `generate_dynamic_gemini_clone_prompt`.
5. **Deduction (Modes 1 to 5 & 7)**:
   - "Solo Tela", "Solo Madera", and "Tela + Madera" crash on `AttributeError: generate_material_swap_prompt_v4`.
   - "Vistas" crashes on `NameError: notas_vistas_usuario` and `AttributeError: generate_multi_perspective_prompts_v4`.
   - "Vistas + Tela y Madera" crashes on `NameError: key`.
   - "Entorno" crashes on `NameError: medidas_usuario` and `AttributeError: generate_minimalist_environment_prompt_v4`.
6. **From Observation 1.1.B.3**: Because all exceptions are caught by `except Exception as e:`, line 378 (`st.session_state["last_studio_result_v4"]`) is never reached in these 6 modes. Tab 4 is never rendered at all.
7. **From Observation 1.1.B.4**: In the remaining modes ("Vistas + Tela"), `furniture_analysis` is never computed (`m_ana` remains `None`). When saved, `"furniture_analysis": None`.
8. **Deduction (Tab 4 Display)**:
   - When `"furniture_analysis"` is `None`, `res.get("furniture_analysis", default)` returns `None`. `st.code(None)` displays `"None"` inside a markdown block.
   - In the only mode that succeeds ("Solo mueble"), `furniture_analysis` is a Python dictionary. `st.code(dict, language="markdown")` displays raw Python representation `{'furniture_item': ...}`, which is unformatted and poorly structured.
9. **Deduction (Acceptance Criteria R1 & R2)**:
   - All 4 new user inputs do not reach the Gemini prompt reliably:
     - `medidas_usuario`: missing in UI; causes crash.
     - `lugar_casa_usuario`: missing in UI; causes crash.
     - `notas_vistas_usuario`: missing in UI; causes crash; and even when passed to `generate_minimalist_environment_prompt_v3`, it is completely ignored/dropped from the prompt template.
     - `tipo_mueble_usuario`: only collected conditionally for "Entorno" (empty string for all other modes).

---

## 3. Caveats

- **Scope boundary**: This investigation focused on V4 dataflow, service layer logic, output generation, and crash analysis. V1 and V2 are legacy implementations, but an import check revealed `services/ai_prompt_service_v1.py` exports `ai_prompt_service` (imported properly by `prompt_studio_v1.py`).
- **Live Gemini API key**: The hardcoded fallback key in `services/ai_prompt_service_v4.py` was inspected syntactically; live generation calls require a valid working network connection and quota. The investigation verified parsing, schemas, fallbacks, and internal data structures deterministically.

---

## 4. Conclusion

### Summary Assessment
The V4 prompt generation logic is **NOT bug-free and currently fails to generate prompts or display AI reasoning in 7 out of 8 modes**.

### Breakdown of Deficiencies:
| Requirement | Status | Root Cause |
|---|---|---|
| **R3: `furniture_analysis` generated & parsed** | **PARTIAL** | Works in service (`analyze_furniture_for_enhancement` returns `FurnitureAnalysisV3` dict), but in modes "Vistas + Tela" and "Vistas + Tela y Madera" it is never invoked (`m_ana = None`). |
| **R3: Display in 4th Tab ("Razonamiento IA")** | **BROKEN** | In 6 modes it crashes before rendering. In "Vistas + Tela" it displays literal `"None"`. In "Solo mueble" it displays raw Python string `{'item': ...}` instead of formatted JSON/Markdown. Non-ASCII captions are corrupted (`??`). `wood_analysis` is omitted. |
| **R1 & R2: User inputs reach Gemini prompt** | **BROKEN** | UI widgets for `medidas_usuario`, `lugar_casa_usuario`, and `notas_vistas_usuario` are absent from `prompt_studio_v4.py`. Referencing them causes fatal `NameError`. In service, `notas_vistas_usuario` is dropped in `generate_minimalist_environment_prompt_v3`. |
| **End-to-End Pipeline Integrity** | **CRITICAL BUGS** | 3 `AttributeError` (missing `_v4` methods), 4 `NameError` (`key`, `notas_vistas_usuario`, `medidas_usuario`), 1 UI preview bug (`st_vistas_v4`), and UTF-8 BOM characters. |

---

## 5. Verification Method

To independently reproduce and verify all findings:

1. **Verify Method Mismatches & Undefined Variables**:
   ```bash
   python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; print(hasattr(ai_prompt_service_v4, 'generate_material_swap_prompt_v4'))"
   # Output: False
   ```
2. **Verify `generate_dynamic_gemini_clone_prompt` Crash**:
   ```bash
   python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; ai_prompt_service_v4.generate_dynamic_gemini_clone_prompt(b'1', b'2')"
   # Output: NameError: name 'key' is not defined
   ```
3. **Verify `generate_clone_views_prompt_v3` Crash**:
   ```bash
   python -c "from services.ai_prompt_service_v4 import ai_prompt_service_v4; ai_prompt_service_v4.generate_clone_views_prompt_v3('sofa')"
   # Output: NameError: name 'notas_vistas_usuario' is not defined
   ```
4. **Verify Tab 4 Dictionary / None Handling**:
   ```bash
   python -c "res = {'furniture_analysis': None}; print(repr(res.get('furniture_analysis', 'default')))"
   # Output: None
   ```
5. **Inspect Files**:
   - `services/ai_prompt_service_v4.py`: Lines 176, 299, 393, 409, 428, 543, 620–638.
   - `modules/prompt_studio_v4.py`: Lines 161–167, 256, 270, 375, 412, 518–524.
