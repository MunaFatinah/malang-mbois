"""Analisis data survei (data/survei.csv): jam macet, penyebab, kesediaan pakai aplikasi, titik macet."""
import csv, os, re
from collections import Counter

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Titik macet: isian bebas responden dikelompokkan lewat kata kunci (huruf kecil).
# lat,lng = posisi di peta. PERKIRAAN, belum diverifikasi: cek di peta (klik peta untuk lihat koordinat) lalu koreksi.
TITIK = [
    dict(n="Jl. Soekarno-Hatta (Suhat)", t="Suhat", k="Jatimulyo", lat=-7.9455, lng=112.6165, kw=["suhat", "soekarno"]),
    dict(n="Sigura-gura / perempatan Cak Cul", t="Sigura-gura", k="Sumbersari", lat=-7.9585, lng=112.6120, kw=["sigura", "cul"]),
    dict(n="Perempatan Merjosari / Mertojoyo", t="Merjosari", k="Merjosari", lat=-7.9440, lng=112.6000, kw=["merjo", "joyo", "tong"]),
    dict(n="Simpang Lima Tunggulwulung", t="Tunggulwulung", k="Tunggulwulung", lat=-7.9365, lng=112.6045, kw=["perlima", "kampung keramik", "area jembatan"]),
    dict(n="Jl. depan UIN / Watu Gong", t="UIN / Watu Gong", k="Ketawanggede", lat=-7.9520, lng=112.6090, kw=["uin", "watu", "dinoyo", "mt haryono"]),
]
WAKTU = [("Pagi", "Pagi 06-09"), ("Siang", "Siang 10-14"), ("Sore", "Sore 15-18"), ("Malam", "Malam 19-22"), ("Akhir pekan", "Akhir pekan")]
SEBAB = [("Volume kendaraan terlalu banyak", "Volume kendaraan"), ("Parkir di bahu jalan", "Parkir di bahu jalan"),
         ("Pelanggaran lalu lintas", "Pelanggaran lalu lintas"), ("Lampu lalu lintas yang kurang efektif", "Lampu lalin kurang efektif"),
         ("Angkutan umum kurang memadai", "Angkutan umum kurang"), ("Jalan rusak atau ada proyek", "Jalan rusak / proyek")]
TAHU = {"Tahu dan pernah memakai": "Tahu dan pernah pakai", "Tahu tapi belum pernah memakai": "Tahu, belum pernah pakai", "Tidak tahu": "Tidak tahu"}


def kol(cols, kata):
    return next((c for c in cols if kata.lower() in c.lower()), None)


def pct(c, n):
    return round(c * 100 / n)


def multi(rows, col, opts, lainnya=False):
    n, hit = len(rows) or 1, Counter()
    for r in rows:
        rest = str(r.get(col) or "")
        for kunci, label in opts:
            if kunci in rest:
                hit[label] += 1
                rest = rest.replace(kunci, "")
        if lainnya and re.search(r"[A-Za-z]{3,}", rest):
            hit["Lainnya (isian bebas)"] += 1
    return [[k, pct(v, n)] for k, v in hit.most_common()]


def skala(rows, col):
    n, c = len(rows) or 1, Counter()
    for r in rows:
        try:
            v = int(float(r[col]))
        except (TypeError, ValueError, KeyError):
            continue
        c["Setuju (4-5)" if v >= 4 else "Netral (3)" if v == 3 else "Tidak setuju (1-2)"] += 1
    return [[k, pct(c[k], n)] for k in ("Setuju (4-5)", "Netral (3)", "Tidak setuju (1-2)")]


def analisis(kel=""):
    with open(os.path.join(DATA, "survei.csv"), encoding="utf-8-sig", newline="") as f:
        semua = list(csv.DictReader(f))
    cols = list(semua[0].keys()) if semua else []
    ck, cf, cw, ct = kol(cols, "Kelurahan"), kol(cols, "terjebak macet"), kol(cols, "Kapan kemacetan"), kol(cols, "titik macet")
    cs, cp, ca, cu = kol(cols, "penyebab utama"), kol(cols, "Pemkot Malang"), kol(cols, "aplikasi info lalu lintas"), kol(cols, "angkutan umum jika")
    rows = [r for r in semua if not kel or (r[ck] or "").strip() == kel]
    n = len(rows) or 1
    titik = []
    for t in TITIK:
        c = sum(any(k in (r[ct] or "").lower() for k in t["kw"]) for r in rows)
        if c:
            titik.append(dict(n=t["n"], t=t["t"], k=t["k"], lat=t["lat"], lng=t["lng"], c=c, l=3 if c >= 6 else 2 if c >= 3 else 1))
    titik.sort(key=lambda t: -t["c"])
    stat = {}
    for r in semua:
        stat.setdefault((r[ck] or "").strip(), []).append(float(r[cf] or 0))
    tahu = Counter(TAHU.get((r[cp] or "").strip(), "Tidak tahu") for r in rows)
    return dict(
        n=len(rows),
        jam=multi(rows, cw, [(k, v) for k, v in WAKTU]),
        sebab=multi(rows, cs, SEBAB, lainnya=True),
        app=skala(rows, ca), umum=skala(rows, cu),
        tahu=[[k, pct(v, n)] for k, v in tahu.most_common()],
        titik=titik,
        kel={k: {"n": len(v), "f": round(sum(v) / len(v), 1)} for k, v in stat.items()},
    )

