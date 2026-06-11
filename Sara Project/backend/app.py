from dotenv import load_dotenv
load_dotenv()

from database import (
    init_db, get_user_by_username, get_user_by_id, create_user,
    create_submission, get_submissions, update_submission_status,
    create_announcement, get_announcements, create_rating, get_ratings,
    save_chat, get_chat_logs, get_dashboard_stats
)
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests, os, sys, json
from datetime import datetime
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    from knowledge import find_answer
except ImportError:
    def find_answer(msg):
        return None

# ==================== KONFIGURASI PATH ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Import knowledge base
sys.path.insert(0, BASE_DIR)
try:
    from knowledge import find_answer
except ImportError:
    def find_answer(msg):
        return None

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "sara_secret_key_2026"
CORS(app)
init_db()

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max


# ==================== KONFIGURASI LLM ====================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_ENABLED = os.environ.get('GROQ_ENABLED', 'true').lower() == 'true'
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.1-8b-instant')
GROQ_URL = os.environ.get(
    'GROQ_URL',
    'https://api.groq.com/openai/v1/chat/completions'
)

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


# ==================== ROUTES ====================

@app.route('/')
def index():
    """Serve chatbot UI"""
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = get_user_by_username(data['username'])
    
    if not user or user['password'] != data['password']:
        return jsonify({'success': False, 'message': 'Username atau password salah'}), 401
    
    session['user_id'] = user['id']
    session['role'] = user['role']
    
    return jsonify({'success': True, 'role': user['role'], 'nama': user['nama']})

@app.route('/admin')
def admin():
    """Serve admin dashboard"""
    return send_from_directory(BASE_DIR, 'admin.html')

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

    return jsonify({
        "success": True
    })

@app.route('/api/user')
@login_required
def get_user():
    user = get_user_by_id(session['user_id'])
    return jsonify(user)

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files (style.css, script.js, etc.)"""
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
        'groq_enabled': GROQ_ENABLED and bool(GROQ_API_KEY),
        'version': '1.0.0'
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        json_data = request.get_json(force=True, silent=False)
        if json_data is None:
            return jsonify({'error': 'Invalid JSON format'}), 400

        user_message = json_data.get('message', '').strip()

        if not user_message:
            return jsonify({'error': 'Pesan tidak boleh kosong'}), 400

        print(f"\n{'='*60}")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"👤 USER: {user_message}")

        # STEP 1: Cek Knowledge Base
        print("🔍 Checking Knowledge Base...")
        kb_result = find_answer(user_message)

        if kb_result:
            print("✅ FOUND IN KNOWLEDGE BASE")

            if isinstance(kb_result, dict) and kb_result.get('type') == 'location':
                print(f"{'='*60}\n")
                return jsonify({
                    'reply': kb_result['answer'],
                    'type': 'location',
                    'address': kb_result.get('address'),
                    'maps_url': kb_result.get('maps_url'),
                    'details': kb_result.get('details'),
                    'source': 'kb',
                    'timestamp': datetime.now().isoformat()
                })

            answer = kb_result.get('answer') if isinstance(kb_result, dict) else kb_result
            print(f"📝 ANSWER: {str(answer)[:100]}...")
            print(f"{'='*60}\n")

            
        # STEP 2: Coba Groq API
        if GROQ_ENABLED and GROQ_API_KEY:
            print("🤖 Using Groq API...")
            groq_response = call_groq(user_message)
            if groq_response:
                print(f"📝 GROQ ANSWER: {str(groq_response)[:100]}...")
                print(f"{'='*60}\n")
                save_chat_log(user_message, groq_response, 'groq')
                return jsonify({
                    'reply': groq_response,
                    'source': 'groq',
                    'timestamp': datetime.now().isoformat()
                })

        # STEP 3: Coba Ollama
        if OLLAMA_ENABLED:
            print("🤖 Using Ollama...")
            ollama_response = call_ollama(user_message)
            if ollama_response:
                print(f"📝 OLLAMA ANSWER: {str(ollama_response)[:100]}...")
                print(f"{'='*60}\n")
                save_chat_log(user_message, ollama_response, 'ollama')
                return jsonify({
                    'reply': ollama_response,
                    'source': 'ollama',
                    'timestamp': datetime.now().isoformat()
                })

        # STEP 4: Fallback
        print("⚠️  ALL LLM SOURCES FAILED")
        print(f"{'='*60}\n")
        fallback_msg = 'Maaf, saya belum bisa menjawab pertanyaan tersebut. Silakan hubungi HR di hr@samaratu.com untuk informasi lebih lanjut.'
        save_chat_log(user_message, fallback_msg, 'fallback')
        return jsonify({
            'reply': fallback_msg,
            'source': 'fallback',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'reply': f'Maaf, terjadi kesalahan: {str(e)}',
            'source': 'error',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/submissions', methods=['POST'])
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

@app.route('/api/submissions')
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

@app.route('/api/submissions')
def all_submission():

    return jsonify([
        dict(x)
        for x in get_submissions()
    ])

@app.route(
    '/api/submissions/<int:id>/status',
    methods=['PUT']
)
def approve_submission(id):

    data = request.json

    update_submission_status(
        id,
        data['status']
    )

@app.route('/api/announcements',
methods=['POST'])
def add_pengumuman():

    create_announcement(
        request.json['judul'],
        request.json['isi'],
        session['user_id']
    )
@app.route('/api/announcements')
def announcements():

    return jsonify([
        dict(x)
        for x in get_announcements()
    ])

@app.route('/api/rating',
methods=['POST'])
def rating():

    create_rating(
        session['user_id'],
        request.json['rating'],
        request.json.get(
            'komentar',
            ''
        )
    )

    return jsonify({
        "success": True
    })

    return jsonify({
        "success": True
    })

def save_chat_log(user_msg, bot_resp, source):
    """Save chat to database"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO chat_log (user_message, bot_response, source) VALUES (?, ?, ?)',
                  (user_msg, bot_resp, source))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Failed to save chat log: {e}")

# ==================== LLM FUNCTIONS ====================

def call_groq(user_message):
    try:
        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': GROQ_MODEL,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': user_message}
            ],
            'temperature': 0.7,
            'max_tokens': 1024
        }

        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            print(f"❌ Groq error {response.status_code}: {response.text}")
            return None

    except requests.exceptions.Timeout:
        print("⏱️ Groq timeout")
        return None
    except Exception as e:
        print(f"❌ Groq error: {str(e)}")
        return None

def call_ollama(user_message):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'prompt': f"{SYSTEM_PROMPT}\n\nUser: {user_message}\nAssistant:",
                'stream': False,
                'temperature': 0.7
            },
            timeout=60
        )

        if response.status_code == 200:
            return response.json().get('response', 'Tidak bisa menjawab')
        else:
            print(f"❌ Ollama error {response.status_code}")
            return None

    except requests.exceptions.Timeout:
        print("⏱️ Ollama timeout")
        return None
    except requests.exceptions.ConnectionError:
        print("🔌 Ollama connection error")
        return None
    except Exception as e:
        print(f"❌ Ollama error: {str(e)}")
        return None

@app.route('/api/dashboard')
def dashboard():

    """Dashboard: statistik penggunaan"""
    conn = get_db()
    c = conn.cursor()

    # Total chat hari ini
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM chat_log WHERE date(created_at) = ?", (today,))
    chat_today = c.fetchone()[0]

    # Total chat semua
    c.execute("SELECT COUNT(*) FROM chat_log")
    chat_total = c.fetchone()[0]

    # Total pengajuan cuti
    c.execute("SELECT COUNT(*) FROM cuti")
    total_cuti = c.fetchone()[0]

    # Rata-rata rating survey
    c.execute("SELECT AVG(rating) FROM survey")
    avg_rating = c.fetchone()[0] or 0

    # Pengumuman terbaru
    c.execute("SELECT * FROM pengumuman ORDER BY created_at DESC LIMIT 5")
    pengumuman = [dict(row) for row in c.fetchall()]

    conn.close()

    return jsonify({
        get_dashboard_stats()
    })

@app.route('/api/submission', methods=['POST'])
def ajukan_submission():
    """Form pengajuan cuti"""
    data = request.get_json()

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO cuti (nama, nip, jenis_cuti, tanggal_mulai, tanggal_selesai, alasan) VALUES (?, ?, ?, ?, ?, ?)",
              (data.get('nama'), data.get('nip'), data.get('jenis_cuti'), data.get('tanggal_mulai'), data.get('tanggal_selesai'), data.get('alasan')))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Pengajuan cuti berhasil dikirim!'})

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

@app.route('/api/submission', methods=['GET'])
def list_submission():
    """List semua pengajuan cuti (untuk admin)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM cuti ORDER BY created_at DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

UPLOAD_FOLDER = "uploads"


@app.route('/api/pengumuman', methods=['POST'])
def buat_pengumuman():
    """Buat pengumuman baru"""
    data = request.get_json()

    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO pengumuman (judul, isi, tipe) VALUES (?, ?, ?)',
              (data.get('judul'), data.get('isi'), data.get('tipe', 'info')))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Pengumuman berhasil dibuat!'})

@app.route('/api/pengumuman', methods=['GET'])
def list_pengumuman():
    """List semua pengumuman"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM pengumuman ORDER BY created_at DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/survey', methods=['POST'])
def submit_survey():
    """Submit survey kepuasan"""
    data = request.get_json()

    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO survey (nama, rating, saran) VALUES (?, ?, ?)',
              (data.get('nama'), data.get('rating'), data.get('saran')))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Terima kasih atas feedback Anda!'})

@app.route('/api/survey', methods=['GET'])
def list_survey():
    """List semua survey (admin)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM survey ORDER BY created_at DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/chat-logs', methods=['GET'])
def get_chat_logs():
    """Log percakapan untuk admin"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM chat_log ORDER BY created_at DESC LIMIT 100")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route('/api/cuti/<int:id>/status', methods=['PUT'])
def update_cuti_status(id):
    """Update status pengajuan cuti (approve/reject)"""
    data = request.get_json()
    new_status = data.get('status')

    if new_status not in ['pending', 'approved', 'rejected']:
        return jsonify({'error': 'Status tidak valid'}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE cuti SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    updated = c.rowcount
    conn.close()

    if updated == 0:
        return jsonify({'error': 'Pengajuan tidak ditemukan'}), 404

    return jsonify({'message': f'Status berhasil diubah ke {new_status}'})

# ==================== MAIN ====================

if __name__ == '__main__':
    print('\n' + '='*60)
    print('🚀 SARA BOT - PT SAMARATU DAYA TEKNIK')
    print('='*60)
    print(f'✅ Mode:     {"Groq + KB" if GROQ_ENABLED and GROQ_API_KEY else "Ollama + KB"}')
    print(f'📡 Ollama:   {"ENABLED" if OLLAMA_ENABLED else "DISABLED"}')
    print(f'🤖 Groq:     {"ENABLED" if GROQ_ENABLED and GROQ_API_KEY else "DISABLED"}')
    print(f'📁 KB:       Loaded')
    print(f'📁 Base Dir: {BASE_DIR}')
    print(f'⏰ Started:  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('='*60 + '\n')

    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug_mode, port=port, host='0.0.0.0')
