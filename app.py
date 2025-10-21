import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify, session, send_from_directory
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'default-secret-key-change-me-vercel-2024')

SUPABASE_URL = os.environ.get('VITE_SUPABASE_URL', 'https://yxitwgdmfjixhuvictjx.supabase.co')
SUPABASE_KEY = os.environ.get('VITE_SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl4aXR3Z2RtZmppeGh1dmljdGp4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwNTIwNTEsImV4cCI6MjA3NjYyODA1MX0.GbuxGENCj_mB14tKsj7BULyJiJdxJsU5zrMsp1Gka4Q')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DEFAULT_API_KEY = "7658050410:3GTVV630"
API_URL = "https://leakosintapi.com/"
STARTING_CREDITS = 3
CREDIT_COST = 1

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'jao0wo383+_(#)')

def get_api_key():
    try:
        response = supabase.table('app_settings').select('value').eq('key', 'api_key').maybeSingle().execute()
        if response.data:
            return response.data['value']
    except:
        pass
    return DEFAULT_API_KEY

def set_api_key(api_key):
    try:
        supabase.table('app_settings').update({'value': api_key, 'updated_at': datetime.now().isoformat()}).eq('key', 'api_key').execute()
        return True
    except:
        return False

def get_user_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

def get_or_create_user(ip):
    try:
        response = supabase.table('users').select('*').eq('ip_address', ip).maybeSingle().execute()
        if response.data:
            return response.data

        new_user = {
            'ip_address': ip,
            'credits': STARTING_CREDITS,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        response = supabase.table('users').insert(new_user).execute()
        return response.data[0] if response.data else new_user
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")
        return {'ip_address': ip, 'credits': STARTING_CREDITS}

def update_user_credits(ip, credits):
    try:
        supabase.table('users').update({'credits': credits, 'updated_at': datetime.now().isoformat()}).eq('ip_address', ip).execute()
        return True
    except:
        return False

def add_search(ip, query, query_type):
    try:
        supabase.table('searches').insert({
            'ip_address': ip,
            'query': query,
            'query_type': query_type,
            'created_at': datetime.now().isoformat()
        }).execute()
        return True
    except:
        return False

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/premium')
def premium():
    return send_from_directory('templates', 'premium.html')

@app.route('/y92')
def admin_page():
    return send_from_directory('templates', 'admin.html')

@app.route('/<path:filename>')
def serve_static(filename):
    if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
        if os.path.exists(filename):
            return send_from_directory('.', filename)
    return '', 404

@app.route('/api/user-info')
def user_info():
    try:
        ip = get_user_ip()
        user = get_or_create_user(ip)
        return jsonify({
            "credits": user.get('credits', STARTING_CREDITS),
            "ip": ip
        })
    except Exception as e:
        return jsonify({"error": str(e), "credits": 0, "ip": "unknown"}), 500

@app.route('/api/search', methods=['POST'])
def search():
    try:
        ip = get_user_ip()
        user = get_or_create_user(ip)

        if user.get('credits', 0) <= 0:
            return jsonify({
                "error": "No credits remaining. Please purchase premium plan or use a redeem code."
            }), 403

        query_text = request.json.get('query', '').strip()
        query_type = request.json.get('type', 'number')

        if not query_text:
            return jsonify({"error": "Query cannot be empty"}), 400

        new_credits = user['credits'] - CREDIT_COST
        update_user_credits(ip, new_credits)
        add_search(ip, query_text, query_type)

        api_key = get_api_key()
        payload = {
            "token": api_key,
            "request": query_text,
            "limit": 100,
            "lang": "en"
        }

        response = requests.post(API_URL, json=payload, timeout=30)
        result = response.json()

        return jsonify({
            "success": True,
            "data": result,
            "remaining_credits": new_credits
        })
    except Exception as e:
        if 'new_credits' not in locals():
            update_user_credits(ip, user.get('credits', 0) + CREDIT_COST)
        return jsonify({
            "error": f"API Error: {str(e)}"
        }), 500

@app.route('/api/redeem', methods=['POST'])
def redeem():
    try:
        ip = get_user_ip()
        code = request.json.get('code', '').strip().upper()

        response = supabase.table('redeem_codes').select('*').eq('code', code).maybeSingle().execute()

        if not response.data:
            return jsonify({"error": "Invalid redeem code"}), 400

        code_data = response.data

        if code_data['used']:
            return jsonify({"error": "This code has already been used"}), 400

        points = code_data['points']
        user = get_or_create_user(ip)
        new_credits = user.get('credits', STARTING_CREDITS) + points

        update_user_credits(ip, new_credits)

        supabase.table('redeem_codes').update({
            'used': True,
            'used_by': ip,
            'used_at': datetime.now().isoformat()
        }).eq('code', code).execute()

        return jsonify({
            "success": True,
            "points_added": points,
            "new_credits": new_credits
        })
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    try:
        username = request.json.get('username', '')
        password = request.json.get('password', '')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return jsonify({"success": True})

        return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return jsonify({"success": True})

@app.route('/api/admin/stats')
def admin_stats():
    try:
        if not session.get('admin_logged_in'):
            return jsonify({"error": "Unauthorized"}), 401

        users_response = supabase.table('users').select('credits').execute()
        searches_response = supabase.table('searches').select('id', count='exact').execute()
        codes_response = supabase.table('redeem_codes').select('*').execute()

        total_users = len(users_response.data) if users_response.data else 0
        total_searches = searches_response.count if hasattr(searches_response, 'count') else 0

        total_credits_given = total_users * STARTING_CREDITS
        total_credits_redeemed = sum(code['points'] for code in codes_response.data if code['used']) if codes_response.data else 0
        total_credits_available = sum(user['credits'] for user in users_response.data) if users_response.data else 0
        total_credits_used = (total_credits_given + total_credits_redeemed) - total_credits_available

        total_redeem_codes = len(codes_response.data) if codes_response.data else 0
        used_redeem_codes = sum(1 for code in codes_response.data if code['used']) if codes_response.data else 0

        return jsonify({
            "total_users": total_users,
            "total_searches": total_searches,
            "total_credits_used": max(0, total_credits_used),
            "total_redeem_codes": total_redeem_codes,
            "used_redeem_codes": used_redeem_codes,
            "current_api_key": get_api_key()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/update-api-key', methods=['POST'])
def update_api_key():
    try:
        if not session.get('admin_logged_in'):
            return jsonify({"error": "Unauthorized"}), 401

        new_key = request.json.get('api_key', '').strip()

        if not new_key:
            return jsonify({"error": "API key cannot be empty"}), 400

        if set_api_key(new_key):
            return jsonify({"success": True, "api_key": new_key})
        else:
            return jsonify({"error": "Failed to update API key"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/generate-code', methods=['POST'])
def generate_code():
    try:
        if not session.get('admin_logged_in'):
            return jsonify({"error": "Unauthorized"}), 401

        code_name = request.json.get('code', '').strip().upper()
        points = request.json.get('points', 0)

        if not code_name:
            return jsonify({"error": "Code name cannot be empty"}), 400

        try:
            points = int(points)
            if points <= 0:
                raise ValueError()
        except:
            return jsonify({"error": "Points must be a positive number"}), 400

        existing = supabase.table('redeem_codes').select('code').eq('code', code_name).maybeSingle().execute()

        if existing.data:
            return jsonify({"error": "Code already exists"}), 400

        supabase.table('redeem_codes').insert({
            'code': code_name,
            'points': points,
            'used': False,
            'created_at': datetime.now().isoformat()
        }).execute()

        return jsonify({
            "success": True,
            "code": code_name,
            "points": points
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/redeem-codes')
def list_redeem_codes():
    try:
        if not session.get('admin_logged_in'):
            return jsonify({"error": "Unauthorized"}), 401

        response = supabase.table('redeem_codes').select('*').order('created_at', desc=True).execute()

        codes = []
        if response.data:
            for code_data in response.data:
                codes.append({
                    "code": code_data['code'],
                    "points": code_data['points'],
                    "used": code_data['used'],
                    "created_at": code_data.get('created_at', ''),
                    "used_by": code_data.get('used_by', ''),
                    "used_at": code_data.get('used_at', '')
                })

        return jsonify({"codes": codes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)
