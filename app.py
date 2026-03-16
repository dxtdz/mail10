from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, render_template_string, make_response
import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime, timedelta
import hashlib
import secrets
from functools import wraps
from user_agents import parse

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=30)

# Cấu hình cho Vercel
if os.environ.get('VERCEL_ENV'):
    BASE_DIR = '/tmp'
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================
# Database giả lập
# ============================================
class UserDB:
    def __init__(self, db_file="users.json"):
        self.db_file = os.path.join(BASE_DIR, db_file)
        self._init_db()
    
    def _init_db(self):
        if not os.path.exists(self.db_file):
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
    
    def _load_users(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_users(self, users):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register(self, username, password):
        users = self._load_users()
        
        if username in users:
            return False, "Tên đăng nhập đã tồn tại!"
        
        users[username] = {
            'password': self.hash_password(password),
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'remember_me': False
        }
        
        self._save_users(users)
        return True, "Đăng ký thành công!"
    
    def login(self, username, password, remember_me=False):
        users = self._load_users()
        
        if username not in users:
            return False, "Tên đăng nhập không tồn tại!"
        
        if users[username]['password'] != self.hash_password(password):
            return False, "Sai mật khẩu!"
        
        users[username]['last_login'] = datetime.now().isoformat()
        users[username]['remember_me'] = remember_me
        self._save_users(users)
        
        return True, "Đăng nhập thành công!"

user_db = UserDB()

# ============================================
# Decorator yêu cầu đăng nhập
# ============================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'login_required', 'redirect': url_for('login_page')})
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# CLASS TempMailManager
# ============================================
class TempMailManager:
    def __init__(self, username):
        self.username = username
        safe_username = hashlib.md5(username.encode()).hexdigest()
        self.save_file = os.path.join(BASE_DIR, f"mails_{safe_username}.json")
        
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }
        self.email = None
        self.mail_data = None

    def _load_saved_mails(self):
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_mail_data(self, email, cookies, created_at=None):
        saved = self._load_saved_mails()
        cookies_dict = {k: v for k, v in cookies.items()}
        saved[email] = {
            "cookies": cookies_dict,
            "created_at": created_at or datetime.now().isoformat(),
            "last_used": datetime.now().isoformat()
        }
        with open(self.save_file, 'w', encoding='utf-8') as f:
            json.dump(saved, f, indent=2, ensure_ascii=False)
        return True

    def get_saved_emails_with_details(self):
        saved = self._load_saved_mails()
        result = []
        for email, data in saved.items():
            result.append({
                'email': email,
                'created_at': data.get('created_at', 'N/A'),
                'last_used': data.get('last_used', 'N/A')
            })
        return result

    def load_email_data(self, email):
        saved = self._load_saved_mails()
        data = saved.get(email)
        if data:
            self.session.cookies.clear()
            self.session.cookies.update(data["cookies"])
            self.email = email
            self.mail_data = data
            return True
        return False

    def get_new_email(self):
        url = "https://10minutemail.net/?lang=vi"
        response = self.session.get(url, headers=self.headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            email_input = soup.find("input", {"id": "fe_text"})
            
            if email_input and email_input.get("value"):
                self.email = email_input["value"]
                self._save_mail_data(self.email, self.session.cookies.get_dict())
                return self.email
        return None

    def recover_email(self, email):
        if self.load_email_data(email):
            url = "https://10minutemail.net/?lang=vi"
            response = self.session.get(url, headers=self.headers)
            if response.status_code == 200:
                saved = self._load_saved_mails()
                if email in saved:
                    saved[email]["last_used"] = datetime.now().isoformat()
                    with open(self.save_file, 'w', encoding='utf-8') as f:
                        json.dump(saved, f, indent=2, ensure_ascii=False)
                return True
        return False

    def delete_email(self, email):
        saved = self._load_saved_mails()
        if email in saved:
            del saved[email]
            with open(self.save_file, 'w', encoding='utf-8') as f:
                json.dump(saved, f, indent=2, ensure_ascii=False)
            return True
        return False

    def get_mail_content(self, mail_id):
        if not self.email:
            return None
            
        url = f"https://10minutemail.net/mail.php?mid={mail_id}"
        response = self.session.get(url, headers=self.headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            content_div = soup.find("div", class_="mail-body") or soup.find("div", {"id": "mailbody"})
            if content_div:
                return str(content_div)
        return None

    def check_mailbox(self):
        if not self.email:
            return None

        url = "https://10minutemail.net/mailbox.ajax.php"
        params = {"_": int(time.time() * 1000)}
        
        response = self.session.get(url, headers=self.headers, params=params)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            mails = soup.find_all("tr", class_="mail_row") or soup.find_all("tr", attrs={"style": "font-weight: bold; cursor: pointer;"})
            
            mail_list = []
            for mail in mails:
                mail_id = None
                mail_link = mail.find("a", class_="row-link")
                if mail_link and mail_link.get('href'):
                    import re
                    match = re.search(r'mid=(\d+)', mail_link['href'])
                    if match:
                        mail_id = match.group(1)
                
                cells = mail.find_all("td")
                if len(cells) >= 3:
                    sender = cells[0].get_text(strip=True)
                    subject = cells[1].get_text(strip=True)
                    time_received = cells[2].get_text(strip=True)
                    mail_list.append({
                        'id': mail_id,
                        'sender': sender,
                        'subject': subject,
                        'time': time_received,
                        'has_content': mail_id is not None
                    })
                else:
                    links = mail.find_all("a", class_="row-link")
                    if len(links) >= 2:
                        sender = links[0].get_text(strip=True)
                        subject = links[1].get_text(strip=True)
                        mail_list.append({
                            'id': mail_id,
                            'sender': sender,
                            'subject': subject,
                            'time': 'N/A',
                            'has_content': mail_id is not None
                        })
            return mail_list
        return None

# [Phần còn lại của routes và HTML templates giữ nguyên như code trước]
# ... (copy từ code trước từ dòng 260 đến hết)

if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════╗
    ║     TempMail - by Dinh Xuan Thang    ║
    ║         Đang chạy tại:               ║
    ║     http://localhost:5000            ║
    ╚══════════════════════════════════════╝
    """)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
