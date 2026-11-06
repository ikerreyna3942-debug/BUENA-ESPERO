"""Imprime el valor de GOOGLE_OAUTH_CREDENTIALS_JSON en una sola línea,
listo para pegar en Render > Environment. Léelo tú, no lo compartas ni lo subas a Git.

Uso:  python scripts/print_render_env.py
"""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "GOOGLE_OAUTH_CREDENTIALS.json"
if not src.exists():
    sys.exit("No existe GOOGLE_OAUTH_CREDENTIALS.json en la raíz del proyecto.")
print(json.dumps(json.loads(src.read_text(encoding="utf-8")), separators=(",", ":")))
