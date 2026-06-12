from dotenv import load_dotenv
load_dotenv()

from database import (
    init_db, get_user_by_username, get_user_by_id, create_user,
    create_submission, get_submissions, update_submission_status,
    create_announcement, get_announcements, create_rating, get_ratings,
    save_chat, get_chat_logs, get_dashboard_stats
)
from flask import Flask, render_template, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.utils import redirect, secure_filename
import requests, os, sys
from datetime import datetime
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    from knowledge import find_answer
except ImportError:
    def find_answer(msg):
        return None

# ==================== INIT ====================
app = Flask(__name__)
app.secret_key = "sara_secret_key_2026"
CORS(app)
init_db()

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max

# ==================== CONFIG ====================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_ENABLED = os.environ.get('GROQ_ENABLED', 'true').lower() == 'true'
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.1-8b-instant')

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_ENABLED = os.environ.get('OLLAMA_ENABLED', 'true').lower() == 'true'
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3')

SYSTEM_PROMPT = """Kamu adalah SARA, Asisten Digital untuk PT Samaratu Daya Teknik. 
PRIORITAS: Berikan informasi akurat tentang perusahaan (onboarding, jam kerja, benefit, cuti, dll)
GAYA: Ramah, profesional, gunakan emoji yang sesuai."""

# ==================== MIDDLEWARE ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ==================== AUTH ROUTES ====================
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        try:
            with open("admin.json", "r") as f:
                admins = json.load(f)
        except:
            admins = []

        for admin in admins:
            if admin["username"] == username and admin["password"] == password:
                session["hr"] = username
                return redirect("/admin")

        return render_template(
            "login.html",
            error="Username atau Password salah"
        )

    return render_template("login.html")
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    try:
        create_user(data['nama'], data['username'], data['password'], 
                   data.get('email', ''), data.get('jabatan', ''), data.get('nip', ''))
        return jsonify({'success': True, 'message': 'Registrasi berhasil'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/logout')
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/user')
@login_required
def get_user():
    user = get_user_by_id(session['user_id'])
    return jsonify(user)

# ==================== CHAT ROUTE ====================
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'Pesan tidak boleh kosong'}), 400

        print(f"\n{'='*60}")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"👤 USER: {user_message}")

        # Check KB
        print("🔍 Checking Knowledge Base...")
        kb_result = find_answer(user_message)
        
        if kb_result:
            print("✅ FOUND IN KNOWLEDGE BASE")
            answer = kb_result.get('answer') if isinstance(kb_result, dict) else kb_result
            save_chat(session.get('user_id'), user_message, str(answer), 'kb')
            
            if isinstance(kb_result, dict) and kb_result.get('type') == 'location':
                print(f"{'='*60}\n")
                return jsonify({
                    'reply': kb_result['answer'],
                    'type': 'location',
                    'address': kb_result.get('address'),
                    'maps_url': kb_result.get('maps_url'),
                    'details': kb_result.get('details'),
                    'source': 'kb'
                })
            
            print(f"📝 ANSWER: {str(answer)[:100]}...")
            print(f"{'='*60}\n")
            return jsonify({'reply': answer, 'source': 'kb'})

        # Try Groq
        if GROQ_ENABLED and GROQ_API_KEY:
            print("🤖 Using Groq API...")
            response = call_groq(user_message)
            if response:
                print(f"📝 GROQ ANSWER: {str(response)[:100]}...")
                print(f"{'='*60}\n")
                save_chat(session.get('user_id'), user_message, response, 'groq')
                return jsonify({'reply': response, 'source': 'groq'})

        # Try Ollama
        if OLLAMA_ENABLED:
            print("🤖 Using Ollama...")
            response = call_ollama(user_message)
            if response:
                print(f"📝 OLLAMA ANSWER: {str(response)[:100]}...")
                print(f"{'='*60}\n")
                save_chat(session.get('user_id'), user_message, response, 'ollama')
                return jsonify({'reply': response, 'source': 'ollama'})

        # Fallback
        print("⚠️  ALL LLM SOURCES FAILED")
        print(f"{'='*60}\n")
        fallback = 'Maaf, saya tidak bisa menjawab. Hubungi HR: hr@samaratu.com atau (021) 1234-5678'
        save_chat(session.get('user_id'), user_message, fallback, 'fallback')
        return jsonify({'reply': fallback, 'source': 'fallback'})

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== SUBMISSION ROUTES ====================
@app.route('/api/submissions', methods=['POST'])
@login_required
def create_pengajuan():
    try:
        user = get_user_by_id(session['user_id'])
        
        nama = request.form.get('nama', user['nama'])
        nip = request.form.get('nip', user.get('nip', ''))
        jenis = request.form.get('jenis')
        tanggal_mulai = request.form.get('tanggal_mulai')
        tanggal_selesai = request.form.get('tanggal_selesai')
        alasan = request.form.get('alasan')
        
        lampiran = None
        if 'lampiran' in request.files:
            file = request.files['lampiran']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                if ext in ALLOWED_EXTENSIONS:
                    filename = f"{session['user_id']}_{int(datetime.now().timestamp())}.{ext}"
                    file.save(os.path.join(UPLOAD_FOLDER, filename))
                    lampiran = filename

        create_submission(session['user_id'], nama, nip, jenis, tanggal_mulai, tanggal_selesai, alasan, lampiran)
        return jsonify({'success': True, 'message': 'Pengajuan berhasil dikirim'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/submissions', methods=['GET'])
@login_required
def list_pengajuan():
    subs = get_submissions(session['user_id'])
    return jsonify(subs)

@app.route('/api/submissions/<int:id>/status', methods=['PUT'])
@admin_required
def update_status(id):
    data = request.json
    status = data.get('status')
    
    if status not in ['pending', 'approved', 'rejected']:
        return jsonify({'error': 'Status tidak valid'}), 400
    
    update_submission_status(id, status)
    return jsonify({'message': f'Status diubah ke {status}'})

# ==================== ADMIN ROUTES ====================
@app.route('/admin')
def admin():
    return send_from_directory(BASE_DIR, 'admin.html')

@app.route('/api/stats')
@admin_required
def stats():
    return jsonify(get_dashboard_stats())

@app.route('/api/cuti')
@admin_required
def all_cuti():
    subs = get_submissions()
    return jsonify(subs)

@app.route('/api/pengumuman', methods=['POST'])
@admin_required
def buat_pengumuman():
    data = request.json
    create_announcement(data.get('judul'), data.get('isi'), data.get('tipe', 'info'), session['user_id'])
    return jsonify({'message': 'Pengumuman berhasil dibuat'})

@app.route('/api/pengumuman', methods=['GET'])
def list_pengumuman():
    return jsonify(get_announcements())

@app.route('/api/survey', methods=['POST'])
def submit_survey():
    data = request.json
    create_rating(session.get('user_id'), data.get('nama'), data.get('rating'), data.get('saran'))
    return jsonify({'message': 'Terima kasih atas feedback Anda!'})

@app.route('/api/survey', methods=['GET'])
@admin_required
def list_survey():
    return jsonify(get_ratings())

@app.route('/api/chat-logs', methods=['GET'])
@admin_required
def get_logs():
    return jsonify(get_chat_logs())

# ==================== STATIC ====================
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    try:
        return send_from_directory(BASE_DIR, filename)
    except:
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({
        'status': 'ok',
        'message': 'SARA Server Running',
        'timestamp': datetime.now().isoformat(),
        'ollama_enabled': OLLAMA_ENABLED,
        'groq_enabled': GROQ_ENABLED and bool(GROQ_API_KEY)
    })

# ==================== LLM FUNCTIONS ====================
def call_groq(message):
    try:
        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': GROQ_MODEL,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': message}
            ],
            'temperature': 0.7,
            'max_tokens': 1024
        }
        response = requests.post('https://api.groq.com/openai/v1/chat/completions',
                                headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"❌ Groq error {response.status_code}")
    except Exception as e:
        print(f"❌ Groq error: {str(e)}")
    return None

def call_ollama(message):
    try:
        response = requests.post(OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'prompt': f"{SYSTEM_PROMPT}\n\nUser: {message}\nAssistant:",
                'stream': False,
                'temperature': 0.7
            }, timeout=60)
        if response.status_code == 200:
            return response.json().get('response')
        else:
            print(f"❌ Ollama error {response.status_code}")
    except Exception as e:
        print(f"❌ Ollama error: {str(e)}")
    return None

# ==================== MAIN ====================
if __name__ == '__main__':
    print('\n' + '='*60)
    print('🚀 SARA BOT - PT SAMARATU DAYA TEKNIK')
    print('='*60)
    print(f'✅ Mode:     {"Groq + KB" if GROQ_ENABLED and GROQ_API_KEY else "Ollama + KB"}')
    print(f'📡 Ollama:   {"ENABLED" if OLLAMA_ENABLED else "DISABLED"}')
    print(f'🤖 Groq:     {"ENABLED" if GROQ_ENABLED and GROQ_API_KEY else "DISABLED"}')
    print(f'📁 KB:       Loaded')
    print(f'⏰ Started:  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('='*60)
    print('🌐 Server running at http://localhost:5000')
    print('⚙️  Admin at http://localhost:5000/admin')
    print('='*60 + '\n')

    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug_mode, port=port, host='0.0.0.0')
