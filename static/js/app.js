/**
 * app.js
 * ======
 * Frontend Controller for Furniture Prompt Generator Studio.
 * Exclusively handles Drag & Drop image loading, preview rendering,
 * complete state deletion/reset, 5-mode prompt generation via /api/generate,
 * dynamic environment metadata rendering, and clipboard actions.
 */

(function () {
    'use strict';

    // --------------------------------------------------------------------------
    // State Management
    // --------------------------------------------------------------------------
    const state = {
        currentFiles: [],
        isGenerating: false,
        activeMode: null,
        abortController: null,
        lastResult: null
    };

    // Allowed modes strictly matching Requirement R2 & Acceptance Criteria 4
    const ALLOWED_MODES = [
        "solo mueble",
        "vistas",
        "entorno",
        "vistas + tela y madera",
        "vistas + tela"
    ];

    const MAX_IMAGE_SIZE_BYTES = 50 * 1024 * 1024; // 50MB
    const VALID_IMAGE_TYPES = [
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp"
    ];

    // --------------------------------------------------------------------------
    // DOM Element References
    // --------------------------------------------------------------------------
    const DOM = {
        // Dropzone & Preview
        dropzone: document.getElementById('dropzone'),
        dropzoneEmpty: document.getElementById('dropzone-empty'),
        dropzonePreview: document.getElementById('dropzone-preview'),
        previewGallery: document.getElementById('preview-gallery'),

        // Reset / Delete
        btnBorrar: document.getElementById('btn-borrar'),
        stateStatusIndicator: document.getElementById('state-status-indicator'),

        // Optional Direction
        userNotes: document.getElementById('user-notes'),

        // The 5 Generation Buttons
        modeButtons: document.querySelectorAll('.btn-mode'),

        // Results Section
        resultsEmpty: document.getElementById('results-empty'),
        loadingState: document.getElementById('loading-state'),
        loadingTitle: document.getElementById('loading-title'),
        loadingDesc: document.getElementById('loading-desc'),

        // Prompt Card & Subcards
        promptCard: document.getElementById('prompt-card'),
        badgeActiveMode: document.getElementById('badge-active-mode'),
        badgeModelUsed: document.getElementById('badge-model-used'),
        btnCopiar: document.getElementById('btn-copiar'),
        copyBtnText: document.getElementById('copy-btn-text'),
        iconCopy: document.querySelector('.icon-copy'),
        iconCheck: document.querySelector('.icon-check'),
        masterPromptText: document.getElementById('master-prompt-text'),
        charWordCount: document.getElementById('char-word-count'),

        // Environment (R3)
        environmentContainer: document.getElementById('environment-container'),
        envStyleVal: document.getElementById('env-style-val'),
        envLocationVal: document.getElementById('env-location-val'),
        envLightingVal: document.getElementById('env-lighting-val'),
        envPaletteVal: document.getElementById('env-palette-val'),

        // Views Accordion
        viewsContainer: document.getElementById('views-container'),
        viewsAccordion: document.getElementById('views-accordion'),

        // Negative Prompt
        negativePromptContainer: document.getElementById('negative-prompt-container'),
        negativePromptText: document.getElementById('negative-prompt-text'),

        // Analysis
        analysisContainer: document.getElementById('analysis-container'),
        analysisGrid: document.getElementById('analysis-grid'),

        // Notifications
        notificationBanner: document.getElementById('notification-banner'),
        notificationMessage: document.getElementById('notification-message'),
        notificationIcon: document.getElementById('notification-icon'),
        btnNotificationClose: document.getElementById('btn-notification-close')
    };

    // --------------------------------------------------------------------------
    // Utility Helpers
    // --------------------------------------------------------------------------

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function countWords(str) {
        if (!str) return 0;
        return str.trim().split(/\s+/).filter(Boolean).length;
    }

    function showNotification(message, type = 'error', durationMs = 6000) {
        if (!DOM.notificationBanner) return;
        DOM.notificationBanner.hidden = false;
        DOM.notificationBanner.className = 'notification-banner';

        if (type === 'warning') {
            DOM.notificationBanner.classList.add('is-warning');
            DOM.notificationIcon.textContent = '⚠️';
        } else if (type === 'success') {
            DOM.notificationBanner.classList.add('is-success');
            DOM.notificationIcon.textContent = '✓';
        } else {
            DOM.notificationIcon.textContent = '⛔';
        }

        DOM.notificationMessage.textContent = message;

        if (window._notifTimeout) {
            clearTimeout(window._notifTimeout);
        }
        if (durationMs > 0) {
            window._notifTimeout = setTimeout(hideNotification, durationMs);
        }
    }

    function hideNotification() {
        if (DOM.notificationBanner) {
            DOM.notificationBanner.hidden = true;
        }
    }

    // --------------------------------------------------------------------------
    // Drag & Drop Handling (Exclusive Image Loading - R2 & AC 1)
    // --------------------------------------------------------------------------

    function initDragAndDrop() {
        const dropzone = DOM.dropzone;
        if (!dropzone) return;

        // Prevent standard OS file open behaviors on entire window
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            window.addEventListener(eventName, (e) => {
                // If dragged outside dropzone, prevent browser opening file
                if (e.target !== dropzone && !dropzone.contains(e.target)) {
                    e.preventDefault();
                }
            }, false);

            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        // Visual Dragover Highlighting
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => {
                if (!state.isGenerating) {
                    dropzone.classList.add('is-dragover');
                }
            }, false);
        });

        ['dragleave', 'dragend'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => {
                dropzone.classList.remove('is-dragover');
            }, false);
        });

        // Drop Event Listener
        dropzone.addEventListener('drop', (e) => {
            dropzone.classList.remove('is-dragover');
            if (state.isGenerating) return;

            const dt = e.dataTransfer;
            if (!dt || !dt.files || dt.files.length === 0) return;

            Array.from(dt.files).forEach(f => processDroppedFile(f));
        }, false);
    }

    function processDroppedFile(file) {
        if (!file) return;

        // 1. Validate Max 10 Files
        if (state.currentFiles.length >= 10) {
            showNotification("Puedes subir un máximo de 10 fotos.", 'warning');
            return;
        }

        // 2. Validate File Type
        const fileType = (file.type || '').toLowerCase();
        const fileName = (file.name || '').toLowerCase();
        const hasValidExt = /\.(jpg|jpeg|png|webp|gif|bmp|tiff)$/i.test(fileName);
        const hasValidMime = VALID_IMAGE_TYPES.some(t => fileType.startsWith(t)) || fileType.startsWith('image/');

        if (!hasValidExt && !hasValidMime) {
            showNotification(
                "Solo se admiten archivos de imagen válidos (JPG, PNG, WEBP, GIF, BMP).",
                'warning'
            );
            return;
        }

        // 2. Validate Size Limit
        if (file.size > MAX_IMAGE_SIZE_BYTES) {
            showNotification(
                `El archivo supera el tamaño máximo permitido de 50MB (${formatBytes(file.size)}).`,
                'error'
            );
            return;
        }

        // 3. Read & Display Image Preview (AC 2)
        const reader = new FileReader();

        reader.onload = function (event) {
            state.currentFiles.push(file);

            // Update UI elements
            const imgEl = document.createElement('img');
            imgEl.className = 'preview-media';
            imgEl.src = event.target.result;
            imgEl.style.maxWidth = '150px';
            imgEl.style.maxHeight = '150px';
            imgEl.style.objectFit = 'cover';
            imgEl.style.borderRadius = 'var(--radius-md)';
            
            // Allow clicking to remove individual files
            imgEl.style.cursor = 'pointer';
            imgEl.title = 'Haz clic para quitar esta foto';
            imgEl.addEventListener('click', () => {
                const idx = state.currentFiles.indexOf(file);
                if (idx > -1) {
                    state.currentFiles.splice(idx, 1);
                    imgEl.remove();
                    DOM.stateStatusIndicator.textContent = `Fotos listas: ${state.currentFiles.length}`;
                    if (state.currentFiles.length === 0) {
                        resetApplicationState();
                    }
                }
            });

            DOM.previewGallery.appendChild(imgEl);

            DOM.dropzoneEmpty.hidden = true;
            DOM.dropzonePreview.hidden = false;
            DOM.dropzone.classList.add('has-image');

            // Enable "Borrar" button & Mode Buttons
            DOM.btnBorrar.disabled = false;
            setModeButtonsDisabled(false);

            DOM.stateStatusIndicator.textContent = `Fotos listas: ${state.currentFiles.length}`;
            DOM.stateStatusIndicator.classList.add('has-image');

            hideNotification();
        };

        reader.onerror = function () {
            showNotification("Error al leer el archivo de imagen seleccionado.", 'error');
        };

        reader.readAsDataURL(file);
    }

    // --------------------------------------------------------------------------
    // Delete & Reset Logic ("Borrar" Button - R2 & AC 3)
    // --------------------------------------------------------------------------

    function resetApplicationState() {
        // 1. Abort any in-flight API request
        if (state.abortController) {
            state.abortController.abort();
            state.abortController = null;
        }

        // 2. Clear Internal State
        state.currentFiles = [];
        state.isGenerating = false;
        state.activeMode = null;
        state.lastResult = null;

        // 3. Clear Visual Preview
        if (DOM.previewGallery) {
            DOM.previewGallery.innerHTML = '';
        }
        DOM.dropzonePreview.hidden = true;
        DOM.dropzoneEmpty.hidden = false;
        DOM.dropzone.classList.remove('has-image');
        DOM.dropzone.classList.remove('is-dragover');

        // 4. Disable Borrar & 5 Mode Buttons
        DOM.btnBorrar.disabled = true;
        setModeButtonsDisabled(true);

        // 5. Reset Status Indicator
        DOM.stateStatusIndicator.textContent = 'Sin foto cargada';
        DOM.stateStatusIndicator.classList.remove('has-image');

        // 6. Reset Results Area
        DOM.loadingState.hidden = true;
        DOM.promptCard.hidden = true;
        DOM.environmentContainer.hidden = true;
        DOM.viewsContainer.hidden = true;
        DOM.negativePromptContainer.hidden = true;
        DOM.analysisContainer.hidden = true;
        DOM.resultsEmpty.hidden = false;

        // 7. Clear Generated Content
        DOM.masterPromptText.textContent = '';
        DOM.charWordCount.textContent = '0 caracteres · 0 palabras';
        if (DOM.viewsAccordion) DOM.viewsAccordion.innerHTML = '';
        if (DOM.analysisGrid) DOM.analysisGrid.innerHTML = '';

        hideNotification();
    }

    function setModeButtonsDisabled(disabled) {
        DOM.modeButtons.forEach(btn => {
            btn.disabled = disabled;
            if (disabled) {
                btn.classList.remove('is-active-generating');
            }
        });
    }

    // --------------------------------------------------------------------------
    // The 5 Generation Modes & API Communication (AC 4)
    // --------------------------------------------------------------------------

    function initModeButtons() {
        DOM.modeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const mode = btn.getAttribute('data-mode');
                handleGeneratePrompt(mode, btn);
            });
        });
    }

    async function handleGeneratePrompt(mode, triggeredButton) {
        // Guard check: Must have an image loaded
        if (state.currentFiles.length === 0) {
            showNotification("Por favor, arrastra al menos una foto del mueble primero.", 'warning');
            return;
        }

        // Guard check: Mode must be valid
        if (!ALLOWED_MODES.includes(mode)) {
            showNotification(`Modo '${mode}' no reconocido.`, 'error');
            return;
        }

        // Prevent concurrent requests
        if (state.isGenerating) return;

        state.isGenerating = true;
        state.activeMode = mode;
        state.abortController = new AbortController();

        // UI Loading Transition
        setModeButtonsDisabled(true);
        DOM.btnBorrar.disabled = false;
        if (triggeredButton) {
            triggeredButton.classList.add('is-active-generating');
        }

        DOM.resultsEmpty.hidden = true;
        DOM.promptCard.hidden = true;
        DOM.loadingState.hidden = false;

        // Contextual loading message
        const loadingMessages = {
            "solo mueble": "Aislando el mueble digitalmente y generando prompt con fondo blanco puro #FFFFFF...",
            "vistas": "Muestreando escenario arquitectónico dinámico (R3) y calculando 5 perspectivas ortogonales...",
            "entorno": "Ubicando el mueble en interiorismo arquitectónico editorial f/2.8 con Gemini AI...",
            "vistas + tela y madera": "Deconstruyendo texturas textiles y vetas de madera a través de 5 perspectivas...",
            "vistas + tela": "Enfocando análisis en tapicería y drapeado preservando patas de madera..."
        };
        DOM.loadingDesc.textContent = loadingMessages[mode] || "Analizando fotografía con Gemini AI...";

        // Prepare multipart form data payload
        const formData = new FormData();
        state.currentFiles.forEach(file => {
            formData.append('image', file, file.name);
        });
        formData.append('mode', mode);

        const notesVal = DOM.userNotes ? DOM.userNotes.value.trim() : '';
        if (notesVal) {
            formData.append('notes', notesVal);
        }

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                body: formData,
                signal: state.abortController.signal
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                const errorMsg = data.error || `Error del servidor (${response.status})`;
                showNotification(errorMsg, 'error', 9000);
                DOM.loadingState.hidden = true;
                if (!state.lastResult) {
                    DOM.resultsEmpty.hidden = false;
                } else {
                    DOM.promptCard.hidden = false;
                }
                return;
            }

            // Success: Render Prompt & Metadata
            state.lastResult = data;
            renderPromptResult(data);

        } catch (err) {
            if (err.name === 'AbortError') {
                // Request cancelled by user clicking Borrar
                return;
            }
            console.error("Error en solicitud /api/generate:", err);
            showNotification(
                "Error de conexión con el servidor. Verifique su red y asegúrese de que el backend esté ejecutándose.",
                'error'
            );
            DOM.loadingState.hidden = true;
            DOM.resultsEmpty.hidden = false;
        } finally {
            state.isGenerating = false;
            const hasImage = state.currentFiles.length > 0;
            setModeButtonsDisabled(!hasImage);
            DOM.btnBorrar.disabled = !hasImage;
            if (triggeredButton) {
                triggeredButton.classList.remove('is-active-generating');
            }
        }
    }

    // --------------------------------------------------------------------------
    // Result Rendering
    // --------------------------------------------------------------------------

    function renderPromptResult(data) {
        DOM.loadingState.hidden = true;
        DOM.resultsEmpty.hidden = true;
        DOM.promptCard.hidden = false;

        // Mode & Model Badges
        DOM.badgeActiveMode.textContent = `Modo: ${data.mode || state.activeMode}`;
        DOM.badgeModelUsed.textContent = data.model_used || 'gemini-2.5-pro';

        // Master Prompt
        const promptText = data.prompt || data.master_prompt || '';
        DOM.masterPromptText.textContent = promptText;

        const charCount = promptText.length;
        const wordCount = countWords(promptText);
        DOM.charWordCount.textContent = `${charCount} caracteres · ${wordCount} palabras`;

        // Reset Copy Button Feedback
        resetCopyButton();

        // Dynamic Environment (Requirement R3)
        if (data.environment && typeof data.environment === 'object') {
            const env = data.environment;
            DOM.envStyleVal.textContent = env.style || '—';
            DOM.envLocationVal.textContent = env.location || '—';
            DOM.envLightingVal.textContent = env.lighting || '—';
            DOM.envPaletteVal.textContent = env.palette || '—';
            DOM.environmentContainer.hidden = false;
        } else {
            DOM.environmentContainer.hidden = true;
        }

        // View Prompts (vistas modes)
        if (data.view_prompts && typeof data.view_prompts === 'object') {
            renderViewPromptsAccordion(data.view_prompts);
            DOM.viewsContainer.hidden = false;
        } else {
            DOM.viewsContainer.hidden = true;
        }

        // Negative Prompt
        if (data.negative_prompt && data.negative_prompt.trim()) {
            DOM.negativePromptText.textContent = data.negative_prompt;
            DOM.negativePromptContainer.hidden = false;
        } else {
            DOM.negativePromptContainer.hidden = true;
        }

        // Furniture Deconstruction Analysis
        if (data.analysis && typeof data.analysis === 'object') {
            renderAnalysisGrid(data.analysis);
            DOM.analysisContainer.hidden = false;
        } else {
            DOM.analysisContainer.hidden = true;
        }

        // Scroll to result on smaller screens
        if (window.innerWidth < 1024) {
            DOM.promptCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    const VIEW_LABELS = {
        vista_frente_0deg: "Vista Frontal (0°)",
        vista_lateral_90deg: "Vista Lateral (90°)",
        vista_3_4_izquierda: "Vista Isométrica 3/4",
        vista_desde_arriba: "Vista Cenital (Desde arriba)",
        vista_3_4_posterior: "Vista Posterior 3/4"
    };

    function renderViewPromptsAccordion(viewPrompts) {
        DOM.viewsAccordion.innerHTML = '';

        Object.entries(viewPrompts).forEach(([key, viewText]) => {
            const label = VIEW_LABELS[key] || key.replace(/_/g, ' ');

            const item = document.createElement('div');
            item.className = 'view-item';

            const header = document.createElement('div');
            header.className = 'view-header';

            const titleSpan = document.createElement('span');
            titleSpan.textContent = label;

            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'view-btn-copy';
            copyBtn.textContent = 'Copiar vista';
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                copyTextToClipboard(viewText, copyBtn, '¡Copiado!');
            });

            header.appendChild(titleSpan);
            header.appendChild(copyBtn);

            const body = document.createElement('div');
            body.className = 'view-body';
            body.textContent = viewText;

            item.appendChild(header);
            item.appendChild(body);
            DOM.viewsAccordion.appendChild(item);
        });
    }

    const ANALYSIS_LABELS = {
        furniture_type: "Tipo de Mueble",
        geometry_topology: "Geometría y Topología",
        color_palette: "Paleta Cromática",
        materials_texture: "Materiales y Textura",
        lighting_optics: "Iluminación y Óptica"
    };

    function renderAnalysisGrid(analysis) {
        DOM.analysisGrid.innerHTML = '';

        Object.entries(analysis).forEach(([key, val]) => {
            if (!val) return;
            const label = ANALYSIS_LABELS[key] || key.replace(/_/g, ' ');

            const item = document.createElement('div');
            item.className = 'analysis-item';

            const keyEl = document.createElement('span');
            keyEl.className = 'analysis-key';
            keyEl.textContent = label;

            const valEl = document.createElement('span');
            valEl.className = 'analysis-val';
            valEl.textContent = String(val);

            item.appendChild(keyEl);
            item.appendChild(valEl);
            DOM.analysisGrid.appendChild(item);
        });
    }

    // --------------------------------------------------------------------------
    // Clipboard Actions (Copy with Visual Feedback)
    // --------------------------------------------------------------------------

    function initClipboard() {
        if (!DOM.btnCopiar) return;

        DOM.btnCopiar.addEventListener('click', () => {
            const textToCopy = DOM.masterPromptText.textContent;
            if (!textToCopy) return;

            copyTextToClipboard(textToCopy, DOM.btnCopiar, '¡Copiado!', true);
        });
    }

    function resetCopyButton() {
        if (!DOM.btnCopiar) return;
        DOM.btnCopiar.classList.remove('is-copied');
        if (DOM.copyBtnText) DOM.copyBtnText.textContent = 'Copiar prompt';
        if (DOM.iconCopy) DOM.iconCopy.hidden = false;
        if (DOM.iconCheck) DOM.iconCheck.hidden = true;
    }

    async function copyTextToClipboard(text, targetButton, feedbackText = '¡Copiado!', isMasterBtn = false) {
        let success = false;

        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                success = true;
            } catch (err) {
                console.warn("navigator.clipboard falló, intentando fallback execCommand:", err);
            }
        }

        // Fallback using temporary textarea
        if (!success) {
            try {
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                success = document.execCommand('copy');
                document.body.removeChild(textArea);
            } catch (fallbackErr) {
                console.error("Fallback execCommand falló:", fallbackErr);
            }
        }

        if (success) {
            if (isMasterBtn) {
                targetButton.classList.add('is-copied');
                if (DOM.copyBtnText) DOM.copyBtnText.textContent = feedbackText;
                if (DOM.iconCopy) DOM.iconCopy.hidden = true;
                if (DOM.iconCheck) DOM.iconCheck.hidden = false;

                if (window._copyTimeout) clearTimeout(window._copyTimeout);
                window._copyTimeout = setTimeout(() => {
                    resetCopyButton();
                }, 2500);
            } else {
                const originalText = targetButton.textContent;
                targetButton.textContent = feedbackText;
                targetButton.style.borderColor = 'var(--accent-emerald)';
                targetButton.style.color = 'var(--accent-emerald)';
                setTimeout(() => {
                    targetButton.textContent = originalText;
                    targetButton.style.borderColor = '';
                    targetButton.style.color = '';
                }, 2000);
            }
        } else {
            showNotification("No se pudo copiar automáticamente. Por favor, selecciona el texto y copia con Ctrl+C.", 'warning');
        }
    }

    // --------------------------------------------------------------------------
    // Initializer
    // --------------------------------------------------------------------------

    function init() {
        initDragAndDrop();
        initModeButtons();
        initClipboard();

        // Borrar Button
        if (DOM.btnBorrar) {
            DOM.btnBorrar.addEventListener('click', resetApplicationState);
        }

        // Notification Close Button
        if (DOM.btnNotificationClose) {
            DOM.btnNotificationClose.addEventListener('click', hideNotification);
        }

        // Initial State Reset
        resetApplicationState();
    }

    // Bootstrap once DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
