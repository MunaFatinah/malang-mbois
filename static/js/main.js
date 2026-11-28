// Malang Mbois: logika frontend (navigasi, peta, grafik, laporan, notifikasi). CFG.role berasal dari server.
const $ = s => document.querySelector(s);
const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const COL = { Lancar: "#2e9b5a", Ramai: "#8bc34a", Padat: "#e5a50a", Macet: "#d6453d" };
const NAV = {
  warga: [["ringkasan", "Beranda"], ["lapor", "Lapor Kejadian"], ["laporan", "Riwayat Laporan"]],
  dishub: [["ringkasan", "Monitoring"], ["laporan", "Manajemen Laporan"], ["analisis", "Analisis"]],
  polsek: [["ringkasan", "Ringkasan Tugas"], ["laporan", "Laporan Diteruskan"]],
};
const AKSI = {  // aksi yang tersedia per role dan status (diperiksa ulang oleh server)
  dishub: { Dilaporkan: ["verifikasi", "pantau"], Diverifikasi: ["pantau", "instruksi"], Dipantau: ["instruksi"] },
  polsek: { Diverifikasi: ["tangani"], Dipantau: ["tangani"], "Dalam Penanganan": ["selesai"] },
};
const LBL = { verifikasi: "Verifikasi", pantau: "Tandai Dipantau", instruksi: "Kirim Instruksi ke Polsek", tangani: "Mulai Penanganan", selesai: "Tandai Selesai" };
const st = { reports: [], sig: null, charts: {}, map: null, layer: null, fitted: false, pick: null, pickMark: null };

async function api(url, opt) {
  const r = await fetch(url, opt), d = await r.json().catch(() => ({}));
  if (r.status === 401) location = "/login";
  if (!r.ok) throw new Error(d.error || "Terjadi kesalahan");
  return d;
}
function toast(msg, bad) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (bad ? " bad" : "");
  clearTimeout(t.h); t.h = setTimeout(() => t.className = "", 3500);
}
const badge = s => `<span class="b b-${String(s).replace(/\s/g, "")}">${esc(s)}</span>`;
const tiles = m => L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(m);

function chart(id, type, labels, data, colors) {
  st.charts[id]?.destroy();
  st.charts[id] = new Chart($("#" + id), {
    type: type === "barh" ? "bar" : type,
    data: { labels, datasets: [{ data, backgroundColor: colors || "#1d5fa8", borderColor: "#1d5fa8", tension: .3 }] },
    options: { indexAxis: type === "barh" ? "y" : "x", plugins: { legend: { display: type === "doughnut" } } },
  });
}

// ---------- navigasi ----------
function show(v) {
  document.querySelectorAll("main > section").forEach(s => s.hidden = s.id !== "v-" + v);
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.v === v));
  $("#ttl").textContent = NAV[CFG.role].find(n => n[0] === v)[1];
  $("#side").classList.remove("open");
  if (v === "ringkasan") setTimeout(() => st.map.invalidateSize(), 50);
  if (v === "lapor") initPick();
  if (v === "analisis") loadAnalisis();
}

// ---------- ringkasan, peta ----------
async function loadStats() {
  const s = await api("/api/stats"), r = CFG.role, p = s.polsek;
  const cards = r === "polsek" ? [[p.total, "Laporan diteruskan"], [p.belum, "Belum ditangani"], [p.proses, "Sedang ditangani"], [p.selesai, "Selesai"]]
    : r === "dishub" ? [[s.total, "Laporan masuk"], [s.titik, "Titik kemacetan"], [s.belum, "Belum diverifikasi"], [s.proses, "Sedang ditangani"], [s.selesai, "Selesai"]]
    : [[s.titik, "Titik dipantau"], [s.total, "Laporan kemacetan"], [s.selesai, "Laporan selesai ditangani"]];
  $("#cards").innerHTML = cards.map(c => `<div class="card stat"><b>${c[0]}</b><span>${c[1]}</span></div>`).join("");
  const k = Object.keys(s.kondisi);
  chart("c-kondisi", "doughnut", k, Object.values(s.kondisi), k.map(x => COL[x]));
}
async function loadMap() {
  const pts = await api("/api/peta");
  st.layer.clearLayers();
  pts.forEach(p => L.circleMarker([p.lat, p.lng], { radius: 11, color: COL[p.tingkat], fillOpacity: .6 }).bindPopup(
    `<b>${esc(p.lokasi)}</b><br>${esc(p.kelurahan)} · ${esc(p.jenis)}<br>Kondisi: ${esc(p.tingkat)}<br>Status: ${esc(p.status)}<br><small>Koordinat ${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}<br>Diperbarui ${esc(p.diubah)}${p.simulasi ? " (data simulasi)" : ""}</small>`).addTo(st.layer));
  $("#mapnote").textContent = pts.length ? `Laporan terakhir: ${pts[0].diubah}. Titik berlabel simulasi adalah data contoh, bukan data lalu lintas langsung.` : "Belum ada laporan.";
  if (pts.length && !st.fitted) { st.map.fitBounds(pts.map(p => [p.lat, p.lng]), { padding: [40, 40], maxZoom: 15 }); st.fitted = true; }
}

// ---------- laporan ----------
async function loadReports(quiet) {
  const prev = new Set(st.reports.map(r => r.id));
  st.reports = await api("/api/reports");
  const sig = JSON.stringify(st.reports.map(r => [r.id, r.status, r.diubah]));
  const changed = !quiet && st.sig !== null && sig !== st.sig;
  st.sig = sig; renderTable();
  if (changed) {
    const baru = st.reports.filter(r => !prev.has(r.id));
    toast(baru.length && CFG.role !== "warga" ? (CFG.role === "polsek" ? "Laporan baru diteruskan Dishub: " : "Laporan baru: ") + baru[0].lokasi : "Ada pembaruan laporan");
    loadStats(); loadMap();
  }
}
function renderTable() {
  const q = $("#q").value.toLowerCase(), fs = $("#fs").value, fk = $("#fk").value;
  const rows = st.reports.filter(r => (!fs || r.status === fs) && (!fk || r.kelurahan === fk) && (r.lokasi + " " + r.deskripsi).toLowerCase().includes(q));
  $("#tbl").innerHTML = "<tr><th>#<th>Waktu<th>Lokasi<th>Jenis<th>Kondisi<th>Status<th></tr>" + (rows.map(r =>
    `<tr><td>${r.id}<td>${esc(r.dibuat.slice(0, 16))}<td>${esc(r.lokasi)}<br><small>${esc(r.kelurahan)}</small><td>${esc(r.jenis)}<td>${badge(r.tingkat)}<td>${badge(r.status)}<td><button class="sm" data-id="${r.id}">Detail</button>`).join("")
    || "<tr><td colspan=7>Belum ada laporan.</tr>");
}
function openDetail(id) {
  const r = st.reports.find(x => x.id === id), acts = (AKSI[CFG.role] || {})[r.status] || [];
  $("#dlg").innerHTML = `<h3>Laporan #${r.id} ${badge(r.status)}</h3>
    <p><b>${esc(r.lokasi)}</b>, ${esc(r.kelurahan)}<br>${esc(r.jenis)} · kondisi ${badge(r.tingkat)}${r.simulasi ? " · <i>data simulasi</i>" : ""}</p>
    <p><small>Koordinat: ${r.lat.toFixed(5)}, ${r.lng.toFixed(5)} · <a href="https://www.google.com/maps?q=${r.lat},${r.lng}" target="_blank">Buka di Google Maps</a></small></p><p>${esc(r.deskripsi)}</p>${r.foto ? `<img src="${r.foto}" alt="Foto bukti">` : ""}
    ${r.instruksi ? `<p class="note"><b>Instruksi Dishub:</b> ${esc(r.instruksi)}</p>` : ""}
    <h4>Riwayat</h4><ul class="tl">${r.riwayat.map(h => `<li><b>${esc(h.aksi)}</b> · ${esc(h.aktor)} · <small>${esc(h.waktu)}</small>${h.catatan ? "<br>" + esc(h.catatan) : ""}${h.foto ? `<br><a href="${h.foto}" target="_blank">Lihat foto</a>` : ""}</li>`).join("")}</ul>
    ${acts.length ? `<form id="act"><textarea name="catatan" rows="2" placeholder="Catatan, instruksi, atau tindakan"></textarea><input type="file" name="foto" accept="image/*"><div class="row">${acts.map(a => `<button data-a="${a}">${LBL[a]}</button>`).join("")}</div></form>` : ""}
    <button class="sec" id="tutup">Tutup</button>`;
  $("#dlg").showModal();
  $("#tutup").onclick = () => $("#dlg").close();
  const f = $("#act");
  if (f) f.onclick = async e => {
    const a = e.target.dataset.a; if (!a) return;
    e.preventDefault();
    try {
      await api(`/api/reports/${id}/${a}`, { method: "POST", body: new FormData(f) });
      toast("Berhasil: " + LBL[a]); $("#dlg").close();
      await loadReports(true); loadStats(); loadMap();
    } catch (er) { toast(er.message, true); }
  };
}

// ---------- form lapor + peta penanda ----------
function setPin(lat, lng) {  // pasang/geser pin, isi latitude dan longitude, lalu cari nama jalan
  if (st.pickMark) st.pickMark.setLatLng([lat, lng]);
  else {
    st.pickMark = L.marker([lat, lng], { draggable: true }).addTo(st.pick);
    st.pickMark.on("dragend", () => { const p = st.pickMark.getLatLng(); setPin(p.lat, p.lng); });
  }
  const f = $("#frm").elements;
  f.lat.value = lat.toFixed(6); f.lng.value = lng.toFixed(6);
  st.pick.panTo([lat, lng]);
  namaJalan(lat, lng);
}
async function namaJalan(lat, lng) {  // reverse geocoding OpenStreetMap (Nominatim); jika gagal, isi manual
  try {
    const d = await (await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&accept-language=id`)).json();
    const a = d.address || {}, f = $("#frm").elements, nama = a.road || a.neighbourhood || d.name || "";
    if (nama) f.lokasi.value = nama;
    const kel = [...f.kelurahan.options].map(o => o.value).find(k => JSON.stringify(a).toLowerCase().includes(k.toLowerCase()));
    if (kel) f.kelurahan.value = kel;
  } catch (e) { toast("Nama jalan tidak terbaca, isi manual.", true); }
}
function initPick() {
  if (!st.pick) {
    st.pick = L.map("pick").setView([-7.948, 112.608], 14); tiles(st.pick);
    st.pick.on("click", e => setPin(e.latlng.lat, e.latlng.lng));
    $("#myloc").onclick = () => {
      if (!navigator.geolocation) return toast("Browser tidak mendukung lokasi.", true);
      navigator.geolocation.getCurrentPosition(p => { st.pick.setZoom(17); setPin(p.coords.latitude, p.coords.longitude); },
        () => toast("Lokasi tidak bisa diakses. Izinkan akses lokasi atau klik peta.", true), { enableHighAccuracy: true, timeout: 10000 });
    };
  }
  setTimeout(() => st.pick.invalidateSize(), 50);
}
$("#frm")?.addEventListener("submit", async e => {
  e.preventDefault();
  if (!e.target.elements.lat.value) return toast("Tandai titik lokasi di peta dulu.", true);
  try {
    await api("/api/reports", { method: "POST", body: new FormData(e.target) });
    toast("Laporan terkirim"); e.target.reset(); st.pickMark?.remove(); st.pickMark = null;
    await loadReports(true); loadStats(); loadMap(); show("laporan");
  } catch (er) { toast(er.message, true); }
});

// ---------- analisis (Dishub): data laporan dari database + survei.csv ----------
async function loadAnalisis() {
  const s = await api("/api/stats");
  chart("c-harian", "line", Object.keys(s.harian), Object.values(s.harian));
  chart("c-kel", "bar", Object.keys(s.kelurahan), Object.values(s.kelurahan));
  chart("c-jenis", "doughnut", Object.keys(s.jenis), Object.values(s.jenis), ["#1d5fa8", "#4c9be8", "#e5a50a", "#d6453d", "#2e9b5a", "#8e7cc3", "#90a4ae"]);
  chart("c-lokasi", "barh", s.lokasi.map(x => x[0]), s.lokasi.map(x => x[1]));
  const v = await api("/api/survei?kel=" + encodeURIComponent($("#sk").value));
  $("#nsv").textContent = v.n;
  chart("c-jam", "bar", v.jam.map(x => x[0]), v.jam.map(x => x[1]));
  chart("c-sebab", "barh", v.sebab.map(x => x[0]), v.sebab.map(x => x[1]));
}
$("#sk")?.addEventListener("change", loadAnalisis);

// ---------- inisialisasi ----------
$("#nav").innerHTML = NAV[CFG.role].map(n => `<a href="#" data-v="${n[0]}">${n[1]}</a>`).join("");
$("#nav").onclick = e => { const v = e.target.dataset.v; if (v) { e.preventDefault(); show(v); } };
$("#burger").onclick = () => $("#side").classList.toggle("open");
$("#tbl").onclick = e => e.target.dataset.id && openDetail(+e.target.dataset.id);
["#q", "#fs", "#fk"].forEach(s => $(s).addEventListener("input", renderTable));
(async () => {
  st.map = L.map("map").setView([-7.948, 112.608], 13); tiles(st.map); st.layer = L.layerGroup().addTo(st.map);
  show("ringkasan");
  try { await Promise.all([loadStats(), loadMap(), loadReports(true)]); } catch (e) { toast(e.message, true); }
  setInterval(() => loadReports().catch(() => {}), 8000);  // polling: notifikasi jika ada laporan/status baru
})();