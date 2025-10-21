#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify, session, send_file

# --- App Setup ---
app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'a-very-secure-default-secret-key-change-me')

# --- Constants ---
DATA_FILE = "data.json"
DEFAULT_API_KEY = "7658050410:3GTVV630"
API_URL = "https://leakosintapi.com/"
STARTING_CREDITS = 3
CREDIT_COST = 1
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'jao0wo383+_(#)')

# --- Helper Functions ---
def load_data():
    try:
        if not os.path.exists(DATA_FILE):
            return {"users": {}, "redeem_codes": {}, "api_key": os.environ.get('LEAKOSINT_API_KEY', DEFAULT_API_KEY), "total_searches": 0}
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            data = json.load(f)
        # Ensure all keys exist
        if "total_searches" not in data: data["total_searches"] = 0
        if "api_key" not in data: data["api_key"] = os.environ.get('LEAKOSINT_API_KEY', DEFAULT_API_KEY)
        if "users" not in data: data["users"] = {}
        if "redeem_codes" not in data: data["redeem_codes"] = {}
        return data
    except json.JSONDecodeError:
        # File is corrupted, start fresh
        return {"users": {}, "redeem_codes": {}, "api_key": os.environ.get('LEAKOSINT_API_KEY', DEFAULT_API_KEY), "total_searches": 0}
    except Exception as e:
        # Other file errors, start fresh
        return {"users": {}, "redeem_codes": {}, "api_key": os.environ.get('LEAKOSINT_API_KEY', DEFAULT_API_KEY), "total_searches": 0}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        # If saving fails, we can't do much. For now, we'll just print it.
        # In a real app, you'd log this to a logging service.
        print(f"CRITICAL: Could not save data file. Error: {e}")
        # You might want to raise the exception here to be caught by the route
        raise

def get_user_ip():
    if request.headers.get('X-Forwarded-For'): return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def get_or_create_user(ip):
    data = load_data()
    if ip not in data["users"]:
        data["users"][ip] = {"credits": STARTING_CREDITS, "created_at": datetime.now().isoformat(), "searches": []}
        save_data(data)
    return data["users"][ip]

# --- Page Serving Routes ---
@app.route('/')
def index(): return send_file('index.html')
@app.route('/premium')
def premium(): return send_file('premium.html')
@app.route('/y92')
def admin_page(): return send_file('admin.html')

# --- API Routes (with Safety Net) ---
@app.route('/api/user-info')
def user_info():
    try:
        ip = get_user_ip()
        user = get_or_create_user(ip)
        return jsonify({"credits": user["credits"], "ip": ip})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/search', methods=['POST'])
def search():
    try:
        ip = get_user_ip()
        data = load_data()
        if ip not in data["users"]: get_or_create_user(ip); data = load_data()
        user = data["users"][ip]
        if user["credits"] <= 0: return jsonify({"error": "No credits remaining. Please purchase premium plan or use a redeem code."}), 403
        query_text = request.json.get('query', '').strip()
        if not query_text: return jsonify({"error": "Query cannot be empty"}), 400
        user["credits"] -= CREDIT_COST
        user["searches"].append({"query": query_text, "type": request.json.get('type', 'number'), "timestamp": datetime.now().isoformat()})
        save_data(data)
        payload = {"token": data["api_key"], "request": query_text, "limit": 100, "lang": "en"}
        response = requests.post(API_URL, json=payload, timeout=30)
        result = response.json()
        data = load_data(); data["total_searches"] += 1; save_data(data)
        return jsonify({"success": True, "data": result, "remaining_credits": user["credits"]})
    except requests.exceptions.RequestException as e:
        # Refund credit on API failure
        try:
            data = load_data()
            data["users"][ip]["credits"] += CREDIT_COST
            save_data(data)
        except:
            pass # Ignore errors during refund
        return jsonify({"error": f"External API Error: {str(e)}"}), 502 # 502 Bad Gateway
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/redeem', methods=['POST'])
def redeem():
    try:
        ip = get_user_ip()
        code = request.json.get('code', '').strip().upper()
        data = load_data()
        if code not in data["redeem_codes"]: return jsonify({"error": "Invalid redeem code"}), 400
        if data["redeem_codes"][code]["used"]: return jsonify({"error": "This code has already been used"}), 400
        points = data["redeem_codes"][code]["points"]
        if ip not in data["users"]: get_or_create_user(ip); data = load_data()
        data["users"][ip]["credits"] += points
        data["redeem_codes"][code]["used"] = True; data["redeem_codes"][code]["used_by"] = ip; data["redeem_codes"][code]["used_at"] = datetime.now().isoformat()
        save_data(data)
        return jsonify({"success": True, "points_added": points, "new_credits": data["users"][ip]["credits"]})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    try:
        username = request.json.get('username', ''); password = request.json.get('password', '')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD: session['admin_logged_in'] = True; return jsonify({"success": True})
        return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    try:
        session.pop('admin_logged_in', None); return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/admin/stats')
def admin_stats():
    try:
        if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
        data = load_data()
        total_users = len(data["users"]); total_searches = data.get("total_searches", 0)
        total_credits_given = sum(STARTING_CREDITS for _ in data["users"].keys())
        total_credits_redeemed = sum(code["points"] for code in data["redeem_codes"].values() if code["used"])
        total_credits_available = sum(user["credits"] for user in data["users"].values())
        total_credits_used = (total_credits_given + total_credits_redeemed) - total_credits_available
        return jsonify({"total_users": total_users, "total_searches": total_searches, "total_credits_used": max(0, total_credits_used), "total_redeem_codes": len(data["redeem_codes"]), "used_redeem_codes": sum(1 for code in data["redeem_codes"].values() if code["used"]), "current_api_key": data["api_key"]})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/admin/update-api-key', methods=['POST'])
def update_api_key():
    try:
        if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
        new_key = request.json.get('api_key', '').strip()
        if not new_key: return jsonify({"error": "API key cannot be empty"}), 400
        data = load_data(); data["api_key"] = new_key; save_data(data)
        return jsonify({"success": True, "api_key": new_key})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/admin/generate-code', methods=['POST'])
def generate_code():
    try:
        if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
        code_name = request.json.get('code', '').strip().upper(); points = request.json.get('points', 0)
        if not code_name: return jsonify({"error": "Code name cannot be empty"}), 400
        try: points = int(points); if points <= 0: raise ValueError()
        except: return jsonify({"error": "Points must be a positive number"}), 400
        data = load_data()
        if code_name in data["redeem_codes"]: return jsonify({"error": "Code already exists"}), 400
        data["redeem_codes"][code_name] = {"points": points, "used": False, "created_at": datetime.now().isoformat()}
        save_data(data)
        return jsonify({"success": True, "code": code_name, "points": points})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route('/api/admin/redeem-codes')
def list_redeem_codes():
    try:
        if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
        data = load_data()
        codes = []
        for code, info in data["redeem_codes"].items(): codes.append({"code": code, "points": info["points"], "used": info["used"], "created_at": info.get("created_at", ""), "used_by": info.get("used_by", ""), "used_at": info.get("used_at", "")})
        return jsonify({"codes": codes})
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

# --- Static File Handler ---
@app.route('/<path:filename>')
def serve_static(filename):
    if '.' not in filename: return "Not Found", 404
    ext = filename.rsplit('.', 1)[1].lower()
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'css', 'js'}
    if ext in allowed_extensions and os.path.isfile(filename):
        return send_file(filename)
    return "Not Found", 404
