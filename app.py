from flask import Flask, render_template, request, redirect, session
import json
import os
import hashlib
import time
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.secret_key = "servicepilot_v17"

USERS_FILE = "users.json"
DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"
LOG_FILE = "activity_log.json"
FLEETS_FILE = "fleets.json"
USER_META_FILE = "user_meta.json"

ADMIN_PASSWORD = "admin123"
BERLIN = ZoneInfo("Europe/Berlin")

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

CHECKLISTS = {
    "machine": [
        "Motorölstand geprüft",
        "Motoröl gewechselt",
        "Ölfilter gewechselt",
        "Hydraulikölstand geprüft",
        "Hydrauliköl gewechselt falls fällig",
        "Hydraulikfilter geprüft / gewechselt",
        "Kühlflüssigkeit geprüft",
        "Luftfilter geprüft / gereinigt",
        "Kraftstofffilter geprüft / gewechselt",
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
        "Hydrauliköl geprüft falls vorhanden",
        "TÜV / Kennzeichen geprüft"
    ],
    "small_device": [
        "Motoröl geprüft",
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


def now_str():
    return datetime.now(BERLIN).strftime("%d.%m.%Y %H:%M:%S")


def load(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def is_admin():
    return session.get("admin") is True


def current_user():
    return session.get("user", "Unbekannt")


def load_settings():
    settings = load(SETTINGS_FILE)
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)
    return settings


def load_fleets():
    fleets = load(FLEETS_FILE)

    if not fleets:
        fleets = {
            "default": {
                "name": "ServicePilot Fuhrpark",
                "password_hash": hash_password("fuhrpark123")
            }
        }
        save(FLEETS_FILE, fleets)

    return fleets


def load_user_meta():
    users = load(USERS_FILE)
    meta = load(USER_META_FILE)

    for username in users.keys():
        meta.setdefault(username, {
            "role": "Baustelle",
            "custom_role": "",
            "permissions": DEFAULT_PERMISSIONS.copy(),
            "force_token": secrets.token_hex(8)
        })

        meta[username].setdefault("role", "Baustelle")
        meta[username].setdefault("custom_role", "")
        meta[username].setdefault("permissions", DEFAULT_PERMISSIONS.copy())
        meta[username].setdefault("force_token", secrets.token_hex(8))

    save(USER_META_FILE, meta)
    return meta


def save_user_meta(meta):
    save(USER_META_FILE, meta)


def get_user_permissions(username=None):
    if is_admin():
        return {
            "create_machines": True,
            "send_reports": True,
            "do_service": True
        }

    username = username or current_user()
    meta = load_user_meta()
    return meta.get(username, {}).get("permissions", DEFAULT_PERMISSIONS.copy())


def has_perm(permission):
    return is_admin() or get_user_permissions().get(permission, False)


def current_fleet_id():
    return session.get("fleet_id")


def current_fleet_name():
    fleets = load_fleets()
    fleet_id = current_fleet_id()

    if fleet_id in fleets:
        return fleets[fleet_id]["name"]

    return "Kein Fuhrpark gewählt"


def log_action(action, details="", fleet_id=None):
    logs = load(LOG_FILE)

    if not isinstance(logs, list):
        logs = []

    logs.insert(0, {
        "time": now_str(),
        "user": current_user(),
        "fleet_id": fleet_id or current_fleet_id() or "admin",
        "fleet_name": current_fleet_name() if current_fleet_id() else "Admin / System",
        "action": action,
        "details": details
    })

    save(LOG_FILE, logs[:1000])


def get_all_data():
    data = load(DATA_FILE)

    if "fleets" not in data:
        old_shared_fleet = data.get("shared_fleet", [])
        old_max_fleet = data.get("Max", [])

        if old_shared_fleet:
            old_data = old_shared_fleet
        else:
            old_data = old_max_fleet

        data = {
            "fleets": {
                "default": old_data
            }
        }

        save(DATA_FILE, data)

    data.setdefault("fleets", {})
    return data


def get_machines(fleet_id=None):
    fleet_id = fleet_id or current_fleet_id() or "default"

    data = get_all_data()
    data["fleets"].setdefault(fleet_id, [])

    save(DATA_FILE, data)
    return data["fleets"][fleet_id]


def save_machines(machines, fleet_id=None):
    fleet_id = fleet_id or current_fleet_id() or "default"

    data = get_all_data()
    data["fleets"].setdefault(fleet_id, [])
    data["fleets"][fleet_id] = machines

    save(DATA_FILE, data)


def unit(machine):
    return "km" if machine.get("type") == "vehicle" else "h"


def type_name(machine):
    machine_type = machine.get("type")

    if machine_type == "vehicle":
        return "Fahrzeug"

    if machine_type == "trailer":
        return "Gerät / Anhänger"

    if machine_type == "small_device":
        return "Kleingerät"

    return "Baumaschine"


def image_url(machine):
    name = machine.get("name", "").lower()
    machine_type = machine.get("type", "machine")

    if "stihl" in name or "kettensäge" in name or "motorsäge" in name or "freischneider" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Chainsaw_Stihl_MS_170.jpg/640px-Chainsaw_Stihl_MS_170.jpg"

    if "rasenmäher" in name or "rüttel" in name or machine_type == "small_device":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Plate_compactor.jpg/640px-Plate_compactor.jpg"

    if "anhänger" in name or "demmler" in name or "unsinn" in name or "reisch" in name or machine_type == "trailer":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Car_trailer.jpg/640px-Car_trailer.jpg"

    if "ford" in name or "transit" in name or "vw" in name or "crafter" in name or machine_type == "vehicle":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Ford_Transit_Connect_%28III%29_IMG_8620.jpg/640px-Ford_Transit_Connect_%28III%29_IMG_8620.jpg"

    if "radlader" in name or "zeppelin" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/CAT_950M_wheel_loader.jpg/640px-CAT_950M_wheel_loader.jpg"

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
    order = {
        "red": 0,
        "yellow": 1,
        "green": 2
    }

    for machine in machines:
        machine.setdefault("id", str(time.time()).replace(".", ""))
        machine.setdefault("license_plate", "")
        machine.setdefault("tuv", "")
        machine.setdefault("independent", False)
        machine.setdefault("attachments", "")
        machine.setdefault("notes", [])
        machine.setdefault("history", [])

        if machine.get("type") == "hours":
            machine["type"] = "machine"

        color, rest = final_status(machine)

        machine["final_color"] = color
        machine["rest"] = rest
        machine["unit"] = unit(machine)
        machine["type_name"] = type_name(machine)
        machine["image_url"] = image_url(machine)

    return sorted(machines, key=lambda x: (order[x["final_color"]], x["rest"]))


@app.before_request
def check_force_logout():
    if "user" in session and not is_admin():
        meta = load_user_meta()
        username = session["user"]

        server_token = meta.get(username, {}).get("force_token")
        session_token = session.get("force_token")

        if server_token and session_token and server_token != session_token:
            session.clear()
            return redirect("/")


@app.context_processor
def inject_global_data():
    return {
        "fleet_name": current_fleet_name(),
        "permissions": get_user_permissions() if "user" in session else {},
        "is_admin": is_admin()
    }


@app.route("/")
def login_page():
    return render_template("login.html")


@app.route("/denied")
def denied():
    return render_template("denied.html")


@app.route("/login", methods=["POST"])
def login():
    users = load(USERS_FILE)

    username = request.form["username"]
    password = request.form["password"]

    if username in users and users[username] == hash_password(password):
        meta = load_user_meta()
        token = meta[username].setdefault("force_token", secrets.token_hex(8))

        save_user_meta(meta)

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

        log_action("Admin-Login", "Admin hat sich angemeldet.")

        return redirect("/admin")

    return redirect("/denied")


@app.route("/register", methods=["GET", "POST"])
def register():
    users = load(USERS_FILE)

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users:
            return "Benutzer existiert bereits"

        users[username] = hash_password(password)
        save(USERS_FILE, users)

        meta = load_user_meta()

        meta[username] = {
            "role": "Baustelle",
            "custom_role": "",
            "permissions": DEFAULT_PERMISSIONS.copy(),
            "force_token": secrets.token_hex(8)
        }

        save_user_meta(meta)

        session["user"] = username
        session["admin"] = False
        session["force_token"] = meta[username]["force_token"]
        session.pop("fleet_id", None)

        log_action("Registrierung", f"Benutzer '{username}' wurde erstellt.")

        return redirect("/fleet-select")

    return render_template("register.html")


@app.route("/fleet-select")
def fleet_select():
    if "user" not in session:
        return redirect("/")

    if is_admin():
        return redirect("/admin")

    return render_template("fleet_select.html", fleets=load_fleets())


@app.route("/join-fleet", methods=["POST"])
def join_fleet():
    if "user" not in session:
        return redirect("/")

    fleet_id = request.form["fleet_id"]
    fleet_password = request.form["fleet_password"]

    fleets = load_fleets()

    if fleet_id in fleets and fleets[fleet_id]["password_hash"] == hash_password(fleet_password):
        session["fleet_id"] = fleet_id

        log_action(
            "Fuhrpark gewählt",
            f"Benutzer ist Fuhrpark '{fleets[fleet_id]['name']}' beigetreten.",
            fleet_id
        )

        return redirect("/dashboard")

    return redirect("/denied")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    if not current_fleet_id():
        return redirect("/fleet-select")

    machines = prepare_machines(get_machines())

    red = len([machine for machine in machines if machine["final_color"] == "red"])
    yellow = len([machine for machine in machines if machine["final_color"] == "yellow"])
    green = len([machine for machine in machines if machine["final_color"] == "green"])

    return render_template(
        "dashboard.html",
        user=current_user(),
        machines=machines,
        red=red,
        yellow=yellow,
        green=green
    )


@app.route("/machines", methods=["GET", "POST"])
def machines():
    if "user" not in session:
        return redirect("/")

    if not current_fleet_id():
        return redirect("/fleet-select")

    if request.method == "POST":
        if not has_perm("create_machines"):
            return "Keine Berechtigung: Maschinen anlegen"

        machines_data = get_machines()

        machine = {
            "id": str(time.time()).replace(".", ""),
            "name": request.form["name"],
            "type": request.form["type"],
            "license_plate": request.form.get("license_plate", ""),
            "tuv": request.form.get("tuv", ""),
            "current_value": float(request.form["current_value"]),
            "interval": float(request.form["interval"]),
            "responsible": request.form["responsible"],
            "current_location": request.form["current_location"],
            "independent": "independent" in request.form,
            "attachments": request.form["attachments"],
            "notes": [],
            "history": []
        }

        machines_data.append(machine)
        save_machines(machines_data)

        log_action(
            "Eintrag angelegt",
            f"{machine['name']} | {type_name(machine)} | Stand: {machine['current_value']} {unit(machine)}"
        )

    return render_template(
        "machines.html",
        machines=prepare_machines(get_machines()),
        edit_machine=None
    )


@app.route("/edit-machine/<machine_id>", methods=["GET", "POST"])
def edit_machine(machine_id):
    if "user" not in session:
        return redirect("/")

    if not current_fleet_id():
        return redirect("/fleet-select")

    if not has_perm("create_machines"):
        return "Keine Berechtigung: Maschinen bearbeiten"

    machines_data = get_machines()
    machine = next((m for m in machines_data if m["id"] == machine_id), None)

    if machine is None:
        return "Eintrag nicht gefunden"

    if request.method == "POST":
        old = machine.copy()

        machine["name"] = request.form["name"]
        machine["type"] = request.form["type"]
        machine["license_plate"] = request.form.get("license_plate", "")
        machine["tuv"] = request.form.get("tuv", "")
        machine["current_value"] = float(request.form["current_value"])
        machine["interval"] = float(request.form["interval"])
        machine["responsible"] = request.form["responsible"]
        machine["current_location"] = request.form["current_location"]
        machine["independent"] = "independent" in request.form
        machine["attachments"] = request.form["attachments"]

        save_machines(machines_data)

        log_action(
            "Eintrag bearbeitet",
            f"{old.get('name')} → {machine['name']} | Stand: {old.get('current_value')} → {machine['current_value']}"
        )

        return redirect("/machines")

    return render_template(
        "machines.html",
        machines=prepare_machines(machines_data),
        edit_machine=machine
    )


@app.route("/reports", methods=["GET", "POST"])
def reports():
    if "user" not in session:
        return redirect("/")

    if not current_fleet_id():
        return redirect("/fleet-select")

    if not has_perm("send_reports"):
        return "Keine Berechtigung: Tagesberichte senden"

    machines_data = get_machines()

    if request.method == "POST":
        machine_id = request.form["machine_id"]
        new_value = float(request.form["new_value"])
        note = request.form["note"]
        priority = request.form["priority"]

        location_change = "location_change" in request.form
        selected_location = request.form.get("selected_location", "")
        new_location_select = request.form.get("new_location_select", "")
        new_location_text = request.form.get("new_location_text", "").strip()
        independent = "independent" in request.form

        for machine in machines_data:
            if machine["id"] == machine_id:
                old_value = machine["current_value"]
                old_location = machine["current_location"]

                if location_change:
                    final_location = new_location_text if new_location_text else new_location_select
                else:
                    final_location = selected_location

                machine["current_value"] = new_value
                machine["current_location"] = final_location
                machine["independent"] = independent

                if note.strip():
                    machine["notes"].append({
                        "text": note,
                        "priority": priority,
                        "location": final_location,
                        "independent": independent,
                        "created_by": current_user(),
                        "created_at": now_str()
                    })

                machine["history"].append({
                    "user": current_user(),
                    "new_value": new_value,
                    "note": note,
                    "priority": priority,
                    "old_location": old_location,
                    "new_location": final_location,
                    "location_change": location_change,
                    "time": now_str()
                })

                log_action(
                    "Tagesbericht",
                    f"{machine['name']} | Stand: {old_value} → {new_value} | Standort: {old_location} → {final_location} | Notiz: {note}"
                )

                break

        save_machines(machines_data)

    machines_prepared = prepare_machines(machines_data)

    locations = sorted(
        {machine["current_location"] for machine in machines_prepared if machine.get("current_location")},
        key=lambda x: x.lower()
    )

    return render_template(
        "reports.html",
        machines=machines_prepared,
        locations=locations
    )


@app.route("/service")
def service():
    if "user" not in session:
        return redirect("/")

    if not current_fleet_id():
        return redirect("/fleet-select")

    if not has_perm("do_service"):
        return "Keine Berechtigung: Service durchführen"

    machines_data = prepare_machines(get_machines())

    sort_by = request.args.get("sort_by", "status")
    filter_value = request.args.get("filter", "").strip().lower()

    if filter_value:
        machines_data = [
            machine for machine in machines_data
            if filter_value in str(machine.get(sort_by, "")).lower()
        ]

    if sort_by == "type":
        machines_data = sorted(machines_data, key=lambda machine: (machine["type_name"].lower(), machine["rest"]))
    elif sort_by == "responsible":
        machines_data = sorted(machines_data, key=lambda machine: (machine["responsible"].lower(), machine["rest"]))
    elif sort_by == "current_location":
        machines_data = sorted(machines_data, key=lambda machine: (machine["current_location"].lower(), machine["rest"]))

    return render_template(
        "service.html",
        machines=machines_data,
        sort_by=sort_by,
        filter_value=filter_value
    )


@app.route("/service-check/<machine_id>")
def service_check(machine_id):
    if "user" not in session:
        return redirect("/")

    if not current_fleet_id():
        return redirect("/fleet-select")

    if not has_perm("do_service"):
        return "Keine Berechtigung: Service durchführen"

    machine = next((m for m in get_machines() if m["id"] == machine_id), None)

    if machine is None:
        return "Eintrag nicht gefunden"

    machine = prepare_machines([machine])[0]
    checklist = CHECKLISTS.get(machine.get("type", "machine"), CHECKLISTS["machine"])

    return render_template(
        "service_check.html",
        machine=machine,
        checklist=checklist
    )


@app.route("/service-done/<machine_id>", methods=["POST"])
def service_done(machine_id):
    if "user" not in session:
        return redirect("/")

    if not has_perm("do_service"):
        return "Keine Berechtigung"

    machines_data = get_machines()
    settings = load_settings()

    resolved_indexes = [int(i) for i in request.form.getlist("resolved_notes")]
    checked_items = request.form.getlist("checklist")
    new_note = request.form.get("new_note", "").strip()
    new_note_priority = request.form.get("new_note_priority", "green")

    for machine in machines_data:
        if machine["id"] == machine_id:
            machine_type = machine.get("type", "machine")
            increase = float(settings.get(machine_type, DEFAULT_SETTINGS.get(machine_type, 500)))

            old_interval = machine["interval"]
            old_notes = len(machine.get("notes", []))

            machine["interval"] = float(machine["interval"]) + increase

            machine["notes"] = [
                note for index, note in enumerate(machine.get("notes", []))
                if index not in resolved_indexes
            ]

            if new_note:
                machine["notes"].append({
                    "text": new_note,
                    "priority": new_note_priority,
                    "location": machine.get("current_location", ""),
                    "independent": machine.get("independent", False),
                    "created_by": current_user(),
                    "created_at": now_str()
                })

            machine["history"].append({
                "user": current_user(),
                "service": "Service erledigt",
                "increase": increase,
                "checked_items": checked_items,
                "resolved_notes": resolved_indexes,
                "time": now_str()
            })

            log_action(
                "Service erledigt",
                f"{machine['name']} | Intervall: {old_interval} → {machine['interval']} | erledigte Notizen: {len(resolved_indexes)} von {old_notes}"
            )

            break

    save_machines(machines_data)

    return redirect("/service")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not is_admin():
        return redirect("/dashboard")

    fleets = load_fleets()
    users = load(USERS_FILE)
    meta = load_user_meta()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_fleet":
            fleet_id = "fleet_" + str(time.time()).replace(".", "")

            fleets[fleet_id] = {
                "name": request.form["fleet_name"],
                "password_hash": hash_password(request.form["fleet_password"])
            }

            save(FLEETS_FILE, fleets)

            log_action(
                "Fuhrpark angelegt",
                f"Name: {request.form['fleet_name']}"
            )

        elif action == "update_fleet":
            fleet_id = request.form["fleet_id"]

            if fleet_id in fleets:
                old_name = fleets[fleet_id]["name"]
                fleets[fleet_id]["name"] = request.form["fleet_name"]

                if request.form.get("fleet_password"):
                    fleets[fleet_id]["password_hash"] = hash_password(request.form["fleet_password"])

                save(FLEETS_FILE, fleets)

                log_action(
                    "Fuhrpark geändert",
                    f"{old_name} → {fleets[fleet_id]['name']}"
                )

        elif action == "update_user":
            username = request.form["username"]

            meta.setdefault(username, {})
            meta[username]["role"] = request.form.get("role", "Baustelle")
            meta[username]["custom_role"] = request.form.get("custom_role", "")
            meta[username]["permissions"] = {
                "create_machines": "create_machines" in request.form,
                "send_reports": "send_reports" in request.form,
                "do_service": "do_service" in request.form
            }
            meta[username].setdefault("force_token", secrets.token_hex(8))

            save_user_meta(meta)

            log_action(
                "User-Rechte geändert",
                f"{username}: {meta[username]}"
            )

        elif action == "force_logout":
            username = request.form["username"]

            meta.setdefault(username, {})
            meta[username]["force_token"] = secrets.token_hex(16)

            save_user_meta(meta)

            log_action(
                "User rausgeworfen",
                f"{username} wurde zwangsweise ausgeloggt."
            )

        return redirect("/admin")

    filter_user = request.args.get("user", "")

    logs = load(LOG_FILE)

    if not isinstance(logs, list):
        logs = []

    if filter_user:
        logs = [log for log in logs if log.get("user") == filter_user]

    all_data = get_all_data()
    prepared_by_fleet = {}

    for fleet_id, machines in all_data.get("fleets", {}).items():
        prepared_by_fleet[fleet_id] = prepare_machines(machines)

    return render_template(
        "admin.html",
        logs=logs,
        users=users,
        user_meta=meta,
        fleets=fleets,
        all_data=prepared_by_fleet,
        filter_user=filter_user
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if not is_admin():
        return redirect("/dashboard")

    settings_data = load_settings()

    if request.method == "POST":
        old = settings_data.copy()

        settings_data["machine"] = float(request.form["machine"])
        settings_data["vehicle"] = float(request.form["vehicle"])
        settings_data["trailer"] = float(request.form["trailer"])
        settings_data["small_device"] = float(request.form["small_device"])

        save(SETTINGS_FILE, settings_data)

        log_action(
            "Service-Intervalle geändert",
            f"Vorher: {old} | Nachher: {settings_data}"
        )

        return redirect("/settings")

    return render_template(
        "settings.html",
        settings=settings_data
    )


@app.route("/delete-all", methods=["POST"])
def delete_all():
    if not is_admin():
        return "Nur im Admin-Modus erlaubt"

    if request.form.get("confirm_admin_password") != ADMIN_PASSWORD:
        return redirect("/denied")

    fleet_id = request.form.get("fleet_id", "default")
    deleted_count = len(get_machines(fleet_id))

    save_machines([], fleet_id)

    log_action(
        "Fuhrpark gelöscht",
        f"Fuhrpark: {fleet_id}, gelöschte Einträge: {deleted_count}"
    )

    return redirect("/admin")


@app.route("/logout")
def logout():
    log_action("Logout", "Benutzer hat sich abgemeldet.")
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)