from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from contextlib import contextmanager
from dotenv import load_dotenv
import sqlite3, os, base64
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default-secret-key")
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.'in filename and filename.rsplit('.', 1) [1].lower() in ALLOWED_EXTENSIONS

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
                status TEXT CHECK(status IN ('Aktif','Nonaktif')),
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )''')

        cur.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO users (name, email, password, role, status) VALUES (?, ?, ?, ?, ?)",
                        ("Admin", "admin@example.com", generate_password_hash("admin123"), "ADMIN", "Aktif"))
        conn.commit()

@app.route('/')
def home():
    return redirect(url_for('dashboard') if 'user' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user['password'], password):
                session['user'] = dict(user)
                return redirect(url_for('dashboard'))
            flash("Login gagal", "danger")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = {k: request.form[k] for k in request.form}
        if data['password'] != data['confirm_password']:
            flash("Password tidak cocok", "danger")
            return render_template('signup.html')
        hashed = generate_password_hash(data['password'])
        with db_connection() as conn:
            try:
                conn.execute("INSERT INTO users (name, email, password, role, nip, jabatan, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (data['name'], data['email'], hashed, data['role'], data['nip'], data['jabatan'], data['status']))
                conn.commit()
                flash("Pendaftaran berhasil", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Email sudah terdaftar", "danger")
    return render_template('signup.html')

@app.route('/dashboard')
@require_role('ADMIN', 'GURU', 'KARYAWAN', 'KEPALA SEKOLAH')
def dashboard():
    user = session['user']
    with db_connection() as conn:
        chart = conn.execute("SELECT date, COUNT(*) FROM attendance GROUP BY date ORDER BY date DESC LIMIT 7").fetchall()
        labels = [row[0] for row in reversed(chart)]
        counts = [row[1] for row in reversed(chart)]
        if user['role'] in ['GURU', 'KARYAWAN']:
            riwayat = conn.execute("SELECT date, waktu_masuk, waktu_keluar, status, keterangan FROM attendance WHERE user_id = ? ORDER BY date DESC LIMIT 5", (user['id'],)).fetchall()
            return render_template('dashboard.html', user=user, riwayat=riwayat, labels=labels, data=counts)
        return render_template('dashboard.html', user=user, labels=labels, data=counts)

@app.route('/profil', methods=['GET', 'POST'])
def profil():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        nip = request.form.get('nip', '')
        jabatan = request.form.get('jabatan', '')
        status = request.form.get('status', '')
        password = request.form.get('password', '')

        photo_profile = request.files.get('photo_profile')
        photo_ref1 = request.files.get('photo_ref1')
        photo_ref2 = request.files.get('photo_ref2')

        filenames = {}

        # ✅ Perbaikan struktur for-if
        for file_key, file_obj in {
            'photo_profile': photo_profile,
            'photo_ref1': photo_ref1,
            'photo_ref2': photo_ref2
        }.items():
            if file_obj and file_obj.filename != '' and allowed_file(file_obj.filename):
                filename = secure_filename(file_obj.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_obj.save(file_path)
                filenames[file_key] = filename
            else:
                filenames[file_key] = user.get(file_key)

        with db_connection() as conn:
            if password:
                hashed_pw = generate_password_hash(password)
                conn.execute("""
                    UPDATE users SET name=?, email=?, nip=?, jabatan=?, status=?,
                        password=?, photo_profile=?, photo_ref1=?, photo_ref2=?
                    WHERE id=?
                """, (
                    name, email, nip, jabatan, status, hashed_pw,
                    filenames['photo_profile'], filenames['photo_ref1'], filenames['photo_ref2'], user['id']
                ))
            else:
                conn.execute("""
                    UPDATE users SET name=?, email=?, nip=?, jabatan=?, status=?,
                        photo_profile=?, photo_ref1=?, photo_ref2=?
                    WHERE id=?
                """, (
                    name, email, nip, jabatan, status,
                    filenames['photo_profile'], filenames['photo_ref1'], filenames['photo_ref2'], user['id']
                ))
            conn.commit()

        # Perbarui session user
        user.update({
            'name': name,
            'email': email,
            'nip': nip,
            'jabatan': jabatan,
            'status': status,
            'photo_profile': filenames['photo_profile'],
            'photo_ref1': filenames['photo_ref1'],
            'photo_ref2': filenames['photo_ref2']
        })
        session['user'] = user
        flash('Profil berhasil diperbarui!', 'success')
        return redirect(url_for('profil'))

    return render_template('profil.html', user=user)

@app.route('/presensi', methods=['GET', 'POST'])
@require_role('GURU', 'KARYAWAN','ADMIN','KEPALA SEKOLAH')
def presensi():
    today = datetime.now().strftime('%Y-%m-%d')
    if request.method == 'POST':
        form = request.form
        image_data = form.get('image_data')
        filename = None
        if image_data:
            try:
                img_str = image_data.split(',')[1]
                img_bytes = base64.b64decode(img_str)
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                filename = f"presensi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'wb') as f:
                    f.write(img_bytes)
            except:
                flash("Gagal menyimpan foto", "warning")
        with db_connection() as conn:
            conn.execute("INSERT INTO attendance (user_id, date, waktu_masuk, waktu_keluar, status, keterangan, latitude, longitude, image_filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (session['user']['id'], today, form['waktu_masuk'], form['waktu_keluar'], form['status'], form['keterangan'], form['latitude'], form['longitude'], filename))
            conn.commit()
        flash("Presensi berhasil", "success")
        return redirect(url_for('dashboard'))
    return render_template('presensi.html', tanggal=today)

@app.route('/riwayat')
@require_role('GURU', 'KARYAWAN', 'ADMIN', 'KEPALA SEKOLAH')
def riwayat():
    user = session['user']
    with db_connection() as conn:
        # Ambil semua data riwayat presensi user
        riwayat = conn.execute(
            "SELECT date, waktu_masuk, waktu_keluar, status, keterangan, latitude, longitude, image_filename FROM attendance WHERE user_id = ? ORDER BY date DESC",
            (user['id'],)
        ).fetchall()

        # Hitung rekap berdasarkan status
        rows = conn.execute(
            "SELECT status FROM attendance WHERE user_id = ?", (user['id'],)
        ).fetchall()

        rekap = {'Hadir': 0, 'Izin': 0, 'Sakit': 0}
        for row in rows:
            status = row[0]
            if status in rekap:
                rekap[status] += 1

    return render_template('riwayat.html', riwayat=riwayat, user=user, rekap=rekap)


@app.route('/rekap', methods=['GET', 'POST'])
@require_role('ADMIN', 'KEPALA SEKOLAH')
def rekap():
    with db_connection() as conn:
        data = conn.execute("""
            SELECT users.name, attendance.date, attendance.status, attendance.image_filename 
            FROM attendance 
            JOIN users ON users.id = attendance.user_id 
            ORDER BY attendance.date DESC
        """).fetchall()
        print("Data Rekap:", data)  # <-- ini untuk debug
    return render_template('rekap.html', hasil=data)

@app.route('/kelola_guru', methods=['GET', 'POST'])
@require_role('ADMIN', 'KEPALA SEKOLAH')
def kelola_guru():
    if request.method == 'POST':
        name = request.form['name']
        nip = request.form['nip']
        email = request.form['email']
        password = request.form['password']
        status = request.form['status']
        hashed_password = generate_password_hash(password)

        with db_connection() as conn:
            conn.execute("INSERT INTO users (name, nip, email, password, role, status) VALUES (?, ?, ?, ?, ?, ?)",
                         (name, nip, email, hashed_password, 'GURU', status))
            conn.commit()

    with db_connection() as conn:
        data_guru = conn.execute("SELECT * FROM users WHERE role = 'GURU'").fetchall()
    return render_template('kelola_guru.html', data_guru=data_guru)


@app.route('/hapus_guru/<int:id>')
@require_role('ADMIN', 'KEPALA SEKOLAH')
def hapus_guru(id):
    with db_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (id,))
        conn.commit()
    flash("Data guru berhasil dihapus", "success")
    return redirect(url_for('kelola_guru'))



@app.route('/logout')
def logout():
    session.clear()
    flash("Logout berhasil", "info")
    return redirect(url_for('login'))

@app.route('/chatbot', methods=['POST'])
def chatbot():
    message = request.json.get('message', '').lower()
    response = "Maaf, saya tidak mengerti."
    if "halo" in message:
        response = "Halo! Ada yang bisa saya bantu?"
    elif "presensi" in message:
        response = "Silakan klik menu Presensi di sidebar."
    elif "logout" in message:
        response = "Klik tombol logout di atas."
    elif "terima kasih" in message:
        response = "Sama-sama 😊"
    return jsonify({'response': response})

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    init_db()
    app.run(debug=True, host='0.0.0.0', port=8000)