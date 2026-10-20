import os
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────
# KONFIGURACE
# ─────────────────────────────────────────────
st.set_page_config(page_title="Energie doma", page_icon="⚡", layout="centered")

AUTOR = "Pavel Dvořáček"
EMAIL = "pavel.dvoracek@obchod.t-mobile.cz"

# Moderní paleta (tmavé téma, smaragdová jako nástupce „lesní“ zelené z Apaluchy)
BARVA_PRIMARNI = "#10b981"
BARVA_OK = "#22c55e"
BARVA_VAROVANI = "#f59e0b"
BARVA_ZLE = "#ef4444"
BARVA_MOC = "#38bdf8"
BARVA_PLAN = "#64748b"
BARVA_TEXT_TLUMENY = "#94a3b8"

ENERGIE = {
    "plyn": {"nazev": "Plyn", "ikona": "🔥", "jednotka": "m³", "desetiny": 3, "barva": "#f97316"},
    "elektrina": {"nazev": "Elektřina", "ikona": "⚡", "jednotka": "kWh", "desetiny": 1, "barva": "#facc15"},
    "voda": {"nazev": "Voda", "ikona": "💧", "jednotka": "m³", "desetiny": 3, "barva": "#38bdf8"},
}
PORADI = ["plyn", "elektrina", "voda"]

# Typické rozložení roční spotřeby do měsíců (%) – plyn podle topné sezóny
PROFIL = {
    "elektrina": [9.5, 8.5, 8.5, 8.0, 7.8, 7.3, 7.3, 7.3, 7.6, 8.4, 9.2, 10.6],
    "plyn": [16.5, 14.0, 12.0, 8.0, 4.5, 2.5, 2.0, 2.0, 3.5, 8.0, 12.0, 15.0],
    "voda": [8.33, 8.33, 8.33, 8.33, 8.34, 8.33, 8.33, 8.34, 8.33, 8.33, 8.33, 8.34],
}

SLOUPCE_ODECTY = ["id", "datum", "energie", "stav", "typ", "poznamka"]
SLOUPCE_TARIFY = [
    "energie", "dodavatel", "cena_za_kwh", "kwh_na_jednotku", "mesicni_platy",
    "zaloha", "obdobi_od", "stav_obdobi_od", "obdobi_do",
    "zaplaceno", "zaplaceno_k_datu", "den_splatnosti", "rezerva_pct", "cena_plati",
]

# Výchozí data z faktur (použijí se jen při prvním spuštění, když je tabulka prázdná)
VYCHOZI_ODECTY = [
    ("2025-01-08", "elektrina", 47722, "odečet", "Faktura E.ON"),
    ("2025-08-31", "elektrina", 49756, "odečet", "Faktura E.ON"),
    ("2025-12-31", "elektrina", 50899, "odhad", "Faktura E.ON"),
    ("2026-01-06", "elektrina", 50963, "odečet", "Faktura E.ON"),
    ("2026-10-20", "elektrina", 53356.2, "vlastní", "Fotka elektroměru"),
    ("2025-01-05", "plyn", 5051, "odečet", "Faktura E.ON"),
    ("2025-10-10", "plyn", 5483, "odečet", "Faktura E.ON"),
    ("2026-01-05", "plyn", 5676, "odhad", "Faktura E.ON"),
    ("2026-01-16", "plyn", 5801, "odečet", "Faktura E.ON"),
    ("2026-10-08", "plyn", 6391, "odečet", "Faktura E.ON"),
    ("2026-10-20", "plyn", 6429.916, "vlastní", "Fotka plynoměru"),
    ("2025-05-23", "voda", 2153, "odečet", "Faktura VS Chrudim"),
    ("2025-12-31", "voda", 2234, "odhad", "Faktura VS Chrudim"),
    ("2026-05-15", "voda", 2283, "odečet", "Faktura VS Chrudim"),
    ("2026-10-20", "voda", 2336.233, "vlastní", "Fotka vodoměru"),
]
VYCHOZI_TARIFY = [
    {"energie": "elektrina", "dodavatel": "E.ON", "cena_za_kwh": 6.28731, "kwh_na_jednotku": 1,
     "mesicni_platy": 407.61, "zaloha": 2110, "obdobi_od": "2026-01-06", "stav_obdobi_od": 50963,
     "obdobi_do": "2027-01-06", "zaplaceno": 20390, "zaplaceno_k_datu": "2026-10-20",
     "den_splatnosti": 15, "rezerva_pct": 0, "cena_plati": "Nefixováno (smlouva do 3. 12. 2026)"},
    {"energie": "plyn", "dodavatel": "E.ON", "cena_za_kwh": 1.48004, "kwh_na_jednotku": 10.92,
     "mesicni_platy": 384.36, "zaloha": 1310, "obdobi_od": "2026-10-08", "stav_obdobi_od": 6391,
     "obdobi_do": "2027-10-08", "zaplaceno": 1000, "zaplaceno_k_datu": "2026-10-20",
     "den_splatnosti": 15, "rezerva_pct": 0, "cena_plati": "Fixováno do 31. 12. 2027"},
    {"energie": "voda", "dodavatel": "VS Chrudim", "cena_za_kwh": 143.04, "kwh_na_jednotku": 1,
     "mesicni_platy": 81.08, "zaloha": 2000, "obdobi_od": "2026-05-15", "stav_obdobi_od": 2283,
     "obdobi_do": "2027-05-15", "zaplaceno": 10000, "zaplaceno_k_datu": "2026-10-20",
     "den_splatnosti": 15, "rezerva_pct": 5, "cena_plati": "Ceník 2026, rezerva 5 % na zdražení"},
]


# ─────────────────────────────────────────────
# ÚLOŽIŠTĚ – Google Sheets (jako Apalucha), lokálně CSV
# ─────────────────────────────────────────────
class Uloziste:
    def __init__(self):
        self.gs = None
        try:
            if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
                from streamlit_gsheets import GSheetsConnection
                self.gs = st.connection("gsheets", type=GSheetsConnection)
        except Exception:
            self.gs = None
        self.slozka = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_lokalne")

    @property
    def popis(self):
        return "Google Sheets" if self.gs else "lokální soubory (bez Google Sheets)"

    def nacti(self, list_, sloupce):
        try:
            if self.gs:
                df = self.gs.read(worksheet=list_, ttl=0)
            else:
                df = pd.read_csv(os.path.join(self.slozka, f"{list_}.csv"))
        except Exception:
            return None
        df = df.dropna(how="all")
        if df.empty or not set(sloupce).issubset(df.columns):
            return None
        return df[sloupce]

    def uloz(self, list_, df):
        if self.gs:
            try:
                self.gs.update(worksheet=list_, data=df)
            except Exception:
                self.gs.create(worksheet=list_, data=df)
        else:
            os.makedirs(self.slozka, exist_ok=True)
            df.to_csv(os.path.join(self.slozka, f"{list_}.csv"), index=False)


def nove_id():
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def nacti_data(ul):
    odecty = ul.nacti("odecty", SLOUPCE_ODECTY)
    if odecty is None:
        odecty = pd.DataFrame(
            [{"id": f"init{i:03d}", "datum": d, "energie": e, "stav": s, "typ": t, "poznamka": p}
             for i, (d, e, s, t, p) in enumerate(VYCHOZI_ODECTY)],
            columns=SLOUPCE_ODECTY,
        )
        ul.uloz("odecty", odecty)
    tarify = ul.nacti("tarify", SLOUPCE_TARIFY)
    if tarify is None:
        tarify = pd.DataFrame(VYCHOZI_TARIFY, columns=SLOUPCE_TARIFY)
        ul.uloz("tarify", tarify)
    odecty = odecty.copy()
    odecty["id"] = odecty["id"].astype(str)
    odecty["datum"] = pd.to_datetime(odecty["datum"]).dt.date
    odecty["stav"] = pd.to_numeric(odecty["stav"], errors="coerce")
    odecty["poznamka"] = odecty["poznamka"].fillna("").astype(str)
    odecty["typ"] = odecty["typ"].fillna("vlastní").astype(str)
    return odecty, tarify


# ─────────────────────────────────────────────
# VÝPOČTY
# ─────────────────────────────────────────────
def podil(energie, od, do):
    """Jaký podíl roční spotřeby připadá na dny od (včetně) do (bez)."""
    s, d = 0.0, od
    while d < do:
        dni_v_mesici = ((d.replace(day=28) + timedelta(days=4)).replace(day=1) - d.replace(day=1)).days
        s += PROFIL[energie][d.month - 1] / 100 / dni_v_mesici
        d += timedelta(days=1)
    return s


def rocni_odhad(rs, energie):
    """Roční spotřeba z úseku odečtů dlouhého zhruba rok (min. 300 dní)."""
    posl = rs.iloc[-1]
    kandidati = [r for _, r in rs.iterrows() if (posl["datum"] - r["datum"]).days >= 300]
    ref = min(kandidati, key=lambda r: abs((posl["datum"] - r["datum"]).days - 365)) if kandidati else rs.iloc[0]
    p = podil(energie, ref["datum"], posl["datum"])
    return (posl["stav"] - ref["stav"]) / p if p > 0 else 0.0


def platby(t, dnes):
    """Zaplaceno a zbývající zálohy v období (záloha splatná každý měsíc v den splatnosti)."""
    zaplaceno = float(t["zaplaceno"])
    k_datu = pd.to_datetime(t["zaplaceno_k_datu"]).date()
    do = pd.to_datetime(t["obdobi_do"]).date()
    den = int(t["den_splatnosti"])
    zaloha = float(t["zaloha"])
    zbyva = 0
    d = date(k_datu.year, k_datu.month, 1)
    while d <= do:
        splatnost = date(d.year, d.month, min(den, 28))
        if k_datu < splatnost <= do:
            if splatnost <= dnes:
                zaplaceno += zaloha
            else:
                zbyva += 1
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return zaplaceno, zbyva


def spocitej(energie, odecty, t, dnes):
    rs = odecty[(odecty["energie"] == energie) & (odecty["typ"] != "odhad")].sort_values("datum").reset_index(drop=True)
    if rs.empty:
        return None
    posl = rs.iloc[-1]
    od = pd.to_datetime(t["obdobi_od"]).date()
    do = pd.to_datetime(t["obdobi_do"]).date()
    A = rocni_odhad(rs, energie)
    pouzito = posl["stav"] - float(t["stav_obdobi_od"])
    plan = A * podil(energie, od, posl["datum"])
    projekce = pouzito + A * podil(energie, posl["datum"], do)
    kwh, cena, mes = float(t["kwh_na_jednotku"]), float(t["cena_za_kwh"]), float(t["mesicni_platy"])
    rez = 1 + float(t["rezerva_pct"]) / 100
    mesicu = (do - od).days / (365 / 12)
    naklad = (projekce * kwh * cena + mesicu * mes) * rez
    zaplaceno, zbyva = platby(t, dnes)
    zalohy = zaplaceno + zbyva * float(t["zaloha"])
    doporucena = (naklad - zaplaceno) / zbyva if zbyva > 0 else None
    if doporucena is not None:
        doporucena = max(0, -(-doporucena // 50) * 50)
    # „Vyúčtování k poslednímu odečtu“ – co je spotřebováno a co zaplaceno k datu posledního stavu
    mesicu_dosud = max(0, (posl["datum"] - od).days) / (365 / 12)
    naklad_dosud = pouzito * kwh * cena + mesicu_dosud * mes
    zaplaceno_dosud, _ = platby(t, posl["datum"])
    # tempo mezi posledními dvěma odečty
    tempo = None
    if len(rs) >= 2:
        pred = rs.iloc[-2]
        dni = (posl["datum"] - pred["datum"]).days
        if dni > 0:
            tempo = (posl["stav"] - pred["stav"]) / dni
    return {
        "rocni": A, "pouzito": pouzito, "plan": plan, "projekce": projekce,
        "naklad": naklad, "zalohy": zalohy, "bilance": zalohy - naklad,
        "zaplaceno": zaplaceno, "zbyva": zbyva, "zaloha": float(t["zaloha"]),
        "doporucena": doporucena, "mesicne": (A * kwh * cena + 12 * mes) * rez / 12,
        "posledni_datum": posl["datum"], "posledni_stav": posl["stav"],
        "obdobi_od": od, "obdobi_do": do, "tempo": tempo,
        "cena_jednotky": kwh * cena, "rs": rs, "stav_od": float(t["stav_obdobi_od"]),
        "naklad_dosud": naklad_dosud, "zaplaceno_dosud": zaplaceno_dosud,
        "bilance_dosud": zaplaceno_dosud - naklad_dosud,
    }


def kc(v):
    return f"{v:,.0f} Kč".replace(",", " ")


def kc_znamenko(v):
    if round(v) == 0:
        return "0 Kč"
    return ("+" if v > 0 else "−") + kc(abs(v))


def cislo(v, des=1):
    return f"{v:,.{des}f}".replace(",", " ").replace(".", ",")


def datum_cz(d):
    return f"{d.day}. {d.month}. {d.year}"


# ─────────────────────────────────────────────
# VZHLED
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea {{ font-family: 'Inter', sans-serif !important; }}
.block-container {{ padding-top: 1rem; padding-bottom: 2rem; max-width: 820px; }}
header[data-testid="stHeader"] {{ background: transparent; }}

.hero {{ position: relative; overflow: hidden; border-radius: 22px; padding: 22px 22px 18px;
  background: radial-gradient(120% 140% at 0% 0%, rgba(16,185,129,.35) 0%, rgba(16,185,129,0) 55%),
              radial-gradient(120% 140% at 100% 100%, rgba(249,115,22,.28) 0%, rgba(249,115,22,0) 55%),
              linear-gradient(135deg, #111827 0%, #0b1220 100%);
  border: 1px solid rgba(148,163,184,.18); margin-bottom: 16px; }}
.hero h1 {{ margin: 0; font-size: 1.85rem; font-weight: 800; letter-spacing: -.02em; color: #f8fafc; }}
.hero .sub {{ margin: 2px 0 14px; color: {BARVA_TEXT_TLUMENY}; font-size: .92rem; }}
.hero-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
.hero-kpi {{ background: rgba(15,23,42,.55); border: 1px solid rgba(148,163,184,.15); border-radius: 14px; padding: 10px 12px; }}
.hero-kpi .l {{ font-size: .72rem; color: {BARVA_TEXT_TLUMENY}; text-transform: uppercase; letter-spacing: .06em; }}
.hero-kpi .v {{ font-size: 1.35rem; font-weight: 700; color: #f8fafc; font-variant-numeric: tabular-nums; margin-top: 2px; }}
.hero-kpi .s {{ font-size: .75rem; color: {BARVA_TEXT_TLUMENY}; }}
@media (max-width: 520px) {{ .hero-grid {{ grid-template-columns: 1fr 1fr; }} .hero-kpi:last-child {{ grid-column: span 2; }} }}

.chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }}
.chip {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px;
  font-size: .82rem; font-weight: 600; border: 1px solid rgba(148,163,184,.2); background: rgba(30,41,59,.6); color: #e2e8f0; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}

.tiles {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 6px 0 12px; }}
.tile {{ background: rgba(30,41,59,.55); border: 1px solid rgba(148,163,184,.15); border-radius: 16px; padding: 12px 14px; }}
.tile .l {{ font-size: .72rem; color: {BARVA_TEXT_TLUMENY}; text-transform: uppercase; letter-spacing: .06em; }}
.tile .v {{ font-size: 1.45rem; font-weight: 700; margin-top: 2px; font-variant-numeric: tabular-nums; color: #f8fafc; }}
.tile .s {{ font-size: .78rem; color: {BARVA_TEXT_TLUMENY}; margin-top: 2px; }}
.tile.hl {{ border-color: var(--acc); box-shadow: inset 0 0 0 1px var(--acc); }}

.gauge-title {{ text-align: center; font-size: .8rem; font-weight: 600; color: {BARVA_TEXT_TLUMENY};
  text-transform: uppercase; letter-spacing: .06em; margin-bottom: -6px; }}
.gauge-label {{ text-align: center; font-weight: 700; font-size: .95rem; margin-top: -18px; }}

.sekce {{ font-size: 1.05rem; font-weight: 700; margin: 18px 0 8px; color: #f1f5f9; }}
.pozn {{ font-size: .8rem; color: {BARVA_TEXT_TLUMENY}; }}

.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 12px; padding: 8px 14px; background: rgba(30,41,59,.6);
  border: 1px solid rgba(148,163,184,.15); }}
.stTabs [aria-selected="true"] {{ background: rgba(16,185,129,.18); border-color: {BARVA_PRIMARNI}; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

div.stButton > button, div.stFormSubmitButton > button {{ border-radius: 12px; min-height: 2.9rem; font-weight: 600; }}
div[data-testid="stForm"] {{ border-radius: 16px; border: 1px solid rgba(148,163,184,.18); background: rgba(30,41,59,.35); }}
div[data-testid="stExpander"] {{ border-radius: 16px; border: 1px solid rgba(148,163,184,.18); }}

.dnes {{ background: rgba(30,41,59,.55); border: 1px solid rgba(148,163,184,.15); border-radius: 16px;
  padding: 14px 16px; margin: 6px 0 10px; }}
.dnes .l {{ font-size: .72rem; color: {BARVA_TEXT_TLUMENY}; text-transform: uppercase; letter-spacing: .06em; }}
.dnes .v {{ font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 2px; }}
.dnes .s {{ font-size: .78rem; color: {BARVA_TEXT_TLUMENY}; margin-top: 4px; }}
.bar-radek {{ display: grid; grid-template-columns: 92px 1fr auto; align-items: center; gap: 10px;
  font-size: .85rem; margin-top: 8px; color: #e2e8f0; }}
.bar-radek b {{ font-variant-numeric: tabular-nums; font-weight: 600; min-width: 72px; text-align: right; }}
.bar {{ height: 10px; border-radius: 999px; background: rgba(148,163,184,.15); overflow: hidden; }}
.bar > div {{ height: 100%; border-radius: 999px; }}

.paticka {{ margin-top: 30px; padding-top: 14px; border-top: 1px solid rgba(148,163,184,.2);
  font-size: .85rem; color: {BARVA_TEXT_TLUMENY}; line-height: 1.7; }}
.paticka b {{ color: #e2e8f0; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)

ul = Uloziste()
odecty, tarify = nacti_data(ul)
dnes = date.today()
vysledky = {}
for e in PORADI:
    t = tarify[tarify["energie"] == e]
    if not t.empty:
        vysledky[e] = spocitej(e, odecty, t.iloc[0], dnes)


def stav_zalohy(v):
    """Vrátí (text, barva, poměr v %) – jak sedí současná záloha vůči potřebné."""
    if v["doporucena"] is None or v["doporucena"] <= 0:
        return "–", BARVA_PLAN, 100
    pomer = v["zaloha"] / v["doporucena"] * 100
    if pomer < 92:
        return "Málo", BARVA_ZLE, pomer
    if pomer > 108:
        return "Moc", BARVA_MOC, pomer
    return "Optimální", BARVA_OK, pomer


def budik(hodnota, kroky, barva, text, vyska=190):
    """Půlkruhový ukazatel (barometr)."""
    fig = go.Figure(go.Indicator(
        mode="gauge", value=max(0, min(hodnota, 200)),
        gauge=dict(
            shape="angular",
            axis=dict(range=[0, 200], tickvals=[], showticklabels=False),
            bar=dict(color=barva, thickness=0.28),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            steps=[dict(range=r, color=c) for r, c in kroky],
            threshold=dict(line=dict(color="#f8fafc", width=3), thickness=0.85, value=max(0, min(hodnota, 200))),
        ),
        domain=dict(x=[0, 1], y=[0, 1]),
    ))
    fig.add_annotation(x=0.5, y=0.08, text=f"<b>{text}</b>", showarrow=False,
                       font=dict(size=17, color=barva))
    fig.update_layout(height=vyska, margin=dict(l=18, r=18, t=8, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"))
    return fig


KROKY_ZALOHA = [([0, 92], "rgba(239,68,68,.22)"), ([92, 108], "rgba(34,197,94,.25)"), ([108, 200], "rgba(56,189,248,.20)")]
KROKY_PLAN = [([0, 95], "rgba(34,197,94,.25)"), ([95, 115], "rgba(245,158,11,.22)"), ([115, 200], "rgba(239,68,68,.22)")]

# ─────────────────────────────────────────────
# HERO – celkový přehled
# ─────────────────────────────────────────────
platne = [v for v in vysledky.values() if v]
zalohy_ted = sum(v["zaloha"] for v in platne)
zalohy_nulu = sum(v["doporucena"] if v["doporucena"] is not None else v["zaloha"] for v in platne)
bilance_celkem = sum(v["bilance"] for v in platne)
mesicne_celkem = sum(v["mesicne"] for v in platne)
barva_bil = BARVA_OK if bilance_celkem >= 0 else BARVA_ZLE

st.markdown(f"""
<div class="hero">
  <h1>⚡ Energie doma</h1>
  <div class="sub">Spotřeba, zálohy a odhad vyúčtování · aktualizováno {datum_cz(max(v['posledni_datum'] for v in platne)) if platne else '–'}</div>
  <div class="hero-grid">
    <div class="hero-kpi"><div class="l">Zálohy teď</div><div class="v">{kc(zalohy_ted)}</div><div class="s">měsíčně celkem</div></div>
    <div class="hero-kpi"><div class="l">Zálohy na nulu</div><div class="v">{kc(zalohy_nulu)}</div><div class="s">rozdíl {kc_znamenko(zalohy_nulu - zalohy_ted)}</div></div>
    <div class="hero-kpi"><div class="l">Odhad vyúčtování</div><div class="v" style="color:{barva_bil}">{kc_znamenko(bilance_celkem)}</div><div class="s">≈ {kc(mesicne_celkem)} měsíčně skutečně</div></div>
  </div>
</div>
""", unsafe_allow_html=True)

chips = []
for e in PORADI:
    v = vysledky.get(e)
    if not v:
        continue
    txt, barva, _ = stav_zalohy(v)
    if txt == "Optimální":
        popis = "záloha sedí"
    elif txt == "Málo":
        popis = f"zvednout na {kc(v['doporucena'])}"
    else:
        popis = f"snížit na {kc(v['doporucena'])}"
    chips.append(f'<span class="chip"><span class="dot" style="background:{barva}"></span>'
                 f'{ENERGIE[e]["ikona"]} {ENERGIE[e]["nazev"]}: {popis}</span>')
st.markdown(f'<div class="chips">{"".join(chips)}</div>', unsafe_allow_html=True)

if "ulozeno" in st.session_state:
    st.success(st.session_state.pop("ulozeno"))

# ─────────────────────────────────────────────
# ZÁLOŽKY PO ENERGIÍCH
# ─────────────────────────────────────────────
zalozky = st.tabs([f"{ENERGIE[e]['ikona']} {ENERGIE[e]['nazev']}" for e in PORADI])
for e, tab in zip(PORADI, zalozky):
    with tab:
        v = vysledky.get(e)
        info = ENERGIE[e]
        acc = info["barva"]
        if not v:
            st.info("Zatím žádná data.")
            continue

        # Barometry
        g1, g2 = st.columns(2)
        txt, barva, pomer = stav_zalohy(v)
        with g1:
            st.markdown('<div class="gauge-title">Nastavení zálohy</div>', unsafe_allow_html=True)
            st.plotly_chart(budik(pomer, KROKY_ZALOHA, barva, txt), width="stretch",
                            config={"displayModeBar": False, "staticPlot": True}, key=f"g1_{e}")
        pomer_plan = v["pouzito"] / v["plan"] * 100 if v["plan"] > 0 else 100
        if pomer_plan < 95:
            t2, b2 = "Pod plánem", BARVA_OK
        elif pomer_plan <= 115:
            t2, b2 = f"Na plánu {pomer_plan - 100:+.0f} %", BARVA_VAROVANI if pomer_plan > 105 else BARVA_OK
        else:
            t2, b2 = f"Nad plánem {pomer_plan - 100:+.0f} %", BARVA_ZLE
        with g2:
            st.markdown('<div class="gauge-title">Spotřeba vs plán</div>', unsafe_allow_html=True)
            st.plotly_chart(budik(pomer_plan, KROKY_PLAN, b2, t2), width="stretch",
                            config={"displayModeBar": False, "staticPlot": True}, key=f"g2_{e}")

        # Vyúčtování k poslednímu odečtu
        nd, zd, bd = v["naklad_dosud"], v["zaplaceno_dosud"], v["bilance_dosud"]
        maxi = max(nd, zd, 1)
        barva_bd = BARVA_OK if bd >= 0 else BARVA_ZLE
        pomer_d = zd / nd * 100 if nd > 0 else 0
        st.markdown(f"""
<div class="dnes">
  <div class="dnes-hlava">
    <div><div class="l">Kdyby vyúčtování bylo k {datum_cz(v['posledni_datum'])}</div>
      <div class="v" style="color:{barva_bd}">{kc_znamenko(bd)}</div>
      <div class="s">{'přeplatek' if bd >= 0 else 'nedoplatek'} · zálohy pokrývají {pomer_d:.0f} % spotřeby od {datum_cz(v['obdobi_od'])}</div></div>
  </div>
  <div class="bar-radek"><span>Spotřebováno</span><div class="bar"><div style="width:{nd / maxi * 100:.1f}%;background:{acc}"></div></div><b>{kc(nd)}</b></div>
  <div class="bar-radek"><span>Zaplaceno</span><div class="bar"><div style="width:{zd / maxi * 100:.1f}%;background:{BARVA_PRIMARNI}"></div></div><b>{kc(zd)}</b></div>
  <div class="s">{cislo(v['pouzito'], 1)} {info['jednotka']} × {cislo(v['cena_jednotky'], 2)} Kč + stálé platby. Pozor: nezahrnuje spotřebu, která teprve přijde (u plynu hlavně zima) – na konci období rozhoduje „Odhad vyúčtování“.</div>
</div>
""", unsafe_allow_html=True)

        # Dlaždice
        barva_bil =BARVA_OK if v["bilance"] >= 0 else BARVA_ZLE
        popis_bil = "přeplatek" if v["bilance"] >= 0 else "nedoplatek"
        dop = kc(v["doporucena"]) if v["doporucena"] is not None else "–"
        tempo = f"{cislo(v['tempo'], 2)} {info['jednotka']}/den" if v["tempo"] is not None else "–"
        st.markdown(f"""
<div class="tiles" style="--acc:{acc}">
  <div class="tile"><div class="l">Odhad vyúčtování</div>
    <div class="v" style="color:{barva_bil}">{kc_znamenko(v['bilance'])}</div>
    <div class="s">{popis_bil} k {datum_cz(v['obdobi_do'])}</div></div>
  <div class="tile hl"><div class="l">Záloha na nulu</div>
    <div class="v">{dop}</div>
    <div class="s">teď platíš {kc(v['zaloha'])}</div></div>
  <div class="tile"><div class="l">Roční spotřeba</div>
    <div class="v">{cislo(v['rocni'], 0)} {info['jednotka']}</div>
    <div class="s">≈ {kc(v['mesicne'])} měsíčně</div></div>
  <div class="tile"><div class="l">Tempo</div>
    <div class="v">{tempo}</div>
    <div class="s">poslední stav {cislo(v['posledni_stav'], info['desetiny'])} · {datum_cz(v['posledni_datum'])}</div></div>
</div>
""", unsafe_allow_html=True)

        # Zadání stavu
        with st.form(f"novy_{e}", clear_on_submit=True):
            st.markdown(f"**📝 Nový stav – {info['nazev'].lower()}**")
            c1, c2 = st.columns([3, 2])
            stav = c1.number_input(f"Stav ({info['jednotka']})", min_value=0.0, value=None,
                                   step=0.1 if e == "elektrina" else 0.001,
                                   format="%.1f" if e == "elektrina" else "%.3f",
                                   placeholder="Opiš číslo z měřidla", key=f"stav_{e}")
            dat = c2.date_input("Datum", value=dnes, format="DD.MM.YYYY", key=f"dat_{e}")
            pozn = st.text_input("Poznámka (nepovinné)", placeholder="např. po dovolené", key=f"pozn_{e}")
            odeslat = st.form_submit_button("Uložit stav", type="primary", width="stretch")
        if odeslat:
            if stav is None:
                st.error("Zadej stav měřidla.")
            elif dat >= v["posledni_datum"] and stav < v["posledni_stav"]:
                st.error(f"Stav je nižší než poslední ({cislo(v['posledni_stav'], info['desetiny'])}). Zkontroluj číslo.")
            else:
                novy = pd.DataFrame([{"id": nove_id(), "datum": dat.isoformat(), "energie": e,
                                      "stav": stav, "typ": "vlastní", "poznamka": pozn}])
                ven = pd.concat([odecty.assign(datum=odecty["datum"].astype(str)), novy], ignore_index=True)
                ul.uloz("odecty", ven[SLOUPCE_ODECTY])
                zprava = f"Uloženo: {info['nazev']} {cislo(stav, info['desetiny'])} {info['jednotka']}"
                if dat > v["posledni_datum"]:
                    rozdil = stav - v["posledni_stav"]
                    dni = (dat - v["posledni_datum"]).days
                    zprava += (f" · od minule +{cislo(rozdil, info['desetiny'])} {info['jednotka']} za {dni} dní"
                               f" ≈ {kc(rozdil * v['cena_jednotky'])}")
                st.session_state["ulozeno"] = zprava
                st.rerun()

        # Graf skutečnost vs plán
        st.markdown(f'<div class="sekce">Průběh zúčtovacího období</div>', unsafe_allow_html=True)
        od, do = v["obdobi_od"], v["obdobi_do"]
        dny = [od + timedelta(days=i) for i in range(0, (do - od).days + 1, 3)] + [do]
        plan_y = [v["rocni"] * podil(e, od, d) for d in dny]
        rs = v["rs"][v["rs"]["datum"] >= od]
        skut_x = [od] + list(rs["datum"])
        skut_y = [0.0] + list(rs["stav"] - v["stav_od"])
        r, g, b = int(acc[1:3], 16), int(acc[3:5], 16), int(acc[5:7], 16)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dny, y=plan_y, name="Plán", mode="lines",
                                 line=dict(color=BARVA_PLAN, width=2, dash="dot"),
                                 hovertemplate="%{x|%d.%m.%Y}<br>Plán %{y:.1f} " + info["jednotka"] + "<extra></extra>"))
        fig.add_trace(go.Scatter(x=skut_x, y=skut_y, name="Skutečnost", mode="lines+markers",
                                 line=dict(color=acc, width=3, shape="linear"), marker=dict(size=9, color=acc,
                                 line=dict(color="#0b1220", width=2)),
                                 fill="tozeroy", fillcolor=f"rgba({r},{g},{b},.12)",
                                 hovertemplate="%{x|%d.%m.%Y}<br>Skutečnost %{y:.1f} " + info["jednotka"] + "<extra></extra>"))
        fig.add_vline(x=dnes, line=dict(color="rgba(148,163,184,.5)", width=1, dash="dash"))
        fig.update_layout(height=280, margin=dict(l=6, r=6, t=6, b=6),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#cbd5e1", family="Inter"),
                          legend=dict(orientation="h", y=1.1, x=0), hovermode="closest",
                          xaxis=dict(showgrid=False, tickformat="%m/%y"),
                          yaxis=dict(gridcolor="rgba(148,163,184,.12)", zeroline=False,
                                     title=dict(text=info["jednotka"], font=dict(size=11))))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"graf_{e}")
        st.markdown(f'<div class="pozn">Od {datum_cz(od)}: {cislo(v["pouzito"], 1)} {info["jednotka"]}, '
                    f'plán {cislo(v["plan"], 1)} {info["jednotka"]}. Plán = roční odhad rozložený podle typického průběhu roku.</div>',
                    unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HISTORIE ODEČTŮ – úprava a mazání s potvrzením
# ─────────────────────────────────────────────
st.markdown('<div class="sekce">Správa</div>', unsafe_allow_html=True)
with st.expander(f"📋 Historie odečtů ({len(odecty)})"):
    filtr = st.radio("Filtr", ["vše"] + PORADI, horizontal=True, label_visibility="collapsed",
                     format_func=lambda x: "Vše" if x == "vše" else f"{ENERGIE[x]['ikona']} {ENERGIE[x]['nazev']}",
                     key="filtr_hist")
    seznam = odecty if filtr == "vše" else odecty[odecty["energie"] == filtr]
    seznam = seznam.sort_values("datum", ascending=False)
    for _, r in seznam.iterrows():
        inf = ENERGIE.get(r["energie"], {"ikona": "", "jednotka": "", "desetiny": 1})
        rid = r["id"]
        c1, c2, c3 = st.columns([6, 1, 1])
        c1.markdown(f"{inf['ikona']} **{cislo(r['stav'], inf['desetiny'])} {inf['jednotka']}** · {datum_cz(r['datum'])}"
                    f"  \n<span style='font-size:.8rem;color:{BARVA_TEXT_TLUMENY}'>{r['typ']}"
                    f"{' · ' + r['poznamka'] if r['poznamka'] else ''}</span>", unsafe_allow_html=True)
        if c2.button("✏️", key=f"upr_{rid}", help="Upravit"):
            st.session_state["upravuji"] = rid
            st.session_state.pop("mazu", None)
        if c3.button("🗑️", key=f"maz_{rid}", help="Smazat"):
            st.session_state["mazu"] = rid
            st.session_state.pop("upravuji", None)

        if st.session_state.get("mazu") == rid:
            st.warning("Opravdu smazat tento odečet?")
            a, b = st.columns(2)
            if a.button("Ano, smazat", key=f"ano_{rid}", type="primary", width="stretch"):
                ven = odecty[odecty["id"] != rid].assign(datum=lambda d: d["datum"].astype(str))
                ul.uloz("odecty", ven[SLOUPCE_ODECTY])
                st.session_state.pop("mazu", None)
                st.session_state["ulozeno"] = "Odečet smazán."
                st.rerun()
            if b.button("Ne", key=f"ne_{rid}", width="stretch"):
                st.session_state.pop("mazu", None)
                st.rerun()

        if st.session_state.get("upravuji") == rid:
            typy = ["vlastní", "odečet", "odhad"]
            with st.form(f"form_{rid}"):
                n_stav = st.number_input("Stav", value=float(r["stav"]), min_value=0.0, step=0.001, format="%.3f")
                n_dat = st.date_input("Datum", value=r["datum"], format="DD.MM.YYYY")
                n_typ = st.selectbox("Typ", typy, index=typy.index(r["typ"]) if r["typ"] in typy else 0)
                n_pozn = st.text_input("Poznámka", value=r["poznamka"])
                a, b = st.columns(2)
                ok = a.form_submit_button("Uložit změny", type="primary", width="stretch")
                zrus = b.form_submit_button("Zrušit", width="stretch")
            if ok:
                ven = odecty.copy()
                m = ven["id"] == rid
                ven.loc[m, ["stav", "datum", "typ", "poznamka"]] = [n_stav, n_dat, n_typ, n_pozn]
                ven["datum"] = ven["datum"].astype(str)
                ul.uloz("odecty", ven[SLOUPCE_ODECTY])
                st.session_state.pop("upravuji", None)
                st.session_state["ulozeno"] = "Odečet upraven."
                st.rerun()
            if zrus:
                st.session_state.pop("upravuji", None)
                st.rerun()
    st.caption("Typ „odhad“ (odhad dodavatele) se do výpočtů nepočítá.")

# ─────────────────────────────────────────────
# CENY A ZÁLOHY – úprava po novém vyúčtování
# ─────────────────────────────────────────────
with st.expander("⚙️ Ceny a zálohy"):
    st.caption("Uprav po každém vyúčtování nebo změně ceny či zálohy. Ceny vč. DPH. "
               "Plyn: cena za kWh a přepočet kWh na m³ z faktury (objemový koeficient × spalné teplo).")
    for e in PORADI:
        t = tarify[tarify["energie"] == e]
        if t.empty:
            continue
        t = t.iloc[0]
        info = ENERGIE[e]
        with st.form(f"tarif_{e}"):
            st.markdown(f"**{info['ikona']} {info['nazev']}** · {t['dodavatel']}")
            c1, c2 = st.columns(2)
            zaloha = c1.number_input("Měsíční záloha (Kč)", value=float(t["zaloha"]), step=10.0, format="%.0f")
            cena = c2.number_input("Cena za kWh (Kč)" if e != "voda" else "Cena za m³ (Kč)",
                                   value=float(t["cena_za_kwh"]), step=0.01, format="%.5f")
            c1, c2 = st.columns(2)
            mes = c1.number_input("Měsíční stálé platby (Kč)", value=float(t["mesicni_platy"]), step=1.0, format="%.2f")
            prepocet = c2.number_input("kWh na jednotku", value=float(t["kwh_na_jednotku"]), step=0.01, format="%.3f",
                                       disabled=(e != "plyn"))
            c1, c2, c3 = st.columns(3)
            od = c1.date_input("Období od", value=pd.to_datetime(t["obdobi_od"]).date(), format="DD.MM.YYYY")
            do = c2.date_input("Období do", value=pd.to_datetime(t["obdobi_do"]).date(), format="DD.MM.YYYY")
            stav_od = c3.number_input("Stav na začátku", value=float(t["stav_obdobi_od"]), step=0.001, format="%.3f")
            c1, c2 = st.columns(2)
            zaplaceno = c1.number_input("Zaplaceno v období (Kč)", value=float(t["zaplaceno"]), step=10.0, format="%.0f")
            k_datu = c2.date_input("…k datu", value=pd.to_datetime(t["zaplaceno_k_datu"]).date(), format="DD.MM.YYYY")
            c1, c2 = st.columns(2)
            rezerva = c1.number_input("Rezerva na zdražení (%)", value=float(t["rezerva_pct"]), step=1.0, format="%.0f")
            plati = c2.text_input("Cena platí", value=str(t["cena_plati"]))
            if st.form_submit_button("Uložit", width="stretch"):
                ven = tarify.copy()
                m = ven["energie"] == e
                ven.loc[m, ["zaloha", "cena_za_kwh", "mesicni_platy", "kwh_na_jednotku", "obdobi_od", "obdobi_do",
                            "stav_obdobi_od", "zaplaceno", "zaplaceno_k_datu", "rezerva_pct", "cena_plati"]] = [
                    zaloha, cena, mes, prepocet, od.isoformat(), do.isoformat(), stav_od,
                    zaplaceno, k_datu.isoformat(), rezerva, plati]
                ul.uloz("tarify", ven[SLOUPCE_TARIFY])
                st.session_state["ulozeno"] = f"{info['nazev']}: ceny a zálohy uloženy."
                st.rerun()
    st.caption("Zálohy splatné po datu „k datu“ appka připočítává automaticky každý měsíc.")

# ─────────────────────────────────────────────
# PATIČKA
# ─────────────────────────────────────────────
st.markdown(f"""
<div class="paticka">
  Autor: <b>{AUTOR}</b><br>
  E-mail: <b>{EMAIL}</b><br>
  <span style="font-size:.75rem">Data: {ul.popis}</span>
</div>
""", unsafe_allow_html=True)
