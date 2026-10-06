import re

with open('services/gemini_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'Field\(\s*None,\s*', 'Field(', content)
content = re.sub(r'Field\(\s*\"\",\s*', 'Field(', content)

with open('services/gemini_service.py', 'w', encoding='utf-8') as f:
    f.write(content)
