from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from contextlib import contextmanager
import sqlite3, os, base64, math
from functools import wraps
import numpy as np
from PIL import Image
import io
import json  # <-- TAMBAH INI

# Try to import face recognition with fallback
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
    print("✅ Face recognition loaded successfully")
except ImportError as e:
    print(f"❌ Face recognition not available: {e}")
    FACE_RECOGNITION_AVAILABLE = False
    # Fallback: simple face detection using OpenCV
    try:
        import cv2
        print("✅ Using OpenCV as fallback")
    except ImportError:
        print("❌ OpenCV also not available")

app = Flask(__name__)
app.secret_key = "face-recognition-secret-123"
app.config['UPLOAD_FOLDER'] = "static/uploads"
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Create uploads folder if not exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

SCHOOL_LOCATION = {'latitude': -6.2088, 'longitude': 106.8456}
MAX_RADIUS_METERS = 100

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@contextmanager
def db_connection():
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            if session['user']['role'].upper() not in roles:
                flash("Akses ditolak", "danger")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000
    try:
        lat1_rad = radians(float(lat1))
        lon1_rad = radians(float(lon1))
        lat2_rad = radians(float(lat2))
        lon2_rad = radians(float(lon2))

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c
    except (ValueError, TypeError):
        return float('inf')

def check_duplicate_attendance(user_id, date):
    with db_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM attendance WHERE user_id = ? AND date = ?",
            (user_id, date)
        ).fetchone()
        return existing is not None

def simple_face_detection(image_data):
    """Simple face detection using OpenCV as fallback"""
    try:
        import cv2

        # Decode base64 image
        img_data = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Load face detector
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # Detect faces
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        return len(faces) > 0, len(faces)
    except Exception as e:
        print(f"Simple face detection error: {e}")
        return False, 0

def verify_face_with_fallbacks(user_id, image_data):
    """Verify face with multiple fallback methods"""

    # Method 1: Using face_recognition library
    if FACE_RECOGNITION_AVAILABLE:
        try:
            # Decode base64 image
            img_data = base64.b64decode(image_data.split(',')[1])
            image = face_recognition.load_image_file(io.BytesIO(img_data))

            # Get face encodings
            face_encodings = face_recognition.face_encodings(image)

            if len(face_encodings) > 0:
                # For now, just return that a face was detected
                # In a real system, you'd compare with reference photos
                return True, 0.8, "Face detected (face_recognition)"
            else:
                return False, 0.0, "No face detected"

        except Exception as e:
            print(f"Face recognition error: {e}")

    # Method 2: Simple face detection with OpenCV
    try:
        face_detected, face_count = simple_face_detection(image_data)
        if face_detected:
            return True, 0.7, f"Face detected (OpenCV) - {face_count} faces"
        else:
            return False, 0.0, "No face detected (OpenCV)"
    except Exception as e:
        print(f"OpenCV face detection error: {e}")

    # Method 3: Basic validation - just check if image exists
    try:
        img_data = base64.b64decode(image_data.split(',')[1])
        image = Image.open(io.BytesIO(img_data))
        return True, 0.5, "Image validated (basic check)"
    except:
        return False, 0.0, "Invalid image"

def calculate_similarity(text1, text2):
    """Hitung similarity antara dua text (sederhana)"""
    words1 = set(text1.split())
    words2 = set(text2.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union)

def find_best_response(conn, user_message):
    """Cari jawaban terbaik dari knowledge base"""

    # Default response jika tidak ditemukan
    default_response = {
        'response': 'Maaf, saya belum paham pertanyaan itu. Coba tanya tentang:\n• Cara presensi\n• Face recognition\n• Reset password\n• Riwayat presensi\n• Fitur sistem',
        'type': 'info',
        'confidence': 0.0
    }

    # Cari pattern yang match di knowledge base
    knowledge_items = conn.execute('''
        SELECT question_pattern, answer, category, priority 
        FROM chatbot_knowledge 
        WHERE is_active = TRUE
        ORDER BY priority DESC
    ''').fetchall()

    best_match = None
    highest_score = 0

    for pattern, answer, category, priority in knowledge_items:
        patterns = pattern.split('|')
        for p in patterns:
            score = calculate_similarity(user_message, p)
            if score > highest_score and score > 0.3:  # Threshold similarity
                highest_score = score
                best_match = {
                    'response': answer,
                    'type': 'success' if score > 0.7 else 'info',
                    'confidence': round(score, 2)
                }

    # Jika ada match yang cukup baik
    if best_match and highest_score > 0.4:
        return best_match

    # Fallback ke hardcoded responses untuk pattern umum
    fallback_responses = {
        'hai|halo|hi|hello|hey': 'Halo! Ada yang bisa saya bantu? 😊',
        'terima kasih|thanks|makasih': 'Sama-sama! Semoga harimu menyenangkan 🌟',
        'baik|good|oke': 'Bagus! Ada yang bisa saya bantu?',
        'apa kabar|how are you': 'Saya baik-baik saja, siap membantu Anda!',
        'nama kamu|siapa kamu': 'Saya asisten virtual sistem presensi MTs Nurul Huda 🤖',
        'help|bantuan|tolong': 'Saya bisa membantu dengan:\n• Presensi dan face recognition\n• Masalah teknis\n• Informasi sistem\n• Panduan penggunaan'
    }

    for pattern, response in fallback_responses.items():
        patterns = pattern.split('|')
        for p in patterns:
            if p in user_message:
                return {
                    'response': response,
                    'type': 'info',
                    'confidence': 0.8
                }

    return default_response

def init_db():
    with db_connection() as conn:
        cur = conn.cursor()

        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT CHECK(role IN ('ADMIN','GURU','KARYAWAN','KEPALA SEKOLAH')),
                nip TEXT,
                jabatan TEXT,
                status TEXT DEFAULT 'Aktif',
                photo_profile TEXT,
                photo_ref1 TEXT,
                photo_ref2 TEXT,
                face_descriptors TEXT,
                face_trained_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                waktu_masuk TEXT,
                waktu_keluar TEXT,
                status TEXT,
                keterangan TEXT,
                latitude TEXT,
                longitude TEXT,
                image_filename TEXT,
                face_confidence REAL DEFAULT 0,
                face_verified BOOLEAN DEFAULT FALSE,
                verification_method TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE(user_id, date)
            )''')

        # Tabel untuk chatbot conversations
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chatbot_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                message_type TEXT DEFAULT 'general',
                confidence_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

        # Tabel untuk chatbot knowledge base
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chatbot_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_pattern TEXT NOT NULL,
                answer TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                tags TEXT,
                priority INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO users (name, email, password, role, status) VALUES (?, ?, ?, ?, ?)",
                        ("Admin", "admin@example.com", generate_password_hash("admin123"), "ADMIN", "Aktif"))

        # Insert default knowledge data
        cur.execute("SELECT COUNT(*) FROM chatbot_knowledge")
        if cur.fetchone()[0] == 0:
            default_knowledge = [
                # Presensi questions
                ("cara presensi|bagaimana presensi|presensi bagaimana", 
                 "Untuk melakukan presensi:\n1. Buka menu 'Presensi'\n2. Pastikan GPS aktif\n3. Nyalakan kamera\n4. Ambil foto wajah\n5. Submit presensi", 
                 "presensi", "cara,presensi,tutorial"),

                ("face recognition|verifikasi wajah|wajah tidak terdeteksi", 
                 "Sistem menggunakan face recognition untuk keamanan. Pastikan:\n- Wajah terlihat jelas\n- Pencahayaan cukup\n- Tidak menggunakan masker\n- Background netral", 
                 "teknologi", "face recognition,wajah,verifikasi"),

                ("radius presensi|jarak presensi|gps tidak bekerja", 
                 "Presensi hanya bisa dilakukan dalam radius 100 meter dari sekolah. Pastikan:\n- GPS smartphone aktif\n- Izin lokasi diberikan\n- Koneksi internet stabil", 
                 "presensi", "gps,radius,lokasi"),

                ("lupa password|reset password|ganti password", 
                 "Untuk reset password:\n1. Login sebagai admin\n2. Buka menu 'Kelola Guru' \n3. Pilih user yang ingin direset\n4. Klik 'Reset Password'", 
                 "akun", "password,login,akun"),

                ("riwayat presensi|lihat presensi|history presensi", 
                 "Untuk melihat riwayat presensi:\n1. Buka menu 'Riwayat'\n2. Pilih bulan yang diinginkan\n3. Lihat data presensi Anda", 
                 "presensi", "riwayat,history,data"),

                ("rekap presensi|data presensi|laporan presensi", 
                 "Untuk melihat rekap presensi (Admin/Kepala Sekolah):\n1. Buka menu 'Rekap'\n2. Filter berdasarkan nama/tanggal\n3. Lihat data rekap lengkap", 
                 "admin", "rekap,laporan,data"),

                ("login error|tidak bisa login|gagal login", 
                 "Jika mengalami masalah login:\n1. Periksa email dan password\n2. Pastikan akun masih aktif\n3. Hubungi admin jika lupa password\n4. Clear cache browser jika perlu", 
                 "akun", "login,error,masalah"),

                ("fitur sistem|apa saja fitur|kemampuan sistem", 
                 "Fitur sistem presensi:\n✅ Presensi dengan face recognition\n✅ Verifikasi GPS real-time\n✅ Riwayat dan rekap presensi\n✅ Management user\n✅ Chatbot assistance", 
                 "sistem", "fitur,kemampuan,sistem"),

                ("admin|peran admin|hak akses admin", 
                 "Peran Admin memiliki akses:\n- Kelola data guru/karyawan\n- Lihat rekap semua presensi\n- Reset password user\n- Management sistem", 
                 "admin", "admin,peran,akses"),

                ("guru|peran guru|hak akses guru", 
                 "Peran Guru memiliki akses:\n- Presensi harian\n- Lihat riwayat pribadi\n- Update profil\n- Chatbot assistance", 
                 "user", "guru,peran,akses")
            ]

            for question, answer, category, tags in default_knowledge:
                cur.execute(
                    "INSERT INTO chatbot_knowledge (question_pattern, answer, category, tags) VALUES (?, ?, ?, ?)",
                    (question, answer, category, tags)
                )

        conn.commit()

# ===== ROUTES =====

@app.route('/')
def home():
    return redirect(url_for('dashboard') if 'user' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ? AND status = 'Aktif'", (email,)).fetchone()
            if user and check_password_hash(user['password'], password):
                session['user'] = dict(user)
                flash("Login berhasil!", "success")
                return redirect(url_for('dashboard'))
            flash("Email atau password salah", "danger")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        try:
            data = {k: request.form.get(k, '') for k in ['name', 'email', 'password', 'confirm_password', 'role', 'nip', 'jabatan', 'status']}

            if data['password'] != data['confirm_password']:
                flash("Password tidak cocok", "danger")
                return render_template('signup.html')

            hashed = generate_password_hash(data['password'])
            with db_connection() as conn:
                conn.execute("""
                    INSERT INTO users (name, email, password, role, nip, jabatan, status) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (data['name'], data['email'], hashed, data['role'], data['nip'], data['jabatan'], data['status'] or 'Aktif'))
                conn.commit()
                flash("Pendaftaran berhasil! Silakan login.", "success")
                return redirect(url_for('login'))

        except sqlite3.IntegrityError:
            flash("Email sudah terdaftar", "danger")
        except Exception as e:
            flash(f"Terjadi error: {str(e)}", "danger")

    return render_template('signup.html')

@app.route('/dashboard')
@require_role('ADMIN', 'GURU', 'KARYAWAN', 'KEPALA SEKOLAH')
def dashboard():
    user = session['user']
    with db_connection() as conn:
        chart_data = conn.execute("""
            SELECT date, COUNT(*) as count FROM attendance 
            WHERE date >= date('now', '-6 days') 
            GROUP BY date ORDER BY date
        """).fetchall()

        labels = [row['date'] for row in chart_data]
        counts = [row['count'] for row in chart_data]

        if user['role'] in ['GURU', 'KARYAWAN']:
            riwayat = conn.execute("""
                SELECT date, waktu_masuk, waktu_keluar, status, keterangan 
                FROM attendance WHERE user_id = ? 
                ORDER BY date DESC LIMIT 5
            """, (user['id'],)).fetchall()
            return render_template('dashboard.html', user=user, riwayat=riwayat, labels=labels, data=counts)

        return render_template('dashboard.html', user=user, labels=labels, data=counts)

@app.route('/presensi', methods=['GET', 'POST'])
@require_role('GURU', 'KARYAWAN','ADMIN','KEPALA SEKOLAH')
def presensi():
    today = datetime.now().strftime('%Y-%m-%d')
    user_id = session['user']['id']

    # Cek apakah sudah absen hari ini
    sudah_absen = check_duplicate_attendance(user_id, today)
    presensi_hari_ini = None

    if sudah_absen:
        with db_connection() as conn:
            presensi_hari_ini = conn.execute(
                "SELECT waktu_masuk, status, keterangan FROM attendance WHERE user_id = ? AND date = ?",
                (user_id, today)
            ).fetchone()

    # Cek training status untuk frontend
    with db_connection() as conn:
        training_status = conn.execute(
            "SELECT face_descriptors FROM users WHERE id = ?", 
            (user_id,)
        ).fetchone()
        is_trained = training_status and training_status['face_descriptors'] is not None

    if request.method == 'POST':
        if sudah_absen:
            flash("Anda sudah melakukan presensi hari ini", "warning")
            return redirect(url_for('dashboard'))

        try:
            waktu_masuk = request.form.get('waktu_masuk')
            waktu_keluar = request.form.get('waktu_keluar')
            status = request.form.get('status')
            keterangan = request.form.get('keterangan', '')
            latitude = request.form.get('latitude', '')
            longitude = request.form.get('longitude', '')
            image_data = request.form.get('image_data')
            face_detected = request.form.get('face_detected', 'false')
            face_confidence = request.form.get('face_confidence', 0)
            filename = None

            # Validasi data wajib
            if not all([waktu_masuk, status]):
                flash("Data tidak lengkap", "danger")
                return redirect(url_for('presensi'))

            # Validasi GPS
            if latitude and longitude:
                try:
                    distance = calculate_distance(
                        float(latitude), float(longitude),
                        SCHOOL_LOCATION['latitude'], SCHOOL_LOCATION['longitude']
                    )

                    if distance > MAX_RADIUS_METERS:
                        flash(f"Presensi gagal: Anda berada {distance:.0f}m dari sekolah", "danger")
                        return redirect(url_for('presensi'))
                except (ValueError, TypeError):
                    pass

            # Validasi Face Recognition (DUAL SYSTEM)
            verification_method = "Face-API.js Matching"
            face_verified = face_detected == 'true'

            # Fallback ke sistem lama jika face-API.js tidak mendeteksi
            if not face_verified and image_data:
                face_verified, fallback_confidence, fallback_method = verify_face_with_fallbacks(user_id, image_data)
                face_confidence = fallback_confidence
                verification_method = fallback_method

            if not face_verified:
                flash("Wajah tidak terdeteksi. Pastikan wajah terlihat jelas!", "danger")
                return redirect(url_for('presensi'))

            # Simpan foto
            if image_data and image_data.startswith('data:image'):
                try:
                    img_str = image_data.split(',')[1]
                    img_bytes = base64.b64decode(img_str)
                    filename = f"presensi_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                    with open(file_path, 'wb') as f:
                        f.write(img_bytes)
                except Exception as e:
                    print(f"Error saving image: {e}")
                    filename = None

            # Simpan presensi
            with db_connection() as conn:
                conn.execute("""
                    INSERT INTO attendance 
                    (user_id, date, waktu_masuk, waktu_keluar, status, keterangan, 
                     latitude, longitude, image_filename, face_confidence, face_verified, verification_method) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, today, waktu_masuk, waktu_keluar, status, keterangan, 
                     latitude, longitude, filename, face_confidence, face_verified, verification_method))
                conn.commit()

            flash(f"Presensi berhasil! {verification_method}", "success")
            return redirect(url_for('dashboard'))

        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('presensi'))

    return render_template('presensi.html', 
                         tanggal=today, 
                         sudah_absen=sudah_absen,
                         presensi_hari_ini=presensi_hari_ini,
                         face_recognition_available=FACE_RECOGNITION_AVAILABLE,
                         is_trained=is_trained)

# Routes lainnya
@app.route('/riwayat')
@require_role('GURU', 'KARYAWAN', 'ADMIN', 'KEPALA SEKOLAH')
def riwayat():
    user = session['user']
    bulan = request.args.get('bulan', datetime.now().strftime('%Y-%m'))

    with db_connection() as conn:
        riwayat = conn.execute("""
            SELECT date, waktu_masuk, waktu_keluar, status, keterangan, 
                   face_confidence, verification_method
            FROM attendance WHERE user_id = ? AND date LIKE ? 
            ORDER BY date DESC
        """, (user['id'], f"{bulan}-%")).fetchall()

        rekap_data = conn.execute("""
            SELECT status, COUNT(*) as count 
            FROM attendance 
            WHERE user_id = ? AND date LIKE ?
            GROUP BY status
        """, (user['id'], f"{bulan}-%")).fetchall()

        rekap = {'Hadir': 0, 'Izin': 0, 'Sakit': 0}
        for row in rekap_data:
            status = row['status']
            if status in rekap:
                rekap[status] = row['count']

    return render_template('riwayat.html', 
                         riwayat=riwayat, 
                         user=user, 
                         rekap=rekap, 
                         bulan=bulan)

@app.route('/profil', methods=['GET', 'POST'])
@require_role('ADMIN', 'GURU', 'KARYAWAN', 'KEPALA SEKOLAH')
def profil():
    user = session['user']

    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            nip = request.form.get('nip', '')
            jabatan = request.form.get('jabatan', '')
            password = request.form.get('password', '')

            # Handle reference photos for face recognition
            photo_ref1 = request.files.get('photo_ref1')
            photo_ref2 = request.files.get('photo_ref2')

            filenames = {
                'photo_ref1': user.get('photo_ref1'),
                'photo_ref2': user.get('photo_ref2')
            }

            # Upload reference photos
            for i, photo_file in enumerate([photo_ref1, photo_ref2], 1):
                if photo_file and photo_file.filename != '' and allowed_file(photo_file.filename):
                    filename = secure_filename(f"ref_{user['id']}_{i}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    photo_file.save(file_path)
                    filenames[f'photo_ref{i}'] = filename

            with db_connection() as conn:
                if password:
                    hashed_pw = generate_password_hash(password)
                    conn.execute("""
                        UPDATE users SET name=?, email=?, nip=?, jabatan=?, 
                        password=?, photo_ref1=?, photo_ref2=? WHERE id=?
                    """, (name, email, nip, jabatan, hashed_pw, 
                         filenames['photo_ref1'], filenames['photo_ref2'], user['id']))
                else:
                    conn.execute("""
                        UPDATE users SET name=?, email=?, nip=?, jabatan=?,
                        photo_ref1=?, photo_ref2=? WHERE id=?
                    """, (name, email, nip, jabatan, 
                         filenames['photo_ref1'], filenames['photo_ref2'], user['id']))
                conn.commit()

            # Update session
            user.update({
                'name': name,
                'email': email,
                'nip': nip,
                'jabatan': jabatan,
                'photo_ref1': filenames['photo_ref1'],
                'photo_ref2': filenames['photo_ref2']
            })
            session['user'] = user

            flash('Profil berhasil diperbarui!', 'success')
            return redirect(url_for('profil'))

        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')

    return render_template('profil.html', user=user, face_recognition_available=FACE_RECOGNITION_AVAILABLE)

@app.route('/rekap')
@require_role('ADMIN', 'KEPALA SEKOLAH')
def rekap():
    selected_nama = request.args.get('nama', '')
    selected_tanggal = request.args.get('tanggal', '')

    with db_connection() as conn:
        nama_list = [row[0] for row in conn.execute("SELECT name FROM users WHERE role IN ('GURU', 'KARYAWAN') ORDER BY name").fetchall()]

        query = """
            SELECT u.name, a.date, a.waktu_masuk, a.waktu_keluar, a.status, a.keterangan,
                   a.face_confidence, a.verification_method
            FROM attendance a
            JOIN users u ON a.user_id = u.id
            WHERE 1=1
        """
        params = []

        if selected_nama:
            query += " AND u.name = ?"
            params.append(selected_nama)
        if selected_tanggal:
            query += " AND a.date = ?"
            params.append(selected_tanggal)

        query += " ORDER BY a.date DESC, u.name"

        data = conn.execute(query, params).fetchall()

        total_hadir = sum(1 for row in data if row['status'] == 'Hadir')
        total_izin = sum(1 for row in data if row['status'] == 'Izin')
        total_sakit = sum(1 for row in data if row['status'] == 'Sakit')

    return render_template('rekap.html',
                         hasil=data,
                         nama_list=nama_list,
                         selected_nama=selected_nama,
                         selected_tanggal=selected_tanggal,
                         total_hadir=total_hadir,
                         total_izin=total_izin,
                         total_sakit=total_sakit)

@app.route('/kelola_guru')
@require_role('ADMIN', 'KEPALA SEKOLAH')
def kelola_guru():
    with db_connection() as conn:
        data_guru = conn.execute("SELECT * FROM users WHERE role = 'GURU' ORDER BY name").fetchall()
    return render_template('kelola_guru.html', data_guru=data_guru)

@app.route('/logout')
def logout():
    session.clear()
    flash("Logout berhasil", "info")
    return redirect(url_for('login'))

# ===== FACE API ROUTES =====

@app.route('/api/face/train', methods=['POST'])
@require_role('GURU', 'KARYAWAN', 'ADMIN', 'KEPALA SEKOLAH')
def api_face_train():
    """API untuk training wajah user"""
    try:
        data = request.get_json()
        descriptors = data.get('descriptors', [])
        user_id = session['user']['id']

        if not descriptors:
            return jsonify({
                'success': False,
                'message': 'Tidak ada data wajah yang diterima'
            })

        # Simpan face descriptors sebagai JSON
        descriptors_json = json.dumps(descriptors)

        with db_connection() as conn:
            conn.execute(
                "UPDATE users SET face_descriptors = ?, face_trained_at = CURRENT_TIMESTAMP WHERE id = ?",
                (descriptors_json, user_id)
            )
            conn.commit()

        return jsonify({
            'success': True,
            'message': 'Training wajah berhasil! Sistem sekarang dapat mengenali wajah Anda.'
        })

    except Exception as e:
        print(f"Face training error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@app.route('/api/face/verify', methods=['POST'])
@require_role('GURU', 'KARYAWAN', 'ADMIN', 'KEPALA SEKOLAH')
def api_face_verify():
    """API untuk verifikasi wajah dengan matching ke database"""
    try:
        data = request.get_json()
        descriptor = data.get('descriptor', [])
        user_id = session['user']['id']

        if not descriptor:
            return jsonify({
                'success': False,
                'verified': False,
                'message': 'Tidak ada descriptor wajah yang diterima'
            })

        # Ambil stored descriptors user
        with db_connection() as conn:
            user = conn.execute(
                "SELECT face_descriptors FROM users WHERE id = ?", 
                (user_id,)
            ).fetchone()

            if not user or not user['face_descriptors']:
                return jsonify({
                    'success': False,
                    'verified': False,
                    'message': 'Anda belum melakukan training wajah. Silakan training terlebih dahulu.'
                })

            # Compare dengan stored descriptors
            stored_descriptors = json.loads(user['face_descriptors'])
            best_distance = float('inf')

            for stored_desc in stored_descriptors:
                distance = np.linalg.norm(np.array(descriptor) - np.array(stored_desc))
                if distance < best_distance:
                    best_distance = distance

            # Threshold untuk face matching (bisa disesuaikan)
            verified = best_distance < 0.6
            confidence = max(0, 1 - best_distance)

            return jsonify({
                'success': True,
                'verified': verified,
                'confidence': round(confidence, 2),
                'distance': round(best_distance, 2),
                'message': 'Wajah dikenali' if verified else 'Wajah tidak dikenali'
            })

    except Exception as e:
        print(f"Face verification error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@app.route('/api/face/check-training')
@require_role('GURU', 'KARYAWAN', 'ADMIN', 'KEPALA SEKOLAH')
def api_face_check_training():
    """Cek status training user"""
    try:
        user_id = session['user']['id']

        with db_connection() as conn:
            user = conn.execute(
                "SELECT face_descriptors, face_trained_at FROM users WHERE id = ?", 
                (user_id,)
            ).fetchone()

            trained = user and user['face_descriptors'] is not None
            trained_at = user['face_trained_at'] if trained else None

            return jsonify({
                'success': True,
                'trained': trained,
                'trained_at': trained_at
            })

    except Exception as e:
        print(f"Check training error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@app.route('/api/face/reset-training', methods=['POST'])
@require_role('GURU', 'KARYAWAN', 'ADMIN', 'KEPALA SEKOLAH')
def api_face_reset_training():
    """Reset training wajah user"""
    try:
        user_id = session['user']['id']

        with db_connection() as conn:
            conn.execute(
                "UPDATE users SET face_descriptors = NULL, face_trained_at = NULL WHERE id = ?",
                (user_id,)
            )
            conn.commit()

        return jsonify({
            'success': True,
            'message': 'Training wajah berhasil direset. Silakan training ulang.'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

# ===== CHATBOT ROUTES =====

@app.route('/chatbot', methods=['POST'])
def chatbot():
    if 'user' not in session:
        return jsonify({'response': 'Silakan login terlebih dahulu 😊', 'type': 'error'})

    user_id = session['user']['id']
    data = request.get_json()
    user_message = data.get('message', '').lower().strip()

    if not user_message:
        return jsonify({'response': 'Pesan tidak boleh kosong', 'type': 'error'})

    try:
        # Simpan pesan user ke database
        with db_connection() as conn:
            # Cari jawaban di knowledge base
            bot_response = find_best_response(conn, user_message)

            # Simpan conversation ke database
            conn.execute(
                "INSERT INTO chatbot_conversations (user_id, user_message, bot_response) VALUES (?, ?, ?)",
                (user_id, user_message, bot_response['response'])
            )
            conn.commit()

        return jsonify({
            'response': bot_response['response'],
            'type': bot_response['type'],
            'confidence': bot_response['confidence']
        })

    except Exception as e:
        print(f"Chatbot error: {e}")
        return jsonify({
            'response': 'Maaf, sedang ada gangguan teknis. Silakan coba lagi.',
            'type': 'error'
        })

@app.route('/api/chatbot/history')
@require_role('ADMIN', 'GURU', 'KARYAWAN', 'KEPALA SEKOLAH')
def chatbot_history():
    """Ambil history chat user"""
    try:
        user_id = session['user']['id']
        limit = request.args.get('limit', 10, type=int)

        with db_connection() as conn:
            history = conn.execute('''
                SELECT user_message, bot_response, created_at 
                FROM chatbot_conversations 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit)).fetchall()

            history_list = [
                {
                    'user_message': row['user_message'],
                    'bot_response': row['bot_response'],
                    'time': row['created_at']
                }
                for row in reversed(history)  # Reverse untuk urutan kronologis
            ]

            return jsonify({
                'success': True,
                'history': history_list
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@app.route('/api/chatbot/clear-history', methods=['POST'])
@require_role('ADMIN', 'GURU', 'KARYAWAN', 'KEPALA SEKOLAH')
def clear_chat_history():
    """Clear chat history user"""
    try:
        user_id = session['user']['id']

        with db_connection() as conn:
            conn.execute(
                "DELETE FROM chatbot_conversations WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()

        return jsonify({
            'success': True,
            'message': 'Riwayat chat berhasil dihapus'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@app.route('/admin/chatbot-knowledge')
@require_role('ADMIN', 'KEPALA SEKOLAH')
def chatbot_knowledge_management():
    """Halaman management knowledge base (Admin only)"""
    with db_connection() as conn:
        knowledge_items = conn.execute('''
            SELECT id, question_pattern, answer, category, tags, priority, is_active, created_at
            FROM chatbot_knowledge 
            ORDER BY priority DESC, created_at DESC
        ''').fetchall()

        conversation_stats = conn.execute('''
            SELECT COUNT(*) as total_conversations, 
                   COUNT(DISTINCT user_id) as unique_users,
                   MAX(created_at) as last_activity
            FROM chatbot_conversations
        ''').fetchone()

    return render_template('chatbot_knowledge.html', 
                         knowledge_items=knowledge_items,
                         stats=conversation_stats)

@app.route('/api/chatbot/knowledge', methods=['POST'])
@require_role('ADMIN', 'KEPALA SEKOLAH')
def add_chatbot_knowledge():
    """Tambah knowledge baru"""
    try:
        data = request.get_json()
        question_pattern = data.get('question_pattern')
        answer = data.get('answer')
        category = data.get('category', 'general')
        tags = data.get('tags', '')
        priority = data.get('priority', 1)

        with db_connection() as conn:
            conn.execute('''
                INSERT INTO chatbot_knowledge (question_pattern, answer, category, tags, priority)
                VALUES (?, ?, ?, ?, ?)
            ''', (question_pattern, answer, category, tags, priority))
            conn.commit()

        return jsonify({'success': True, 'message': 'Knowledge berhasil ditambah'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.before_request
def before_request():
    init_db()

if __name__ == '__main__':
    print("=" * 50)
    print("FACE RECOGNITION SYSTEM STATUS")
    print("=" * 50)
    print(f"Face Recognition Library: {'✅ READY' if FACE_RECOGNITION_AVAILABLE else '❌ UNAVAILABLE'}")
    print(f"Upload Folder: {app.config['UPLOAD_FOLDER']}")
    print("=" * 50)

    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
