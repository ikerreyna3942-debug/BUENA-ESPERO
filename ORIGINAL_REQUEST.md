# Original User Request

## 2026-10-06T07:41:16Z

Analyze the application `BUENA ESPERO` to ensure the 4 versions (V1-V4) and their AI prompt generation logic are perfectly correct and bug-free.

Working directory: C:\ProgramData\Lenovo\GitHubDesktop\app-3.6.6\APPV3\BUENA ESPERO
Integrity mode: development

## Requirements

### R1. UI and Routing Validation
Verify `main.py` correctly routes the 4 versions (V1, V2, V3, V4) without overlapping sessions. Check `modules/prompt_studio_v4.py` to ensure the new inputs (medidas_usuario, lugar_casa_usuario, tipo_mueble_usuario, notas_vistas_usuario) are correctly collected and passed to the service layer.

### R2. Prompt Engineering Validation
Analyze `services/ai_prompt_service_v4.py`. Confirm that the new variables are correctly formatted and injected into the Gemini API system prompts. Verify the fallback models are updated to `gemini-3.5-flash` and `gemini-3.1-pro-preview`.

### R3. Output Generation
Confirm that the AI's internal analysis (`furniture_analysis`) is properly returned and displayed in the 4th tab ("Razonamiento IA") of the frontend.

## Acceptance Criteria

### Code Review Report
- [ ] A definitive summary stating whether the V4 prompt generation logic is perfectly correct.
- [ ] Explicit confirmation that all new user inputs reach the final Gemini prompt.
- [ ] Identification of any crashes, syntax errors, or logical bugs in the data flow.
