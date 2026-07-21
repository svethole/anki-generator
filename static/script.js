document.addEventListener('DOMContentLoaded', function() {
    // ==================== DOM-ELEMENTE ====================
    const startBtn = document.getElementById('start-btn');
    const sourceText = document.getElementById('source-text');
    const modeSelect = document.getElementById('mode');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultsContainer = document.getElementById('results-container');
    const resultsBody = document.getElementById('results-body');
    const cardCount = document.getElementById('card-count');
    const downloadBtn = document.getElementById('download-btn');
    const resetBtn = document.getElementById('reset-btn');
    const historyList = document.getElementById('history-list');
    const historyEmpty = document.getElementById('history-empty');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar');
    const sidebarContent = document.getElementById('sidebar-content');
    const settingsBtn = document.getElementById('settings-btn');
    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsForm = document.getElementById('settings-form');
    const closeSettingsBtn = document.querySelector('.close-btn');
    const apiStatusText = document.getElementById('api-status-text');
    const apiStatusDot = document.querySelector('.status-dot');
    const temperatureSlider = document.getElementById('temperature');
    const temperatureValue = document.getElementById('temperature-value');

    // ==================== GLOBALE VARIABLEN ====================
    let eventSource = null;
    let currentCards = [];
    let currentCsvData = '';
    let currentSourceText = '';
    let isProcessing = false;
    let lastCardCount = 0;
    let currentRequestId = null;

    // ==================== KONFIGURATION ====================
    function loadConfig() {
        const config = {
            apiKey: localStorage.getItem('anki_api_key') || '',
            model: localStorage.getItem('anki_model') || 'gpt-4o-mini',
            temperature: parseFloat(localStorage.getItem('anki_temperature')) || 0.7,
            maxTokens: parseInt(localStorage.getItem('anki_max_tokens')) || 500,
            csvDelimiter: localStorage.getItem('anki_csv_delimiter') || ';',
            saveSourceText: localStorage.getItem('anki_save_source') !== 'false',
            autoOpenSidebar: localStorage.getItem('anki_auto_sidebar') !== 'false'
        };
        return config;
    }

    function saveConfig(config) {
        localStorage.setItem('anki_api_key', config.apiKey);
        localStorage.setItem('anki_model', config.model);
        localStorage.setItem('anki_temperature', config.temperature.toString());
        localStorage.setItem('anki_max_tokens', config.maxTokens.toString());
        localStorage.setItem('anki_csv_delimiter', config.csvDelimiter);
        localStorage.setItem('anki_save_source', config.saveSourceText.toString());
        localStorage.setItem('anki_auto_sidebar', config.autoOpenSidebar.toString());
    }

    function loadConfigToUI() {
        const config = loadConfig();
        document.getElementById('api-key').value = config.apiKey;
        document.getElementById('model-name').value = config.model;
        document.getElementById('temperature').value = config.temperature;
        document.getElementById('temperature-value').textContent = config.temperature;
        document.getElementById('max-tokens').value = config.maxTokens;
        document.getElementById('csv-delimiter').value = config.csvDelimiter;
        document.getElementById('save-source-text').checked = config.saveSourceText;
        document.getElementById('auto-open-sidebar').checked = config.autoOpenSidebar;

        updateApiStatus(config.apiKey);

        if (config.autoOpenSidebar) {
            sidebarContent.style.display = 'block';
            toggleSidebarBtn.textContent = '📚 Historie verbergen';
            loadHistory();
        }
    }

    function updateApiStatus(apiKey) {
        if (apiKey && apiKey.startsWith('sk-')) {
            apiStatusDot.className = 'status-dot status-configured';
            apiStatusText.textContent = 'API-Key konfiguriert ✅';
        } else if (apiKey) {
            apiStatusDot.className = 'status-dot status-error';
            apiStatusText.textContent = 'Ungültiger API-Key ⚠️';
        } else {
            apiStatusDot.className = 'status-dot status-unknown';
            apiStatusText.textContent = 'API-Key nicht konfiguriert ⚙️';
        }
    }

    // ==================== STATUS-MELDUNGEN ====================
    function showStatusMessage(message, type) {
        const oldStatus = document.getElementById('status-message');
        if (oldStatus) {
            oldStatus.remove();
        }

        const statusDiv = document.createElement('div');
        statusDiv.id = 'status-message';
        statusDiv.className = type;
        statusDiv.textContent = message;

        const inputSection = document.querySelector('.input-section');
        inputSection.parentNode.insertBefore(statusDiv, inputSection.nextSibling);

        if (type === 'success') {
            setTimeout(() => {
                const msg = document.getElementById('status-message');
                if (msg) {
                    msg.style.opacity = '0';
                    msg.style.transition = 'opacity 0.5s';
                    setTimeout(() => msg.remove(), 500);
                }
            }, 10000);
        }
    }

    // ==================== KARTEN ANZEIGEN ====================
    function displayCards(cards) {
        currentCards = cards;
        resultsBody.innerHTML = '';
        cards.forEach((card) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${card.front}</td>
                <td>${card.back}</td>
            `;
            resultsBody.appendChild(row);
        });
        cardCount.textContent = `📚 ${cards.length} Karteikarten generiert`;
        resultsContainer.style.display = 'block';
    }

    // ==================== OVERLAY (EINSTELLUNGEN) ====================
    function openSettings() {
        loadConfigToUI();
        settingsOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    window.closeSettings = function() {
        settingsOverlay.classList.remove('active');
        document.body.style.overflow = '';
    };

    settingsBtn.addEventListener('click', openSettings);
    closeSettingsBtn.addEventListener('click', closeSettings);

    settingsOverlay.addEventListener('click', function(e) {
        if (e.target === this) {
            closeSettings();
        }
    });

    temperatureSlider.addEventListener('input', function() {
        temperatureValue.textContent = this.value;
    });

    settingsForm.addEventListener('submit', function(e) {
        e.preventDefault();

        const config = {
            apiKey: document.getElementById('api-key').value.trim(),
            model: document.getElementById('model-name').value,
            temperature: parseFloat(document.getElementById('temperature').value),
            maxTokens: parseInt(document.getElementById('max-tokens').value),
            csvDelimiter: document.getElementById('csv-delimiter').value,
            saveSourceText: document.getElementById('save-source-text').checked,
            autoOpenSidebar: document.getElementById('auto-open-sidebar').checked
        };

        if (!config.apiKey) {
            showSettingsStatus('Bitte gib einen API-Key ein.', 'error');
            return;
        }

        if (!config.apiKey.startsWith('sk-')) {
            showSettingsStatus('Der API-Key sollte mit "sk-" beginnen.', 'error');
            return;
        }

        saveConfig(config);
        updateApiStatus(config.apiKey);
        showSettingsStatus('✅ Einstellungen wurden gespeichert!', 'success');

        if (config.autoOpenSidebar) {
            sidebarContent.style.display = 'block';
            toggleSidebarBtn.textContent = '📚 Historie verbergen';
            loadHistory();
        } else {
            sidebarContent.style.display = 'none';
            toggleSidebarBtn.textContent = '📚 Historie';
        }

        setTimeout(closeSettings, 1500);
    });

    function showSettingsStatus(message, type) {
        const statusEl = document.getElementById('settings-status-text');
        const container = statusEl.parentElement;
        container.className = 'settings-status ' + type;
        statusEl.textContent = message;
    }

    // ==================== HISTORIE ====================
    function loadHistory() {
        fetch('/history')
            .then(response => response.json())
            .then(data => {
                historyList.innerHTML = '';
                if (data.length === 0) {
                    historyEmpty.style.display = 'block';
                    return;
                }
                historyEmpty.style.display = 'none';

                data.forEach(entry => {
                    const li = document.createElement('li');
                    li.innerHTML = `
                        <div class="history-item-info" data-id="${entry.id}">
                            <div class="timestamp">${new Date(entry.timestamp).toLocaleString()}</div>
                            <div class="count">📝 ${entry.card_count} Karten</div>
                        </div>
                        <button class="delete-btn" data-id="${entry.id}">🗑️</button>
                    `;

                    li.querySelector('.history-item-info').addEventListener('click', function() {
                        const id = this.dataset.id;
                        loadHistoryEntry(id);
                    });

                    li.querySelector('.delete-btn').addEventListener('click', function(e) {
                        e.stopPropagation();
                        const id = this.dataset.id;
                        if (confirm('Diesen Eintrag wirklich löschen?')) {
                            fetch(`/history/${id}`, { method: 'DELETE' })
                                .then(() => {
                                    loadHistory();
                                    // Wenn der gelöschte Eintrag gerade angezeigt wurde, zurücksetzen
                                    if (currentSourceText === sourceText.value) {
                                        downloadBtn.style.display = 'none';
                                        resetBtn.style.display = 'none';
                                        document.querySelector('.input-section').classList.remove('success');
                                        const statusMsg = document.getElementById('status-message');
                                        if (statusMsg) statusMsg.remove();
                                    }
                                });
                        }
                    });

                    historyList.appendChild(li);
                });
            })
            .catch(error => {
                console.error('Fehler beim Laden der Historie:', error);
            });
    }

    // ==================== HISTORISCHEN EINTRAG LADEN ====================
    function loadHistoryEntry(id) {
        showStatusMessage('⏳ Lade Eintrag...', 'info');

        fetch(`/history/${id}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP-Fehler: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                sourceText.value = data.source_text;
                currentCsvData = data.csv_data;

                displayCards(data.cards);
                downloadBtn.style.display = 'inline-block';
                resetBtn.style.display = 'inline-block';

                progressContainer.style.display = 'block';
                progressBar.style.width = '100%';
                progressText.textContent = '100% (abgeschlossen)';

                const date = new Date(data.timestamp || Date.now());
                showStatusMessage(`✅ Eintrag vom ${date.toLocaleString()} geladen (${data.cards.length} Karten)`, 'success');
                document.querySelector('.input-section').classList.add('success');

                resultsContainer.scrollIntoView({ behavior: 'smooth' });

                startBtn.disabled = false;
                startBtn.textContent = '🚀 Karten generieren';
                isProcessing = false;
            })
            .catch(error => {
                console.error('Fehler beim Laden des History-Eintrags:', error);
                showStatusMessage('❌ Fehler beim Laden: ' + error.message, 'error');
            });
    }

    // ==================== SEITENLEISTE TOGGLEN ====================
    toggleSidebarBtn.addEventListener('click', function() {
        if (sidebarContent.style.display === 'none') {
            sidebarContent.style.display = 'block';
            toggleSidebarBtn.textContent = '📚 Historie verbergen';
            loadHistory();
        } else {
            sidebarContent.style.display = 'none';
            toggleSidebarBtn.textContent = '📚 Historie';
        }
    });

    // ==================== INTERFACE ZURÜCKSETZEN ====================
    function resetInterface() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        isProcessing = false;
        lastCardCount = 0;

        sourceText.value = '';
        progressContainer.style.display = 'none';
        progressBar.style.width = '0%';
        progressText.textContent = '0%';
        resultsContainer.style.display = 'none';
        resultsBody.innerHTML = '';
        cardCount.textContent = '';
        downloadBtn.style.display = 'none';
        resetBtn.style.display = 'none';
        startBtn.disabled = false;
        startBtn.textContent = '🚀 Karten generieren';

        const statusMsg = document.getElementById('status-message');
        if (statusMsg) {
            statusMsg.remove();
        }

        document.querySelector('.input-section').classList.remove('success');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        sourceText.focus();
    }

    resetBtn.addEventListener('click', resetInterface);

    // ==================== DEBOUNCE-FUNKTION ====================
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // ==================== START-BUTTON ====================
    const debouncedStart = debounce(function() {
        if (isProcessing) {
            console.log('⚠️ Verarbeitung läuft bereits...');
            return;
        }

        const config = loadConfig();

        if (!config.apiKey) {
            alert('⚠️ Bitte konfiguriere zuerst deinen OpenAI API-Key in den Einstellungen (⚙️).');
            openSettings();
            return;
        }

        const text = sourceText.value.trim();
        const mode = modeSelect.value;

        if (!text) {
            alert('Bitte gib einen Text ein.');
            return;
        }

        // Request-ID für Debugging
        const requestId = Date.now().toString() + '_' + Math.random().toString(36).substr(2, 9);
        currentRequestId = requestId;
        console.log(`📨 Sende Request mit ID: ${requestId}`);

        isProcessing = true;
        lastCardCount = 0;

        const oldStatus = document.getElementById('status-message');
        if (oldStatus) {
            oldStatus.remove();
        }

        // UI zurücksetzen
        resultsContainer.style.display = 'none';
        resultsBody.innerHTML = '';
        cardCount.textContent = '';
        downloadBtn.style.display = 'none';
        resetBtn.style.display = 'none';
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.textContent = '0%';
        currentCards = [];
        currentCsvData = '';
        currentSourceText = text;
        startBtn.disabled = true;
        startBtn.textContent = '⏳ Verarbeitung läuft...';

        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        document.querySelector('.input-section').classList.remove('success');

        // Prozess starten
        fetch('/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                mode: mode,
                apiKey: config.apiKey,
                model: config.model,
                temperature: config.temperature,
                maxTokens: config.maxTokens,
                csvDelimiter: config.csvDelimiter,
                requestId: requestId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showStatusMessage('❌ Fehler: ' + data.error, 'error');
                startBtn.disabled = false;
                startBtn.textContent = '🚀 Karten generieren';
                progressContainer.style.display = 'none';
                isProcessing = false;
                return;
            }

            console.log(`✅ Prozess gestartet: ${data.total} Vokabeln`);

            eventSource = new EventSource('/progress');

            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    progressBar.style.width = data.progress + '%';
                    progressText.textContent = data.progress + '%';

                    if (data.cards && data.cards.length > 0 && data.cards.length !== lastCardCount) {
                        displayCards(data.cards);
                        lastCardCount = data.cards.length;
                    }

                    if (data.done) {
                        console.log('✅ Prozess abgeschlossen');
                        if (eventSource) {
                            eventSource.close();
                            eventSource = null;
                        }

                        downloadBtn.style.display = 'inline-block';
                        resetBtn.style.display = 'inline-block';
                        startBtn.disabled = false;
                        startBtn.textContent = '🚀 Karten generieren';
                        isProcessing = false;
                        lastCardCount = 0;

                        showStatusMessage(`✅ ${data.cards ? data.cards.length : 0} Karten erfolgreich generiert!`, 'success');
                        document.querySelector('.input-section').classList.add('success');

                        setTimeout(() => {
                            fetch('/download')
                                .then(response => response.text())
                                .then(csv => {
                                    currentCsvData = csv;
                                    loadHistory();
                                })
                                .catch(err => console.error('Fehler beim CSV-Download:', err));
                        }, 500);
                    }
                } catch (e) {
                    console.error('Fehler beim Verarbeiten der EventSource-Nachricht:', e);
                }
            };

            eventSource.onerror = function(error) {
                console.error('EventSource-Fehler:', error);
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                // Nicht sofort auf isProcessing = false setzen, da der Server noch arbeitet
            };
        })
        .catch(error => {
            console.error('Fehler beim Starten:', error);
            showStatusMessage('❌ Fehler beim Starten: ' + error.message, 'error');
            startBtn.disabled = false;
            startBtn.textContent = '🚀 Karten generieren';
            progressContainer.style.display = 'none';
            isProcessing = false;
        });
    }, 300);

    startBtn.addEventListener('click', debouncedStart);

    // ==================== DOWNLOAD-BUTTON ====================
    downloadBtn.addEventListener('click', function() {
        if (currentCsvData) {
            const blob = new Blob(['\uFEFF' + currentCsvData], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `anki_karten_${new Date().toISOString().slice(0,10)}.csv`;
            link.click();
        } else {
            alert('Keine CSV-Daten verfügbar.');
        }
    });

    // ==================== TEXT-MARKIERUNG ====================
    const textarea = document.getElementById('source-text');
    const tooltip = document.getElementById('selection-tooltip');
    const markBtn = document.getElementById('mark-selection-btn');

    let tooltipTimeout = null;
    let isTooltipVisible = false;
    let currentSelection = '';

    // === 1. Doppelklick auf ein Wort → in Sternchen setzen ===
    textarea.addEventListener('dblclick', function(e) {
        const text = this.value;
        const cursorPos = this.selectionStart;

        // Finde das Wort unter dem Cursor
        const wordStart = text.lastIndexOf(' ', cursorPos - 1) + 1;
        const wordEnd = text.indexOf(' ', cursorPos);
        const end = wordEnd === -1 ? text.length : wordEnd;

        // Extrahiere das Wort (nur Buchstaben und Bindestriche)
        let word = text.substring(wordStart, end).trim();
        if (!word || word.length === 0) return;

        // Prüfe ob es schon in Sternchen ist
        if (word.startsWith('*') && word.endsWith('*')) return;

        // Prüfe ob es ein einzelnes Wort ist (keine Leerzeichen)
        if (word.includes(' ')) return;

        // Ersetze das Wort mit Sternchen
        const before = text.substring(0, wordStart);
        const after = text.substring(end);
        const newText = before + '*' + word + '*' + after;

        this.value = newText;

        // Setze Cursor hinter das markierte Wort
        const newPos = wordStart + word.length + 2;
        this.setSelectionRange(newPos, newPos);

        // Kurze visuelle Rückmeldung
        this.style.transition = 'background 0.2s';
        this.style.background = '#e8f5e9';
        setTimeout(() => {
            this.style.background = '';
        }, 300);

        // Event auslösen, damit der Tooltip aktualisiert wird
        this.dispatchEvent(new Event('input'));
    });

    // === 2. Textauswahl → Tooltip anzeigen ===
    textarea.addEventListener('mouseup', function(e) {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        // Tooltip ausblenden, wenn nichts ausgewählt oder nur Leerzeichen
        if (!selectedText || selectedText.length === 0) {
            hideTooltip();
            return;
        }

        // Prüfe ob die Auswahl innerhalb des Textareas ist
        const isInside = this === document.activeElement || 
                         this.contains(selection.anchorNode);

        if (!isInside) {
            hideTooltip();
            return;
        }

        // Prüfe ob der markierte Text Sternchen enthält (verhindert doppelte Markierung)
        if (selectedText.includes('*')) {
            hideTooltip();
            return;
        }

        // Prüfe ob es ein einzelnes Wort oder ein Satzteil ist
        // Erlaube auch mehrere Wörter (für Phrasen)
        currentSelection = selectedText;

        // Position des Tooltips berechnen
        const rect = this.getBoundingClientRect();
        const selectionRect = selection.getRangeAt(0).getBoundingClientRect();

        // Tooltip über der Auswahl positionieren
        const tooltipX = selectionRect.left + (selectionRect.width / 2);
        const tooltipY = selectionRect.top - 50;

        // Prüfe ob Tooltip außerhalb des Fensters ist
        const tooltipWidth = 200; // geschätzte Breite
        const tooltipHeight = 40; // geschätzte Höhe

        let adjustedY = tooltipY;
        let tooltipClass = '';

        if (tooltipY < 10) {
            // Zu nah am oberen Rand → unterhalb anzeigen
            adjustedY = selectionRect.bottom + 10;
            tooltipClass = 'above';
        }

        if (tooltipX - tooltipWidth/2 < 10) {
            // Zu nah am linken Rand
            tooltip.style.left = '10px';
        } else if (tooltipX + tooltipWidth/2 > window.innerWidth - 10) {
            // Zu nah am rechten Rand
            tooltip.style.left = (window.innerWidth - 10) + 'px';
        } else {
            tooltip.style.left = tooltipX + 'px';
        }

        tooltip.style.top = adjustedY + 'px';
        tooltip.className = 'selection-tooltip' + (tooltipClass ? ' ' + tooltipClass : '');
        tooltip.style.display = 'block';
        isTooltipVisible = true;

        // Tooltip nach 3 Sekunden Inaktivität ausblenden (außer Maus ist drüber)
        clearTimeout(tooltipTimeout);
        tooltipTimeout = setTimeout(() => {
            if (!isTooltipVisible) return;
            // Nur ausblenden, wenn Maus nicht über Tooltip ist
            if (!tooltip.matches(':hover')) {
                hideTooltip();
            }
        }, 3000);
    });

    // === Tooltip sichtbar halten wenn Maus drüber ist ===
    tooltip.addEventListener('mouseenter', function() {
        clearTimeout(tooltipTimeout);
        isTooltipVisible = true;
    });

    tooltip.addEventListener('mouseleave', function() {
        // Tooltip nach kurzer Verzögerung ausblenden
        tooltipTimeout = setTimeout(() => {
            hideTooltip();
        }, 500);
    });

    // === Markierungs-Button ===
    markBtn.addEventListener('click', function(e) {
        e.stopPropagation();

        if (!currentSelection) {
            hideTooltip();
            return;
        }

        // Aktuelle Auswahl im Textarea ersetzen
        const text = textarea.value;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;

        // Prüfe ob die Auswahl noch aktuell ist
        const selectedText = text.substring(start, end);
        if (selectedText !== currentSelection) {
            // Versuche die Auswahl zu finden
            const index = text.indexOf(currentSelection);
            if (index === -1) {
                hideTooltip();
                return;
            }
            // Ersetze an der gefundenen Stelle
            const before = text.substring(0, index);
            const after = text.substring(index + currentSelection.length);
            const newText = before + '*' + currentSelection + '*' + after;
            textarea.value = newText;

            // Setze Cursor hinter die Markierung
            const newPos = index + currentSelection.length + 2;
            textarea.setSelectionRange(newPos, newPos);
        } else {
            // Normale Ersetzung an der aktuellen Auswahl
            const before = text.substring(0, start);
            const after = text.substring(end);
            const newText = before + '*' + currentSelection + '*' + after;
            textarea.value = newText;

            // Setze Cursor hinter die Markierung
            const newPos = start + currentSelection.length + 2;
            textarea.setSelectionRange(newPos, newPos);
        }

        // Event auslösen
        textarea.dispatchEvent(new Event('input'));

        // Tooltip ausblenden
        hideTooltip();

        // Kurze visuelle Rückmeldung
        textarea.style.transition = 'background 0.2s';
        textarea.style.background = '#e8f5e9';
        setTimeout(() => {
            textarea.style.background = '';
        }, 300);
    });

    // === Tooltip ausblenden ===
    function hideTooltip() {
        tooltip.style.display = 'none';
        isTooltipVisible = false;
        clearTimeout(tooltipTimeout);
    }

    // === Tooltip ausblenden bei Klick außerhalb ===
    document.addEventListener('click', function(e) {
        if (!tooltip.contains(e.target) && e.target !== textarea) {
            hideTooltip();
        }
    });

    // === Tooltip ausblenden bei Escape ===
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideTooltip();
        }
    });

    // === Tooltip ausblenden wenn Textarea den Fokus verliert ===
    textarea.addEventListener('blur', function() {
        setTimeout(hideTooltip, 200);
    });

    // === Tastenkürzel: Strg+Shift+M = Markierung in Sternchen setzen ===
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'm' || e.key === 'M')) {
            e.preventDefault();
            if (currentSelection) {
                markBtn.click();
            }
        }
    });

    // === Info in der Statusleiste anzeigen ===
    console.log('📝 Tastenkürzel: Strg+Shift+M markiert den ausgewählten Text als Vokabel');
    
    // ==================== INITIALISIERUNG ====================
    loadConfigToUI();
    console.log('🚀 Anki-Kartengenerator geladen');
});