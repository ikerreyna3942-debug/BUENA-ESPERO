import re

files = {
    'V1': 'modules/prompt_studio_v1.py',
    'V2': 'modules/prompt_studio_v2.py',
    'V3': 'modules/prompt_studio_v3.py',
    'V4': 'modules/prompt_studio_v4.py',
}

key_map = {}
for ver, fpath in files.items():
    with open(fpath, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    
    # find key="..." or key='...'
    widget_keys = re.findall(r'key\s*=\s*["\']([^"\']+)["\']', content)
    # find st.session_state["..."] or st.session_state.get("...")
    ss_keys = re.findall(r'st\.session_state(?:\[|\.get\()\s*["\']([^"\']+)["\']', content)
    
    all_keys = set(widget_keys + ss_keys)
    key_map[ver] = all_keys

all_unique_keys = set().union(*key_map.values())

shared = {}
for k in sorted(all_unique_keys):
    vers = [ver for ver, keys in key_map.items() if k in keys]
    if len(vers) > 1:
        shared[k] = vers

print('=== SHARED SESSION STATE & WIDGET KEYS ===')
for k, vers in shared.items():
    print(f'{k:30} -> {vers}')
