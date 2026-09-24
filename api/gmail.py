import os
import time
import requests
import urllib.parse
from flask import Flask, render_template, request, redirect, session

# Root directory (..) থেকে HTML পড়ার কনফিগারেশন
app = Flask(__name__, template_folder='../', static_folder='../')
app.secret_key = "emon_gmail_secret_key_2026"

# Default OAuth Credentials
DEFAULT_GMAIL_CLIENT = "646477291706-udv6l8ibmu9i3or0qsm3hfu02rj2f7fk.apps.googleusercontent.com"
DEFAULT_GMAIL_SECRET = "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"

FIREBASE_REST_URL = "https://mail-shop-bd-default-rtdb.firebaseio.com"

def get_google_auth_url(email_login_hint):
    redirect_uri = f"{request.url_root.rstrip('/')}/gmail-callback"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2.0/auth?"
        f"client_id={DEFAULT_GMAIL_CLIENT}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"response_type=code&"
        f"scope=https://www.googleapis.com/auth/gmail.readonly&"
        f"access_type=offline&"
        f"prompt=consent&"
        f"login_hint={urllib.parse.quote(email_login_hint)}"
    )
    return auth_url

@app.route('/', methods=['GET'])
@app.route('/gmail-token.html', methods=['GET'])
def gmail_page():
    return render_template('gmail-token.html')

@app.route('/start-gmail-bulk', methods=['POST'])
def start_gmail_bulk():
    raw_data = request.form.get('bulk_accounts', '').strip()
    lines = raw_data.split('\n')
    
    queue = []
    for line in lines:
        line = line.strip()
        if "|" in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                queue.append({"email": parts[0], "pass": parts[1]})

    if not queue:
        return render_template('gmail-token.html', status='error', msg="কোনো সঠিক email|pass দেওয়া হয়নি!")

    # সেশনে অ্যাকাউন্ট কিউ (Queue) সেভ করা
    session['gmail_queue'] = queue
    current_item = session['gmail_queue'].pop(0)
    session['current_account'] = current_item
    session.modified = True

    return redirect(get_google_auth_url(current_item['email']))

@app.route('/gmail-callback', methods=['GET'])
def gmail_callback():
    code = request.args.get('code')
    current_account = session.get('current_account', {})
    email = current_account.get('email', 'unknown')
    password = current_account.get('pass', '')

    if not code:
        error_desc = request.args.get('error_description', 'অথরাইজেশন বাতিল করা হয়েছে!')
        return render_template('gmail-token.html', status='error', msg=f"{email} ➔ {error_desc}")

    redirect_uri = f"{request.url_root.rstrip('/')}/gmail-callback"

    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "client_id": DEFAULT_GMAIL_CLIENT,
            "client_secret": DEFAULT_GMAIL_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        res = requests.post(token_url, data=token_data, timeout=10).json()
        refresh_token = res.get("refresh_token", "")
        
        if refresh_token:
            # চাওয়া অনুযায়ী ফরম্যাট: email|pass|refresh_token|client_id|client_secret
            formatted_value = f"{email}|{password}|{refresh_token}|{DEFAULT_GMAIL_CLIENT}|{DEFAULT_GMAIL_SECRET}"
            
            # Firebase-এ সেভ করা (Top Node Placement)
            reverse_timestamp = str(9999999999999 - int(time.time() * 1000))
            fb_url = f"{FIREBASE_REST_URL}/gmail_tokens/{reverse_timestamp}.json"
            
            payload = {
                "account_data": formatted_value,
                "email": email,
                "timestamp": time.time()
            }
            requests.put(fb_url, json=payload, timeout=5)
            
            # Queue-তে পরবর্তী অ্যাকাউন্ট চেক করা
            queue = session.get('gmail_queue', [])
            if queue:
                next_item = queue.pop(0)
                session['gmail_queue'] = queue
                session['current_account'] = next_item
                session.modified = True
                
                next_redirect_url = get_google_auth_url(next_item['email'])
                
                return render_template(
                    'gmail-token.html', 
                    status='success', 
                    msg=f"✅ {email} সেভ হয়েছে! পরবর্তী অ্যাকাউন্টে নেওয়া হচ্ছে...", 
                    saved_text=formatted_value,
                    remaining_count=len(queue) + 1,
                    next_redirect=next_redirect_url
                )
            else:
                return render_template(
                    'gmail-token.html', 
                    status='success', 
                    msg="✅ সফলভাবে সব জিমেইল অ্যাকাউন্টের টোকেন সেভ হয়েছে!", 
                    saved_text=formatted_value,
                    remaining_count=0
                )
        else:
            err_msg = res.get("error_description", "গুগল রিফ্রেশ টোকেন দেয়নি।")
            return render_template('gmail-token.html', status='error', msg=f"{email} ➔ {err_msg}")

    except Exception as e:
        return render_template('gmail-token.html', status='error', msg=f"Crash Error: {str(e)}")

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5002, debug=True)
