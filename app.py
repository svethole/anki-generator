import os
import json
import sqlite3
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS
from openai import OpenAI
import io
import csv

app = Flask(__name__)
CORS(app)

# OpenAI-Client initialisieren (API-Key muss in Umgebungsvariable oder .env)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Datenbank initialisieren
DB_PATH = "anki_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source_text TEXT NOT NULL,
            csv_data TEXT NOT NULL,
            card_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Globale Variable für laufenden Prozess
current_process = {
    "running": False,
    "progress": 0,
    "cards": [],
    "source_text": "",
    "csv_data": "",
    "card_count": 0
}

def extract_words_from_text(text, mode):
    """Extrahiert Vokabeln aus dem Quelltext."""
    if mode == "fluent":
        # Fließtext: Wörter zwischen * * extrahieren
        import re
        return re.findall(r'\*(.*?)\*', text)
    else:
        # Vokabelliste: jede nicht-leere Zeile ist eine Vokabel
        return [line.strip() for line in text.split('\n') if line.strip()]

def generate_card_with_ai(word, context_sentence=None):
    """Generiert eine Karteikarte mit GPT-4o-mini."""
    if context_sentence:
        prompt = f"""
        Erstelle eine Anki-Karteikarte für die italienische Vokabel "{word}" im Kontext des Satzes:
        "{context_sentence}"

        Gib die Antwort im folgenden JSON-Format:
        {{
            "sentence": "Der vollständige Satz mit der fett markierten Vokabel (in ** doppelten Sternchen **)",
            "translation": "Deutsche Übersetzung der Vokabel",
            "meaning": "Bedeutung auf Italienisch (kurze Erklärung)",
            "etymology": "Etymologie des Wortes (auf Italienisch, kurz)",
            "inflection": "Flexionen (z.B. Konjugation oder Deklination, auf Italienisch)",
            "notes": "Weitere Anmerkungen (auf Italienisch)"
        }}
        """
    else:
        prompt = f"""
        Erstelle eine Anki-Karteikarte für die italienische Vokabel "{word}".
        Erstelle auch einen Beispielsatz, der die Vokabel enthält.

        Gib die Antwort im folgenden JSON-Format:
        {{
            "sentence": "Der Beispielsatz mit der fett markierten Vokabel (in ** doppelten Sternchen **)",
            "translation": "Deutsche Übersetzung der Vokabel",
            "meaning": "Bedeutung auf Italienisch (kurze Erklärung)",
            "etymology": "Etymologie des Wortes (auf Italienisch, kurz)",
            "inflection": "Flexionen (z.B. Konjugation oder Deklination, auf Italienisch)",
            "notes": "Weitere Anmerkungen (auf Italienisch)"
        }}
        """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher Assistent für Italienisch-Lernende. Antworte immer im gültigen JSON-Format."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )

    # JSON aus der Antwort extrahieren
    import re
    content = response.choices[0].message.content
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    else:
        raise ValueError("Kein gültiges JSON in der Antwort gefunden")

def process_cards(words, mode, client, model, temperature, max_tokens, csv_delimiter):
    global current_process

    current_process["running"] = True
    current_process["progress"] = 0
    current_process["cards"] = []
    current_process["card_count"] = len(words)

    source_text = current_process["source_text"]
    csv_rows = []

    for i, word in enumerate(words):
        try:
            # ... KI-Aufruf mit den Parametern ...
            response = client.chat.completions.create(
                model=model,
                messages=[...],
                temperature=temperature,
                max_tokens=max_tokens
            )

            if mode == "fluent":
                # Bei Fließtext müssen wir den Satz finden, der das Wort enthält
                # Einfache Implementierung: Suche den Satz mit dem Wort
                sentences = source_text.split('.')
                context = None
                for sent in sentences:
                    if word in sent:
                        context = sent.strip() + "."
                        break
                card_data = generate_card_with_ai(word, context)
            else:
                card_data = generate_card_with_ai(word)

            # HTML-fetten Text für Anki vorbereiten
            front = card_data["sentence"].replace("**", "<b>").replace("**", "</b>", 1)
            # Der zweite ** wird durch </b> ersetzt (Anki unterstützt HTML)
            # Aber eigentlich ist der doppelte ** für Markdown, wir müssen es anpassen
            front = front.replace("**", "<b>", 1)
            front = front.replace("**", "</b>", 1)

            back = f"""
            {card_data["sentence"]}<br><br>
            <b>Übersetzung:</b> {card_data["translation"]}<br>
            <b>Bedeutung:</b> {card_data["meaning"]}<br>
            <b>Etymologie:</b> {card_data["etymology"]}<br>
            <b>Flexionen:</b> {card_data["inflection"]}<br>
            <b>Anmerkungen:</b> {card_data["notes"]}
            """

            # CSV-Zeile vorbereiten (Semikolon als Trennzeichen)
            # Ersetze Semikolons in Texten
            front_clean = front.replace(";", ",")
            back_clean = back.replace(";", ",")

            csv_rows.append([front_clean, back_clean])
            current_process["cards"].append({"front": front, "back": back})

            # Fortschritt aktualisieren
            current_process["progress"] = int(((i + 1) / len(words)) * 100)

        except Exception as e:
            print(f"Fehler bei Vokabel {word}: {e}")
            # Fehlerhafte Karte überspringen

    # CSV-Daten erstellen
    output = io.StringIO()
    writer = csv.writer(output, delimiter=csv_delimiter, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Front", "Back"])
    writer.writerows(csv_rows)

    current_process["csv_data"] = output.getvalue()
    current_process["card_count"] = len(csv_rows)
    current_process["running"] = False
    current_process["progress"] = 100

    # In Datenbank speichern
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (timestamp, source_text, csv_data, card_count) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), source_text, current_process["csv_data"], len(csv_rows))
    )
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

# In der start_processing-Funktion die Konfiguration aus dem Request holen
@app.route('/start', methods=['POST'])
def start_processing():
    global current_process

    data = request.json
    text = data.get('text', '')
    mode = data.get('mode', 'fluent')
    api_key = data.get('apiKey', '')
    model = data.get('model', 'gpt-4o-mini')
    temperature = data.get('temperature', 0.7)
    max_tokens = data.get('maxTokens', 500)
    csv_delimiter = data.get('csvDelimiter', ';')

    if not text:
        return jsonify({"error": "Kein Text eingegeben"}), 400

    if not api_key:
        return jsonify({"error": "Kein API-Key angegeben"}), 400

    # OpenAI-Client mit dem übergebenen Key initialisieren
    client = OpenAI(api_key=api_key)

    # Wörter extrahieren
    words = extract_words_from_text(text, mode)
    if not words:
        return jsonify({"error": "Keine Vokabeln gefunden"}), 400

    # Prozess starten mit der Konfiguration
    current_process["source_text"] = text
    thread = threading.Thread(
        target=process_cards,
        args=(words, mode, client, model, temperature, max_tokens, csv_delimiter)
    )
    thread.start()

    return jsonify({"message": "Verarbeitung gestartet", "total": len(words)})

@app.route('/progress')
def progress():
    def generate():
        while True:
            if current_process["running"] or current_process["progress"] < 100:
                # Sende Fortschritt und aktuelle Karten
                yield f"data: {json.dumps({'progress': current_process['progress'], 'cards': current_process['cards']})}\n\n"
                time.sleep(0.5)
            else:
                # Finale Daten senden
                yield f"data: {json.dumps({'progress': 100, 'cards': current_process['cards'], 'done': True})}\n\n"
                break

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@app.route('/download')
def download():
    if not current_process["csv_data"]:
        return jsonify({"error": "Keine CSV-Daten verfügbar"}), 404

    return Response(
        current_process["csv_data"],
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=anki_karten.csv"}
    )

@app.route('/history')
def get_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, card_count FROM history ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()

    return jsonify([{"id": row[0], "timestamp": row[1], "card_count": row[2]} for row in rows])

@app.route('/history/<int:entry_id>')
def get_history_entry(entry_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT source_text, csv_data, card_count FROM history WHERE id = ?", (entry_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Eintrag nicht gefunden"}), 404

    # CSV-Daten in Karten umwandeln
    cards = []
    csv_reader = csv.reader(io.StringIO(row[1]), delimiter=';')
    next(csv_reader)  # Header überspringen
    for front, back in csv_reader:
        cards.append({"front": front, "back": back})

    return jsonify({
        "source_text": row[0],
        "cards": cards,
        "card_count": row[2],
        "csv_data": row[1]
    })

@app.route('/history/<int:entry_id>', methods=['DELETE'])
def delete_history_entry(entry_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Eintrag gelöscht"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)