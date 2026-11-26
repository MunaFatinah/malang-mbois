"""Malang Mbois: Smart Traffic Monitoring & Reporting System (Flask + SQLite)."""
import os, random, sqlite3, uuid
from datetime import datetime
from functools import wraps
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import survei as sv

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database", "malang_mbois.db")
UP = os.path.join(BASE, "static", "uploads")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "malang-mbois-dev-key")  # ganti lewat env SECRET_KEY jika dipublikasikan
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

STATUS = ["Dilaporkan", "Diverifikasi", "Dipantau", "Dalam Penanganan", "Selesai"]
JENIS = ["Kemacetan", "Kecelakaan", "Parkir Liar", "Pelanggaran Lalu Lintas", "Jalan Rusak", "Lampu Lalu Lintas Mati", "Lainnya"]
TINGKAT = ["Lancar", "Ramai", "Padat", "Macet"]
KEL = {t["k"]: (t["lat"], t["lng"]) for t in sv.TITIK}  # pusat perkiraan tiap kelurahan (dari TITIK di survei.py)
# aksi: (role, status baru, status yang diizinkan, catatan wajib, teks riwayat)
ACT = {
    "verifikasi": ("dishub", "Diverifikasi", ["Dilaporkan"], False, "Laporan diverifikasi"),
    "pantau": ("dishub", "Dipantau", ["Dilaporkan", "Diverifikasi"], False, "Ditandai dipantau"),
    "instruksi": ("dishub", "Dipantau", ["Diverifikasi", "Dipantau"], True, "Instruksi ke Polsek"),
    "tangani": ("polsek", "Dalam Penanganan", ["Dipantau"], True, "Mulai penanganan"),
    "selesai": ("polsek", "Selesai", ["Dalam Penanganan"], True, "Penanganan selesai"),
}


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    os.makedirs(UP, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, nama TEXT, role TEXT, pw TEXT);
    CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, user_id INT, lokasi TEXT, kelurahan TEXT, jenis TEXT, tingkat TEXT,
      deskripsi TEXT, foto TEXT, lat REAL, lng REAL, status TEXT, instruksi TEXT DEFAULT '', simulasi INT DEFAULT 0, dibuat TEXT, diubah TEXT);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, report_id INT, aktor TEXT, aksi TEXT, catatan TEXT, foto TEXT, waktu TEXT);""")
    if not c.execute("SELECT 1 FROM users").fetchone():
        for u, n in [("warga", "Warga Demo"), ("dishub", "Dishub Kota Malang"), ("polsek", "Polsek Lowokwaru")]:
            c.execute("INSERT INTO users(username,nama,role,pw) VALUES(?,?,?,?)", (u, n, u, generate_password_hash(u + "123")))
        contoh = [("Simpang Suhat", "Jatimulyo", "Kemacetan", "Macet", "Antrean panjang saat jam pulang"),
                  ("Jl. Mertojoyo Selatan", "Merjosari", "Parkir Liar", "Padat", "Kendaraan parkir di bahu jalan"),
                  ("Jl. Gajayana depan UIN", "Ketawanggede", "Kemacetan", "Ramai", "Arus melambat saat jam masuk kampus")]
        for lok, kel, j, t, d in contoh:  # data simulasi, diberi label "simulasi"
            ts, (la, ln) = now(), KEL[kel]
            rid = c.execute("INSERT INTO reports(user_id,lokasi,kelurahan,jenis,tingkat,deskripsi,lat,lng,status,simulasi,dibuat,diubah) "
                            "VALUES(1,?,?,?,?,?,?,?,'Dilaporkan',1,?,?)", (lok, kel, j, t, d, la, ln, ts, ts)).lastrowid
            c.execute("INSERT INTO history(report_id,aktor,aksi,catatan,waktu) VALUES(?,?,?,?,?)", (rid, "Warga Demo", "Melapor", d, ts))
    c.commit()
    c.close()


def need(*roles):
    """Wajib login; jika roles diisi, hanya role tersebut yang boleh."""
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = db().execute("SELECT * FROM users WHERE id=?", (session.get("uid"),)).fetchone()
            if not u:
                return (jsonify(error="Belum login"), 401) if request.path.startswith("/api") else redirect(url_for("login"))
            if roles and u["role"] not in roles:
                return jsonify(error="Anda tidak punya akses ke fitur ini"), 403
            return f(u, *a, **k)
        return w
    return deco


def simpan_foto(f):
    if not f or not f.filename:
        return ""
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise ValueError("Foto harus berformat png, jpg, atau webp")
    nama = uuid.uuid4().hex + "." + ext
    f.save(os.path.join(UP, nama))
    return "/static/uploads/" + nama


def catat(rid, aktor, aksi, cat, foto, ts):
    db().execute("INSERT INTO history(report_id,aktor,aksi,catatan,foto,waktu) VALUES(?,?,?,?,?,?)", (rid, aktor, aksi, cat, foto, ts))


@app.route("/")
def home():
    return redirect(url_for("dashboard" if "uid" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        row = db().execute("SELECT * FROM users WHERE username=?", (request.form.get("username", "").strip().lower(),)).fetchone()
        if row and check_password_hash(row["pw"], request.form.get("password", "")):
            session.clear()
            session["uid"] = row["id"]
            return redirect(url_for("dashboard"))
        err = "Username atau password salah."
    return render_template("login.html", err=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@need()
def dashboard(u):
    return render_template("dashboard.html", u=u, kel=list(KEL), jenis=JENIS, tingkat=TINGKAT, status=STATUS, cfg=dict(role=u["role"]))


@app.route("/api/reports")
@need()
def reports(u):
    w, a = "", ()
    if u["role"] == "warga":
        w, a = " WHERE r.user_id=?", (u["id"],)
    elif u["role"] == "polsek":
        w = " WHERE r.instruksi!=''"
    rows = [dict(r) for r in db().execute("SELECT r.*, u.nama pelapor FROM reports r JOIN users u ON u.id=r.user_id" + w + " ORDER BY r.id DESC", a)]
    for r in rows:
        r["riwayat"] = [dict(h) for h in db().execute("SELECT * FROM history WHERE report_id=? ORDER BY id", (r["id"],))]
    return jsonify(rows)


@app.route("/api/reports", methods=["POST"])
@need("warga")
def buat(u):
    f = request.form
    lok, kel, jenis, tk, desk = [f.get(k, "").strip() for k in ("lokasi", "kelurahan", "jenis", "tingkat", "deskripsi")]
    if not (lok and desk and kel in KEL and jenis in JENIS and tk in TINGKAT):
        return jsonify(error="Lengkapi semua isian dengan benar."), 400
    try:
        foto = simpan_foto(request.files.get("foto"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    try:
        lat, lng = float(f["lat"]), float(f["lng"])
    except (KeyError, ValueError):  # tidak menandai peta: pakai pusat kelurahan + sedikit geseran agar marker tidak menumpuk
        lat, lng = KEL[kel][0] + random.uniform(-.0008, .0008), KEL[kel][1] + random.uniform(-.0008, .0008)
    ts = now()
    rid = db().execute("INSERT INTO reports(user_id,lokasi,kelurahan,jenis,tingkat,deskripsi,foto,lat,lng,status,dibuat,diubah) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (u["id"], lok, kel, jenis, tk, desk, foto, lat, lng, "Dilaporkan", ts, ts)).lastrowid
    catat(rid, u["nama"], "Melapor", desk, foto, ts)
    db().commit()
    return jsonify(id=rid)


@app.route("/api/reports/<int:rid>/<aksi>", methods=["POST"])
@need("dishub", "polsek")
def aksi_laporan(u, rid, aksi):
    a = ACT.get(aksi)
    r = db().execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    if not a or not r or a[0] != u["role"]:
        return jsonify(error="Aksi tidak valid untuk peran Anda."), 403
    if r["status"] not in a[2] or (u["role"] == "polsek" and not r["instruksi"]):
        return jsonify(error="Status laporan (%s) tidak sesuai untuk aksi ini." % r["status"]), 409
    cat = request.form.get("catatan", "").strip()
    if a[3] and not cat:
        return jsonify(error="Catatan wajib diisi."), 400
    try:
        foto = simpan_foto(request.files.get("foto"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    ts = now()
    db().execute("UPDATE reports SET status=?, instruksi=?, diubah=? WHERE id=?", (a[1], cat if aksi == "instruksi" else r["instruksi"], ts, rid))
    catat(rid, "%s (%s)" % (u["nama"], u["role"]), a[4], cat, foto, ts)
    db().commit()
    return jsonify(ok=True)


@app.route("/api/peta")
@need()
def peta(u):
    return jsonify([dict(r) for r in db().execute(
        "SELECT id,lokasi,kelurahan,jenis,tingkat,status,lat,lng,simulasi,diubah FROM reports ORDER BY diubah DESC")])


@app.route("/api/stats")
@need()
def stats(u):
    d = db()
    n = lambda w="1": d.execute("SELECT COUNT(*) FROM reports WHERE " + w).fetchone()[0]
    grp = lambda col: {r[0]: r[1] for r in d.execute("SELECT %s, COUNT(*) FROM reports GROUP BY 1" % col)}
    ins = "instruksi!=''"
    return jsonify(
        total=n(), titik=d.execute("SELECT COUNT(DISTINCT lokasi) FROM reports").fetchone()[0], belum=n("status='Dilaporkan'"),
        proses=n("status IN ('Dipantau','Dalam Penanganan')"), selesai=n("status='Selesai'"),
        polsek=dict(total=n(ins), belum=n(ins + " AND status='Dipantau'"), proses=n(ins + " AND status='Dalam Penanganan'"), selesai=n(ins + " AND status='Selesai'")),
        kondisi=grp("tingkat"), kelurahan=grp("kelurahan"), jenis=grp("jenis"), harian=grp("substr(dibuat,1,10)"),
        lokasi=[[r[0], r[1]] for r in d.execute("SELECT lokasi, COUNT(*) c FROM reports GROUP BY lokasi ORDER BY c DESC LIMIT 5")])


@app.route("/api/survei")
@need()
def survei(u):
    return jsonify(sv.analisis(request.args.get("kel", "")))


init_db()
if __name__ == "__main__":
    app.run(debug=True)
