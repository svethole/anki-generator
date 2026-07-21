import io
import csv
import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from contextlib import contextmanager
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
<<<<<<< Updated upstream
import io
import csv
import re
=======
from openai import OpenAI
import os
>>>>>>> Stashed changes

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

app = Flask(__name__)
CORS(app)

<<<<<<< Updated upstream
# Datenbank initialisieren
=======
# ==================== KONFIGURATION ====================
>>>>>>> Stashed changes
DB_PATH = "anki_history.db"

# ==================== GLOBALE VARIABLEN ====================
# Thread-sichere Prozess-Steuerung
process_lock = threading.Lock()
process_running = False

current_process = {
    "running": False,
    "progress": 0,
    "cards": [],
    "source_text": "",
    "csv_data": "",
    "card_count": 0,
    "process_id": None
}

# ==================== DATENBANK ====================
@contextmanager
def get_db_connection(max_retries=5, retry_delay=0.5):
    """Stellt eine Datenbankverbindung mit Retry-Logic bereit."""
    conn = None
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                yield conn
                conn.commit()
            except Exception:
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()
            return  # Erfolgreich beendet
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                print(f"⚠️ Datenbank gesperrt, Versuch {attempt + 1}/{max_retries}...")
                time.sleep(retry_delay)
                continue
            else:
                raise
        except Exception as e:
            raise

def init_db():
    """Initialisiert die SQLite-Datenbank."""
    try:
        with get_db_connection() as conn:
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
            # Index für bessere Performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON history(timestamp DESC)')
            print("✅ Datenbank initialisiert")
    except Exception as e:
        print(f"❌ Fehler bei der Datenbank-Initialisierung: {e}")
        raise

def migrate_database():
    """Konvertiert alte 2-Spalten-CSV-Einträge in das neue 4-Spalten-Format."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, csv_data FROM history")
            rows = c.fetchall()
            
            if not rows:
                print("✅ Keine Migration nötig (Datenbank leer)")
                return
            
            migrated_count = 0
            for entry_id, csv_data in rows:
                try:
                    reader = csv.reader(io.StringIO(csv_data), delimiter=';')
                    header = next(reader, [])
                    
                    # Prüfen ob schon im neuen Format
                    if len(header) >= 4 and header[0] == "Wort":
                        continue
                    
                    # Altes Format konvertieren
                    new_rows = []
                    for row in reader:
                        if len(row) >= 2:
                            front = row[0]
                            back = row[1]
                            
                            word_match = re.search(r'<b>(.*?)</b>', front)
                            word = word_match.group(1) if word_match else front[:20]
                            
                            translation_match = re.search(r'<b>Übersetzung:</b>\s*(.*?)(?:<br>|$)', back, re.DOTALL)
                            translation = translation_match.group(1).strip() if translation_match else ""
                            
                            infos = re.sub(r'<b>Übersetzung:</b>\s*.*?(?:<br>|$)', '', back, flags=re.DOTALL)
                            
                            new_rows.append([word, front, translation, infos])
                    
                    if new_rows:
                        output = io.StringIO()
                        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                        writer.writerow(["Wort", "Beispielsatz", "Übersetzung", "Infos"])
                        writer.writerows(new_rows)
                        
                        c.execute("UPDATE history SET csv_data = ? WHERE id = ?", (output.getvalue(), entry_id))
                        migrated_count += 1
                        print(f"✅ Eintrag {entry_id} migriert")
                except Exception as e:
                    print(f"❌ Fehler bei Eintrag {entry_id}: {e}")
            
            print(f"✅ Migration abgeschlossen! {migrated_count} Einträge migriert.")
    except Exception as e:
        print(f"❌ Fehler bei der Migration: {e}")

# Datenbank initialisieren
print("📊 Initialisiere Datenbank...")
init_db()
print("🔄 Führe Migration durch...")
migrate_database()
print("✅ Datenbank bereit")

# ==================== HILFSFUNKTIONEN ====================
def extract_words_from_text(text, mode):
    """Extrahiert Vokabeln aus dem Quelltext."""
    if mode == "fluent":
        return re.findall(r'\*(.*?)\*', text)
    else:
        return [line.strip() for line in text.split('\n') if line.strip()]

def generate_card_with_ai(word, context_sentence=None, client=None, model="gpt-4o-mini", temperature=0.7, max_tokens=500):
    """Generiert eine Karteikarte mit KI, mit robustem Error-Handling."""
    try:
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
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            json_str = re.sub(r'\.\.\.', '', json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*\]', ']', json_str)
            
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                json_str = re.sub(r'[^\{\}\[\]\,\"\:\w\s\-\.\*]', '', json_str)
                return json.loads(json_str)
        
        return {
            "sentence": f"**{word}** (Fehler bei der JSON-Generierung)",
            "translation": "Fehler bei der Übersetzung",
            "meaning": "Fehler bei der Bedeutung",
            "etymology": "Fehler bei der Etymologie",
            "inflection": "Fehler bei den Flexionen",
            "notes": "Bitte manuell korrigieren"
        }
        
    except Exception as e:
        print(f"❌ Fehler bei Vokabel {word}: {str(e)}")
        return {
            "sentence": f"**{word}** (Fehler: {str(e)[:50]})",
            "translation": "Fehler bei der Übersetzung",
            "meaning": "Fehler bei der Bedeutung",
            "etymology": "Fehler bei der Etymologie",
            "inflection": "Fehler bei den Flexionen",
            "notes": "Bitte manuell korrigieren"
        }

def process_cards(words, mode, client, model, temperature, max_tokens, csv_delimiter):
    """Hauptverarbeitungsfunktion (wird im Thread ausgeführt)."""
    global process_running, current_process
    
    try:
        print(f"🔄 Prozess gestartet für {len(words)} Vokabeln")
        
        with process_lock:
            current_process["running"] = True
            current_process["progress"] = 0
            current_process["cards"] = []
            current_process["card_count"] = len(words)
        
        source_text = current_process["source_text"]
        csv_rows = []
        
        for i, word in enumerate(words):
            try:
                context = None
                if mode == "fluent":
                    sentences = source_text.split('.')
                    for sent in sentences:
                        if word in sent:
                            context = sent.strip() + "."
                            break
                
                print(f"  📝 Verarbeite Vokabel {i+1}/{len(words)}: {word}")
                
                card_data = generate_card_with_ai(
                    word,
                    context_sentence=context,
                    client=client,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                word_field = f"<b>{word}</b>"
                
                example_sentence = card_data["sentence"]
                example_sentence = example_sentence.replace("**", "<b>", 1)
                example_sentence = example_sentence.replace("**", "</b>", 1)
                
                translation = card_data["translation"]
                
                infos = f"""
                <b>Bedeutung (Italienisch):</b> {card_data["meaning"]}<br>
                <b>Etymologie:</b> {card_data["etymology"]}<br>
                <b>Flexionen:</b> {card_data["inflection"]}<br>
                <b>Anmerkungen:</b> {card_data["notes"]}
                """
                
                word_clean = word_field.replace(";", ",").replace('"', "'").replace("\n", " ")
                example_clean = example_sentence.replace(";", ",").replace('"', "'").replace("\n", " ")
                translation_clean = translation.replace(";", ",").replace('"', "'").replace("\n", " ")
                infos_clean = infos.replace(";", ",").replace('"', "'").replace("\n", " ")
                
                csv_rows.append([word_clean, example_clean, translation_clean, infos_clean])
                
                with process_lock:
                    current_process["cards"].append({
                        "front": example_sentence,
                        "back": f"""
                        <b>Wort:</b> {word_field}<br>
                        <b>Beispielsatz:</b> {example_sentence}<br>
                        <b>Übersetzung:</b> {translation}<br>
                        <b>Infos:</b> {infos}
                        """
                    })
                    current_process["progress"] = int(((i + 1) / len(words)) * 100)
                
            except Exception as e:
                print(f"❌ Fehler bei Vokabel {word}: {str(e)}")
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
                
                with process_lock:
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
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=csv_delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Wort", "Beispielsatz", "Übersetzung", "Infos"])
        writer.writerows(csv_rows)
        
        with process_lock:
            current_process["csv_data"] = output.getvalue()
            current_process["card_count"] = len(csv_rows)
            current_process["running"] = False
            current_process["progress"] = 100
        
        # In Datenbank speichern
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO history (timestamp, source_text, csv_data, card_count) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), source_text, current_process["csv_data"], len(csv_rows))
            )
        
        print(f"✅ Prozess abgeschlossen: {len(csv_rows)} Karten generiert")
        
    except Exception as e:
        print(f"❌ Kritischer Fehler in process_cards: {e}")
        import traceback
        traceback.print_exc()
    finally:
        with process_lock:
            process_running = False

# ==================== ROUTEN ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_processing():
    global process_running, current_process
    
    with process_lock:
        if process_running:
            return jsonify({
                "error": "Es läuft bereits eine Verarbeitung. Bitte warte bis sie abgeschlossen ist.",
                "running": True
            }), 409
        process_running = True
    
    try:
        data = request.json
        request_id = data.get('requestId', 'unknown')
        print(f"📨 Start-Request empfangen: {request_id}")
        
        text = data.get('text', '')
        mode = data.get('mode', 'fluent')
        api_key = data.get('apiKey', '')
        model = data.get('model', 'gpt-4o-mini')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('maxTokens', 500)
        csv_delimiter = data.get('csvDelimiter', ';')
        
        if not text:
            with process_lock:
                process_running = False
            return jsonify({"error": "Kein Text eingegeben"}), 400
        
        if not api_key:
            with process_lock:
                process_running = False
            return jsonify({"error": "Kein API-Key angegeben"}), 400
        
        words = extract_words_from_text(text, mode)
        if not words:
            with process_lock:
                process_running = False
            return jsonify({"error": "Keine Vokabeln gefunden"}), 400
        
        print(f"📝 Extrahierte Vokabeln: {len(words)} - {words}")
        
        client = OpenAI(api_key=api_key)
        
        with process_lock:
            current_process["running"] = True
            current_process["progress"] = 0
            current_process["cards"] = []
            current_process["source_text"] = text
            current_process["csv_data"] = ""
            current_process["card_count"] = 0
            current_process["process_id"] = str(time.time())
        
        thread = threading.Thread(
            target=process_cards,
            args=(words, mode, client, model, temperature, max_tokens, csv_delimiter)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "message": "Verarbeitung gestartet",
            "total": len(words),
            "process_id": current_process["process_id"]
        })
        
    except Exception as e:
        with process_lock:
            process_running = False
            current_process["running"] = False
        print(f"❌ Fehler beim Start: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/progress')
def progress():
    def generate():
        last_progress = -1
        last_card_count = 0
        sent_done = False
        
        while True:
            with process_lock:
                is_running = current_process["running"]
                current_progress = current_process["progress"]
                current_cards = current_process["cards"].copy()
            
            if not is_running and current_progress >= 100 and not sent_done:
                yield f"data: {json.dumps({'progress': 100, 'cards': current_cards, 'done': True})}\n\n"
                sent_done = True
                break
            
            if (current_progress != last_progress or 
                len(current_cards) != last_card_count):
                
                data = {
                    'progress': current_progress,
                    'cards': current_cards,
                    'done': False
                }
                yield f"data: {json.dumps(data)}\n\n"
                
                last_progress = current_progress
                last_card_count = len(current_cards)
            
            if not is_running and current_progress >= 100 and not sent_done:
                yield f"data: {json.dumps({'progress': 100, 'cards': current_cards, 'done': True})}\n\n"
                sent_done = True
                break
            
            time.sleep(0.5)
    
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
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, timestamp, card_count FROM history ORDER BY timestamp DESC")
        rows = c.fetchall()
    
    return jsonify([{"id": row[0], "timestamp": row[1], "card_count": row[2]} for row in rows])

@app.route('/history/<int:entry_id>')
def get_history_entry(entry_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT source_text, csv_data, card_count FROM history WHERE id = ?", (entry_id,))
        row = c.fetchone()
    
    if not row:
        return jsonify({"error": "Eintrag nicht gefunden"}), 404
    
    cards = []
    try:
        csv_reader = csv.reader(io.StringIO(row[1]), delimiter=';')
        header = next(csv_reader, [])
        
        for csv_row in csv_reader:
            if len(csv_row) >= 4:
                word = csv_row[0]
                example = csv_row[1]
                translation = csv_row[2]
                infos = csv_row[3] if len(csv_row) > 3 else ""
                
                front = example
                back = f"""
                <b>Wort:</b> {word}<br>
                <b>Beispielsatz:</b> {example}<br>
                <b>Übersetzung:</b> {translation}<br>
                <b>Infos:</b> {infos}
                """
                cards.append({"front": front, "back": back})
            elif len(csv_row) >= 2:
                front = csv_row[0]
                back = csv_row[1]
                cards.append({"front": front, "back": back})
    except Exception as e:
        print(f"❌ Fehler beim Parsen: {e}")
        cards = [{"front": "Fehler", "back": f"CSV konnte nicht geparst werden: {str(e)}"}]
    
    return jsonify({
        "source_text": row[0],
        "cards": cards,
        "card_count": row[2],
        "csv_data": row[1]
    })

@app.route('/history/<int:entry_id>', methods=['DELETE'])
def delete_history_entry(entry_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM history WHERE id = ?", (entry_id,))
        # Kein manuelles commit nötig - der Context-Manager macht das automatisch
    
    return jsonify({"message": "Eintrag gelöscht"})

@app.route('/close-progress')
def close_progress():
    def generate():
        yield "data: {\"closed\": true}\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream")

# ==================== MAIN ====================
if __name__ == '__main__':
    print("🚀 Starte Anki-Kartengenerator...")
    print(f"📊 Datenbank: {DB_PATH}")
    print("🌐 Server läuft auf http://localhost:5000")
    app.run(debug=True, port=5000)