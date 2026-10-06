import re
from pathlib import Path

base_dir = Path("C:/ProgramData/Lenovo/GitHubDesktop/app-3.6.6/APPV3/BUENA ESPERO")

for v in ["v1", "v2", "v3", "v4"]:
    filepath = base_dir / "modules" / f"prompt_studio_{v}.py"
    if not filepath.exists():
        print(f"File not found: {filepath}")
        continue
    content = filepath.read_text(encoding="utf-8")
    
    # find st.session_state["..."] or st.session_state.xyz or "..." in st.session_state
    session_keys = set(re.findall(r'st\.session_state\[["\']([a-zA-Z0-9_]+)["\']\]', content))
    in_session = set(re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s+in\s+st\.session_state', content))
    session_keys.update(in_session)
    session_keys.update(re.findall(r'st\.session_state\.([a-zA-Z0-9_]+)', content))
    session_keys.update(re.findall(r'st\.session_state\.get\(["\']([a-zA-Z0-9_]+)["\']', content))
    
    widget_keys = set(re.findall(r'key=["\']([a-zA-Z0-9_]+)["\']', content))
    fstring_keys = set(re.findall(r'key=f["\']([a-zA-Z0-9_{}]+)["\']', content))
    
    print(f"=== {v.upper()} ===")
    print(f"Session State Keys: {sorted(session_keys)}")
    print(f"Widget Keys: {sorted(widget_keys)}")
    print(f"F-String Keys: {sorted(fstring_keys)}")
    print()
