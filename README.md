# flaks--presensi-mts
Judul sistem : Sistem Presensi Guru & Karyawan
Deskripsi:
Aplikasi web berbasis Python (Flask) untuk presensi guru dan karyawan dengan manajemen user multi-role (ADMIN, GURU, KARYAWAN, KEPALA SEKOLAH). Sistem ini mendukung presensi harian lengkap dengan catatan waktu masuk/keluar, status, lokasi GPS, dan foto, serta rekap presensi otomatis dan dashboard interaktif.
Fitur Utama:
1.Login, signup, dan manajemen profil pengguna
2.Presensi harian dengan status (Hadir, Izin, Sakit, Alpa), lokasi GPS, dan foto
3.Rekap presensi harian, mingguan, bulanan, dan tahunan
4.Dashboard interaktif dengan grafik presensi 7 hari terakhir
5.Chatbot internal untuk menanyakan status presensi
6.Manajemen guru/admin oleh ADMIN atau KEPALA SEKOLAH (CRUD user)
7.Keamanan: role-based access control, hashed passwords, validasi file upload
Teknologi yang Digunakan:
1.Backend: Python (Flask)
2.Frontend: HTML / CSS / JavaScript
3.Database: SQLite
4.File Upload: foto profil, dokumen, foto presensi
Skill yang Ditonjolkan:

1.Full-stack development (backend + frontend + database)
2.Membuat sistem multi-role dengan keamanan data
3.Integrasi fitur real-time dan chatbot sederhana
4.Membuat sistem presensi fungsional dengan laporan otomatis
Dependencies / Yang Perlu Di-install
1. Flask
pip install Flask
2. Werkzeug
pip install Werkzeug
3. python-dotenv
pip install python-dotenv
4. SQLite3 → sudah built-in di Python
5. Base64 → sudah built-in di Python

Opsional:

Gunakan virtual environment:

python -m venv venv
source venv/bin/activate  # Linux / macOS
venv\Scripts\activate     # Windows

Bisa buat file requirements.txt untuk install sekaligus:

Flask
Werkzeug
python-dotenv



---

Cara Menjalankan:

1. Clone repository ini


2. Install dependencies (atau pip install -r requirements.txt)


3. Jalankan aplikasi:

python app.py


4. Buka browser dan akses http://localhost:8000
