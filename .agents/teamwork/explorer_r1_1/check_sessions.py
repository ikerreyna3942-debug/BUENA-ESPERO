import re

for v in ['v1', 'v2', 'v3', 'v4']:
    filepath = f"modules/prompt_studio_{v}.py"
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # find st.session_state[...] or st.session_state.xyz
    keys_bracket = re.findall(r'session_state\[["\']([^"\']+)["\']\]', content)
    keys_dot = re.findall(r'session_state\.([a-zA-Z0-9_]+)', content)
    keys_in = re.findall(r'["\']([^"\']+)["\']\s+in\s+st\.session_state', content)
    keys_get = re.findall(r'session_state\.get\(["\']([^"\']+)["\']', content)
    
    # find widget keys: key="..." or key=f"..."
    widget_keys = re.findall(r'key=([^\),\s]+)', content)
    
    all_session = sorted(set(keys_bracket + keys_dot + keys_in + keys_get))
    print(f"=== {v.upper()} SESSION KEYS ===")
    for k in all_session:
        print(f"  {k}")
    print(f"=== {v.upper()} WIDGET KEYS ===")
    for wk in sorted(set(widget_keys)):
        print(f"  {wk}")
    print()
