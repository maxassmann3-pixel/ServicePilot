from flask import Flask, render_template, request, redirect, session
import os, hashlib, time, secrets, base64, json
from datetime import datetime
from zoneinfo import ZoneInfo
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = "servicepilot_postgres_v3"

ADMIN_PASSWORD = "admin123"
BERLIN = ZoneInfo("Europe/Berlin")
DATABASE_URL = os.environ.get("DATABASE_URL")

DEFAULT_PERMISSIONS = {
    "create_machines": False,
    "send_reports": True,
    "do_service": False
}

DEFAULT_SETTINGS = {
    "machine": 500,
    "vehicle": 15000,
    "trailer": 500,
    "small_device": 100
}


def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL fehlt.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def sql_fetchone(query, params=()):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def sql_fetchall(query, params=()):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def sql_execute(query, params=()):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()


def now_dt():
    return datetime.now(BERLIN)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def is_admin():
    return session.get("admin") is True


def current_user():
    return session.get("user", "Unbekannt")


def current_fleet_id():
    return session.get("fleet_id")


def uploaded_image_to_data_url(file):
    if not file or file.filename == "":
        return ""

    data = file.read()

    if len(data) > 2_500_000:
        return ""

    mime = file.mimetype or "image/jpeg"
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def init_db():
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

            cur.execute("""
                ALTER TABLE machines
                ADD COLUMN IF NOT EXISTS custom_image TEXT DEFAULT '';
            """)

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

            cur.execute("""
                ALTER TABLE notes
                ADD COLUMN IF NOT EXISTS photo TEXT DEFAULT '';
            """)

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


def default_machine_image(machine):
    name = machine.get("name", "").lower()
    t = machine.get("type", "machine")

    if machine.get("custom_image"):
        return machine.get("custom_image")

    if "liebherr" in name and ("bagger" in name or "r9" in name or "r 9" in name):
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Liebherr_934_Hydraulic_Excavator.jpg/640px-Liebherr_934_Hydraulic_Excavator.jpg"

    if "radlader" in name or "wheel loader" in name or "lader" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/CAT_950M_wheel_loader.jpg/640px-CAT_950M_wheel_loader.jpg"

    if "stihl" in name or "kettensäge" in name or "motorsäge" in name or "freischneider" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Chainsaw_Stihl_MS_170.jpg/640px-Chainsaw_Stihl_MS_170.jpg"

    if "rasenmäher" in name or "rüttel" in name or "platte" in name or t == "small_device":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Plate_compactor.jpg/640px-Plate_compactor.jpg"

    if "anhänger" in name or "trailer" in name or t == "trailer":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Car_trailer.jpg/640px-Car_trailer.jpg"

    if "ford" in name or "transit" in name or "vw" in name or "crafter" in name or t == "vehicle":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Ford_Transit_Connect_%28III%29_IMG_8620.jpg/640px-Ford_Transit_Connect_%28III%29_IMG_8620.jpg"

    if "deutz" in name or "lamborghini" in name or "traktor" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/Deutz-Fahr_Agrotron_165.7.jpg/640px-Deutz-Fahr_Agrotron_165.7.jpg"

    return "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Liebherr_934_Hydraulic_Excavator.jpg/640px-Liebherr_934_Hydraulic_Excavator.jpg"


def final_status(machine):
    rest = float(machine["interval"]) - float(machine["current_value"])

    service_color = "green"
    if rest <= 0:
        service_color = "red"
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


def prepare_machines(machines):
    order = {"red": 0, "yellow": 1, "green": 2}

    for m in machines:
        notes = sql_fetchall("SELECT * FROM notes WHERE machine_id = %s ORDER BY id DESC;", (m["id"],))
        m["notes"] = notes
        m["final_color"], m["rest"] = final_status(m)
        m["unit"] = unit(m)
        m["type_name"] = type_name(m)
        m["image_url"] = default_machine_image(m)

    return sorted(machines, key=lambda x: (order[x["final_color"]], x["rest"]))


def get_machines(fleet_id=None):
    fid = fleet_id or current_fleet_id() or "default"
    machines = sql_fetchall("SELECT * FROM machines WHERE fleet_id = %s;", (fid,))
    return prepare_machines(machines)


def load_old_json_machines():
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


@app.before_request
def check_force_logout():
    if "user" in session and not is_admin():
        row = sql_fetchone("SELECT force_token FROM users WHERE username = %s;", (session["user"],))
        if row and session.get("force_token") != row["force_token"]:
            session.clear()
            return redirect("/")


@app.context_processor
def inject_global_data():
    return {
        "fleet_name": get_fleet_name(),
        "permissions": get_permissions() if "user" in session else {},
        "is_admin": is_admin()
    }


@app.route("/")
def login_page():
    return render_template("login.html")


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

        session["user"] = username
        session["admin"] = False
        session["force_token"] = token
        session.pop("fleet_id", None)

        log_action("Login", "Benutzer hat sich angemeldet.")
        return redirect("/fleet-select")

    return redirect("/denied")


@app.route("/admin-login", methods=["POST"])
def admin_login():
    if request.form["admin_password"] == ADMIN_PASSWORD:
        session["user"] = "Admin"
        session["admin"] = True
        session["fleet_id"] = "default"
        return redirect("/admin/fleets")

    return redirect("/denied")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
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
        """, (
            username, hash_password(password), "Baustelle", "",
            False, True, False, token
        ))

        session["user"] = username
        session["admin"] = False
        session["force_token"] = token
        session.pop("fleet_id", None)

        log_action("Registrierung", f"Benutzer '{username}' wurde erstellt.")
        return redirect("/fleet-select")

    return render_template("register.html")


@app.route("/fleet-select")
def fleet_select():
    if "user" not in session:
        return redirect("/")
    if is_admin():
        return redirect("/admin/fleets")

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
    if not current_fleet_id():
        return redirect("/fleet-select")

    if request.method == "POST":
        if not has_perm("create_machines"):
            return no_permission("Du hast keine Berechtigung, Maschinen anzulegen.")

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
            current_fleet_id(),
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

        log_action("Eintrag angelegt", f"{request.form['name']} wurde angelegt.")

    return render_template("machines.html", machines=get_machines(), edit_machine=None)


@app.route("/edit-machine/<machine_id>", methods=["GET", "POST"])
def edit_machine(machine_id):
    if "user" not in session:
        return redirect("/")
    if not has_perm("create_machines"):
        return no_permission("Du hast keine Berechtigung, Maschinen zu bearbeiten.")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    if not machine:
        return "Eintrag nicht gefunden"

    if request.method == "POST":
        uploaded = uploaded_image_to_data_url(request.files.get("machine_image_file"))
        custom_image = uploaded or request.form.get("machine_image_url", "") or machine.get("custom_image", "")

        sql_execute("""
            UPDATE machines SET
                name=%s, type=%s, license_plate=%s, tuv=%s,
                current_value=%s, interval=%s, responsible=%s,
                current_location=%s, independent=%s, attachments=%s, custom_image=%s
            WHERE id=%s;
        """, (
            request.form["name"], request.form["type"],
            request.form.get("license_plate", ""), request.form.get("tuv", ""),
            float(request.form["current_value"]), float(request.form["interval"]),
            request.form["responsible"], request.form["current_location"],
            "independent" in request.form, request.form["attachments"],
            custom_image, machine_id
        ))

        log_action("Eintrag bearbeitet", f"{machine['name']} → {request.form['name']}")
        return redirect("/machines")

    return render_template("machines.html", machines=get_machines(), edit_machine=machine)


@app.route("/reports", methods=["GET", "POST"])
def reports():
    if "user" not in session:
        return redirect("/")
    if not current_fleet_id():
        return redirect("/fleet-select")
    if not has_perm("send_reports"):
        return no_permission("Du hast keine Berechtigung, Tagesberichte zu senden.")

    if request.method == "POST":
        machine_id = request.form["machine_id"]
        machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))

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
                machine_id, note, priority, final_location,
                "independent" in request.form, current_user(), now_dt(), value_type, note_photo
            ))

        sql_execute("""
            INSERT INTO histories (
                machine_id, username, action, new_value, value_type,
                note, priority, old_location, new_location,
                location_change, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (
            machine_id, current_user(), "Tagesbericht",
            new_value, value_type, note, priority,
            old_location, final_location, location_change, now_dt()
        ))

        log_action(
            "Tagesbericht",
            f"{machine['name']} | {old_value} → {new_value} ({value_type}) | Standort: {old_location} → {final_location}"
        )

    machines_list = get_machines()
    locations = sorted({m["current_location"] for m in machines_list if m.get("current_location")}, key=lambda x: x.lower())

    return render_template("reports.html", machines=machines_list, locations=locations)


@app.route("/service")
def service():
    if "user" not in session:
        return redirect("/")
    if not current_fleet_id():
        return redirect("/fleet-select")
    if not has_perm("do_service"):
        return no_permission("Du hast keine Berechtigung, Servicearbeiten durchzuführen.")

    machines_data = get_machines()
    return render_template("service.html", machines=machines_data, sort_by="status", filter_value="")


@app.route("/service-check/<machine_id>")
def service_check(machine_id):
    if "user" not in session:
        return redirect("/")
    if not has_perm("do_service"):
        return no_permission("Du hast keine Berechtigung, Servicearbeiten durchzuführen.")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    machine = prepare_machines([machine])[0]

    return render_template("service_check.html", machine=machine, checklist=[])


@app.route("/service-done/<machine_id>", methods=["POST"])
def service_done(machine_id):
    if "user" not in session:
        return redirect("/")
    if not has_perm("do_service"):
        return no_permission("Du hast für diese Aktion keine Berechtigung.")

    machine = sql_fetchone("SELECT * FROM machines WHERE id = %s;", (machine_id,))
    settings = get_settings()
    increase = float(settings.get(machine["type"], 500))

    sql_execute("UPDATE machines SET interval = interval + %s WHERE id = %s;", (increase, machine_id))
    log_action("Service erledigt", f"{machine['name']} | Intervall erhöht um {increase}")

    return redirect("/service")


@app.route("/admin")
def admin():
    return redirect("/admin/fleets")


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
            """, ("fleet_" + str(time.time()).replace(".", ""), request.form["fleet_name"], hash_password(request.form["fleet_password"]), profile_image))

        elif action == "update_fleet":
            fleet_id = request.form["fleet_id"]

            if request.form.get("fleet_password"):
                sql_execute("""
                    UPDATE fleets SET name=%s, password_hash=%s, profile_image=%s WHERE id=%s;
                """, (request.form["fleet_name"], hash_password(request.form["fleet_password"]), profile_image, fleet_id))
            else:
                sql_execute("""
                    UPDATE fleets SET name=%s, profile_image=COALESCE(NULLIF(%s,''), profile_image) WHERE id=%s;
                """, (request.form["fleet_name"], profile_image, fleet_id))

        return redirect("/admin/fleets")

    fleets = sql_fetchall("SELECT * FROM fleets ORDER BY name ASC;")
    return render_template("admin_fleets.html", fleets=fleets)


@app.route("/admin/migrate-json-to-fleet", methods=["POST"])
def migrate_json_to_fleet():
    if not is_admin():
        return redirect("/dashboard")

    if request.form.get("confirm_admin_password") != ADMIN_PASSWORD:
        return redirect("/denied")

    fleet_id = request.form["fleet_id"]
    old_machines = load_old_json_machines()

    imported = 0

    for old in old_machines:
        machine_id = str(old.get("id") or time.time()).replace(".", "") + "_" + str(imported)

        exists = sql_fetchone("SELECT id FROM machines WHERE id = %s;", (machine_id,))
        if exists:
            continue

        sql_execute("""
            INSERT INTO machines (
                id, fleet_id, name, type, license_plate, tuv,
                current_value, interval, responsible,
                current_location, independent, attachments, custom_image
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (
            machine_id, fleet_id, old.get("name", "Unbenannt"), old.get("type", "machine"),
            old.get("license_plate", ""), old.get("tuv", ""),
            float(old.get("current_value", 0)), float(old.get("interval", 500)),
            old.get("responsible", ""), old.get("current_location", ""),
            old.get("independent", False), old.get("attachments", ""),
            old.get("custom_image", "")
        ))

        imported += 1

    return redirect("/admin/fleets")


@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if not is_admin():
        return redirect("/dashboard")

    if request.method == "POST":
        username = request.form.get("username")

        if request.form.get("action") == "update_user":
            sql_execute("""
                UPDATE users SET role=%s, custom_role=%s,
                perm_create_machines=%s, perm_send_reports=%s, perm_do_service=%s
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


@app.route("/delete-all", methods=["POST"])
def delete_all():
    if not is_admin():
        return "Nur im Admin-Modus erlaubt"

    if request.form.get("confirm_admin_password") != ADMIN_PASSWORD:
        return redirect("/denied")

    fleet_id = request.form.get("fleet_id", "default")
    sql_execute("DELETE FROM notes WHERE machine_id IN (SELECT id FROM machines WHERE fleet_id=%s);", (fleet_id,))
    sql_execute("DELETE FROM histories WHERE machine_id IN (SELECT id FROM machines WHERE fleet_id=%s);", (fleet_id,))
    sql_execute("DELETE FROM machines WHERE fleet_id=%s;", (fleet_id,))

    return redirect("/admin/fleets")


@app.route("/logout")
def logout():
    log_action("Logout", "Benutzer hat sich abgemeldet.")
    session.clear()
    return redirect("/")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)