document.addEventListener('DOMContentLoaded', function() {
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

    let eventSource = null;
    let currentCards = [];
    let currentCsvData = '';
    let currentSourceText = '';

    // === Konfiguration laden ===
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

        // API-Status aktualisieren
        updateApiStatus(config.apiKey);

        // Seitenleiste automatisch öffnen?
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

    // === Overlay öffnen/schließen ===
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

    // Overlay schließen bei Klick auf Hintergrund
    settingsOverlay.addEventListener('click', function(e) {
        if (e.target === this) {
            closeSettings();
        }
    });

    // Temperatur-Slider
    temperatureSlider.addEventListener('input', function() {
        temperatureValue.textContent = this.value;
    });

    // Settings speichern
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

        // Seitenleiste nach Einstellung aktualisieren
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

    // === Historie laden ===
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
                <div class="preview">${entry.preview || ''}</div>
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
                        .then(() => loadHistory());
                    }
                });

                historyList.appendChild(li);
            });
        });
    }

    // === Historischen Eintrag laden ===
    function loadHistoryEntry(id) {
        fetch(`/history/${id}`)
        .then(response => response.json())
        .then(data => {
            sourceText.value = data.source_text;
            currentCsvData = data.csv_data;

            displayCards(data.cards);
            downloadBtn.style.display = 'block';

            progressContainer.style.display = 'block';
            progressBar.style.width = '100%';
            progressText.textContent = '100% (abgeschlossen)';

            resultsContainer.scrollIntoView({ behavior: 'smooth' });
        });
    }

    // === Karten anzeigen ===
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

    // === Start-Button ===
    startBtn.addEventListener('click', function() {
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

        // UI zurücksetzen
        resultsContainer.style.display = 'none';
        downloadBtn.style.display = 'none';
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
        }

        // Prozess starten mit Konfiguration
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
                csvDelimiter: config.csvDelimiter
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert('Fehler: ' + data.error);
                startBtn.disabled = false;
                startBtn.textContent = '🚀 Karten generieren';
                return;
            }

            eventSource = new EventSource('/progress');
            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                progressBar.style.width = data.progress + '%';
                progressText.textContent = data.progress + '%';

                if (data.cards) {
                    displayCards(data.cards);
                }

                if (data.done) {
                    eventSource.close();
                    downloadBtn.style.display = 'block';
                    startBtn.disabled = false;
                    startBtn.textContent = '🚀 Karten generieren';

                    setTimeout(() => {
                        fetch('/download')
                        .then(response => response.text())
                        .then(csv => {
                            currentCsvData = csv;
                            loadHistory();
                        });
                    }, 500);
                }
            };
        })
        .catch(error => {
            alert('Fehler beim Starten: ' + error.message);
            startBtn.disabled = false;
            startBtn.textContent = '🚀 Karten generieren';
        });
    });

    // === Download-Button ===
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

    // === Seitenleiste toggeln ===
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

    // === Initialisierung ===
    loadConfigToUI();
});