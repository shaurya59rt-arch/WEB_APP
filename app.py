import os
import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
VERIFY_DB = "verified_devices.json"

def load_v_db():
    if not os.path.exists(VERIFY_DB): return {}
    with open(VERIFY_DB, 'r') as f: return json.load(f)

def save_v_db(data):
    with open(VERIFY_DB, 'w') as f: json.dump(data, f, indent=4)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.json
    uip = data.get('ip')
    udevice = data.get('device')

    db = load_v_db()

    # Check agar dono match hain
    for entry in db.values():
        if entry.get('ip') == uip and entry.get('device') == udevice:
            return jsonify({"status": "fail", "message": "Device Verification Failed!"})

    # Nayi entry save karo (Random ID ke saath)
    entry_id = str(len(db) + 1)
    db[entry_id] = {"ip": uip, "device": udevice}
    save_v_db(db)
    
    return jsonify({"status": "success", "message": "Device Verified!"})
