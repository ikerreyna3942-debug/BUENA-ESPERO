# Generador de Prompts de Muebles (Furniture Prompt Generator Studio)

> **Estudio interactivo de análisis visual de muebles y generación dinámica de prompts cinematográficos mediante Google Gemini AI.**  
> Diseñado con una arquitectura moderna, ligera y de alto rendimiento, preparado para despliegue en **Render** y versionado con **Git**.

---

## 📋 Descripción del Proyecto

El **Generador de Prompts de Muebles** es una aplicación web interactiva que permite a directores de arte, diseñadores de interiores, modeladores 3D y creadores de contenido publicitario analizar fotografías reales de piezas de mobiliario y generar automáticamente prompts profesionales para motores de generación de imágenes de última generación (como Midjourney, Imagen 3, Stable Diffusion XL y Flux).

La aplicación actúa como un **Director de Arte especializado**, examinando exhaustivamente la geometría, paleta cromática, texturas de materiales (telas, maderas, metales, cueros) y condiciones de iluminación de la pieza para transformarla en descripciones fotográficas de alta precisión.

---

## 🚀 Características y Requerimientos Implementados

### R1. Análisis de Fotos con Gemini AI
- **Visión Multimodal de Vanguardia**: Integración con el SDK oficial de Google GenAI (`google-genai`).
- **Análisis Detallado**: Extracción de proporciones volumétricas, curvatura, acabado superficial, balance tonal y comportamiento de la luz sobre los materiales.
- **Rol Director de Arte**: Instrucción de sistema maestra que guía al modelo para formular prompts con especificaciones de lente de cámara (50mm, 85mm tilt-shift), ángulo cenital, iluminación de estudio (softbox, rim light) y descriptores fotorrealistas.
- **Cascada de Modelos con Tolerancia a Fallos**: Sistema de respaldo automático (`gemini-2.5-pro` ➔ `gemini-2.0-flash` ➔ `gemini-1.5-pro` ➔ `gemini-1.5-flash`).
- **Protección de Memoria RAM (Pillow Guard)**: Optimización y redimensionamiento en memoria (< 50MB, máximo 1600px, conversión alfa a RGB) para prevenir desbordamientos en contenedores de recursos limitados.

### R2. Interfaz de Usuario y Controles Interactivos
- **Zona Exclusiva Drag & Drop**: Superficie interactiva dedicada donde el arrastre y suelta es el único método para cargar la imagen principal.
- **Previsualización Instantánea**: Visualización inmediata en alta fidelidad de la imagen arrastrada mediante la API nativa `FileReader`.
- **Botón "Borrar" (Reset Completo)**: Limpieza instantánea tanto visual como del estado reactivo del frontend y memoria del navegador.
- **5 Botones Exactos de Generación**:
  1. `solo mueble`: Aísla la pieza sobre fondo de ciclorama blanco puro de estudio comercial (packshot de e-commerce).
  2. `vistas`: Genera 5 perspectivas ortogonales y de catálogo (frontal, lateral 90°, 3/4 isométrica, cenital/desde arriba y posterior 3/4) con entornos dinámicos variables.
  3. `entorno`: Sitúa el mueble en una escena editorial de interiorismo realista de alta gama.
  4. `vistas + tela y madera`: Perspectivas de catálogo con extracción dual reforzada y macro-detalle de los tejidos textiles y las vetas/tonalidades de la madera.
  5. `vistas + tela`: Perspectivas enfocadas en el tapizado y confección textil, bloqueando y preservando la anatomía de las patas o estructura de madera.
- **Micro-interacciones y Estados de Carga**: Indicadores visuales durante el procesamiento, botón de copiado al portapapeles con confirmación visual de 1 clic y mensajes de error amigables.

### R3. Generación Dinámica de Entornos (Aleatoriedad)
- **Taxonomía Combinatoria de Escenarios**: Para el botón `vistas`, inyección aleatoria de 4 dimensiones independientes antes de consultar a Gemini:
  - 8 estilos arquitectónicos (Japandi, Escandinavo Moderno, Minimalismo Brutalista, Loft Industrial, Mid-Century Modern, Mediterráneo Contemporáneo, etc.)
  - 7 espacios/ubicaciones (Salón con jardín zen interior, ático luminoso, galería de arte contemporáneo, suite residencial, etc.)
  - 6 esquemas de iluminación (Luz dorada de atardecer, luz difusa de claraboya nórdica, sombras dramáticas de persianas, etc.)
  - 5 armonías de color (Monocromático cálido, contrastes orgánicos tierra, etc.)
- **Garantía de Variabilidad**: Más de 1.680 combinaciones posibles que aseguran que cada clic genere un escenario fotográfico completamente nuevo y diferenciado.

### R4. Preparación para Despliegue en Render y Git
- Dependencias estrictamente fijadas en `requirements.txt`.
- Archivo `.gitignore` integral para entornos Python, venv, secretos y sistemas operativos.
- Configuración para Render Web Services: `render.yaml`, `Procfile` y `runtime.txt`.
- Endpoint de monitoreo `/health` para comprobaciones de estado sin tiempo de inactividad (zero-downtime healthcheck).

---

## 🛠️ Estructura del Proyecto

```
generador_prompts_muebles/
├── app.py                         # Servidor FastAPI, endpoints de API y servicio estático
├── services/
│   ├── __init__.py                # Inicializador de paquete
│   ├── gemini_service.py          # Cliente Gemini AI, directiva Director de Arte y cascada de modelos
│   └── random_scenarios.py        # Generador taxonómico de escenarios aleatorios para vistas (R3)
├── static/
│   ├── css/
│   │   └── style.css              # Estilos CSS modernos, tema estudio oscuro y responsive
│   ├── js/
│   │   └── app.js                 # Lógica Drag & Drop exclusiva, previsualización, 5 botones y portapapeles
│   └── index.html                 # Interfaz visual de usuario (SPA)
├── tests/
│   ├── conftest.py                # Fixtures de pytest, cliente de pruebas e imágenes sintéticas
│   ├── test_health.py             # Pruebas del endpoint /health
│   ├── test_backend_api.py        # Pruebas de validación y respuesta de los 5 modos
│   ├── test_randomizer.py         # Pruebas de variabilidad estocástica de escenarios
│   ├── test_e2e_scenarios.py      # Pruebas de integración E2E completas
│   └── run_tests.py               # Ejecutor de pruebas estructurado
├── run_tests.py                   # Script raíz para ejecución de la suite de pruebas
├── requirements.txt               # Dependencias de producción y pruebas fijadas
├── .gitignore                     # Reglas de exclusión de Git
├── render.yaml                    # Blueprint declarativo para Render
├── Procfile                       # Comando de inicio para servidores web PaaS
├── runtime.txt                    # Versión de Python para Render (python-3.12.10)
├── .env.example                   # Plantilla de variables de entorno requeridas
└── README.md                      # Documentación completa del proyecto
```

---

## ⚙️ Instalación Local

### Requisitos Previos
- **Python 3.10** o superior (recomendado **Python 3.12**).
- Clave de API de **Google Gemini** ([Google AI Studio](https://aistudio.google.com/)).

### 1. Clonar o Navegar al Directorio del Proyecto
```bash
cd generador_prompts_muebles
```

### 2. Crear y Activar un Entorno Virtual
En Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
En Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar las Dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar las Variables de Entorno
Copia el archivo de ejemplo `.env.example` a `.env`:
```bash
# En Windows:
copy .env.example .env

# En Linux / macOS:
cp .env.example .env
```
Abre `.env` y coloca tu clave de API de Gemini:
```env
GEMINI_API_KEY=AIzaSy...tu_clave_real_aqui
PORT=8000
```

---

## 💻 Ejecución de la Aplicación

Puedes iniciar la aplicación utilizando cualquiera de las dos alternativas:

### Opción A: Ejecución directa con Python
```bash
python app.py
```

### Opción B: Ejecución con Uvicorn (Recomendado para desarrollo con recarga en vivo)
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Una vez iniciado el servidor, abre tu navegador web en:
👉 **`http://localhost:8000`**

---

## ☁️ Despliegue en Render

El proyecto está 100% configurado para desplegarse en **Render** con un solo clic utilizando su funcionalidad de **Blueprints (render.yaml)** o mediante la creación manual de un **Web Service**.

### Opción 1: Despliegue Automático con Blueprint (render.yaml)
1. Sube tu repositorio a GitHub o GitLab.
2. En tu cuenta de [Render Dashboard](https://dashboard.render.com/), selecciona **New +** ➔ **Blueprint**.
3. Conecta el repositorio del proyecto. Render detectará automáticamente el archivo `render.yaml`.
4. En la configuración de variables de entorno del servicio, introduce el valor secreto para `GEMINI_API_KEY`.
5. Haz clic en **Apply**. Render compilará e iniciará el servicio automáticamente.

### Opción 2: Creación Manual de Web Service
Si prefieres crear el servicio de forma manual:
- **Environment**: `Python`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/health`
- **Environment Variables**:
  - `PYTHON_VERSION`: `3.12.10`
  - `GEMINI_API_KEY`: *(Tu clave de API de Gemini)*

El endpoint `/health` garantiza que Render mantenga el tráfico dirigido únicamente a instancias saludables.

---

## 🧪 Ejecución de la Suite de Pruebas

El proyecto cuenta con una suite integral de pruebas unitarias y de integración E2E que validan la API, el manejo de imágenes, la inyección estocástica de escenarios y la resiliencia del servicio.

Para ejecutar todas las pruebas:
```bash
python run_tests.py
```

O directamente mediante `pytest`:
```bash
pytest tests/ -v
```

---

## 📡 Endpoints de la API

| Método | Ruta | Descripción | Parámetros / Cuerpo |
|---|---|---|---|
| `GET` | `/` | Interfaz web SPA | Ninguno |
| `GET` | `/health` | Chequeo de salud del servicio | `{"status": "ok", "version": "1.0.0"}` |
| `POST` | `/api/generate` | Generación de prompts analíticos | Multipart: `image` (archivo), `mode` (`solo mueble`, `vistas`, `entorno`, `vistas + tela y madera`, `vistas + tela`), `notes` (opcional) |

---

## 📄 Licencia y Créditos
Desarrollado como solución profesional de análisis visual con inteligencia artificial generativa.
