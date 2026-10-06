import os
import sys

# Attempt to load from the env or we can print out the available models
# We will use the dotenv if it's there
sys.path.append(r"g:\Mi unidad\PROYECTOS FINALES\APP PORMPT MEJORADO\generador_prompts_muebles\APP-PROMPT2.1")
try:
    from dotenv import load_dotenv
    load_dotenv(r"g:\Mi unidad\PROYECTOS FINALES\APP PORMPT MEJORADO\generador_prompts_muebles\APP-PROMPT2.1\.env")
except:
    pass

from google import genai
from google.genai.errors import APIError

api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
if not api_key:
    print("NO API KEY")
    sys.exit(1)

client = genai.Client(api_key=api_key)

try:
    models = client.models.list()
    print("Models:")
    for m in models:
        print(m.name)
except Exception as e:
    print(f"Error listing models: {e}")

model_name = "gemini-2.0-flash"
try:
    res = client.models.generate_content(model=model_name, contents="hello")
    print(f"Success with {model_name}")
except Exception as e:
    print(f"Error with {model_name}: {e}")
