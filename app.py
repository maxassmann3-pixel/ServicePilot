from flask import Flask, render_template, request, redirect, session, send_file, make_response
import os, hashlib, time, secrets, base64, json
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO

import psycopg2
from psycopg2.extras import RealDictCursor

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet


app = Flask(__name__)
app.secret_key = "servicepilot_postgres_v8"

ADMIN_PASSWORD = "admin123"
BERLIN = ZoneInfo("Europe/Berlin")
DATABASE_URL = os.environ.get("DATABASE_URL")

#  Voreinstellungen der Intervalle
DEFAULT_SETTINGS = {
    "machine": 500,
    "vehicle": 15000,
    "trailer": 500,
    "small_device": 100
}

#  Voreinstellung User-Rechte
DEFAULT_PERMISSIONS = {
    "create_machines": False,
    "send_reports": True,
    "do_service": False
}


CHECKLISTS = {
    "machine": [
        "Motorölstand geprüft",
        "Motoröl gewechselt",
        "Ölfilter gewechselt",
        "Hydraulikölstand geprüft",
        "Hydrauliköl gewechselt",
        "Kühlflüssigkeit geprüft",
        "Luftfilter geprüft / gereinigt",
        "Kraftstofffilter geprüft",
        "Hydraulikleitungen auf Undichtigkeiten geprüft",
        "Zylinder / Bolzen geprüft",
        "Laufwerk / Ketten / Reifen geprüft",
        "Maschine abgeschmiert",
        "Beleuchtung geprüft",
        "Scheiben / Spiegel geprüft",
        "Anbaugerät / Schnellwechsler geprüft"
    ],
    "vehicle": [
        "Motorölstand geprüft",
        "Motoröl gewechselt",
        "Ölfilter gewechselt",
        "Kühlflüssigkeit geprüft",
        "Bremsflüssigkeit geprüft",
        "Scheibenwaschwasser aufgefüllt",
        "Reifendruck geprüft",
        "Reifenprofil geprüft",
        "Beleuchtung geprüft",
        "Bremsen geprüft",
        "Innenraumfilter geprüft",
        "Kraftstofffilter geprüft",
        "TÜV / Kennzeichen geprüft",
        "Warndreieck / Verbandkasten geprüft"
    ],
    "trailer": [
        "Reifen geprüft",
        "Reifendruck geprüft",
        "Beleuchtung geprüft",
        "Stecker / Kabel geprüft",
        "Kupplung geprüft",
        "Auflaufbremse geprüft",
        "Handbremse geprüft",
        "Radlager geprüft",
        "Rahmen / Aufbau geprüft",
        "Ladefläche geprüft",
        "Zurrpunkte geprüft",
        "Schmierstellen abgeschmiert",
        "Hydraulikölstand geprüft",
        "Hydrauliköl gewechselt falls vorhanden",
        "TÜV / Kennzeichen geprüft"
    ],
    "small_device": [
        "Motorölstand geprüft",
        "Motoröl gewechselt falls nötig",
        "Kraftstoff geprüft",
        "Luftfilter gereinigt / gewechselt",
        "Zündkerze geprüft / gewechselt",
        "Kraftstofffilter geprüft",
        "Kette / Messer / Trennscheibe geprüft",
        "Schutzhaube geprüft",
        "Griffe / Gashebel geprüft",
        "Starter geprüft",
        "Getriebe / Schmierung geprüft",
        "Gerät gereinigt",
        "Schrauben / Muttern geprüft"
    ]
}


def db():
    # Öffnet eine Verbindung zur Render/PostgreSQL-Datenbank.
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL fehlt.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def sql_fetchone(query, params=()):
    # Holt genau einen Datensatz aus der Datenbank.
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def sql_fetchall(query, params=()):
    # Holt mehrere Datensätze aus der Datenbank.
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def sql_execute(query, params=()):
    # Führt Änderungen an der Datenbank durch.
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()


def now_dt():
    # Alle Zeiten werden in deutscher Zeitzone gespeichert/ausgegeben.
    return datetime.now(BERLIN)


def hash_password(password):
    # Passwörter werden niemals im Klartext gespeichert.
    return hashlib.sha256(password.encode()).hexdigest()


def is_admin():
    return session.get("admin") is True


def current_user():
    return session.get("user", "Unbekannt")


def current_fleet_id():
    return session.get("fleet_id")


def uploaded_image_to_data_url(file):
    # Wandelt hochgeladene Bilder in speicherbare Base64-Bilder um.
    if not file or file.filename == "":
        return ""

    data = file.read()

    if len(data) > 8_000_000:
        return ""

    mime = file.mimetype or "image/jpeg"
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def get_type_emoji(machine):
    # Falls kein echtes Bild vorhanden ist, bekommt jede Kategorie ein Symbol.
    t = machine.get("type")
    if t == "vehicle":
        return "🚛"
    if t == "trailer":
        return "⚙️"
    if t == "small_device":
        return "🪚"
    return "🚜"


def init_db():
    # Erstellt alle Tabellen automatisch, falls sie noch nicht existieren.
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'Baustelle',
                    custom_role TEXT DEFAULT '',
                    perm_create_machines BOOLEAN DEFAULT FALSE,
                    perm_send_reports BOOLEAN DEFAULT TRUE,
                    perm_do_service BOOLEAN DEFAULT FALSE,
                    force_token TEXT DEFAULT ''
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS fleets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    profile_image TEXT DEFAULT ''
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS machines (
                    id TEXT PRIMARY KEY,
                    fleet_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    license_plate TEXT DEFAULT '',
                    tuv TEXT DEFAULT '',
                    current_value DOUBLE PRECISION DEFAULT 0,
                    interval DOUBLE PRECISION DEFAULT 0,
                    responsible TEXT DEFAULT '',
                    current_location TEXT DEFAULT '',
                    independent BOOLEAN DEFAULT FALSE,
                    attachments TEXT DEFAULT '',
                    custom_image TEXT DEFAULT ''
                );
            """)

            cur.execute("ALTER TABLE machines ADD COLUMN IF NOT EXISTS custom_image TEXT DEFAULT '';")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    priority TEXT DEFAULT 'green',
                    location TEXT DEFAULT '',
                    independent BOOLEAN DEFAULT FALSE,
                    created_by TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    value_type TEXT DEFAULT '',
                    photo TEXT DEFAULT ''
                );
            """)

            cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS photo TEXT DEFAULT '';")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS histories (
                    id SERIAL PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    username TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    new_value DOUBLE PRECISION,
                    value_type TEXT DEFAULT '',
                    note TEXT DEFAULT '',
                    priority TEXT DEFAULT '',
                    old_location TEXT DEFAULT '',
                    new_location TEXT DEFAULT '',
                    location_change BOOLEAN DEFAULT FALSE,
                    details TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    id SERIAL PRIMARY KEY,
                    username TEXT DEFAULT '',
                    fleet_id TEXT DEFAULT '',
                    fleet_name TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    details TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            cur.execute("SELECT id FROM fleets WHERE id = 'default';")
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO fleets (id, name, password_hash, profile_image)
                    VALUES (%s, %s, %s, %s);
                """, ("default", "ServicePilot Fuhrpark", hash_password("fuhrpark123"), ""))

            for key, value in DEFAULT_SETTINGS.items():
                cur.execute("""
                    INSERT INTO settings (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO NOTHING;
                """, (key, str(value)))

            conn.commit()


def get_setting(key):
    row = sql_fetchone("SELECT value FROM settings WHERE key = %s;", (key,))
    return row["value"] if row else str(DEFAULT_SETTINGS.get(key, ""))


def get_settings():
    return {
        "machine": float(get_setting("machine")),
        "vehicle": float(get_setting("vehicle")),
        "trailer": float(get_setting("trailer")),
        "small_device": float(get_setting("small_device"))
    }


def set_setting(key, value):
    sql_execute("""
        INSERT INTO settings (key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
    """, (key, str(value)))


def get_fleet_name(fleet_id=None):
    fid = fleet_id or current_fleet_id()
    if not fid:
        return "Kein Fuhrpark gewählt"

    row = sql_fetchone("SELECT name FROM fleets WHERE id = %s;", (fid,))
    return row["name"] if row else "Kein Fuhrpark gewählt"


def get_permissions(username=None):
    if is_admin():
        #  Wenn Admin eingeloggt ist, kriegt er alle Rechte.
        return {
            "create_machines": True,
            "send_reports": True,
            "do_service": True
        }

    username = username or current_user()

    row = sql_fetchone("""
        SELECT perm_create_machines, perm_send_reports, perm_do_service
        FROM users WHERE username = %s;
    """, (username,))

    if not row:
        return DEFAULT_PERMISSIONS.copy()

    return {
        "create_machines": row["perm_create_machines"],
        "send_reports": row["perm_send_reports"],
        "do_service": row["perm_do_service"]
    }


def has_perm(permission):
    return is_admin() or get_permissions().get(permission, False)


def no_permission(message):
    return render_template("no_permission.html", message=message)


def log_action(action, details="", fleet_id=None):
    # Admin-Aktivitäten werden bewusst nicht protokolliert.
    if current_user() == "Admin":
        return

    fid = fleet_id or current_fleet_id() or ""
    fname = get_fleet_name(fid) if fid else ""

    sql_execute("""
        INSERT INTO activities (username, fleet_id, fleet_name, action, details, created_at)
        VALUES (%s, %s, %s, %s, %s, %s);
    """, (current_user(), fid, fname, action, details, now_dt()))


def unit(machine):
    return "km" if machine.get("type") == "vehicle" else "h"


def type_name(machine):
    t = machine.get("type")
    if t == "vehicle":
        return "Fahrzeug"
    if t == "trailer":
        return "Gerät / Anhänger"
    if t == "small_device":
        return "Kleingerät"
    return "Baumaschine"


def final_status(machine):
    #  Berechnet Ampelfarbe aus Restlaufzeit und offenen Notizen.
    rest = float(machine["interval"]) - float(machine["current_value"])

    service_color = "green"
    if rest <= 0:
        service_color = "red"
    #  Ab unter 50h Restlaufzeit wird´s gelb.
    elif rest <= 50:
        service_color = "yellow"

    note_color = "green"
    for note in machine.get("notes", []):
        if note.get("priority") == "red":
            note_color = "red"
            break
        elif note.get("priority") == "yellow":
            note_color = "yellow"

    if service_color == "red" or note_color == "red":
        return "red", round(rest, 2)
    if service_color == "yellow" or note_color == "yellow":
        return "yellow", round(rest, 2)
    return "green", round(rest, 2)


def attach_machine_fields(machines, notes_by_machine=None):
    # Ergänzt Maschinen um Notizen, Einheit, Bild/Emoji und Status.
    order = {"red": 0, "yellow": 1, "green": 2}

    if notes_by_machine is None:
        notes_by_machine = {}

    for m in machines:
        m["notes"] = notes_by_machine.get(m["id"], [])
        m["final_color"], m["rest"] = final_status(m)
        m["unit"] = unit(m)
        m["type_name"] = type_name(m)
        m["image_url"] = m.get("custom_image", "")
        m["emoji"] = get_type_emoji(m)

    return sorted(machines, key=lambda x: (order[x["final_color"]], x["rest"]))


def get_machines(fleet_id=None):
    # Lädt Maschinen und Notizen gebündelt -> schneller.
    fid = fleet_id or current_fleet_id() or "default"
    machines = sql_fetchall("SELECT * FROM machines WHERE fleet_id = %s;", (fid,))

    if not machines:
        return []

    ids = [m["id"] for m in machines]
    notes = sql_fetchall("SELECT * FROM notes WHERE machine_id = ANY(%s) ORDER BY id DESC;", (ids,))

    notes_by_machine = {}
    for n in notes:
        notes_by_machine.setdefault(n["machine_id"], []).append(n)

    return attach_machine_fields(machines, notes_by_machine)


def get_all_machines_for_admin():
    # Admin-Dashboard lädt alle Maschinen auf einmal, damit die Seite schneller reagiert.
    machines = sql_fetchall("SELECT * FROM machines ORDER BY name ASC;")

    if not machines:
        return []

    ids = [m["id"] for m in machines]
    notes = sql_fetchall("SELECT * FROM notes WHERE machine_id = ANY(%s) ORDER BY id DESC;", (ids,))

    notes_by_machine = {}
    for n in notes:
        notes_by_machine.setdefault(n["machine_id"], []).append(n)

    return attach_machine_fields(machines, notes_by_machine)


def image_data_to_reportlab(data_url, max_width=4.5 * cm, max_height=3.2 * cm):
    # Fügt hochgeladene Bilder in PDFs ein. Externe URLs werden bewusst nicht genutzt -> Urheberrecht.
    if not data_url or not str(data_url).startswith("data:image"):
        return ""

    try:
        header, encoded = data_url.split(",", 1)
        raw = base64.b64decode(encoded)
        bio = BytesIO(raw)
        img = Image(bio)
        img._restrictSize(max_width, max_height)
        return img
    except Exception:
        return ""


def pdf_footer(canvas, doc):
    # Schwarzer Seitenrand und Seitenzahlen für .pdf-Datei.
    canvas.saveState()
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(1)
    canvas.rect(1.2 * cm, 1.2 * cm, A4[0] - 2.4 * cm, A4[1] - 2.4 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(A4[0] / 2, 0.75 * cm, f"Seite {doc.page}")
    canvas.restoreState()


def status_dot_table(machine):
    # Status wird im PDF als Emoji dargestellt.
    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    if machine["final_color"] == "red":
        return Paragraph("🔴 Rot / dringend", normal)
    if machine["final_color"] == "yellow":
        return Paragraph("🟡 Gelb / Achtung", normal)
    return Paragraph("🟢 Grün / OK", normal)


def checkbox_paragraph(text, style):
    # Unicode-Kästchen für Papierausdruck. Mitarbeiter können es später mit Stift abhaken.
    return Paragraph(f"☐ {text}", style)


def build_fleet_pdf(fleet, machines):
    # Erstellt einen kompakten Fuhrparkbericht mit kleinen Sedcards.
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    story = []

    logo = image_data_to_reportlab(fleet.get("profile_image"), 3.0 * cm, 2.0 * cm)

    header = Table([
        [
            Paragraph(f"<b>Fuhrparkbericht: {fleet['name']}</b>", styles["Title"]),
            logo
        ]
    ], colWidths=[12 * cm, 4 * cm])

    header.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))

    story.append(header)
    story.append(Paragraph(f"Erstellt am: {now_dt().strftime('%d.%m.%Y %H:%M:%S')} Uhr", normal))
    story.append(Spacer(1, 0.35 * cm))

    for m in machines:
        stand_label = "Kilometerstand" if m["type"] == "vehicle" else "Betriebsstundenstand"
        unit_text = "km" if m["type"] == "vehicle" else "h"

        img = image_data_to_reportlab(m.get("image_url"), 2.4 * cm, 1.8 * cm)
        if not img:
            img = Paragraph(f"<font size='24'>{m.get('emoji', '🚜')}</font>", normal)

        details = [
            Paragraph(f"<b>{m['name']}</b>", normal),
            status_dot_table(m),
            Paragraph(f"{m['type_name']}", normal),
            Paragraph(f"{stand_label}: {m['current_value']} {unit_text}", normal),
            Paragraph(f"Rest bis Service: {m['rest']} {unit_text}", normal),
            Paragraph(f"Standort: {'ortsunabhängig' if m.get('independent') else m.get('current_location', '')}", normal),
            Paragraph(f"Verantwortlicher: {m.get('responsible', '')}", normal)
        ]

        table = Table([[img, details]], colWidths=[2.8 * cm, 13.2 * cm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fc")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))

        story.append(table)
        story.append(Spacer(1, 0.18 * cm))

    doc.build(story, onFirstPage=pdf_footer, onLaterPages=pdf_footer)
    buffer.seek(0)
    return buffer


def build_service_pdf(machine):
    # Erstellt die druckbare Servicekarte für eine einzelne Maschine.
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.7 * cm,
        leftMargin=1.7 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    story = []

    fleet = sql_fetchone("SELECT * FROM fleets WHERE id = %s;", (machine["fleet_id"],))
    logo = image_data_to_reportlab(fleet.get("profile_image") if fleet else "", 3.0 * cm, 2.0 * cm)

    header = Table([
        [
            Paragraph(f"<b>Servicekarte: {machine['name']}</b>", styles["Title"]),
            logo
        ]
    ], colWidths=[12 * cm, 4 * cm])

    header.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))

    story.append(header)
    story.append(Paragraph(f"Ausgedruckt von: {current_user()}", normal))
    story.append(Paragraph(f"Erstellt am: {now_dt().strftime('%d.%m.%Y %H:%M:%S')} Uhr", normal))
    story.append(Spacer(1, 0.35 * cm))

    img = image_data_to_reportlab(machine.get("image_url"), 7.5 * cm, 4.0 * cm)
    if img:
        story.append(img)
    else:
        story.append(Paragraph(f"<font size='38'>{machine.get('emoji', '🚜')}</font>", normal))

    story.append(Spacer(1, 0.25 * cm))
    story.append(status_dot_table(machine))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph(f"<b>Art:</b> {machine['type_name']}", normal))
    story.append(Paragraph(f"<b>Standort:</b> {machine.get('current_location', '')}", normal))
    story.append(Paragraph(f"<b>Verantwortlicher:</b> {machine.get('responsible', '')}", normal))
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("<b>Wartungscheckliste:</b>", styles["Heading2"]))

    checklist = CHECKLISTS.get(machine.get("type", "machine"), CHECKLISTS["machine"])
    for item in checklist:
        story.append(checkbox_paragraph(item, normal))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("<b>Offene Mängel / Notizen:</b>", styles["Heading2"]))

    if machine.get("notes"):
        for n in machine["notes"]:
            story.append(checkbox_paragraph(f"{n.get('priority', '')}: {n.get('text', '')}", normal))
            note_img = image_data_to_reportlab(n.get("photo"), 8 * cm, 4 * cm)
            if note_img:
                story.append(note_img)
                story.append(Spacer(1, 0.15 * cm))
    else:
        story.append(Paragraph("Keine offenen Mängel vorhanden.", normal))

    story.append(Spacer(1, 1.4 * cm))

    sign_table = Table([
        ["______________________________", "______________________________"],
        ["Ort, Datum", "Unterschrift"]
    ], colWidths=[8 * cm, 8 * cm])

    sign_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story.append(sign_table)

    doc.build(story, onFirstPage=pdf_footer, onLaterPages=pdf_footer)
    buffer.seek(0)
    return buffer


def load_old_json_machines():
    # Importiert alte lokale JSON-Daten, falls man Programm neu mit Demo-Daten generieren will.
    if not os.path.exists("data.json"):
        return []

    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    if "fleets" in data and "default" in data["fleets"]:
        return data["fleets"]["default"]

    if "shared_fleet" in data:
        return data["shared_fleet"]

    if "Max" in data:
        return data["Max"]

    return []


def clear_entire_program():
    # Löscht alles und legt danach einen leeren Standard-Fuhrpark an.
    sql_execute("DELETE FROM notes;")
    sql_execute("DELETE FROM histories;")
    sql_execute("DELETE FROM activities;")
    sql_execute("DELETE FROM machines;")
    sql_execute("DELETE FROM users;")
    sql_execute("DELETE FROM fleets;")

    sql_execute("""
        INSERT INTO fleets (id, name, password_hash, profile_image)
        VALUES (%s, %s, %s, %s);
    """, ("default", "ServicePilot Fuhrpark", hash_password("fuhrpark123"), ""))


@app.before_request
def check_force_logout():
    # Prüft bei jedem Seitenaufruf, ob ein Nutzer vom Admin rausgeworfen wurde, wenn ja, kommt er nicht rein.
    if "user" in session and not is_admin():
        row = sql_fetchone("SELECT force_token FROM users WHERE username = %s;", (session["user"],))
        if row and session.get("force_token") != row["force_token"]:
            theme = session.get("theme", "dark")
            session.clear()
            session["theme"] = theme
            return redirect("/")


@app.context_processor
def inject_global_data():
    # Die Werte stehen in allen Seiten zur Verfügung.
    return {
        "fleet_name": get_fleet_name(),
        "permissions": get_permissions() if "user" in session else {},
        "is_admin": is_admin(),
        "theme": session.get("theme", request.cookies.get("theme", "dark")),
        "current_fleet_id": current_fleet_id()
    }


@app.route("/")
def login_page():
    if "theme" not in session:
        session["theme"] = request.cookies.get("theme", "dark")
    return render_template("login.html")


@app.route("/toggle-theme", methods=["POST"])
def toggle_theme():
    # Speichert hell/dunkel dauerhaft im Cookie und zusätzlich in der Session.
    current = session.get("theme", request.cookies.get("theme", "dark"))
    new_theme = "light" if current == "dark" else "dark"
    session["theme"] = new_theme

    response = make_response(redirect(request.referrer or "/dashboard"))
    response.set_cookie("theme", new_theme, max_age=60 * 60 * 24 * 365)
    return response


@app.route("/impressum")
def impressum():
    return render_template("impressum.html")


@app.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html")


@app.route("/denied")
def denied():
    return render_template("denied.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    row = sql_fetchone("SELECT * FROM users WHERE username = %s;", (username,))

    if row and row["password_hash"] == hash_password(password):
        token = row["force_token"] or secrets.token_hex(8)
        sql_execute("UPDATE users SET force_token = %s WHERE username = %s;", (token, username))

        theme = session.get("theme", request.cookies.get("theme", "dark"))
        session.clear()
        session["theme"] = theme
        session["user"] = username
        session["admin"] = False
        session["force_token"] = token

        log_action("Login", "Benutzer hat sich angemeldet.")
        return redirect("/fleet-select")

    return redirect("/denied")


@app.route("/admin-login", methods=["POST"])
def admin_login():
    if request.form["admin_password"] == ADMIN_PASSWORD:
        theme = session.get("theme", request.cookies.get("theme", "dark"))
        session.clear()
        session["theme"] = theme
        session["user"] = "Admin"
        session["admin"] = True
        return redirect("/admin/overview")

    return redirect("/denied")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        #  Neuanlegung Nutzer-Account.
        username = request.form["username"]
        password = request.form["password"]

        exists = sql_fetchone("SELECT username FROM users WHERE username = %s;", (username,))
        if exists:
            return "Benutzer existiert bereits"

        token = secrets.token_hex(8)

        sql_execute("""
            INSERT INTO users (
                username, password_hash, role, custom_role,
                perm_create_machines, perm_send_reports, perm_do_service, force_token
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (username, hash_password(password), "Baustelle", "", False, True, False, token))

        theme = session.get("theme", request.cookies.get("theme", "dark"))
        session.clear()
        session["theme"] = theme
        session["user"] = username
        session["admin"] = False
        session["force_token"] = token

        log_action("Registrierung", f"Benutzer '{username}' wurde erstellt.")
        return redirect("/fleet-select")

    return render_template("register.html")


@app.route("/fleet-select")
def fleet_select():
    if "user" not in session:
        return redirect("/")
    if is_admin():
        return redirect("/admin/overview")

    fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;")
    return render_template("fleet_select.html", fleets=fleets)


@app.route("/join-fleet", methods=["POST"])
def join_fleet():
    fleet_id = request.form["fleet_id"]
    password = request.form["fleet_password"]

    fleet = sql_fetchone("SELECT * FROM fleets WHERE id = %s;", (fleet_id,))

    if fleet and fleet["password_hash"] == hash_password(password):
        session["fleet_id"] = fleet_id
        log_action("Fuhrpark gewählt", f"Benutzer ist Fuhrpark '{fleet['name']}' beigetreten.", fleet_id)
        return redirect("/dashboard")

    return redirect("/denied")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    if is_admin():
        return redirect("/admin/overview")

    if not current_fleet_id():
        return redirect("/fleet-select")

    machines = get_machines()

    red = len([m for m in machines if m["final_color"] == "red"])
    yellow = len([m for m in machines if m["final_color"] == "yellow"])
    green = len([m for m in machines if m["final_color"] == "green"])

    return render_template("dashboard.html", user=current_user(), machines=machines, red=red, yellow=yellow, green=green)


@app.route("/machines", methods=["GET", "POST"])
def machines():
    if "user" not in session:
        return redirect("/")

    if not is_admin() and not current_fleet_id():
        return redirect("/fleet-select")

    if request.method == "POST":
        if not has_perm("create_machines"):
            return no_permission("Du hast keine Berechtigung, Maschinen anzulegen.")

        target_fleet_id = request.form.get("fleet_id") if is_admin() else current_fleet_id()

        uploaded = uploaded_image_to_data_url(request.files.get("machine_image_file"))
        custom_image = uploaded or request.form.get("machine_image_url", "")

        sql_execute("""
            INSERT INTO machines (
                id, fleet_id, name, type, license_plate, tuv,
                current_value, interval, responsible,
                current_location, independent, attachments, custom_image
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (
            str(time.time()).replace(".", ""),
            target_fleet_id,
            request.form["name"],
            request.form["type"],
            request.form.get("license_plate", ""),
            request.form.get("tuv", ""),
            float(request.form["current_value"]),
            float(request.form["interval"]),
            request.form["responsible"],
            request.form["current_location"],
            "independent" in request.form,
            request.form["attachments"],
            custom_image
        ))

    fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;") if is_admin() else []

    if is_admin():
        machines_data = get_all_machines_for_admin()
    else:
        machines_data = get_machines()

    return render_template("machines.html", machines=machines_data, edit_machine=None, fleets=fleets)


@app.route("/edit-machine/<machine_id>", methods=["GET", "POST"])
def edit_machine(machine_id):
    if "user" not in session:
        return redirect("/")

    if not has_perm("create_machines"):
        return no_permission("Du hast keine Berechtigung, Maschinen zu bearbeiten.")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    if not machine:
        return "Eintrag nicht gefunden"

    if not is_admin() and machine["fleet_id"] != current_fleet_id():
        return no_permission("Du hast keine Berechtigung, diese Maschine zu bearbeiten.")

    if request.method == "POST":
        uploaded = uploaded_image_to_data_url(request.files.get("machine_image_file"))
        submitted_url = request.form.get("machine_image_url", "").strip()

        if uploaded:
            custom_image = uploaded
        elif submitted_url:
            custom_image = submitted_url
        else:
            custom_image = machine.get("custom_image", "")

        sql_execute("""
            UPDATE machines SET
                name=%s, type=%s, license_plate=%s, tuv=%s,
                current_value=%s, interval=%s, responsible=%s,
                current_location=%s, independent=%s, attachments=%s, custom_image=%s
            WHERE id=%s;
        """, (
            request.form["name"],
            request.form["type"],
            request.form.get("license_plate", ""),
            request.form.get("tuv", ""),
            float(request.form["current_value"]),
            float(request.form["interval"]),
            request.form["responsible"],
            request.form["current_location"],
            "independent" in request.form,
            request.form["attachments"],
            custom_image,
            machine_id
        ))

        return redirect("/machines")

    fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;") if is_admin() else []
    machines_data = get_machines(machine["fleet_id"]) if is_admin() else get_machines()

    return render_template("machines.html", machines=machines_data, edit_machine=machine, fleets=fleets)


@app.route("/reports", methods=["GET", "POST"])
def reports():
    if "user" not in session:
        return redirect("/")

    if not is_admin() and not current_fleet_id():
        return redirect("/fleet-select")

    if not has_perm("send_reports"):
        return no_permission("Du hast keine Berechtigung, Tagesberichte zu senden.")

    if request.method == "POST":
        machine_id = request.form["machine_id"]
        machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))

        if not is_admin() and machine["fleet_id"] != current_fleet_id():
            return no_permission("Du hast keine Berechtigung für diese Maschine.")

        exact = request.form.get("new_value", "").strip()
        today_used = request.form.get("today_used", "").strip()

        if not exact and not today_used:
            return "Bitte aktuellen Stand oder heute gefahrene Stunden/Kilometer eintragen."

        if exact:
            new_value = float(exact)
            value_type = "exakt"
        else:
            new_value = float(machine["current_value"]) + float(today_used)
            value_type = f"heute gefahren: {today_used} {unit(machine)}"

        old_value = machine["current_value"]
        old_location = machine["current_location"]

        location_change = "location_change" in request.form
        selected_location = request.form.get("selected_location", "")
        new_location_select = request.form.get("new_location_select", "")
        new_location_text = request.form.get("new_location_text", "").strip()

        final_location = new_location_text if location_change and new_location_text else new_location_select if location_change else selected_location

        sql_execute("""
            UPDATE machines SET current_value=%s, current_location=%s, independent=%s
            WHERE id=%s;
        """, (new_value, final_location, "independent" in request.form, machine_id))

        note = request.form["note"]
        priority = request.form["priority"]
        note_photo = uploaded_image_to_data_url(request.files.get("note_photo_file"))

        if note.strip() or note_photo:
            sql_execute("""
                INSERT INTO notes (
                    machine_id, text, priority, location, independent,
                    created_by, created_at, value_type, photo
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """, (
                machine_id,
                note,
                priority,
                final_location,
                "independent" in request.form,
                current_user(),
                now_dt(),
                value_type,
                note_photo
            ))

        sql_execute("""
            INSERT INTO histories (
                machine_id, username, action, new_value, value_type,
                note, priority, old_location, new_location,
                location_change, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (
            machine_id,
            current_user(),
            "Tagesbericht",
            new_value,
            value_type,
            note,
            priority,
            old_location,
            final_location,
            location_change,
            now_dt()
        ))

        log_action(
            "Tagesbericht",
            f"{machine['name']} | {old_value} → {new_value} ({value_type}) | Standort: {old_location} → {final_location}",
            machine["fleet_id"]
        )

    if is_admin():
        machines_list = get_all_machines_for_admin()
        fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;")
    else:
        machines_list = get_machines()
        fleets = []

    locations = sorted({m["current_location"] for m in machines_list if m.get("current_location")}, key=lambda x: x.lower())

    return render_template("reports.html", machines=machines_list, locations=locations, fleets=fleets)


@app.route("/service")
def service():
    if "user" not in session:
        return redirect("/")

    if not is_admin() and not current_fleet_id():
        return redirect("/fleet-select")

    if not has_perm("do_service"):
        return no_permission("Du hast keine Berechtigung, Servicearbeiten durchzuführen.")

    machines_data = get_all_machines_for_admin() if is_admin() else get_machines()

    return render_template("service.html", machines=machines_data, sort_by="status", filter_value="")


@app.route("/service-check/<machine_id>")
def service_check(machine_id):
    if "user" not in session:
        return redirect("/")

    if not has_perm("do_service"):
        return no_permission("Du hast keine Berechtigung, Servicearbeiten durchzuführen.")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    if not machine:
        return "Eintrag nicht gefunden"

    if not is_admin() and machine["fleet_id"] != current_fleet_id():
        return no_permission("Du hast keine Berechtigung für diese Maschine.")

    machine = attach_machine_fields([machine], {
        machine_id: sql_fetchall("SELECT * FROM notes WHERE machine_id=%s ORDER BY id DESC;", (machine_id,))
    })[0]

    checklist = CHECKLISTS.get(machine.get("type", "machine"), CHECKLISTS["machine"])

    return render_template("service_check.html", machine=machine, checklist=checklist)


@app.route("/service-done/<machine_id>", methods=["POST"])
def service_done(machine_id):
    if "user" not in session:
        return redirect("/")

    if not has_perm("do_service"):
        return no_permission("Du hast für diese Aktion keine Berechtigung.")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    if not machine:
        return "Eintrag nicht gefunden"

    if not is_admin() and machine["fleet_id"] != current_fleet_id():
        return no_permission("Du hast keine Berechtigung für diese Maschine.")

    settings = get_settings()
    increase = float(settings.get(machine["type"], 500))

    sql_execute("UPDATE machines SET interval = interval + %s WHERE id = %s;", (increase, machine_id))

    for note_id in request.form.getlist("resolved_note_ids"):
        sql_execute("DELETE FROM notes WHERE id = %s;", (note_id,))

    new_note = request.form.get("new_note", "").strip()
    new_note_photo = uploaded_image_to_data_url(request.files.get("new_note_photo_file"))

    if new_note or new_note_photo:
        sql_execute("""
            INSERT INTO notes (
                machine_id, text, priority, location, independent,
                created_by, created_at, photo
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
        """, (
            machine_id,
            new_note,
            request.form.get("new_note_priority", "green"),
            machine.get("current_location", ""),
            machine.get("independent", False),
            current_user(),
            now_dt(),
            new_note_photo
        ))

    checked = ", ".join(request.form.getlist("checklist"))

    sql_execute("""
        INSERT INTO histories (machine_id, username, action, details, created_at)
        VALUES (%s,%s,%s,%s,%s);
    """, (machine_id, current_user(), "Service erledigt", checked, now_dt()))

    log_action("Service erledigt", f"{machine['name']} | Intervall erhöht um {increase}", machine["fleet_id"])

    return redirect("/service")


@app.route("/fleet-pdf/<fleet_id>")
def fleet_pdf(fleet_id):
    # PDF wird als Download gesendet, damit die App-Seite offen bleibt.
    if "user" not in session:
        return redirect("/")

    if not is_admin() and current_fleet_id() != fleet_id:
        return no_permission("Du hast keine Berechtigung, diesen Fuhrpark zu exportieren.")

    fleet = sql_fetchone("SELECT * FROM fleets WHERE id = %s;", (fleet_id,))
    if not fleet:
        return "Fuhrpark nicht gefunden"

    machines = get_machines(fleet_id)
    pdf = build_fleet_pdf(fleet, machines)

    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Fuhrpark_{fleet['name']}.pdf"
    )


@app.route("/service-pdf/<machine_id>")
def service_pdf(machine_id):
    # PDF wird als Download gesendet, damit kein Zurückklicken nötig ist.
    if "user" not in session:
        return redirect("/")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    if not machine:
        return "Maschine nicht gefunden"

    if not is_admin() and current_fleet_id() != machine["fleet_id"]:
        return no_permission("Du hast keine Berechtigung, diese Servicekarte zu exportieren.")

    machine = attach_machine_fields([machine], {
        machine_id: sql_fetchall("SELECT * FROM notes WHERE machine_id=%s ORDER BY id DESC;", (machine_id,))
    })[0]

    pdf = build_service_pdf(machine)

    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Servicekarte_{machine['name']}.pdf"
    )


@app.route("/admin")
def admin():
    if not is_admin():
        return redirect("/dashboard")
    return redirect("/admin/overview")


@app.route("/admin/overview")
def admin_overview():
    if not is_admin():
        return redirect("/dashboard")

    fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;")
    all_machines = get_all_machines_for_admin()

    overview = []

    for fleet in fleets:
        machines = [m for m in all_machines if m["fleet_id"] == fleet["id"]]

        red = len([m for m in machines if m["final_color"] == "red"])
        yellow = len([m for m in machines if m["final_color"] == "yellow"])
        green = len([m for m in machines if m["final_color"] == "green"])
        total = red + yellow + green

        red_deg = 0
        yellow_deg = 0

        if total > 0:
            red_deg = round((red / total) * 360, 1)
            yellow_deg = round(((red + yellow) / total) * 360, 1)

        overview.append({
            "fleet": fleet,
            "machines": machines,
            "red": red,
            "yellow": yellow,
            "green": green,
            "total": total,
            "red_deg": red_deg,
            "yellow_deg": yellow_deg
        })

    return render_template("admin_overview.html", overview=overview)


@app.route("/admin/fleets", methods=["GET", "POST"])
def admin_fleets():
    if not is_admin():
        return redirect("/dashboard")

    if request.method == "POST":
        uploaded = uploaded_image_to_data_url(request.files.get("profile_image_file"))
        profile_image = uploaded or request.form.get("profile_image", "")
        action = request.form.get("action")

        if action == "create_fleet":
            sql_execute("""
                INSERT INTO fleets (id, name, password_hash, profile_image)
                VALUES (%s,%s,%s,%s);
            """, (
                "fleet_" + str(time.time()).replace(".", ""),
                request.form["fleet_name"],
                hash_password(request.form["fleet_password"]),
                profile_image
            ))

        elif action == "update_fleet":
            fleet_id = request.form["fleet_id"]

            if request.form.get("fleet_password"):
                sql_execute("""
                    UPDATE fleets SET name=%s, password_hash=%s, profile_image=%s
                    WHERE id=%s;
                """, (
                    request.form["fleet_name"],
                    hash_password(request.form["fleet_password"]),
                    profile_image,
                    fleet_id
                ))
            else:
                sql_execute("""
                    UPDATE fleets SET name=%s, profile_image=COALESCE(NULLIF(%s,''), profile_image)
                    WHERE id=%s;
                """, (request.form["fleet_name"], profile_image, fleet_id))

        return redirect("/admin/fleets")

    fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;")
    return render_template("admin_fleets.html", fleets=fleets)


@app.route("/admin/delete-machine/<machine_id>", methods=["POST"])
def admin_delete_machine(machine_id):
    if not is_admin():
        return redirect("/dashboard")

    if request.form.get("confirm_admin_password") != ADMIN_PASSWORD:
        return redirect("/denied")

    sql_execute("DELETE FROM notes WHERE machine_id = %s;", (machine_id,))
    sql_execute("DELETE FROM histories WHERE machine_id = %s;", (machine_id,))
    sql_execute("DELETE FROM machines WHERE id = %s;", (machine_id,))

    return redirect("/admin/overview")


@app.route("/admin/delete-fleet/<fleet_id>", methods=["POST"])
def admin_delete_fleet(fleet_id):
    if not is_admin():
        return redirect("/dashboard")

    if request.form.get("confirm_admin_password") != ADMIN_PASSWORD:
        return redirect("/denied")

    sql_execute("DELETE FROM notes WHERE machine_id IN (SELECT id FROM machines WHERE fleet_id=%s);", (fleet_id,))
    sql_execute("DELETE FROM histories WHERE machine_id IN (SELECT id FROM machines WHERE fleet_id=%s);", (fleet_id,))
    sql_execute("DELETE FROM machines WHERE fleet_id=%s;", (fleet_id,))
    sql_execute("DELETE FROM activities WHERE fleet_id=%s;", (fleet_id,))
    sql_execute("DELETE FROM fleets WHERE id=%s;", (fleet_id,))

    return redirect("/admin/fleets")


@app.route("/admin/clear-program", methods=["POST"])
def admin_clear_program():
    if not is_admin():
        return redirect("/dashboard")

    if request.form.get("confirm_admin_password") != ADMIN_PASSWORD:
        return redirect("/denied")

    clear_entire_program()
    return redirect("/admin/overview")


@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if not is_admin():
        return redirect("/dashboard")

    if request.method == "POST":
        username = request.form.get("username")

        if request.form.get("action") == "update_user":
            sql_execute("""
                UPDATE users SET
                    role=%s,
                    custom_role=%s,
                    perm_create_machines=%s,
                    perm_send_reports=%s,
                    perm_do_service=%s
                WHERE username=%s;
            """, (
                request.form.get("role", "Baustelle"),
                request.form.get("custom_role", ""),
                "create_machines" in request.form,
                "send_reports" in request.form,
                "do_service" in request.form,
                username
            ))

        elif request.form.get("action") == "force_logout":
            sql_execute("UPDATE users SET force_token=%s WHERE username=%s;", (secrets.token_hex(16), username))

        return redirect("/admin/users")

    users = sql_fetchall("SELECT * FROM users ORDER BY username ASC;")
    return render_template("admin_users.html", users=users)


@app.route("/admin/activity", methods=["GET", "POST"])
def admin_activity():
    if not is_admin():
        return redirect("/dashboard")

    if request.method == "POST":
        if request.form.get("action") == "clear_activity":
            sql_execute("DELETE FROM activities;")
        return redirect("/admin/activity")

    filter_user = request.args.get("user", "")
    users = sql_fetchall("SELECT username FROM users ORDER BY username ASC;")

    if filter_user:
        logs = sql_fetchall("SELECT * FROM activities WHERE username=%s ORDER BY created_at DESC;", (filter_user,))
    else:
        logs = sql_fetchall("SELECT * FROM activities ORDER BY created_at DESC LIMIT 500;")

    return render_template("admin_activity.html", logs=logs, users=users, filter_user=filter_user)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if not is_admin():
        return redirect("/dashboard")

    settings_data = get_settings()

    if request.method == "POST":
        set_setting("machine", request.form["machine"])
        set_setting("vehicle", request.form["vehicle"])
        set_setting("trailer", request.form["trailer"])
        set_setting("small_device", request.form["small_device"])
        return redirect("/settings")

    return render_template("settings.html", settings=settings_data)


@app.route("/logout")
def logout():
    theme = session.get("theme", request.cookies.get("theme", "dark"))
    log_action("Logout", "Benutzer hat sich abgemeldet.")
    session.clear()
    session["theme"] = theme
    return redirect("/")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)