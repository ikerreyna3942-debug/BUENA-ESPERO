import re
import os

file_path = r'I:\Mi unidad\PROYECTOS FINALES\APP PORMPT MEJORADO\PROMPRT 2.1\APP-FINAL\services\ai_prompt_service_v3.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('def generate_material_swap_prompt_v3(', 'def generate_material_swap_prompt_v3(\n        self, hd: bool = False,')
content = content.replace('def generate_multi_perspective_prompts_v3(', 'def generate_multi_perspective_prompts_v3(\n        self, hd: bool = False,')
content = content.replace('def generate_dynamic_fabric_view_prompt(', 'def generate_dynamic_fabric_view_prompt(\n        self, hd: bool = False,')
content = content.replace('def generate_minimalist_environment_prompt_v3(', 'def generate_minimalist_environment_prompt_v3(\n        self, hd: bool = False,')
content = content.replace('def generate_dynamic_gemini_clone_prompt(', 'def generate_dynamic_gemini_clone_prompt(\n        self, hd: bool = False,')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
