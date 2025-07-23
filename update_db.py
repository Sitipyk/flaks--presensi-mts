import sqlite3

# Koneksi ke database SQLite
conn = sqlite3.connect('attendance.db')
cur = conn.cursor()

# Tambah kolom photo_profile
try:
    cur.execute("ALTER TABLE users ADD COLUMN photo_profile TEXT")
    print("Kolom photo_profile ditambahkan.")
except sqlite3.OperationalError:
    print("Kolom photo_profile sudah ada.")

# Tambah kolom photo_ref1
try:
    cur.execute("ALTER TABLE users ADD COLUMN photo_ref1 TEXT")
    print("Kolom photo_ref1 ditambahkan.")
except sqlite3.OperationalError:
    print("Kolom photo_ref1 sudah ada.")

# Tambah kolom photo_ref2
try:
    cur.execute("ALTER TABLE users ADD COLUMN photo_ref2 TEXT")
    print("Kolom photo_ref2 ditambahkan.")
except sqlite3.OperationalError:
    print("Kolom photo_ref2 sudah ada.")

# Simpan perubahan dan tutup koneksi
conn.commit()
conn.close()

print("Update struktur database selesai.")