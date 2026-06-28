# ChamberCal

**ChamberCal** is a Streamlit web application for managing and analysing **propane combustion recovery tests**, a standard calibration procedure used to validate indirect calorimetry / metabolic chambers. It was built as a project for the *Applied Python Programming* course (opencampus.sh) by **Rebecca Dörner** and **Rohan Sasidharan Nair**.

Lab staff upload a chamber's raw measurement file together with the propane weights recorded before/after the burn. ChamberCal trims the warm-up/cool-down window, computes the theoretical ("SOLL") and measured ("IST") O₂/CO₂ volumes, scores the chamber's recovery quality, and lets the user save, browse, and export the results. Admins manage users, chambers, calculation constants, and can audit everything that happened in the system.

---

## 1. What the system does (functional overview)

1. **Authenticate** — username/password login against a local SQLite database (PBKDF2-SHA256, salted).
2. **Route by role** — `admin` accounts see an administration area; everyone else sees the standard user dashboard.
3. **User workflow**
   - Upload a tab-separated `.txt` measurement export from the chamber.
   - The chamber (`m1`, `m2`, …) is auto-detected from the filename (e.g. `..._m2_extracted.txt`).
   - Enter the propane cylinder weight **before** and **after** the test.
   - Run the analysis: the app trims the start/end of the recording, computes the theoretical O₂ consumption / CO₂ production from the propane burned, compares it against the chamber's measured `VO2_c` / `VCO2_c` columns, and assigns a **Green / Yellow / Orange / Red** quality grade based on the deviation from 100% recovery.
   - Review historical trends (chart + summary stats) for the logged-in user, optionally save the report to the database, and download it as **CSV, XLSX, or PDF**.
4. **Admin workflow**
   - Create/activate/deactivate user accounts.
   - Manage **chambers** (codes used for filename detection) and **analysis settings** (combustion constants, trim window, quality thresholds) — all editable from the UI, with protected/default keys that cannot be deleted.
   - Browse a categorised **audit log** of everything tracked by the system (logins are not logged, but uploads, analyses, exports, settings changes, and user management are), with global + per-tab filters and XLSX/ZIP-of-CSV export.
   - Run **read-only** SQL queries or browse tables directly against the SQLite database via a guarded **SQL Viewer**.

---

## 2. Tech stack

| Concern | Library |
|---|---|
| UI framework | [Streamlit](https://streamlit.io) |
| Data wrangling | pandas |
| Database | SQLite (`database/chambercal.db`), accessed via the standard `sqlite3` module |
| XLSX read/write | openpyxl (via `pandas.ExcelWriter`) |
| PDF report generation | ReportLab (`platypus` flowables) |
| Hashing | `hashlib.pbkdf2_hmac` (stdlib) |

> **Note:** the repository's `requirements.txt` (from version control) lists `streamlit`, `pandas`, `numpy`, `plotly`, and `openpyxl`, but the code as shipped imports `reportlab` (for PDF export) and does not actually import `numpy` or `plotly` anywhere. If you are setting up a fresh environment, install at least:
> ```
> pip install streamlit pandas openpyxl reportlab
> ```

---

## 3. Project structure

```
chambercal/
├── main.py                      # Streamlit entry point: page config, styling, login screen
├── assets/
│   └── chambercal_logo.png      # Logo shown on the landing page and in PDF reports
├── database/
│   └── chambercal.db            # SQLite database (auto-created/seeded on first run)
└── modules/
    ├── db.py                    # All SQL access: schema, CRUD, seeding, activity log writer
    ├── auth.py                  # authenticate_user() — wraps db.py for login
    ├── dashboard.py              # Post-login header + admin/user routing + logout
    ├── admin_dashboard.py        # Admin landing tab: metrics, user table, create-user form
    ├── analysis_settings.py      # Admin tab: chambers, constants, trim & quality thresholds
    ├── audit.py                  # Admin tab: categorised activity log, filters, exports
    ├── sql_viewer.py             # Admin tab: read-only table browser + SELECT/WITH runner
    ├── analyzer.py                # Core scientific logic: file parsing + propane calculation
    ├── user_dashboard.py          # User-facing tabs: upload/run/history + saved reports
    └── exporter.py                # CSV / XLSX / PDF report builders
```

---

## 4. Architecture at a glance

Two diagrams are provided alongside this README:

- **Program flowchart** — traces a single session from app launch through login, role-based routing, and the upload → analyse → save/export loop for a regular user, with the admin-side branch (manage settings, audit, SQL viewer) shown in parallel.
- **Module interaction map** — shows the static import graph between `main.py` and the files in `modules/`, colour-coded by responsibility (data layer, auth/routing, admin tools, user dashboard, calculation/export).

### Layering

ChamberCal has no formal MVC split, but a layering convention is followed consistently:

- **`db.py`** is the *only* module that should contain SQL. Every other module calls into it rather than opening its own connection (with the exception that some functions inside `db.py` itself, and `sql_viewer.py`, connect directly to `database/chambercal.db` by relative path instead of going through `get_connection()` — see Known Issues).
- **`analyzer.py`** and **`exporter.py`** are pure-ish computation modules: they accept data in, return data/bytes out, and never touch Streamlit (`st.*`) or the database directly. This makes them the easiest modules to unit-test.
- **`auth.py`, `dashboard.py`, `admin_dashboard.py`, `analysis_settings.py`, `audit.py`, `sql_viewer.py`, `user_dashboard.py`** are all Streamlit "view" modules: they render widgets, read `st.session_state`, and call down into `db.py` / `analyzer.py` / `exporter.py`.

---

## 5. Module-by-module reference

### `main.py`
The Streamlit entry point.
- Configures the page (`st.set_page_config`), injects custom CSS for the landing page, buttons, and tabs.
- Calls `setup_database()` once per run (idempotent — uses `INSERT OR IGNORE` everywhere).
- Initialises `st.session_state` keys: `logged_in`, `user_name`, `name`, `role`, `user_id`.
- If already logged in, immediately delegates to `show_dashboard()` and stops.
- Otherwise renders a two-column landing page: branding/logo on the left, a sign-in card on the right. On submit, calls `authenticate_user()` and populates the session on success.

### `modules/auth.py`
- `authenticate_user(username, password)` — looks up the user via `db.get_user_by_username`, verifies the password with `db.verify_password`, and returns a small dict (`user_id`, `username`, `name`, `role`) or `None`.

### `modules/db.py`
The data-access layer and the largest module in the codebase. Responsibilities:
- **Connection helper** `get_connection()` — opens `database/chambercal.db` (creating the `database/` folder if missing) with `row_factory = sqlite3.Row` so rows behave like dicts.
- **Password hashing** `hash_password()` / `verify_password()` — PBKDF2-HMAC-SHA256 with a random 16-byte salt, 100,000 iterations, stored as `salt$hash`.
- **Schema creation** `initialize_database()` and `create_analysis_reports_table()` — `CREATE TABLE IF NOT EXISTS` for all five tables (see §6).
- **Seed data** `create_default_users()`, `create_default_chambers()`, `create_default_analysis_settings()` — inserted once via `INSERT OR IGNORE`.
- **`setup_database()`** — the single function called from `main.py` that runs all of the above in order every time the app starts.
- **Users** — `create_user`, `get_user_by_username`, `get_active_users`, `get_all_users`, `count_active_users`, `update_user_active_status`, `deactivate_user`.
- **Chambers** — `get_all_chambers`, `add_chamber`, `update_chamber`, `delete_chamber`, `count_chambers`.
- **Analysis settings** — `get_analysis_settings_by_group`, `add_analysis_setting`, `update_analysis_setting`, `delete_analysis_setting`.
- **Analysis reports** — `save_analysis_report`, `get_analysis_reports_for_user` (with optional date-range and chamber filters), `count_analysis_reports`, `delete_sample_analysis_reports_for_user` (dev-time helper for cleaning up `sample_*` test rows).
- **Activity log** — `log_activity(category, action, ...)` and `get_activity_logs_by_category(category)`.

### `modules/dashboard.py`
- `show_dashboard_header()` — welcome message, role, user ID, and a logout button.
- `logout_user()` — clears the relevant `st.session_state` keys and reruns.
- `show_dashboard()` — calls the header, then branches to `show_admin_dashboard()` or `show_user_dashboard()` based on `st.session_state.role`.

### `modules/admin_dashboard.py`
Renders the admin shell with four tabs: **Admin Dashboard**, **Analysis Settings**, **Audit**, **SQL Viewer**.
- `show_admin_metrics()` — three `st.metric` cards (active users, analysis reports, chambers) backed by `db.py` counters.
- `show_registered_users_table()` — an editable `st.data_editor` grid of all users with an `Active` checkbox column. On "Save Changes", diffs the edited rows against the original, calls `update_user_active_status` for each change, writes an `activity_logs` entry per change, and **blocks an admin from deactivating their own account**.
- `show_create_user_form()` — a form to create a new user (full name, username, temp password, role), guarded against duplicate usernames.
- `show_admin_dashboard()` — assembles the four tabs and delegates each to its respective module.

### `modules/analysis_settings.py`
The "Analysis Settings" admin tab, split into four sections via a `st.radio` selector (chosen over `st.tabs` specifically because radio state survives `st.rerun()`, whereas Streamlit tabs reset to the first tab):
- **Chambers** — `show_chambers_settings()` / `show_add_chamber_form()`: edit name/active/notes, delete custom chambers (the defaults `m1`/`m2` are protected via `REQUIRED_CHAMBER_CODES` and cannot be deleted), add new chambers.
- **Calculation Constants**, **Trim Settings**, **Quality Thresholds** — all three render through the shared `show_settings_group()` / `show_add_setting_form()` pair, parameterised by `setting_group`. Each editable table lets the admin change numeric values or delete custom (non-protected) settings; the ten keys in `REQUIRED_ANALYSIS_SETTING_KEYS` (molar mass, molar volume, O₂/CO₂ factors, expected RQ, trim start/end, green/yellow/orange limits) are protected because `analyzer.py` depends on them by name.
- Every successful change is written to `activity_logs` and triggers `st.rerun()`, with the success message buffered through `st.session_state.analysis_settings_message` so it survives the rerun.

### `modules/audit.py`
The "Audit" admin tab. Activity logs are grouped into six categories (`AUDIT_CATEGORIES`): Admin/User Management, Analysis Settings, Analysis Tracking, File Uploads, Exports/Backups, Database Viewer.
- **Global filters** (`show_global_audit_filters` / `apply_global_audit_filters`) — username multiselect, date range, free-text search — apply across every category tab and the export.
- **Per-tab filters** (`show_tab_audit_filters` / `apply_tab_audit_filters`) — action, target type, free-text search — apply only within the currently open tab.
- **Exports** — `create_audit_xlsx_export()` (one sheet per category plus a metadata sheet, auto-sized columns) and `create_audit_csv_zip_export()` (one CSV per category plus `export_metadata.csv`, zipped). Both export *all* logs matching the **global** filters only, independent of which tab is open.
- `show_audit_tab()` assembles the global filter bar, the export buttons, and one `st.tabs()` entry per category.

### `modules/sql_viewer.py`
The "SQL Viewer" admin tab — a deliberately constrained, read-only database console.
- `get_read_only_connection()` opens the SQLite file with `file:...?mode=ro` so the OS-level connection itself cannot write.
- `validate_read_only_query()` additionally only allows queries starting with `SELECT`/`WITH`, rejects multiple statements (`;`), and regex-blocks a list of write/DDL keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `REPLACE`, `VACUUM`, `ATTACH`, `DETACH`, `REINDEX`, `TRUNCATE`) as a defence-in-depth measure on top of the read-only connection.
- `add_limit_if_missing()` appends a `LIMIT` if the admin's query doesn't specify one, to avoid accidentally dumping a huge result set.
- **Table Browser** tab — pick a table from a dropdown, see its columns (`PRAGMA table_info`), preview N rows.
- **Custom SQL Query** tab — free-form `SELECT`/`WITH` box, with results downloadable as CSV.
- Every executed query is logged via `log_sql_viewer_query()` (category `database_viewer`), including the query text (truncated to 500 characters) and row count.

### `modules/analyzer.py`
The scientific core. Contains no Streamlit or database calls — pure functions over pandas DataFrames and dicts.
- `read_measurement_file(uploaded_file)` — parses the uploaded `.txt` as tab-separated, **European-style decimal commas** (`decimal=","`), strips whitespace from column names, requires a `datetime` column in `%d.%m.%Y %H:%M:%S` format, and drops unparseable rows.
- `trim_measurement_data(df, trim_start_min, trim_end_min)` — removes the configured warm-up/cool-down window from the start and end of the recording based on timestamps (not row counts).
- `calculate_key_statistics(trimmed_df)` — mean/SD/min/max for every numeric column in the trimmed window.
- `calculate_quality_category(deviation_percent, settings_dict)` — maps an absolute deviation-from-100%-recovery value to **Green ≤1%, Yellow ≤3%, Orange ≤5%, Red >5%** (thresholds are admin-configurable).
- `run_propane_analysis(uploaded_file, propane_before_g, propane_after_g, chamber, settings_dict)` — the orchestrating function:
  1. Read + trim the file.
  2. `propane_burned_g = before − after`; `burning_rate_g_min = burned / analysed_duration_min`.
  3. Theoretical (**SOLL**) volumes from stoichiometry: `VO2_soll = burned / molar_mass × O2_factor × molar_volume` (and analogously for VCO₂ with the CO₂ factor).
  4. Measured (**IST**) volumes: sum of the trimmed file's `VO2_c` / `VCO2_c` columns.
  5. Recovery % = IST / SOLL × 100; deviation % = `|recovery − 100|`; quality category per metric, then **overall quality = the worse of the two**.
  6. Mean of `RQ_c` if present, for comparison against the configured expected RQ.
  7. Returns one large `report_data` dict — including the trimmed DataFrame itself (used later for the XLSX export's raw-data sheet) — ready to be displayed, saved, or exported.

### `modules/user_dashboard.py`
The largest UI module, rendering two top-level tabs: **User Dashboard** and **Reports**.

*User Dashboard tab, top to bottom:*
1. `show_upload_and_test_information()` — file uploader + propane before/after inputs; logs a `file_uploads` activity entry (deduplicated per file via a session-state key so re-renders don't double-log); shows the auto-detected chamber via `detect_chamber_from_filename()` (regex match on `_m1_`, `-m2.`, `#m1`, etc.).
2. `show_historical_analysis_overview()` — date/chamber filters, a multi-metric `st.line_chart` (raw or min–max normalised) over the user's saved reports, and a summary panel (files analysed, average recovery/deviation/burning rate/duration, most common quality, a quality-count table).
3. `show_analysis_settings_used()` — read-only table of the admin-configured constants currently in effect.
4. `show_run_analysis_placeholder()` — the "Run Analysis" button; disabled until a file and valid before/after weights are present; on click, loads settings via `get_current_analysis_settings_dict()`, calls `analyzer.run_propane_analysis()`, and stores the result in `st.session_state.current_analysis_result`.
5. `show_current_analysis_result()` — renders the just-completed analysis (metrics, SOLL/IST comparison table, statistics table) and calls `show_save_report_section()`, which lets the user download the unsaved result or persist it via `db.save_analysis_report()` (logging an `analysis_tracking` event) — after saving, the report ID is remembered in session state so repeated downloads use the correct filename.

*Reports tab:* `show_reports_tab()` — date/chamber/quality filters over `db.get_analysis_reports_for_user()`, a sortable table of all matching saved reports, and a detail view for one selected report (full SOLL/IST table, parsed JSON statistics and settings snapshot, download buttons).

Shared helpers: `style_quality_cells()` / `style_historical_summary_row()` (colour-code Green/Yellow/Orange/Red cells), `build_report_file_prefix()` (standard `yyyymmdd_chambercal_<report_id>` naming), `show_report_download_buttons()` (wires up the three `exporter.py` functions to `st.download_button`, logging each click as an `exports_backups` activity).

### `modules/exporter.py`
Turns a report (either the in-memory dict from a fresh analysis, or a `pandas.Series` row loaded back from the database) into downloadable bytes. `get_value()` / `get_report_value()` abstract over those two shapes so the rest of the module doesn't care which one it received.
- `build_summary_df`, `build_comparison_df`, `build_statistics_df`, `build_settings_df`, `build_metadata_df` — shared table builders reused by all three export formats.
- `create_csv_report()` — single CSV with four stacked sections (Summary, SOLL/IST, Statistics, Settings).
- `create_xlsx_report()` — one workbook with sheets `Summary`, `SOLL_IST`, `Statistics`, `Settings_Used`, and (only when a fresh, unsaved analysis is exported) `Trimmed_Data` with the full trimmed measurement series.
- `create_pdf_report()` — a single-page-oriented ReportLab document: logo + title header, metadata table, summary and settings tables side by side, SOLL/IST comparison and statistics tables, and a footer with chamber/file name on every page. Quality cells are colour-shaded the same way as in the Streamlit UI.

---

## 6. Database schema

SQLite file: `database/chambercal.db`. All tables are created with `CREATE TABLE IF NOT EXISTS`, so re-running the app never destroys existing data.

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Login accounts | `user_id` PK, `username` UNIQUE, `password_hash` (`salt$hash`), `full_name`, `role` (`admin`/`user`), `is_active` |
| `chambers` | Metabolic chambers, matched from filenames | `chamber_id` PK, `chamber_code` UNIQUE (e.g. `m1`), `chamber_name`, `is_active`, `notes` |
| `analysis_settings` | Key-value settings used by the analyzer | `setting_id` PK, `setting_group`, `setting_key` UNIQUE, `setting_value` (REAL), `unit`, `is_editable` |
| `analysis_reports` | One row per completed/saved analysis | `report_id` PK, `user_id`, `file_name`, `chamber_*`, all SOLL/IST/recovery/deviation/quality columns, `statistics_json`, `settings_snapshot_json` |
| `activity_logs` | Append-only audit trail | `log_id` PK, `category`, `action`, `actor_user_id`, `actor_username`, `target_type`, `target_id`, `target_name`, `details`, `created_at` |

Default seed data created on first run: an `admin` user (`admin` / `admin123`) and two demo `user` accounts (`rebecca` / `user123`, `rohan` / `user123`); chambers `m1` and `m2`; and the ten default analysis settings described in §5 under *Analysis Settings*.

---

## 7. Running the app

```bash
pip install streamlit pandas openpyxl reportlab
streamlit run main.py
```

On first launch, `setup_database()` creates `database/chambercal.db` and seeds it with the default users, chambers, and settings listed above. Log in with one of the seeded accounts to explore the user or admin views.

**Expected measurement file format** (tab-separated `.txt`):
- Must include a `datetime` column formatted `dd.mm.yyyy HH:MM:SS`.
- Must include `VO2_c` and `VCO2_c` numeric columns (volumes per row, summed over the trimmed window).
- Optionally a `RQ_c` column (averaged over the trimmed window, for comparison against the expected RQ).
- Decimal values use a comma (`,`) as the decimal separator, consistent with the source measurement system.
- The chamber is detected from the filename via a code like `m1`/`m2` surrounded by `_`, `-`, `#`, or `.` — e.g. `200930_propane_10h#1_m2_extracted.txt` → Chamber 2.

---

## 8. Known issues / things to be aware of

- **Inconsistent DB path handling.** `db.get_connection()` resolves the database path relative to the project root (`Path(__file__).resolve().parent.parent / "database" / "chambercal.db"`), but several later functions in `db.py` (`count_analysis_reports`, `count_chambers`, `delete_chamber`, the `analysis_reports` functions) and all of `sql_viewer.py` instead hardcode the relative string `"database/chambercal.db"`. This works as long as Streamlit is always launched from the project root, but will silently fail to find the database if run from another working directory.
- **No password complexity rules, no rate-limiting / lockout** on login. Default seeded passwords are weak (`admin123`, `user123`) and intended only for the demo.
- **`requirements.txt` (from version control) is out of date**: it does not list `reportlab` (needed for PDF export) and lists `numpy`/`plotly`, neither of which the current code imports.
- **No automated tests** are included in the repository.
- The README and `requirements.txt` files that previously existed in the project's git history were not present in the snapshot this documentation was generated from — see §2 for the inferred dependency list.

---

## 9. Suggested next steps

- Centralise all database access through `db.get_connection()` (remove the hardcoded relative paths in `sql_viewer.py` and parts of `db.py`).
- Pin and correct `requirements.txt` to match actual imports.
- Add input validation / unit tests around `analyzer.run_propane_analysis()`, since it is the scientifically critical path.
- Consider hashing/salting review and a password-change flow — there is currently no way for a user to change their own password from the UI.
