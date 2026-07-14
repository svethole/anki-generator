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
import re

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

def fix_broken_json(json_str, word):
    """Versucht, ein kaputtes JSON zu reparieren."""
    try:
        # Entferne alle ... und andere Platzhalter
        json_str = re.sub(r'\.\.\.', '', json_str)
        
        # Entferne Kommentare (falls vorhanden)
        json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
        
        # Entferne nachfolgende Kommas
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)
        
        return json.loads(json_str)
    except:
        # Wenn alles fehlschlägt, Fallback-Karte
        return {
            "sentence": f"**{word}** (Fehler bei der JSON-Parsing)",
            "translation": "Fehler bei der Übersetzung",
            "meaning": "Fehler bei der Bedeutung",
            "etymology": "Fehler bei der Etymologie",
            "inflection": "Fehler bei den Flexionen",
            "notes": "Bitte manuell korrigieren"
        }

def parse_text_response(content, word):
    """Parsed eine Text-Antwort, wenn kein JSON gefunden wurde."""
    lines = content.strip().split('\n')
    result = {
        "sentence": f"**{word}** (Text konnte nicht geparst werden)",
        "translation": "",
        "meaning": "",
        "etymology": "",
        "inflection": "",
        "notes": ""
    }
    
    current_key = None
    for line in lines:
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            if 'satz' in key or 'sentence' in key:
                result["sentence"] = value.strip()
            elif 'übersetzung' in key or 'translation' in key:
                result["translation"] = value.strip()
            elif 'bedeutung' in key or 'meaning' in key:
                result["meaning"] = value.strip()
            elif 'etymologie' in key or 'etymology' in key:
                result["etymology"] = value.strip()
            elif 'flexion' in key or 'inflection' in key:
                result["inflection"] = value.strip()
            elif 'anmerkung' in key or 'notes' in key:
                result["notes"] = value.strip()
    
    return result

def extract_words_from_text(text, mode):
    """Extrahiert Vokabeln aus dem Quelltext."""
    if mode == "fluent":
        # Fließtext: Wörter zwischen * * extrahieren
        import re
        return re.findall(r'\*(.*?)\*', text)
    else:
        # Vokabelliste: jede nicht-leere Zeile ist eine Vokabel
        return [line.strip() for line in text.split('\n') if line.strip()]

def generate_card_with_ai(word, context_sentence=None, client=None, model="gpt-4o-mini", temperature=0.7, max_tokens=500):
    """Generiert eine Karteikarte mit KI, mit robustem Error-Handling."""
    try:
        # Prompt erstellen
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
            model=model,
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent für Italienisch-Lernende. Antworte ausschließlich im gültigen JSON-Format ohne Markdown. Verwende keine Auslassungspunkte (...). Jedes Feld muss einen vollständigen Text enthalten."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        content = response.choices[0].message.content
        
        # Versuche JSON zu extrahieren
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            # Entferne alle ... (Ellipsis)
            json_str = re.sub(r'\.\.\.', '', json_str)
            # Entferne nachfolgende Kommas
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*\]', ']', json_str)
            
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Fallback: Versuche JSON zu reparieren
                # Entferne alles außer gültigen JSON-Zeichen
                json_str = re.sub(r'[^\{\}\[\]\,\"\:\w\s\-\.\*]', '', json_str)
                return json.loads(json_str)
        
        # Fallback: Text-basierte Antwort parsen
        result = {
            "sentence": f"**{word}** (Fehler bei der JSON-Generierung)",
            "translation": "Fehler bei der Übersetzung",
            "meaning": "Fehler bei der Bedeutung",
            "etymology": "Fehler bei der Etymologie",
            "inflection": "Fehler bei den Flexionen",
            "notes": "Bitte manuell korrigieren"
        }
        return result
        
    except Exception as e:
        print(f"Fehler bei Vokabel {word}: {str(e)}")
        return {
            "sentence": f"**{word}** (Fehler: {str(e)[:50]})",
            "translation": "Fehler bei der Übersetzung",
            "meaning": "Fehler bei der Bedeutung",
            "etymology": "Fehler bei der Etymologie",
            "inflection": "Fehler bei den Flexionen",
            "notes": "Bitte manuell korrigieren"
        }

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
            # Kontext finden (bei Fließtext)
            context = None
            if mode == "fluent":
                sentences = source_text.split('.')
                for sent in sentences:
                    if word in sent:
                        context = sent.strip() + "."
                        break
            
            # Karte mit KI generieren
            card_data = generate_card_with_ai(
                word,
                context_sentence=context,
                client=client,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Felder für CSV vorbereiten
            # 1. Wort: das markierte Wort (fett für Anki)
            word_field = f"<b>{word}</b>"
            
            # 2. Beispielsatz: der Satz mit fett markiertem Wort
            example_sentence = card_data["sentence"]
            # Ersetze ** durch <b> für Anki
            example_sentence = example_sentence.replace("**", "<b>", 1)
            example_sentence = example_sentence.replace("**", "</b>", 1)
            
            # 3. Übersetzung: die deutsche Übersetzung
            translation = card_data["translation"]
            
            # 4. Infos: alle weiteren Informationen
            infos = f"""
            <b>Bedeutung (Italienisch):</b> {card_data["meaning"]}<br>
            <b>Etymologie:</b> {card_data["etymology"]}<br>
            <b>Flexionen:</b> {card_data["inflection"]}<br>
            <b>Anmerkungen:</b> {card_data["notes"]}
            """
            
            # CSV-Zeile vorbereiten (alle Felder bereinigen)
            word_clean = word_field.replace(";", ",").replace('"', "'").replace("\n", " ")
            example_clean = example_sentence.replace(";", ",").replace('"', "'").replace("\n", " ")
            translation_clean = translation.replace(";", ",").replace('"', "'").replace("\n", " ")
            infos_clean = infos.replace(";", ",").replace('"', "'").replace("\n", " ")
            
            csv_rows.append([word_clean, example_clean, translation_clean, infos_clean])
            
            # Für die Live-Vorschau im Frontend
            current_process["cards"].append({
                "front": example_sentence,  # Vorderseite: Beispielsatz
                "back": f"""
                <b>Wort:</b> {word_field}<br>
                <b>Beispielsatz:</b> {example_sentence}<br>
                <b>Übersetzung:</b> {translation}<br>
                <b>Infos:</b> {infos}
                """
            })
            
            # Fortschritt aktualisieren
            current_process["progress"] = int(((i + 1) / len(words)) * 100)
            
        except Exception as e:
            print(f"Fehler bei Vokabel {word}: {str(e)}")
            # Fallback-Karte
            fallback_word = f"<b>{word}</b>"
            fallback_sentence = f"<b>{word}</b> (Fehler bei der Generierung: {str(e)[:50]})"
            fallback_translation = "Fehler bei der Übersetzung"
            fallback_infos = f"""
            <b>Bedeutung (Italienisch):</b> Fehler bei der Bedeutung<br>
            <b>Etymologie:</b> Fehler bei der Etymologie<br>
            <b>Flexionen:</b> Fehler bei den Flexionen<br>
            <b>Anmerkungen:</b> Bitte manuell korrigieren
            """
            
            word_clean = fallback_word.replace(";", ",").replace('"', "'").replace("\n", " ")
            example_clean = fallback_sentence.replace(";", ",").replace('"', "'").replace("\n", " ")
            translation_clean = fallback_translation.replace(";", ",").replace('"', "'").replace("\n", " ")
            infos_clean = fallback_infos.replace(";", ",").replace('"', "'").replace("\n", " ")
            
            csv_rows.append([word_clean, example_clean, translation_clean, infos_clean])
            
            current_process["cards"].append({
                "front": fallback_sentence,
                "back": f"""
                <b>Wort:</b> {fallback_word}<br>
                <b>Beispielsatz:</b> {fallback_sentence}<br>
                <b>Übersetzung:</b> {fallback_translation}<br>
                <b>Infos:</b> {fallback_infos}
                """
            })
            current_process["progress"] = int(((i + 1) / len(words)) * 100)
    
    # CSV-Daten erstellen mit den neuen Feldern
    output = io.StringIO()
    writer = csv.writer(output, delimiter=csv_delimiter, quoting=csv.QUOTE_MINIMAL)
    # Neue Kopfzeile
    writer.writerow(["Wort", "Beispielsatz", "Übersetzung", "Infos"])
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