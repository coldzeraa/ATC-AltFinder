# Drug Shortage Assistant Austria (Prototype)

## Project Description

This project is a prototype web application developed as part of a Bachelor's thesis at FH Oberösterreich, Hagenberg Campus (2025). Its primary goal is to assist healthcare professionals in handling drug shortages in the Austrian context.

The tool provides the following functionalities:
1.  Checks if a given medication name exists within a locally stored drug shortage list.
2.  Suggests potential alternative medications based on the same ATC pharmacological subgroup, filtering out alternatives also listed as having shortages.
3.  Automates the download of the official Austrian drug shortage list (`Vertriebseinschraenkungen.xlsx`) from the interactive BASG website using Selenium browser automation.
4.  Automatically updates the local shortage database table by parsing the downloaded Excel file.
5.  Initiates a Clinical Decision Support (CDS) Hooks request (as a client) to a configured external service endpoint after performing the local check.
6.  Offers a simple web-based graphical user interface (GUI) for interaction.

**Note:** This is a functional prototype. The shortage check currently only verifies the *presence* of the medication name in the shortage list, ignoring the actual shortage status (e.g., 'AKTIV', 'BEENDET'). The alternative suggestion logic is based on ATC groups and does not guarantee therapeutic interchangeability. The automated download relies on the specific structure of the BASG website and may break if the site changes.

## Features

* **Web Interface:** Simple GUI built with Flask and Pico.css.
* **Autocomplete:** Suggests medication names based on local data as the user types.
* **Local Shortage Check:** Checks medication name against the local SQLite `shortage` table.
* **Alternative Suggestions:** Finds and displays available alternatives from the same ATC subgroup (ATC prefix).
* **Automated BASG Download:** Uses Selenium and webdriver-manager to download the official `.xlsx` shortage list from the BASG web registry.
* **Automated DB Update:** Uses Pandas to read the downloaded Excel file and update the local SQLite `shortage` table.
* **GUI Triggers:** Buttons to perform the medication check/external hook call and to trigger the download/update process.
* **CDS Hooks Client:** Sends a POST request formatted according to CDS Hooks standards (including a minimal FHIR MedicationRequest in context) to an external service.

## Technology Stack

* **Backend:** Python 3.x, Flask
* **Database:** SQLite 3
* **Data Processing:** Pandas
* **Web Automation:** Selenium, Webdriver-Manager
* **HTTP Requests:** Requests
* **Frontend:** HTML, CSS (Pico.css), JavaScript (Fetch API)
* **Standards Used Conceptually:** ATC, FHIR, CDS Hooks

## Prerequisites

* Python 3.7+
* `pip` (Python package installer)
* Google Chrome browser installed (required for Selenium automation)

## Setup & Installation

1.  **Clone/Download:** Get the project files (`app.py`, `templates/index.html`, potentially `drug.db`) into a directory.
2.  **Install Dependencies:** Open a terminal or command prompt in the project directory and run:
    ```bash
    pip install Flask requests selenium webdriver-manager pandas openpyxl
    ```
3.  **Database Setup (`drug.db`):**
    * A SQLite database file named `drug.db` (or as configured in `DATABASE_FILENAME` in `app.py`) is required in the same directory.
    * It must contain two tables: `asp` and `shortage`.
    * **`asp` Table:** Needs to be pre-populated with data from the Austrian Medicines Register (Arzneimittelspezialitätenregister). Minimally, it requires columns like `Name` (TEXT, Primary Key or Unique), `ATC_Code` (TEXT), `Zulassungsnummer` (TEXT). Populating this table is outside the scope of this application's core update functionality.
        ```sql
        -- Example CREATE statement for asp table (adapt as needed)
        CREATE TABLE IF NOT EXISTS asp (
            Name TEXT PRIMARY KEY,
            ATC_Code TEXT,
            Zulassungsnummer TEXT,
            -- Add other columns from ASP register if needed
            Verwendung TEXT
        );
        ```
    * **`shortage` Table:** This table will be automatically cleared and populated by the application when using the "Download & DB Update starten" feature. If running for the first time, ensure the table exists with the correct schema.
        ```sql
        -- Example CREATE statement for shortage table (must match Python INSERT)
        CREATE TABLE IF NOT EXISTS shortage (
            Name TEXT,
            Verwendung TEXT,
            Status TEXT,
            Details REAL, -- Note: Data type might need adjustment based on Excel content
            Melder TEXT,
            "PZN nicht verfügbarer Packungen" TEXT,
            "PZN eingeschränkt verfügbarer Packungen" TEXT, -- Ensure exact name match with DB!
            "PZN wieder verfügbarer Packungen" TEXT,     -- Ensure exact name match with DB!
            "Datum der Meldung" TEXT,
            "Datum der letzten Änderung" TEXT
        );
        ```

## Configuration

Several parameters can be adjusted directly at the top of the `app.py` file:

* `DATABASE_FILENAME`: Name of the SQLite database file.
* `EXTERNAL_CDS_HOOK_URL`: URL of the external CDS Hooks service to call.
* `BASG_PAGE_URL`: URL of the BASG shortage list page for Selenium.
* `EXPORT_BUTTON_ID`: The HTML ID of the Excel export button on the BASG page (critical for Selenium - **may change if BASG updates their site!**).
* `EXPECTED_DOWNLOAD_FILENAME`: The exact name of the file downloaded by Selenium.
* `SELENIUM_TIMEOUT_SECONDS`: How long Selenium waits for the page/button (increase if needed).
* `DOWNLOAD_WAIT_SECONDS`: How long the script waits after clicking download (increase if downloads are slow/incomplete).
* `col_map` (inside `update_database_from_excel` function): **Crucial!** This dictionary maps internal keys to the **exact column header names** found in the downloaded `Vertriebseinschraenkungen.xlsx` file. This *must* be verified and adjusted if the downloaded file structure changes.

## Running the Application

1.  Navigate to the project directory in your terminal.
2.  Run the Flask application:
    ```bash
    python app.py
    ```
3.  Open your web browser and go to `http://localhost:5001` (or the address shown in the terminal).

## Usage

1.  **Check Medication:**
    * Enter a medication name into the input field. Autocomplete suggestions based on the `asp` table data will appear as you type (min. 2 characters).
    * Click the "Prüfen und Externen Hook Senden" button.
    * The application performs the local check (name presence in `shortage` table) and suggests alternatives (from `asp` table, filtered by `shortage` table) based on the ATC subgroup.
    * Simultaneously, it sends a CDS Hooks POST request to the configured external URL.
    * Results from both the local check and the external call attempt (including status code, errors, response body) are displayed below the buttons.
2.  **Update Shortage Database:**
    * Click the "Download & DB Update starten" button.
    * A confirmation prompt will appear.
    * If confirmed, the application will:
        * Launch a headless Chrome browser via Selenium.
        * Navigate to the BASG website.
        * Click the Excel export button.
        * Wait for the download (`Vertriebseinschraenkungen.xlsx`) to complete in the application directory.
        * Read the downloaded Excel file using Pandas.
        * Clear the existing `shortage` table in `drug.db`.
        * Insert the data from the Excel file into the `shortage` table.
    * This process can take **30-60 seconds or longer**. Wait for completion.
    * A status message (success or failure) will be displayed in the GUI. Detailed logs are printed in the Flask server terminal.

## Troubleshooting

* **Selenium/Download Errors:**
    * Ensure Google Chrome is installed.
    * Ensure `webdriver-manager` can download the correct ChromeDriver (check firewall/network restrictions).
    * If download fails consistently, the BASG website structure or the `EXPORT_BUTTON_ID` might have changed. Inspect the website manually using browser developer tools (F12) to find the new ID for the Excel export button and update `app.py`.
    * Increase `SELENIUM_TIMEOUT_SECONDS` or `DOWNLOAD_WAIT_SECONDS` in `app.py` if downloads seem incomplete or time out.
    * Check the Flask terminal logs and any `fehler_screenshot_download.png` created.
* **Database Update Errors:**
    * `FEHLER: Folgende Spalten fehlen...`: The column names in the downloaded Excel file do not match the keys expected in the `col_map` dictionary in `app.py`. Open the `.xlsx` file, verify the exact column headers, and update `col_map` accordingly.
    * `table shortage has no column named...`: The column name used in the `INSERT INTO shortage` SQL statement in `app.py` does not exactly match the column name defined in your `drug.db` schema. Use "DB Browser for SQLite" to check the actual table schema and correct the `INSERT` statement in `app.py`.
    * Check Flask terminal logs for detailed error messages.
* **External Hook Errors (4xx/5xx):**
    * Errors like 412 or 500 returned from the `EXTERNAL_CDS_HOOK_URL` indicate a problem on the *external server's* side (e.g., missing configuration, internal errors). Contact the administrators of that service.

## Limitations

* Prototype stage, not for production use.
* Shortage check only verifies name presence, not active status.
* Alternative suggestions are basic (ATC group only), not clinically validated for interchangeability.
* Selenium download can be slow and may break if the target website changes.
* SQLite database has scalability limits.
* Manual pre-loading required for `asp` table data.
* Lacks automated tests.
* Lacks robust security and privacy features for clinical use.


## Author

* David Derntl

## Project Context

* Bachelor Thesis
* FH Oberösterreich, Hagenberg Campus
* Medizin und Bioinformatik
* April 2025 
