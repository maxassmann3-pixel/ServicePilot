from flask import Flask, render_template, request, redirect, session
import json, os, hashlib, time
from datetime import datetime

app = Flask(__name__)
app.secret_key = "servicepilot_v15"

USERS_FILE = "users.json"
DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"
LOG_FILE = "activity_log.json"

ADMIN_PASSWORD = "admin123"
DATA_KEY = "shared_fleet"

DEFAULT_SETTINGS = {
    "fleet_name": "ServicePilot Fuhrpark",
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


def load(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_settings():
    settings = load(SETTINGS_FILE)
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)
    return settings


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def is_admin():
    return session.get("admin") is True


def current_user():
    return session.get("user", "Unbekannt")


def log_action(action, details=""):
    logs = load(LOG_FILE)
    if not isinstance(logs, list):
        logs = []

    logs.insert(0, {
        "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "user": current_user(),
        "action": action,
        "details": details
    })

    save(LOG_FILE, logs[:500])


def get_fleet_data():
    data = load(DATA_FILE)
    data.setdefault(DATA_KEY, [])
    return data


def get_machines():
    data = get_fleet_data()
    return data[DATA_KEY]


def save_machines(machines):
    data = get_fleet_data()
    data[DATA_KEY] = machines
    save(DATA_FILE, data)


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


def image_url(machine):
    name = machine.get("name", "").lower()
    t = machine.get("type", "machine")

    if "stihl" in name or "kettensäge" in name or "motorsäge" in name or "freischneider" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Chainsaw_Stihl_MS_170.jpg/640px-Chainsaw_Stihl_MS_170.jpg"

    if "rasenmäher" in name or "rüttel" in name or "kleingerät" in name or t == "small_device":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Plate_compactor.jpg/640px-Plate_compactor.jpg"

    if "anhänger" in name or "demmler" in name or "unsinn" in name or "reisch" in name or t == "trailer":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Car_trailer.jpg/640px-Car_trailer.jpg"

    if "ford" in name or "transit" in name or "vw" in name or "crafter" in name or t == "vehicle":
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Ford_Transit_Connect_%28III%29_IMG_8620.jpg/640px-Ford_Transit_Connect_%28III%29_IMG_8620.jpg"

    if "radlader" in name or "zeppelin" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/CAT_950M_wheel_loader.jpg/640px-CAT_950M_wheel_loader.jpg"

    if "takeuchi" in name or "bobcat" in name or "bagger" in name:
        return "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Liebherr_934_Hydraulic_Excavator.jpg/640px-Liebherr_934_Hydraulic_Excavator.jpg"

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
    for n in machine.get("notes", []):
        if n["priority"] == "red":
            note_color = "red"
            break
        elif n["priority"] == "yellow":
            note_color = "yellow"

    if service_color == "red" or note_color == "red":
        return "red", round(rest, 2)
    if service_color == "yellow" or note_color == "yellow":
        return "yellow", round(rest, 2)

    return "green", round(rest, 2)


def prepare_machines(machines):
    order = {"red": 0, "yellow": 1, "green": 2}

    for m in machines:
        m.setdefault("id", str(time.time()).replace(".", ""))
        m.setdefault("license_plate", "")
        m.setdefault("tuv", "")
        m.setdefault("independent", False)
        m.setdefault("attachments", "")
        m.setdefault("notes", [])
        m.setdefault("history", [])

        if m.get("type") == "hours":
            m["type"] = "machine"

        color, rest = final_status(m)
        m["final_color"] = color
        m["rest"] = rest
        m["unit"] = unit(m)
        m["type_name"] = type_name(m)
        m["image_url"] = image_url(m)

    return sorted(machines, key=lambda x: (order[x["final_color"]], x["rest"]))


@app.context_processor
def inject_global_data():
    settings = load_settings()
    return {
        "fleet_name": settings.get("fleet_name", "ServicePilot Fuhrpark")
    }


@app.route("/")
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    users = load(USERS_FILE)
    username = request.form["username"]
    password = request.form["password"]

    if username in users and users[username] == hash_password(password):
        session["user"] = username
        session["admin"] = False
        log_action("Login", "Normaler Benutzer hat sich angemeldet.")
        return redirect("/dashboard")

    return "Login fehlgeschlagen"


@app.route("/admin-login", methods=["POST"])
def admin_login():
    if request.form["admin_password"] == ADMIN_PASSWORD:
        session["user"] = "Admin"
        session["admin"] = True
        log_action("Admin-Login", "Admin hat sich angemeldet.")
        return redirect("/dashboard")

    return "Admin-Passwort falsch"


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

        session["user"] = username
        session["admin"] = False

        log_action("Registrierung", f"Benutzer '{username}' wurde erstellt.")
        return redirect("/dashboard")

    return render_template("register.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    machines = prepare_machines(get_machines())

    red = len([m for m in machines if m["final_color"] == "red"])
    yellow = len([m for m in machines if m["final_color"] == "yellow"])
    green = len([m for m in machines if m["final_color"] == "green"])

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

    machines_data = get_machines()

    if request.method == "POST":
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
            f"{machine['name']} | {type_name(machine)} | Stand: {machine['current_value']} {unit(machine)} | Standort: {machine['current_location']}"
        )

    return render_template(
        "machines.html",
        machines=prepare_machines(machines_data),
        edit_machine=None
    )


@app.route("/edit-machine/<machine_id>", methods=["GET", "POST"])
def edit_machine(machine_id):
    if "user" not in session:
        return redirect("/")

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
            f"{old.get('name')} → {machine['name']} | Stand: {old.get('current_value')} → {machine['current_value']} | Standort: {old.get('current_location')} → {machine['current_location']}"
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

                machine["current_value"] = new_value

                if location_change:
                    if new_location_text:
                        final_location = new_location_text
                    else:
                        final_location = new_location_select

                    machine["current_location"] = final_location
                else:
                    final_location = selected_location
                    machine["current_location"] = selected_location

                machine["independent"] = independent

                if note.strip():
                    machine["notes"].append({
                        "text": note,
                        "priority": priority,
                        "location": final_location,
                        "independent": independent,
                        "created_by": current_user(),
                        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    })

                machine["history"].append({
                    "user": current_user(),
                    "new_value": new_value,
                    "note": note,
                    "priority": priority,
                    "old_location": old_location,
                    "new_location": final_location,
                    "location_change": location_change,
                    "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                })

                log_action(
                    "Tagesbericht",
                    f"{machine['name']} | Stand: {old_value} → {new_value} | Standort: {old_location} → {final_location} | Notiz: {note} | Priorität: {priority}"
                )

                break

        save_machines(machines_data)

    machines_prepared = prepare_machines(machines_data)

    locations = sorted(
        {m["current_location"] for m in machines_prepared if m.get("current_location")},
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

    machines_data = prepare_machines(get_machines())

    sort_by = request.args.get("sort_by", "status")
    filter_value = request.args.get("filter", "").strip().lower()

    if filter_value:
        machines_data = [
            m for m in machines_data
            if filter_value in str(m.get(sort_by, "")).lower()
        ]

    if sort_by == "type":
        machines_data = sorted(machines_data, key=lambda m: (m["type_name"].lower(), m["rest"]))
    elif sort_by == "responsible":
        machines_data = sorted(machines_data, key=lambda m: (m["responsible"].lower(), m["rest"]))
    elif sort_by == "current_location":
        machines_data = sorted(machines_data, key=lambda m: (m["current_location"].lower(), m["rest"]))

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

    machine = next((m for m in get_machines() if m["id"] == machine_id), None)

    if machine is None:
        return "Eintrag nicht gefunden"

    machine = prepare_machines([machine])[0]
    checklist = CHECKLISTS.get(machine.get("type", "machine"), CHECKLISTS["machine"])

    return render_template("service_check.html", machine=machine, checklist=checklist)


@app.route("/service-done/<machine_id>", methods=["POST"])
def service_done(machine_id):
    if "user" not in session:
        return redirect("/")

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
                    "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                })

            machine["history"].append({
                "user": current_user(),
                "service": "Service erledigt",
                "increase": increase,
                "checked_items": checked_items,
                "resolved_notes": resolved_indexes,
                "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            })

            log_action(
                "Service erledigt",
                f"{machine['name']} | Intervall: {old_interval} → {machine['interval']} | erledigte Notizen: {len(resolved_indexes)} von {old_notes} | Checkliste: {', '.join(checked_items)}"
            )

            break

    save_machines(machines_data)
    return redirect("/service")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user" not in session:
        return redirect("/")

    if not is_admin():
        return redirect("/dashboard")

    settings_data = load_settings()

    if request.method == "POST":
        old = settings_data.copy()

        settings_data["fleet_name"] = request.form["fleet_name"]
        settings_data["machine"] = float(request.form["machine"])
        settings_data["vehicle"] = float(request.form["vehicle"])
        settings_data["trailer"] = float(request.form["trailer"])
        settings_data["small_device"] = float(request.form["small_device"])

        save(SETTINGS_FILE, settings_data)

        log_action(
            "Einstellungen geändert",
            f"Vorher: {old} | Nachher: {settings_data}"
        )

        return redirect("/settings")

    return render_template("settings.html", settings=settings_data)


@app.route("/admin")
def admin():
    if not is_admin():
        return redirect("/dashboard")

    logs = load(LOG_FILE)
    if not isinstance(logs, list):
        logs = []

    all_machines = prepare_machines(get_machines())
    settings_data = load_settings()

    return render_template(
        "admin.html",
        logs=logs,
        all_machines=all_machines,
        settings=settings_data
    )


@app.route("/delete-all", methods=["POST"])
def delete_all():
    if "user" not in session:
        return redirect("/")

    if not is_admin():
        return "Nur im Admin-Modus erlaubt"

    confirm = request.form.get("confirm_admin_password", "")

    if confirm != ADMIN_PASSWORD:
        return "Admin-Passwort falsch"

    machines_data = get_machines()
    deleted_count = len(machines_data)

    save_machines([])

    log_action(
        "Alle Einträge gelöscht",
        f"Gelöschte Einträge: {deleted_count}"
    )

    return redirect("/machines")


@app.route("/logout")
def logout():
    log_action("Logout", "Benutzer hat sich abgemeldet.")
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)