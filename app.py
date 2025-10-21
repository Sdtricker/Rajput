#!/usr/bin/env python3
import json
import os
import requests
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, session, send_file, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get('SESSION_SECRET', 'default-secret-key-change-me')

TMP_DATA_FILE = "/tmp/data.json"
ROOT_DATA_FILE = "data.json"
DEFAULT_API_KEY = "7658050410:3GTVV630"
API_URL = "https://leakosintapi.com/"
STARTING_CREDITS = 3
CREDIT_COST = 1
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'jao0wo383+_(#)')

# ------------------- UTILITIES -------------------
def json_response(data, status=200):
    res = make_response(jsonify(data), status)
    res.headers["Content-Type"] = "application/json"
    return res

def init_data():
    if not os.path.exists(TMP_DATA_FILE):
        if os.path.exists(ROOT_DATA_FILE):
            with open(ROOT_DATA_FILE, "r") as src:
                data = json.load(src)
        else:
            data = {
                "users": {},
                "redeem_codes": {},
                "api_key": os.environ.get('LEAKOSINT_API_KEY', DEFAULT_API_KEY),
                "total_searches": 0
            }
        save_data(data)

def load_data():
    if not os.path.exists(TMP_DATA_FILE):
        init_data()
    try:
        with open(TMP_DATA_FILE, "r") as f:
            data = json.load(f)
    except:
        data = {
            "users": {},
            "redeem_codes": {},
            "api_key": os.environ.get('LEAKOSINT_API_KEY', DEFAULT_API_KEY),
            "total_searches": 0
        }
    data.setdefault("api_key", DEFAULT_API_KEY)
    data.setdefault("total_searches", 0)
    return data

def save_data(data):
    with open(TMP_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def get_or_create_user(ip):
    data = load_data()
    if ip not in data["users"]:
        data["users"][ip] = {
            "credits": STARTING_CREDITS,
            "created_at": datetime.now().isoformat(),
            "searches": []
        }
        save_data(data)
    return data["users"][ip]

# ------------------- ROUTES -------------------

@app.route("/")
def home():
    return send_file("index.html")

@app.route("/premium")
def premium():
    return send_file("premium.html")

@app.route("/y92")
def admin_html():
    return send_file("admin.html")

@app.route("/<path:filename>")
def serve_static(filename):
    if filename.endswith(('.png', '.jpg', '.jpeg')):
        return send_file(filename)
    return json_response({"error": "File not found"}, 404)

# -------- USER ENDPOINTS --------
@app.route("/api/user-info")
def user_info():
    ip = get_user_ip()
    user = get_or_create_user(ip)
    return json_response({"credits": user["credits"], "ip": ip})

@app.route("/api/search", methods=["POST"])
def search():
    try:
        ip = get_user_ip()
        data = load_data()
        if ip not in data["users"]:
            get_or_create_user(ip)
            data = load_data()
        user = data["users"][ip]

        if user["credits"] <= 0:
            return json_response({"error": "No credits remaining. Please purchase premium plan or use a redeem code."}, 403)

        query_text = request.json.get("query", "").strip()
        if not query_text:
            return json_response({"error": "Query cannot be empty"}, 400)

        user["credits"] -= CREDIT_COST
        user["searches"].append({
            "query": query_text,
            "timestamp": datetime.now().isoformat()
        })
        save_data(data)

        payload = {"token": data["api_key"], "request": query_text, "limit": 100, "lang": "en"}
        response = requests.post(API_URL, json=payload, timeout=30)
        result = response.json()

        data = load_data()
        data["total_searches"] += 1
        save_data(data)
        return json_response({"success": True, "data": result, "remaining_credits": user["credits"]})

    except Exception as e:
        data = load_data()
        if ip in data["users"]:
            data["users"][ip]["credits"] += CREDIT_COST
            save_data(data)
        return json_response({"error": str(e)}, 500)

@app.route("/api/redeem", methods=["POST"])
def redeem():
    try:
        ip = get_user_ip()
        code = request.json.get("code", "").strip().upper()
        data = load_data()

        if code not in data["redeem_codes"]:
            return json_response({"error": "Invalid redeem code"}, 400)
        if data["redeem_codes"][code]["used"]:
            return json_response({"error": "This code has already been used"}, 400)

        points = data["redeem_codes"][code]["points"]
        if ip not in data["users"]:
            get_or_create_user(ip)
            data = load_data()

        data["users"][ip]["credits"] += points
        data["redeem_codes"][code]["used"] = True
        data["redeem_codes"][code]["used_by"] = ip
        data["redeem_codes"][code]["used_at"] = datetime.now().isoformat()
        save_data(data)

        return json_response({
            "success": True,
            "points_added": points,
            "new_credits": data["users"][ip]["credits"]
        })
    except Exception as e:
        return json_response({"error": str(e)}, 500)

# -------- ADMIN AUTH --------
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    username = request.json.get("username", "")
    password = request.json.get("password", "")
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        return json_response({"success": True})
    return json_response({"error": "Invalid credentials"}, 401)

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_logged_in", None)
    return json_response({"success": True})

# -------- ADMIN FEATURES --------
@app.route("/api/admin/stats")
def admin_stats():
    if not session.get("admin_logged_in"):
        return json_response({"error": "Unauthorized"}, 401)
    data = load_data()
    total_users = len(data["users"])
    total_searches = data.get("total_searches", 0)
    total_credits = sum(u["credits"] for u in data["users"].values())
    used_codes = sum(1 for c in data["redeem_codes"].values() if c["used"])
    return json_response({
        "total_users": total_users,
        "total_searches": total_searches,
        "total_credits_available": total_credits,
        "used_codes": used_codes,
        "api_key": data["api_key"]
    })

@app.route("/api/admin/update-api-key", methods=["POST"])
def update_api_key():
    if not session.get("admin_logged_in"):
        return json_response({"error": "Unauthorized"}, 401)
    new_key = request.json.get("api_key", "").strip()
    if not new_key:
        return json_response({"error": "API key cannot be empty"}, 400)
    data = load_data()
    data["api_key"] = new_key
    save_data(data)
    return json_response({"success": True, "api_key": new_key})

@app.route("/api/admin/generate-code", methods=["POST"])
def generate_code():
    if not session.get("admin_logged_in"):
        return json_response({"error": "Unauthorized"}, 401)
    code_name = request.json.get("code", "").strip().upper()
    points = int(request.json.get("points", 0))
    if not code_name or points <= 0:
        return json_response({"error": "Invalid input"}, 400)
    data = load_data()
    if code_name in data["redeem_codes"]:
        return json_response({"error": "Code already exists"}, 400)
    data["redeem_codes"][code_name] = {
        "points": points,
        "used": False,
        "created_at": datetime.now().isoformat()
    }
    save_data(data)
    return json_response({"success": True, "code": code_name, "points": points})

@app.route("/api/admin/redeem-codes")
def list_codes():
    if not session.get("admin_logged_in"):
        return json_response({"error": "Unauthorized"}, 401)
    data = load_data()
    return json_response({"codes": data["redeem_codes"]})

# ------------- MAIN -------------
if __name__ == "__main__":
    init_data()
    app.run(host="0.0.0.0", port=5000)
