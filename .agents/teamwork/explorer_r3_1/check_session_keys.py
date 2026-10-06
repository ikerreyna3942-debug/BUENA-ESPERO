import re

for i in [1, 2, 3, 4]:
    content = open(f'modules/prompt_studio_v{i}.py', encoding='utf-8-sig').read()
    keys1 = re.findall(r'st\.session_state\["([^"]+)"\]', content)
    keys2 = re.findall(r'st\.session_state\.get\("([^"]+)"', content)
    keys3 = re.findall(r'"([^"]+)" in st\.session_state', content)
    all_keys = sorted(set(keys1 + keys2 + keys3))
    print(f"V{i} session_state keys:")
    for k in all_keys:
        print(f"  - {k}")
