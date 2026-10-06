from services.gemini_service import GeminiService
from PIL import Image
import os

img = Image.new('RGB', (100, 100), color = 'red')
img.save('test.jpg')
with open('test.jpg', 'rb') as f:
    bytes_list = [f.read()]

service = GeminiService()
try:
    result = service.generate_prompt(bytes_list, "vistas", "Some notes")
    print(result)
except Exception as e:
    print(f"FAILED: {e}")
