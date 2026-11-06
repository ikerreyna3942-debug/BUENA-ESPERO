# Despliegue en Render

## Variables de entorno (Render → tu servicio → Environment)

| Variable | Valor | Obligatoria |
|---|---|---|
| `GEMINI_API_KEY` | Tu API key de Google AI Studio | Sí (análisis de fotos) |
| `GOOGLE_OAUTH_CREDENTIALS_JSON` | Salida de `python scripts/print_render_env.py` | Sí (sincronización con Google Sheets) |
| `GOOGLE_CREDENTIALS_JSON` | JSON de cuenta de servicio (respaldo) | No |
| `SPREADSHEET_ID` | Ya viene en `render.yaml` | No |

`render.yaml` ya declara estas variables con `sync: false`: Render te pedirá el valor, no se guarda en Git.

## Pasos
1. Sube los cambios a `main` (Render redeploya solo con `autoDeploy`).
2. En Render, agrega las variables de la tabla.
3. Espera el build (≈3 min). El health check es `/_stcore/health`.
4. Abre la app: la versión por defecto es **V6 Unificado**. Las versiones V1–V5 siguen en el menú lateral como respaldo.
5. Prueba: escribe un SKU → debe llenar tipo y medidas → sube una foto → GENERAR.

## Plan gratuito
El servicio se duerme tras ~15 min sin uso y tarda ~30–60 s en despertar. Es normal.

## ⚠️ Seguridad pendiente
`oauth_client.json` y `GOOGLE_OAUTH_CREDENTIALS.json` están en el historial de un repo **público**, aunque `.gitignore` los lista (ya estaban versionados). Para cerrarlo:
1. Google Cloud Console → Credentials: rota el *client secret* y vuelve a autorizar para obtener un token nuevo.
2. Pon el JSON nuevo en `GOOGLE_OAUTH_CREDENTIALS_JSON` en Render.
3. Deja de versionarlos: `git rm --cached oauth_client.json GOOGLE_OAUTH_CREDENTIALS.json` y commit.
4. Opcional: hacer el repo privado.

## Pruebas locales
```
python tests/test_unified.py
streamlit run main.py
```
