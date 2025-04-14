# Benötigte Bibliotheken:
# pip install Flask requests selenium webdriver-manager pandas openpyxl
import requests
import uuid
import json
from flask import Flask, request, jsonify, render_template
import sqlite3
import os
import time
import pandas as pd # Zum Lesen von Excel-Dateien
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import sys # Für sys.exit in main, falls als Skript genutzt


# --- Flask App Initialisierung ---
app = Flask(__name__)

# --- Konfiguration ---
DATABASE_FILENAME = 'drug.db'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_FILENAME)
EXTERNAL_CDS_HOOK_URL = "http://cql-sandbox.projekte.fh-hagenberg.at:8080/cds-services/EngpassMed"

# --- Konfiguration für Download & DB Update ---
BASG_PAGE_URL = "https://medicineshortage.basg.gv.at/vertriebseinschraenkungen/faces/adf.task-flow?_document=WEB-INF%2Fmain-btf.xml&_id=main-btf"
EXPORT_BUTTON_ID = "t:pc1:ctb2"
DOWNLOAD_DIR = BASE_DIR
EXPECTED_DOWNLOAD_FILENAME = "Vertriebseinschraenkungen.xlsx"
DOWNLOAD_FILE_PATH = os.path.join(DOWNLOAD_DIR, EXPECTED_DOWNLOAD_FILENAME)
SELENIUM_TIMEOUT_SECONDS = 45
DOWNLOAD_WAIT_SECONDS = 30


# --- Datenbankfunktionen ---
def get_db():
    """ Stellt eine Verbindung zur SQLite-Datenbank her. """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"!!! Datenbankfehler beim Verbinden: {e}")
        print(f"    Versuchter Pfad: {DATABASE_PATH}")
        return None

def check_shortage(name):
    """
    Prüft, ob ein Medikamenten-NAME *überhaupt* in der shortage-Tabelle vorkommt,
    IGNORIERT dabei den Status.
    Rückgabe: True wenn Name gefunden, False sonst, None bei DB-Fehler.
    """
    # Eingabevalidierung
    if not name:
        print("Warnung: check_shortage ohne Namen aufgerufen.")
        return False # Kein Name, kein Eintrag

    conn = get_db()
    if not conn:
        print("FEHLER: check_shortage konnte keine DB-Verbindung herstellen.")
        return None # DB-Fehler signalisieren

    is_present = False # Bedeutet jetzt: Name ist in der Tabelle vorhanden?
    try:
        cur = conn.cursor()

        # --- Query sucht NUR nach dem Namen, ignoriert Status ---
        query = """
            SELECT 1
            FROM shortage
            WHERE Name = ?
            LIMIT 1
        """

        # --- Aufruf nur mit dem Namen als Parameter ---
        cur.execute(query, (name,)) # Nur 'name' übergeben

        result = cur.fetchone()
        # is_present ist True, wenn irgendein Eintrag mit dem Namen gefunden wurde
        is_present = result is not None

    except sqlite3.Error as e:
        # Fehlermeldung angepasst
        print(f"!!! Datenbankfehler bei shortage-Abfrage (nur nach Name) für '{name}': {e}")
        is_present = None # DB-Fehler signalisieren
    except Exception as e_generic:
         print(f"!!! Unerwarteter Fehler in check_shortage für Name '{name}': {e_generic}")
         is_present = None
    finally:
        # Sicherstellen, dass die Verbindung geschlossen wird
        if conn:
            conn.close()

    # Gibt True (Name gefunden), False (Name nicht gefunden) oder None (Fehler) zurück
    # WICHTIG: True bedeutet jetzt nicht mehr zwingend "aktiver Engpass"!
    return is_present

def get_medication_details_by_name(name):
    """ Holt ATC-Code etc. aus der asp-Tabelle. """
    if not name: return None
    conn = get_db()
    if not conn: return None
    details = None
    try:
        cur = conn.cursor()
        query = "SELECT Name, ATC_Code, Zulassungsnummer FROM asp WHERE Name = ?"
        cur.execute(query, (name,))
        result = cur.fetchone()
        if result: details = dict(result)
    except sqlite3.Error as e:
        print(f"!!! Fehler bei Detail-Abfrage für Name '{name}': {e}")
        details = None
    finally:
         if conn: conn.close()
    return details

def find_alternatives(atc_code, original_name):
    """ Findet verfügbare Alternativen in der gleichen ATC-Gruppe. """
    if not atc_code or len(atc_code) < 2: return []
    if not original_name: return []
    atc_group_prefix = atc_code[:-2]
    atc_search_pattern = atc_group_prefix + "%"
    conn = get_db()
    if not conn: return None
    potential_alternatives = []
    available_alternatives = []
    try:
        cur = conn.cursor()
        query_alternatives = """
            SELECT Name, ATC_Code, Zulassungsnummer
            FROM asp WHERE ATC_Code LIKE ? AND Name != ? """
        cur.execute(query_alternatives, (atc_search_pattern, original_name))
        potential_alternatives = [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        print(f"!!! Fehler bei Alternativensuche: {e}")
        if conn: conn.close(); return None
    finally:
        if conn: conn.close()
    if not potential_alternatives: return []
    for alt in potential_alternatives:
        alt_name = alt.get("Name")
        if not alt_name: continue
        is_alt_in_shortage = check_shortage(alt_name)
        if is_alt_in_shortage is None: continue
        if not is_alt_in_shortage: available_alternatives.append(alt)
    return available_alternatives

# --- Funktion: Download mit Selenium ---
def download_shortage_list():
    """ Versucht, die Excel-Datei von der BASG-Seite mit Selenium herunterzuladen."""
    # (Code für download_shortage_list bleibt unverändert von vorheriger Antwort)
    # [Code der Funktion hier einfügen...]
    log_messages = []
    log_messages.append(f"Download-Verzeichnis: {DOWNLOAD_DIR}")
    print(log_messages[-1])
    log_messages.append(f"Prüfe auf alte Datei: {DOWNLOAD_FILE_PATH}")
    print(log_messages[-1])
    if os.path.exists(DOWNLOAD_FILE_PATH):
        try:
            os.remove(DOWNLOAD_FILE_PATH)
            log_messages.append(f"Alte Datei '{EXPECTED_DOWNLOAD_FILENAME}' erfolgreich gelöscht.")
            print(log_messages[-1])
        except Exception as e:
            msg = f"FEHLER: Alte Datei '{EXPECTED_DOWNLOAD_FILENAME}' konnte nicht gelöscht werden: {e}"
            log_messages.append(msg); print(f"!!! {msg}"); return None, log_messages
    chrome_options = Options()
    prefs = {"download.default_directory": DOWNLOAD_DIR,"download.prompt_for_download": False,"download.directory_upgrade": True,"plugins.always_open_pdf_externally": True}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--headless=new"); chrome_options.add_argument("--disable-gpu"); chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument('--ignore-certificate-errors'); chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument(f'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
    driver = None
    log_messages.append("Starte den Chrome WebDriver im Hintergrund..."); print(log_messages[-1])
    try:
        service = ChromeService(executable_path=ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        log_messages.append("WebDriver gestartet."); print(log_messages[-1])
        log_messages.append(f"Lade die Seite: {BASG_PAGE_URL}"); print(log_messages[-1])
        driver.get(BASG_PAGE_URL)
        log_messages.append(f"Warte auf Export-Button (ID: {EXPORT_BUTTON_ID})... (Max {SELENIUM_TIMEOUT_SECONDS}s)"); print(log_messages[-1])
        wait = WebDriverWait(driver, SELENIUM_TIMEOUT_SECONDS)
        export_button = wait.until(EC.element_to_be_clickable((By.ID, EXPORT_BUTTON_ID)))
        log_messages.append("Export-Button gefunden."); print(log_messages[-1])
        export_button.click()
        log_messages.append(f"Klick ausgeführt. Warte {DOWNLOAD_WAIT_SECONDS}s auf den Download..."); print(log_messages[-1])
        time.sleep(DOWNLOAD_WAIT_SECONDS)
        if os.path.exists(DOWNLOAD_FILE_PATH):
             if os.path.getsize(DOWNLOAD_FILE_PATH) > 0:
                  msg = f"Download erfolgreich! Datei gefunden: {DOWNLOAD_FILE_PATH}"; log_messages.append(msg); print(msg); return DOWNLOAD_FILE_PATH, log_messages
             else:
                  msg = f"FEHLER: Heruntergeladene Datei '{EXPECTED_DOWNLOAD_FILENAME}' ist leer."; log_messages.append(msg); print(f"!!! {msg}")
                  try: os.remove(DOWNLOAD_FILE_PATH)
                  except: pass
                  return None, log_messages
        else:
            ongoing_downloads = [f for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith('.crdownload')]
            if ongoing_downloads: msg = f"FEHLER: Download scheint nach {DOWNLOAD_WAIT_SECONDS}s noch zu laufen ({ongoing_downloads}). Erhöhe DOWNLOAD_WAIT_SECONDS oder prüfe manuell."
            else: msg = f"FEHLER: Datei '{EXPECTED_DOWNLOAD_FILENAME}' wurde nach Klick nicht im Verzeichnis gefunden. Download fehlgeschlagen?"
            log_messages.append(msg); print(f"!!! {msg}"); return None, log_messages
    except Exception as e:
        msg = f"FEHLER während des Selenium Downloads: {e}"; log_messages.append(msg); print(f"!!! {msg}")
        if driver:
            try:
                screenshot_path = os.path.join(DOWNLOAD_DIR, "fehler_screenshot_download.png")
                driver.save_screenshot(screenshot_path); log_messages.append(f"Screenshot wurde gespeichert: {screenshot_path}"); print(log_messages[-1])
            except Exception as screenshot_error: log_messages.append(f"Konnte keinen Screenshot erstellen: {screenshot_error}"); print(log_messages[-1])
        return None, log_messages
    finally:
        if driver: log_messages.append("Schließe den Hintergrund-Browser."); print(log_messages[-1]); driver.quit()


# --- Angepasste Funktion: DB Update aus Excel ---
def update_database_from_excel(db_path, excel_path):
    """Liest die heruntergeladene Excel-Datei und aktualisiert die shortage-Tabelle."""
    log_messages = []

    if not os.path.exists(excel_path):
        msg = f"FEHLER: Excel-Datei '{os.path.basename(excel_path)}' nicht gefunden für DB Update."
        log_messages.append(msg)
        print(f"!!! {msg}")
        return False, log_messages

    log_messages.append(f"Starte DB-Update aus Excel '{os.path.basename(excel_path)}'...")
    print(log_messages[-1])

    conn = get_db()
    if not conn:
        msg = "FEHLER: Konnte keine Datenbankverbindung herstellen für DB Update."
        log_messages.append(msg)
        print(f"!!! {msg}")
        return False, log_messages

    inserted_rows = 0
    try:
        cur = conn.cursor()

        log_messages.append("Lösche alte Daten aus 'shortage'...")
        print(log_messages[-1])
        cur.execute("DELETE FROM shortage;")

        log_messages.append(f"Lese Excel-Datei '{os.path.basename(excel_path)}'...")
        print(log_messages[-1])
        df = pd.read_excel(excel_path, sheet_name=0)
        log_messages.append(f"Gefundene Spalten im Excel: {list(df.columns)}")
        print(log_messages[-1])

        # --- !!! HIER DAS MAPPING ANPASSEN AN DIE EXCEL-SPALTEN !!! ---
        # Links: Interne Schlüssel (egal wie sie heißen)
        # Rechts: Exakte Spaltenüberschriften aus deiner Excel-Datei!
        col_map = {
            'db_name': 'Name',
            'db_verwendung': 'Verwendung',
            'db_status': 'Status',
            'db_details': 'Details', # Für die REAL-Spalte in der DB
            'db_melder': 'Melder',
            'db_pzn_nicht': 'PZN nicht verfügbarer Packungen',
            'db_pzn_eingeschr': 'PZN eingeschränkt verfügbarer Packungen ', # Auf Tippfehler/Leerzeichen am Ende achten!
            'db_pzn_wieder': 'PZN wieder verfügbarer Packungen ',
            # 'ATC Code' wird ignoriert, da nicht in 'shortage'-Tabelle
            'db_datum_meldung': 'Datum der Meldung',
            'db_datum_aenderung': 'Datum der letzten Änderung'
        }

        # Überprüfe, ob die benötigten Quellspalten (die Werte im col_map) im DataFrame existieren
        missing_cols = [excel_col for excel_col in col_map.values() if excel_col not in df.columns]
        if missing_cols:
             msg = f"FEHLER: Folgende Spalten fehlen in der Excel-Datei: {missing_cols}. Bitte col_map im Skript prüfen/anpassen."
             log_messages.append(msg)
             print(f"!!! {msg}")
             conn.rollback()
             return False, log_messages

        log_messages.append("Füge neue Daten in Tabelle 'shortage' ein...")
        print(log_messages[-1])

        # Iteriere durch die Zeilen des DataFrames
        for index, row in df.iterrows():
            try:
                # Extrahiere Daten mithilfe des Mappings
                med_name = str(row[col_map['db_name']]).strip() if pd.notna(row[col_map['db_name']]) else ''
                if not med_name: continue # Zeile ohne Namen überspringen

                verwendung = str(row[col_map['db_verwendung']]).strip() if pd.notna(row[col_map['db_verwendung']]) else ''
                status = str(row[col_map['db_status']]).strip() if pd.notna(row[col_map['db_status']]) else 'UNBEKANNT'

                # Spezielle Behandlung für 'Details' (DB erwartet REAL = Zahl)
                details_val = row[col_map['db_details']]
                details_db = None # Standardwert NULL
                if pd.notna(details_val):
                    try:
                        # Versuche, in eine Zahl umzuwandeln
                        details_db = float(str(details_val).replace(',', '.')) # Komma durch Punkt ersetzen
                    except (ValueError, TypeError):
                        # Wenn Umwandlung fehlschlägt, logge Warnung, speichere NULL
                        print(f"Warnung [Zeile {index+2}]: Konnte 'Details'-Wert '{details_val}' für '{med_name}' nicht in Zahl umwandeln. Setze auf NULL.")

                melder = str(row[col_map['db_melder']]).strip() if pd.notna(row[col_map['db_melder']]) else ''
                pzn_nicht = str(row[col_map['db_pzn_nicht']]).strip() if pd.notna(row[col_map['db_pzn_nicht']]) else ''
                pzn_eingeschr = str(row[col_map['db_pzn_eingeschr']]).strip() if pd.notna(row[col_map['db_pzn_eingeschr']]) else ''
                pzn_wieder = str(row[col_map['db_pzn_wieder']]).strip() if pd.notna(row[col_map['db_pzn_wieder']]) else ''
                datum_meldung = str(row[col_map['db_datum_meldung']]).strip() if pd.notna(row[col_map['db_datum_meldung']]) else ''
                datum_aenderung = str(row[col_map['db_datum_aenderung']]).strip() if pd.notna(row[col_map['db_datum_aenderung']]) else ''

                # Query zum Einfügen in die 'shortage'-Tabelle
                insert_query = """
                    INSERT INTO shortage (
                        Name, Verwendung, Status, Details, Melder,
                        "PZN nicht verfügbarer Packungen",
                        "PZN eingeschränkt verfügbarer Packungen ",
                        "PZN wieder verfügbarer Packungen ",
                        "Datum der Meldung", "Datum der letzten Änderung"
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cur.execute(insert_query, (
                    med_name, verwendung, status, details_db, melder,
                    pzn_nicht, pzn_eingeschr, pzn_wieder,
                    datum_meldung, datum_aenderung
                ))
                inserted_rows += 1

            except KeyError as e:
                msg = f"FEHLER in Excel Zeile {index+2}: Spaltenname '{e}' im Mapping nicht gefunden oder Zugriff fehlgeschlagen. Überspringe Zeile."
                log_messages.append(msg); print(f"!!! {msg}")
            except Exception as e_row:
                msg = f"FEHLER in Excel Zeile {index+2}: {e_row} - Zeile: {row.to_dict()}"
                log_messages.append(msg); print(f"!!! {msg}")

        conn.commit()
        msg = f"Erfolgreich {inserted_rows} Datensätze aus Excel in 'shortage' eingefügt."
        log_messages.append(msg); print(msg)
        return True, log_messages

    except FileNotFoundError:
        msg = f"FEHLER: Excel-Datei nicht gefunden unter: {excel_path}"
        log_messages.append(msg); print(f"!!! {msg}")
        return False, log_messages
    except ImportError:
         msg = "FEHLER: Die 'pandas' oder 'openpyxl' Bibliothek fehlt. Bitte installieren: pip install pandas openpyxl"
         log_messages.append(msg); print(f"!!! {msg}")
         return False, log_messages
    except Exception as e:
        msg = f"FEHLER während des DB-Updates aus Excel: {e}"
        log_messages.append(msg); print(f"!!! {msg}")
        try: conn.rollback()
        except: pass
        return False, log_messages
    finally:
        if conn: conn.close(); print("Datenbankverbindung geschlossen.")


# --- Route zum Auslösen des Downloads UND DB Updates ---
@app.route('/update-database-auto', methods=['POST'])
def trigger_download_and_update():
    """ Löst Download via Selenium und anschließendes DB-Update aus Excel aus."""
    print("\n--- [Auto Update] Anfrage zum Download & Update erhalten ---")
    all_messages = []

    # Schritt 1: Download versuchen
    print("--- Schritt 1: Starte Download ---")
    downloaded_file_path, download_logs = download_shortage_list()
    all_messages.extend(download_logs)

    # Schritt 2: Wenn Download erfolgreich, DB Update versuchen
    if downloaded_file_path and os.path.exists(downloaded_file_path):
        print("\n--- Schritt 2: Download erfolgreich, starte DB Update ---")
        update_success, update_logs = update_database_from_excel(DATABASE_PATH, downloaded_file_path)
        all_messages.extend(update_logs)

        # Optional: Lösche die heruntergeladene Excel-Datei nach dem Update
        try:
            os.remove(downloaded_file_path)
            print(f"Temporäre Excel-Datei '{os.path.basename(downloaded_file_path)}' gelöscht.")
        except Exception as e_del:
             print(f"Warnung: Konnte temporäre Excel-Datei nicht löschen: {e_del}")


        if update_success:
             print("--- [Auto Update] Gesamter Prozess erfolgreich abgeschlossen. ---")
             return jsonify({"status": "success", "message": "Download und Datenbank-Update erfolgreich.", "details": all_messages}), 200
        else:
             print("--- [Auto Update] Prozess fehlgeschlagen (DB Update Fehler). ---")
             return jsonify({"status": "error", "message": "Download erfolgreich, aber Datenbank-Update fehlgeschlagen.", "details": all_messages}), 500
    else:
        print("--- [Auto Update] Prozess fehlgeschlagen (Download Fehler). ---")
        return jsonify({"status": "error", "message": "Download der Datei fehlgeschlagen.", "details": all_messages}), 500


# --- Route für die Web-Oberfläche ---
@app.route('/')
def index():
    """Liefert die HTML-Seite für das GUI."""
    return render_template('index.html')


# --- Endpunkt für Autocomplete ---
@app.route('/autocomplete/medication')
def autocomplete_medication():
    """Liefert Medikamentennamen für Autocomplete."""
    # (Code bleibt unverändert)
    # [Code der Funktion hier einfügen...]
    search_term = request.args.get('term', '')
    suggestions = []
    if search_term and len(search_term) > 1:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                query = "SELECT Name FROM asp WHERE Name LIKE ? LIMIT 15" # Limit 15
                cur.execute(query, (search_term + '%',))
                results = cur.fetchall()
                suggestions = [row['Name'] for row in results]
            except sqlite3.Error as e:
                print(f"!!! Fehler bei Autocomplete-Abfrage für '{search_term}': {e}")
            finally:
                if conn: conn.close()
    return jsonify(suggestions)


# --- Endpunkt für die Prüfung + Externen Hook ---
@app.route('/check-and-notify-external', methods=['POST'])
def check_and_notify_external_cds_service():
    request_data = request.json
    if not request_data or 'medication_name' not in request_data: return jsonify({"error": "Bitte 'medication_name' im JSON Body angeben."}), 400
    med_name = request_data['medication_name'].strip();
    if not med_name: return jsonify({"error": "'medication_name' darf nicht leer sein."}), 400
    print(f"\n--- [Check & Notify] Lokale Prüfung für '{med_name}' gestartet ---")
    is_shortage = check_shortage(med_name); med_details = get_medication_details_by_name(med_name)
    atc_code = med_details.get("ATC_Code") if med_details else None; alternatives = []
    local_status_text = ""
    if is_shortage is None: local_status_text = "DB Fehler bei lokaler Prüfung"
    else:
        local_status_text = "Engpass (lokal)" if is_shortage else "Verfügbar (lokal)"
        if is_shortage and atc_code:
            alt_result = find_alternatives(atc_code, med_name)
            if alt_result is not None: alternatives = alt_result
            else: print("!!! Fehler bei lokaler Alternativensuche.")
    print(f"Lokaler Status: '{local_status_text}', ATC: {atc_code}, Alternativen gefunden: {len(alternatives)}")
    hook_instance_id = str(uuid.uuid4()); hook_type = "order-sign"
    medication_request_resource = {"resourceType": "MedicationRequest","id": f"medreq-{uuid.uuid4()}","status": "draft","intent": "order","medicationCodeableConcept": { "text": med_name },"subject": { "reference": "Patient/example-patient-1" }};
    if atc_code: medication_request_resource["medicationCodeableConcept"]["coding"] = [{"system": "http://fhir.hl7.org/CodeSystem/v3-atc", "code": atc_code}]
    draft_orders_bundle = {"resourceType": "Bundle","entry": [{ "resource": medication_request_resource }]};
    external_hook_payload = {"hookInstance": hook_instance_id,"hook": hook_type,"context": {"userId": "Practitioner/example-practitioner-1","patientId": "Patient/example-patient-1","draftOrders": draft_orders_bundle}};
    print(f"--- [Check & Notify] Sende STANDARD CDS Hook an externen Service ---"); print(f"    Ziel-URL: {EXTERNAL_CDS_HOOK_URL}")
    response_from_external_service_data = None; external_call_error = None; external_call_status_code = None; response_text = None
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}; response = requests.post( EXTERNAL_CDS_HOOK_URL, headers=headers, json=external_hook_payload, timeout=20)
        external_call_status_code = response.status_code
        try: response_from_external_service_data = response.json()
        except json.JSONDecodeError: print(f"    Antwort vom externen Service (Status {external_call_status_code}) war kein gültiges JSON."); response_text = response.text; response_from_external_service_data = None
        response.raise_for_status(); print(f"    Erfolgreich gesendet. Antwort vom externen Service erhalten (Status {external_call_status_code}).")
    except requests.exceptions.Timeout: error_msg = "Timeout beim Senden des Hooks"; print(f"    FEHLER: {error_msg} an {EXTERNAL_CDS_HOOK_URL}."); external_call_error = error_msg
    except requests.exceptions.RequestException as e: error_msg = f"Fehler beim Senden/Verarbeiten des Hooks: {e}"; print(f"    FEHLER: {error_msg}"); external_call_error = str(e)
    print("--- [Check & Notify] Vorgang abgeschlossen ---")
    final_response = {"medication_checked": med_name,"local_check": {"status": local_status_text,"atc_code_found": atc_code,"alternatives_found_count": len(alternatives),"alternatives_details": alternatives},"external_cds_hook_call": {"target_url": EXTERNAL_CDS_HOOK_URL,"status_code": external_call_status_code,"error": external_call_error,"response_body": response_from_external_service_data if response_from_external_service_data else response_text }}; return jsonify(final_response)


# --- Hauptausführung (Startet den Flask Server) ---
if __name__ == '__main__':
    print("--- Starte Flask Server ---")
    print(f"Datenbank erwartet unter: {DATABASE_PATH}")
    if not os.path.exists(DATABASE_PATH):
        print(f"!!! WARNUNG: Datenbankdatei nicht gefunden: {DATABASE_PATH} !!!")
    print(f"Externer CDS Hook wird gesendet an: {EXTERNAL_CDS_HOOK_URL}")
    print(f"Automatischer Download von: {BASG_PAGE_URL}")
    print(f"Erwartete Downloaddatei: {EXPECTED_DOWNLOAD_FILENAME} in {DOWNLOAD_DIR}")
    print("INFO: Für den automatischen Download muss Google Chrome installiert sein.")
    app.run(host='0.0.0.0', port=5001, debug=True)