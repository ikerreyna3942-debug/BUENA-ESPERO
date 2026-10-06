# Execution Plan: Code Review & Validation of BUENA ESPERO V1-V4

## Objective
Execute a comprehensive, evidence-backed code review and validation of BUENA ESPERO versions V1-V4, focusing on V4 prompt generation, session isolation, user input propagation, model fallbacks, frontend display, and identifying any bugs, syntax errors, or logical discrepancies.

## Scope & Target Files
- `main.py`
- `modules/prompt_studio_v4.py` (and related V1-V3 modules for session overlap analysis)
- `services/ai_prompt_service_v4.py`
- Relevant configuration, utility, and UI files

## Requirements Breakdown
- **R1. UI and Routing Validation**:
  - Routing in `main.py` across V1, V2, V3, V4 without session leakage or collisions.
  - Collection in `modules/prompt_studio_v4.py` of `medidas_usuario`, `lugar_casa_usuario`, `tipo_mueble_usuario`, `notas_vistas_usuario`.
  - Proper passing of these parameters to the service layer.
- **R2. Prompt Engineering Validation**:
  - Formatting and injection of new variables into Gemini system/user prompts in `services/ai_prompt_service_v4.py`.
  - Verification of model list and fallback chain (`gemini-3.5-flash` and `gemini-3.1-pro-preview`).
- **R3. Output Generation & Frontend Display**:
  - AI internal analysis (`furniture_analysis`) extracted and returned by service.
  - Frontend display of `furniture_analysis` in the 4th tab ("Razonamiento IA").
- **Acceptance Criteria**:
  1. Definitive summary on V4 prompt generation logic correctness.
  2. Explicit confirmation of all new user inputs reaching final Gemini prompt.
  3. Complete identification of any crashes, syntax errors, or logical bugs.

## Phased Workflow
1. **Phase 1: Multi-Angle Technical Survey (3 Explorers in parallel)**
   - Explorer 1: Focus on `main.py` routing, session isolation across V1-V4, and `modules/prompt_studio_v4.py` input gathering.
   - Explorer 2: Focus on `services/ai_prompt_service_v4.py`, prompt templates, variable interpolation, API payload, and fallback models.
   - Explorer 3: Focus on output handling (`furniture_analysis`), 4th tab UI rendering, end-to-end trace, syntax verification, and potential runtime crashes.
2. **Phase 2: Review & Adversarial Cross-Check**
   - Reviewer / Challenger: Cross-check findings, verify edge cases, confirm whether inputs truly reach prompts, verify model identifiers.
   - Auditor: Perform integrity check.
3. **Phase 3: Synthesis & Reporting**
   - Synthesize all findings into a unified, definitive Code Review Report.
   - Send final report to parent orchestrator.
