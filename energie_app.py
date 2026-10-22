import hashlib
import hmac
import json
import os
import urllib.request
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

# U dvoutarifního elektroměru je „stav“ součet VT + NT a „stav_nt“ samotný nízký tarif
SLOUPCE_ODECTY = ["id", "datum", "energie", "stav", "typ", "poznamka", "meridlo", "stav_nt"]
SLOUPCE_ODECTY_ZAKLAD = SLOUPCE_ODECTY[:6]
SLOUPCE_TARIFY = [
    "energie", "dodavatel", "cena_za_kwh", "kwh_na_jednotku", "mesicni_platy",
    "zaloha", "obdobi_od", "stav_obdobi_od", "obdobi_do",
    "zaplaceno", "zaplaceno_k_datu", "den_splatnosti", "rezerva_pct", "cena_plati",
    "ucet", "vs", "obchodni_kwh", "obchodni_mesic", "konec_smlouvy", "konec_popis", "cena_nt_kwh",
]
SLOUPCE_TARIFY_ZAKLAD = SLOUPCE_TARIFY[:14]  # starší tabulky bez novějších sloupců

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
# Starší odečty z faktur předchozích dodavatelů (PPAS) a vodárny – včetně starého vodoměru
HISTORIE_ODECTY = [
    ("2024-01-06", "elektrina", 44358, "odečet", "Faktura PPAS", "44931016"),
    ("2024-12-02", "elektrina", 47364, "odečet", "Faktura PPAS", "44931016"),
    ("2024-01-04", "plyn", 4420, "odečet", "Faktura PPAS", "88939"),
    ("2024-10-09", "plyn", 4836, "odečet", "Faktura PPAS", "88939"),
    ("2023-05-23", "voda", 657, "odečet", "Faktura VS Chrudim (starý vodoměr)", "42008342966"),
    ("2023-12-31", "voda", 803, "odhad", "Faktura VS Chrudim (starý vodoměr)", "42008342966"),
    ("2024-05-22", "voda", 897, "odečet", "Faktura VS Chrudim (starý vodoměr)", "42008342966"),
    ("2024-12-31", "voda", 980, "odhad", "Faktura VS Chrudim (starý vodoměr)", "42008342966"),
    ("2025-01-20", "voda", 987, "odečet", "Výměna vodoměru – konečný stav starého", "42008342966"),
    ("2025-01-20", "voda", 2110, "odečet", "Výměna vodoměru – počáteční stav nového", "8SEN0120637256"),
]
MERIDLO_AKTUALNI = {"elektrina": "44931016", "plyn": "88939", "voda": "8SEN0120637256"}


def meridlo_pro(energie, datum):
    if energie == "voda" and str(datum) < "2025-01-20":
        return "42008342966"
    return MERIDLO_AKTUALNI.get(energie, "")


VYCHOZI_TARIFY = [
    {"energie": "elektrina", "dodavatel": "E.ON", "cena_za_kwh": 6.28731, "kwh_na_jednotku": 1,
     "mesicni_platy": 407.61, "zaloha": 2110, "obdobi_od": "2026-01-06", "stav_obdobi_od": 50963,
     "obdobi_do": "2027-01-06", "zaplaceno": 20390, "zaplaceno_k_datu": "2026-10-20",
     "den_splatnosti": 15, "rezerva_pct": 0, "cena_plati": "Nefixováno (smlouva do 3. 12. 2026)",
     "ucet": "19-17608231/0100", "vs": "6401196187",
     "obchodni_kwh": 3.53925, "obchodni_mesic": 143.99,
     "konec_smlouvy": "2026-12-03", "konec_popis": "Smlouva (bez fixace) končí", "cena_nt_kwh": 0},
    {"energie": "plyn", "dodavatel": "E.ON", "cena_za_kwh": 1.48004, "kwh_na_jednotku": 10.92,
     "mesicni_platy": 384.36, "zaloha": 1310, "obdobi_od": "2026-10-08", "stav_obdobi_od": 6391,
     "obdobi_do": "2027-10-08", "zaplaceno": 1000, "zaplaceno_k_datu": "2026-10-20",
     "den_splatnosti": 15, "rezerva_pct": 0, "cena_plati": "Fixováno do 31. 12. 2027",
     "ucet": "19-17608231/0100", "vs": "6401196186",
     "obchodni_kwh": 1.0285, "obchodni_mesic": 156.09,
     "konec_smlouvy": "2027-12-31", "konec_popis": "Fixace ceny končí", "cena_nt_kwh": 0},
    {"energie": "voda", "dodavatel": "VS Chrudim", "cena_za_kwh": 143.04, "kwh_na_jednotku": 1,
     "mesicni_platy": 81.08, "zaloha": 2000, "obdobi_od": "2026-05-15", "stav_obdobi_od": 2283,
     "obdobi_do": "2027-05-15", "zaplaceno": 10000, "zaplaceno_k_datu": "2026-10-20",
     "den_splatnosti": 15, "rezerva_pct": 5, "cena_plati": "Ceník 2026, rezerva 5 % na zdražení",
     "ucet": "1092006008/5500", "vs": "4200385398",
     "obchodni_kwh": 0, "obchodni_mesic": 0,
     "konec_smlouvy": "", "konec_popis": "", "cena_nt_kwh": 0},
]


# ─────────────────────────────────────────────
# ODBĚRNÁ MÍSTA
# ─────────────────────────────────────────────
# Strkov 9 – elektřina PRE, dvoutarif D25d (VT/NT), elektroměr 2480513295. Výchozí data z faktury PRE 180369872.
STRKOV_ODECTY = [  # (datum, energie, stav celkem, typ, poznámka, měřidlo, stav NT)
    ("2025-02-01", "elektrina", 347, "odečet", "Faktura PRE · VT 148 + NT 199", "2480513295", 199),
    ("2025-06-21", "elektrina", 1449, "odečet", "Faktura PRE · VT 390 + NT 1059", "2480513295", 1059),
]
STRKOV_TARIFY = [
    {"energie": "elektrina", "dodavatel": "PRE", "cena_za_kwh": 6.65661, "kwh_na_jednotku": 1,
     "mesicni_platy": 443.88, "zaloha": 1730, "obdobi_od": "2026-06-22", "stav_obdobi_od": 0,
     "obdobi_do": "2027-06-21", "zaplaceno": 0, "zaplaceno_k_datu": "2026-06-22",
     "den_splatnosti": 11, "rezerva_pct": 0, "cena_plati": "Ceník PRE 2025 – aktualizuj (změna 30. 9. 2026)",
     "ucet": "19-2784000277/0100", "vs": "21867837",
     "obchodni_kwh": 2.88457, "obchodni_mesic": 143.99,
     "konec_smlouvy": "2026-09-30", "konec_popis": "Změna ceny / produktu PRE", "cena_nt_kwh": 3.92067},
    {"energie": "voda", "dodavatel": "doplň", "cena_za_kwh": 0, "kwh_na_jednotku": 1,
     "mesicni_platy": 0, "zaloha": 0, "obdobi_od": "2026-01-01", "stav_obdobi_od": 0,
     "obdobi_do": "2026-12-31", "zaplaceno": 0, "zaplaceno_k_datu": "2026-01-01",
     "den_splatnosti": 15, "rezerva_pct": 0, "cena_plati": "Doplň z faktury za vodu",
     "ucet": "", "vs": "", "obchodni_kwh": 0, "obchodni_mesic": 0,
     "konec_smlouvy": "", "konec_popis": "", "cena_nt_kwh": 0},
]

MISTA = {
    "pruhony": {"nazev": "V Průhonech 384", "obec": "Nasavrky", "ikona": "🏠", "popis": "Doma",
                "energie": ["plyn", "elektrina", "voda"], "list_odecty": "odecty", "list_tarify": "tarify",
                "tarify": VYCHOZI_TARIFY},
    "strkov": {"nazev": "Strkov 9", "obec": "Ctětín", "ikona": "🏡", "popis": "Mamka · Pavlína Dvořáčková",
               "energie": ["elektrina", "voda"], "list_odecty": "odecty_strkov", "list_tarify": "tarify_strkov",
               "tarify": STRKOV_TARIFY, "odecty": STRKOV_ODECTY},
}
DUVOD = {}  # proč u energie nejde nic spočítat (zobrazí se v záložce)


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
        return df

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


def nacti_data(ul, misto):
    m = MISTA[misto]
    l_od, l_ta = m["list_odecty"], m["list_tarify"]
    odecty = ul.nacti(l_od, SLOUPCE_ODECTY_ZAKLAD)
    if misto == "pruhony":
        if odecty is None:
            zaklad = [(d, e, s, t, p, meridlo_pro(e, d)) for d, e, s, t, p in VYCHOZI_ODECTY]
            odecty = pd.DataFrame(
                [{"id": f"init{i:03d}", "datum": d, "energie": e, "stav": s, "typ": t, "poznamka": p, "meridlo": mr}
                 for i, (d, e, s, t, p, mr) in enumerate(zaklad + HISTORIE_ODECTY)],
                columns=SLOUPCE_ODECTY,
            )
            ul.uloz(l_od, odecty)
        elif "meridlo" not in odecty.columns:
            # jednorázová migrace: doplnit číslo měřidla a starší odečty z faktur, tvoje záznamy zůstávají
            odecty = odecty.copy()
            odecty["meridlo"] = [meridlo_pro(e, str(d)[:10]) for e, d in zip(odecty["energie"], odecty["datum"])]
            mam = {(str(d)[:10], e, round(float(st_), 3)) for d, e, st_ in zip(odecty["datum"], odecty["energie"], odecty["stav"])}
            nove = [{"id": f"hist{i:03d}", "datum": d, "energie": e, "stav": s, "typ": t, "poznamka": p, "meridlo": mr}
                    for i, (d, e, s, t, p, mr) in enumerate(HISTORIE_ODECTY) if (d, e, round(float(s), 3)) not in mam]
            odecty = pd.concat([odecty, pd.DataFrame(nove, columns=SLOUPCE_ODECTY)], ignore_index=True)
            odecty["datum"] = odecty["datum"].astype(str).str[:10]
            for c in SLOUPCE_ODECTY:
                if c not in odecty.columns:
                    odecty[c] = None
            ul.uloz(l_od, odecty[SLOUPCE_ODECTY])
    elif odecty is None:
        odecty = pd.DataFrame(
            [{"id": f"init{i:03d}", "datum": d, "energie": e, "stav": s, "typ": t, "poznamka": p,
              "meridlo": mr, "stav_nt": nt}
             for i, (d, e, s, t, p, mr, nt) in enumerate(m.get("odecty", []))],
            columns=SLOUPCE_ODECTY,
        )
        ul.uloz(l_od, odecty)
    for c in SLOUPCE_ODECTY:
        if c not in odecty.columns:
            odecty[c] = None
    odecty = odecty[SLOUPCE_ODECTY]

    vych_seznam = m["tarify"]
    tarify = ul.nacti(l_ta, SLOUPCE_TARIFY_ZAKLAD)
    if tarify is None:
        tarify = pd.DataFrame(vych_seznam, columns=SLOUPCE_TARIFY)
        ul.uloz(l_ta, tarify)
    else:
        # doplnění sloupců z novější verze appky bez přepsání tvých úprav
        chybi = [c for c in SLOUPCE_TARIFY if c not in tarify.columns]
        if chybi:
            vych = {d["energie"]: d for d in vych_seznam}
            for c in chybi:
                tarify[c] = tarify["energie"].map(lambda e: vych.get(e, {}).get(c, ""))
            ul.uloz(l_ta, tarify[SLOUPCE_TARIFY])
        tarify = tarify[SLOUPCE_TARIFY].copy()
    for c in ["ucet", "konec_popis", "dodavatel", "cena_plati"]:
        tarify[c] = tarify[c].fillna("").astype(str)
    tarify["konec_smlouvy"] = tarify["konec_smlouvy"].fillna("").astype(str).str[:10]
    tarify["vs"] = tarify["vs"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    for c in ["cena_za_kwh", "kwh_na_jednotku", "mesicni_platy", "zaloha", "stav_obdobi_od", "zaplaceno",
              "den_splatnosti", "rezerva_pct", "obchodni_kwh", "obchodni_mesic", "cena_nt_kwh"]:
        tarify[c] = pd.to_numeric(tarify[c], errors="coerce").fillna(0)
    tarify["den_splatnosti"] = tarify["den_splatnosti"].replace(0, 15)

    odecty = odecty.copy()
    odecty["id"] = odecty["id"].astype(str)
    odecty["datum"] = pd.to_datetime(odecty["datum"]).dt.date
    odecty["stav"] = pd.to_numeric(odecty["stav"], errors="coerce")
    odecty["stav_nt"] = pd.to_numeric(odecty["stav_nt"], errors="coerce")
    odecty["poznamka"] = odecty["poznamka"].fillna("").astype(str)
    odecty["typ"] = odecty["typ"].fillna("vlastní").astype(str)
    odecty["meridlo"] = odecty["meridlo"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    prazdne = odecty["meridlo"] == ""
    if misto == "pruhony":
        odecty.loc[prazdne, "meridlo"] = [meridlo_pro(e, str(d)) for e, d in
                                          zip(odecty.loc[prazdne, "energie"], odecty.loc[prazdne, "datum"])]
    return odecty, tarify


def posledni_meridlo(odecty, energie):
    rs = odecty[(odecty["energie"] == energie) & (odecty["meridlo"] != "")].sort_values("datum")
    if not rs.empty:
        return rs.iloc[-1]["meridlo"]
    return MERIDLO_AKTUALNI.get(energie, "") if MISTO_KLIC == "pruhony" else ""


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


def platne_odecty(odecty, energie):
    rs = odecty[(odecty["energie"] == energie) & (odecty["typ"] != "odhad")]
    return rs.sort_values(["datum", "stav"]).reset_index(drop=True)


def denni_rada(odecty, energie, delky=False):
    """Denní spotřeba rozpočítaná mezi odečty (v rámci jednoho měřidla) podle sezónního profilu.
    S delky=True vrací místo spotřeby délku úseku mezi odečty, ze kterého den pochází."""
    rs = platne_odecty(odecty, energie)
    dny, dl = {}, {}
    for i in range(1, len(rs)):
        a, b = rs.iloc[i - 1], rs.iloc[i]
        if a["meridlo"] != b["meridlo"]:
            continue
        delka = (b["datum"] - a["datum"]).days
        delta = b["stav"] - a["stav"]
        if delka <= 0 or delka > 420 or delta < 0:
            continue
        vahy = []
        d = a["datum"]
        while d < b["datum"]:
            dvm = ((d.replace(day=28) + timedelta(days=4)).replace(day=1) - d.replace(day=1)).days
            vahy.append((d, PROFIL[energie][d.month - 1] / dvm))
            d += timedelta(days=1)
        suma = sum(w for _, w in vahy)
        for d, w in vahy:
            dny[d] = delta * w / suma
            dl[d] = delka
    vysl = dl if delky else dny
    return pd.Series(vysl).sort_index() if vysl else pd.Series(dtype=float)


def anomalie(odecty, energie):
    """Porovná tempo posledního úseku se stejným obdobím o rok dřív. Vrací (poměr, text) nebo None."""
    rs = platne_odecty(odecty, energie)
    if len(rs) < 2:
        return None
    rada = denni_rada(odecty, energie)
    a, b = rs.iloc[-2], rs.iloc[-1]
    if a["meridlo"] != b["meridlo"] or (b["datum"] - a["datum"]).days < 5:
        return None
    ted = rada[(rada.index >= a["datum"]) & (rada.index < b["datum"])]
    od_l = a["datum"] - timedelta(days=365)
    do_l = b["datum"] - timedelta(days=365)
    lon = rada[(rada.index >= od_l) & (rada.index < do_l)]
    if len(lon) < 0.8 * len(ted) or lon.mean() <= 0:
        return None
    # loňské odečty musí být dost husté (úseky do ~2 měsíců), jinak je srovnání jen odhad
    dl = denni_rada(odecty, energie, delky=True)
    if dl[(dl.index >= od_l) & (dl.index < do_l)].max() > 62:
        return None
    return ted.mean() / lon.mean(), ted.mean(), lon.mean()


def spocitej(energie, odecty, t, dnes):
    DUVOD.pop(energie, None)
    rs = platne_odecty(odecty, energie)
    if rs.empty:
        DUVOD[energie] = "Zatím tu není žádný stav měřidla – zadej první níže."
        return None
    rs = rs[rs["meridlo"] == rs.iloc[-1]["meridlo"]].reset_index(drop=True)
    if len(rs) < 2:
        DUVOD[energie] = "Pro výpočet potřebuju aspoň dva stavy měřidla – zadej další, třeba za týden."
        return None
    posl = rs.iloc[-1]
    od = pd.to_datetime(t["obdobi_od"]).date()
    do = pd.to_datetime(t["obdobi_do"]).date()
    if posl["datum"] <= od:
        DUVOD[energie] = (f"Poslední stav je z {datum_cz(posl['datum'])}, ale zúčtovací období začalo "
                          f"{datum_cz(od)}. Zadej aktuální stav měřidla – stav na začátku období dopočítám.")
        return None
    A = rocni_odhad(rs, energie)

    # stav na začátku období – ze zadání, jinak dopočet z odečtů okolo
    stav_od = float(t["stav_obdobi_od"] or 0)
    stav_od_odhad = False
    if not stav_od > 0:
        pred, po = rs[rs["datum"] <= od], rs[rs["datum"] >= od]
        b_ = po.iloc[0]
        if not pred.empty:
            a_ = pred.iloc[-1]
            p_all = podil(energie, a_["datum"], b_["datum"])
            pom = podil(energie, a_["datum"], od) / p_all if p_all > 0 else 0
            stav_od = a_["stav"] + (b_["stav"] - a_["stav"]) * pom
        else:
            stav_od = b_["stav"] - A * podil(energie, od, b_["datum"])
        stav_od_odhad = True

    kwh, mes = float(t["kwh_na_jednotku"]), float(t["mesicni_platy"])
    cena = float(t["cena_za_kwh"])
    cena_nt = float(t.get("cena_nt_kwh", 0) or 0)
    podil_nt = None
    if cena_nt > 0:
        podil_nt = 0.7
        nt = rs[rs["stav_nt"].notna()]
        if len(nt) >= 2:
            r1 = nt.iloc[-1]
            okno = nt[nt["datum"] >= r1["datum"] - timedelta(days=400)]
            r0 = okno.iloc[0] if len(okno) >= 2 else nt.iloc[0]
            celk = r1["stav"] - r0["stav"]
            if r0["datum"] < r1["datum"] and celk > 0:
                podil_nt = min(1.0, max(0.0, (r1["stav_nt"] - r0["stav_nt"]) / celk))
        cena = (1 - podil_nt) * cena + podil_nt * cena_nt

    pouzito = posl["stav"] - stav_od
    plan = A * podil(energie, od, posl["datum"])
    projekce = pouzito + A * podil(energie, posl["datum"], do)
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
        "cena_jednotky": kwh * cena, "rs": rs, "stav_od": stav_od, "stav_od_odhad": stav_od_odhad,
        "podil_nt": podil_nt,
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


def iban_cz(ucet):
    """Převede české číslo účtu (předčíslí-číslo/kód banky) na IBAN."""
    try:
        cislo_cast, banka = ucet.strip().split("/")
        if "-" in cislo_cast:
            predcisli, cislo_uctu = cislo_cast.split("-")
        else:
            predcisli, cislo_uctu = "0", cislo_cast
        bban = banka.zfill(4) + predcisli.zfill(6) + cislo_uctu.zfill(10)
        kontrola = 98 - int(bban + "123500") % 97
        return f"CZ{kontrola:02d}{bban}"
    except Exception:
        return None


def qr_platba(ucet, castka, vs, zprava):
    """QR platba (formát SPD) jako PNG."""
    iban = iban_cz(str(ucet))
    if not iban:
        return None
    try:
        import io
        import qrcode
        spd = f"SPD*1.0*ACC:{iban}*AM:{castka:.2f}*CC:CZK*X-VS:{vs}*MSG:{zprava.upper()}"
        img = qrcode.make(spd, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


# ─────────────────────────────────────────────
# POČASÍ A DENOSTUPNĚ (Open-Meteo, zdarma, bez registrace)
# ─────────────────────────────────────────────
LAT, LON = 49.844, 15.805          # Nasavrky
T_VNITRNI, T_TOPNA_HRANICE = 19.0, 13.0


def _stahni(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))["daily"]
    return {date.fromisoformat(t): v for t, v in zip(d["time"], d["temperature_2m_mean"]) if v is not None}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def nacti_teploty(od_iso, do_iso):
    """Průměrné denní teploty pro Nasavrky. Vrací dict datum → °C (prázdný, když služba nejde)."""
    teploty = {}
    try:
        konec_archivu = min(date.fromisoformat(do_iso), date.today() - timedelta(days=6))
        teploty.update(_stahni(
            "https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={LAT}&longitude={LON}&start_date={od_iso}&end_date={konec_archivu.isoformat()}"
            "&daily=temperature_2m_mean&timezone=Europe%2FPrague"))
    except Exception:
        pass
    try:
        teploty.update(_stahni(
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={LAT}&longitude={LON}&past_days=92&forecast_days=1"
            "&daily=temperature_2m_mean&timezone=Europe%2FPrague"))
    except Exception:
        pass
    return teploty


def denostupne(t):
    return T_VNITRNI - t if t <= T_TOPNA_HRANICE else 0.0


def analyza_plynu(odecty, teploty):
    """Rozdělí spotřebu plynu na teplou vodu/vaření (stálá denní část) a topení (úměrné denostupňům)."""
    if not teploty:
        return None
    rs = platne_odecty(odecty, "plyn")
    useky = []
    for i in range(1, len(rs)):
        a, b = rs.iloc[i - 1], rs.iloc[i]
        dni = (b["datum"] - a["datum"]).days
        if a["meridlo"] != b["meridlo"] or dni < 3 or dni > 420 or b["stav"] < a["stav"]:
            continue
        dny = [a["datum"] + timedelta(days=k) for k in range(dni)]
        zname = [teploty[d] for d in dny if d in teploty]
        if len(zname) < 0.95 * dni:
            continue
        dd = sum(denostupne(t) for t in zname) * dni / len(zname)
        useky.append({"od": a["datum"], "do": b["datum"], "dni": dni, "m3": b["stav"] - a["stav"], "dd": dd})
    if len(useky) < 3:
        return None
    # vážená lineární regrese: m3/den = zaklad + k * (denostupně/den)
    w = [u["dni"] for u in useky]
    x = [u["dd"] / u["dni"] for u in useky]
    y = [u["m3"] / u["dni"] for u in useky]
    sw = sum(w)
    mx = sum(wi * xi for wi, xi in zip(w, x)) / sw
    my = sum(wi * yi for wi, yi in zip(w, y)) / sw
    var = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x))
    if var <= 0:
        return None
    k = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y)) / var
    zaklad = max(0.0, my - k * mx)
    if zaklad == 0.0:
        k = sum(wi * xi * yi for wi, xi, yi in zip(w, x, y)) / sum(wi * xi * xi for wi, xi in zip(w, x))
    k = max(k, 0.0)
    for u in useky:
        u["voda"] = zaklad * u["dni"]
        u["topeni"] = max(0.0, u["m3"] - u["voda"])
        u["na_dd"] = u["topeni"] / u["dd"] if u["dd"] > 20 else None
    return {"zaklad": zaklad, "k": k, "useky": useky}


def srovnani_pocasi(an, teploty, konec):
    """Posledních 365 dní proti 365 dním předtím: počasí (denostupně) a topení na denostupeň."""
    def okno(od, do):
        dd = sum(denostupne(teploty[d]) for d in (od + timedelta(days=i) for i in range((do - od).days)) if d in teploty)
        top, dds = 0.0, 0.0
        for u in an["useky"]:
            stred = u["od"] + (u["do"] - u["od"]) / 2
            if od <= stred < do and u["dd"] > 20:
                top += u["topeni"]
                dds += u["dd"]
        return dd, (top / dds if dds > 0 else None)
    ted = okno(konec - timedelta(days=365), konec)
    pred = okno(konec - timedelta(days=730), konec - timedelta(days=365))
    return ted, pred


# ─────────────────────────────────────────────
# ROČNÍ PŘEHLED – PDF
# ─────────────────────────────────────────────
def obrazek_domu(misto, sirka=1600):
    """Ilustrace domu jako PNG (pro PDF). Bez knihovny resvg vrátí None."""
    try:
        import resvg_py
        svg = {"pruhony": svg_pruhony, "strkov": svg_strkov}.get(misto, svg_obecny)()
        return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=sirka, height=int(sirka * 9 / 16)))
    except Exception:
        return None


def _rgb(hexb):
    return tuple(int(hexb[i:i + 2], 16) for i in (1, 3, 5))


def rocni_pdf(rok, odecty, tarif_podle, vysledky, misto):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fpdf import FPDF

    font = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
    font_b = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    mm_ = MISTA[misto]

    class Prehled(FPDF):
        def footer(self):
            self.set_y(-11)
            self.set_font("DV", "", 8)
            self.set_text_color(148, 163, 184)
            self.cell(0, 5, f"Energie · {mm_['nazev']} · přehled roku {rok}", align="L")
            self.set_x(-40)
            self.cell(26, 5, f"Strana {self.page_no()} / {{nb}}", align="R")

    pdf = Prehled(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_font("DV", "", font)
    pdf.add_font("DV", "B", font_b)

    def drz_pohromade(vyska_mm):
        """Když se blok nevejde na zbytek stránky, začni novou – sekce se nerozdělí."""
        if pdf.get_y() + vyska_mm > pdf.h - 16:
            pdf.add_page()
            pdf.set_y(16)

    # --- data za rok ---
    nazvy_m = ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"]
    data = []
    for e in PORADI:
        t = tarif_podle.get(e)
        v = vysledky.get(e)
        rada = denni_rada(odecty, e)
        if t is None or rada.empty:
            continue
        r = rada[[d.year == rok for d in rada.index]]
        if r.empty:
            continue
        p = rada[[d.year == rok - 1 for d in rada.index]]
        dni = len(r)
        zmena = (r.mean() / p.mean() - 1) * 100 if not p.empty and p.mean() > 0 else None
        if v:
            cena_j = v["cena_jednotky"]
        else:  # bez aktuálního výpočtu – cena z ceníku (u dvoutarifu průměr VT/NT 30:70)
            cena_j = float(t["cena_za_kwh"]) * float(t["kwh_na_jednotku"])
            if float(t["cena_nt_kwh"] or 0) > 0:
                cena_j = 0.3 * float(t["cena_za_kwh"]) + 0.7 * float(t["cena_nt_kwh"])
        naklad = r.sum() * cena_j + dni / 365 * 12 * float(t["mesicni_platy"])
        data.append({"e": e, "r": r, "p": p, "spotreba": r.sum(), "dni": dni, "prumer": r.mean(),
                     "zmena": zmena, "naklad": naklad})
    celkem = sum(d["naklad"] for d in data)

    # --- titulní strana: dům s kartami ---
    pdf.add_page()
    vyska_obr = 210 * 9 / 16
    png = obrazek_domu(misto)
    if png:
        pdf.image(io.BytesIO(png), x=0, y=0, w=210, h=vyska_obr)
    else:
        pdf.set_fill_color(17, 24, 39)
        pdf.rect(0, 0, 210, vyska_obr, "F")

    def karta(x, y, w, h, barva=None):
        with pdf.local_context(fill_opacity=0.84):
            pdf.set_fill_color(15, 23, 42)
            pdf.rect(x, y, w, h, style="F", round_corners=True, corner_radius=2.5)
        with pdf.local_context(stroke_opacity=0.45):
            pdf.set_draw_color(148, 163, 184)
            pdf.set_line_width(0.2)
            pdf.rect(x, y, w, h, style="D", round_corners=True, corner_radius=2.5)
        if barva:
            pdf.set_draw_color(*_rgb(barva))
            pdf.set_line_width(0.9)
            pdf.line(x + 2.5, y + 0.3, x + w - 2.5, y + 0.3)

    def text(x, y, s_, velikost, tucne=False, barva=(248, 250, 252), w=0, zarovnani="L"):
        pdf.set_font("DV", "B" if tucne else "", velikost)
        pdf.set_text_color(*barva)
        pdf.set_xy(x, y)
        pdf.cell(w, velikost * 0.45, s_, align=zarovnani)

    # titulek
    karta(7, 7, 92, 21)
    text(11, 10, f"Přehled roku {rok}", 16, True)
    text(11, 19.5, f"{mm_['nazev']}, {mm_['obec']} · vytvořeno {datum_cz(date.today())}", 7.5, barva=(148, 163, 184))

    # karty energií na domě (stejné rozmístění jako v appce)
    pozice = {"pruhony": {"plyn": (0.63, 0.05, None), "elektrina": (None, 0.50, 0.025), "voda": (0.33, None, 0.04)},
              "strkov": {"elektrina": (0.69, 0.05, None), "voda": (0.33, None, 0.04)}}.get(
        misto, {"plyn": (0.56, 0.06, None), "elektrina": (0.74, 0.38, None), "voda": (0.25, None, 0.05)})
    kw, kh = 56, 25
    for d in data:
        e = d["e"]
        inf = ENERGIE[e]
        lx, ty, dalsi = pozice[e]
        x = 210 - 210 * dalsi - kw if lx is None else 210 * lx
        y = vyska_obr - vyska_obr * dalsi - kh if ty is None else vyska_obr * ty
        x = min(x, 210 - kw - 4)
        karta(x, y, kw, kh, inf["barva"])
        text(x + 4, y + 3.5, inf["nazev"], 8, True, (203, 213, 225))
        text(x + 4, y + 8.5, f"{cislo(d['spotreba'], 0)} {inf['jednotka']}", 14, True)
        zm = f"{d['zmena']:+.0f} % proti {rok - 1}" if d["zmena"] is not None else "bez srovnání"
        barva_zm = (148, 163, 184) if d["zmena"] is None else ((239, 68, 68) if d["zmena"] > 3 else
                                                              (34, 197, 94) if d["zmena"] < -3 else (148, 163, 184))
        text(x + 4, y + 16, kc(d["naklad"]), 8.5, True, (226, 232, 240))
        text(x + 4, y + 20.3, zm, 7, False, barva_zm)

    # souhrn roku vlevo
    if data:
        sx, sy, sw = 7, 33, 58
        sh = 15 + 6 * len(data) + 13
        karta(sx, sy, sw, sh)
        text(sx + 4, sy + 3.5, f"Rok {rok} celkem", 8.5, True, (226, 232, 240))
        yy = sy + 10
        for d in data:
            inf = ENERGIE[d["e"]]
            pdf.set_fill_color(*_rgb(inf["barva"]))
            pdf.ellipse(sx + 4, yy + 0.9, 2.2, 2.2, "F")
            text(sx + 8, yy, inf["nazev"], 7.5, False, (203, 213, 225))
            text(sx + 4, yy, kc(d["naklad"]), 7.5, True, w=sw - 8, zarovnani="R")
            yy += 6
        with pdf.local_context(stroke_opacity=0.4):
            pdf.set_draw_color(148, 163, 184)
            pdf.set_line_width(0.2)
            pdf.line(sx + 4, yy + 0.5, sx + sw - 4, yy + 0.5)
        text(sx + 4, yy + 2.5, "Celkem", 8.5, True)
        text(sx + 4, yy + 2.5, kc(celkem), 8.5, True, w=sw - 8, zarovnani="R")
        text(sx + 4, yy + 7.5, "měsíčně", 7, False, (148, 163, 184))
        text(sx + 4, yy + 7.5, kc(celkem / 12), 7, False, (148, 163, 184), w=sw - 8, zarovnani="R")

    # --- detail po energiích ---
    pdf.set_y(vyska_obr + 8)
    pdf.set_left_margin(14)
    for d in data:
        e = d["e"]
        info = ENERGIE[e]
        drz_pohromade(10 + 2 * 6 + 186 * 2.1 / 7.2 + 6)
        pdf.set_x(14)
        pdf.set_fill_color(*_rgb(info["barva"]))
        pdf.rect(14, pdf.get_y() + 1.2, 1.6, 6, "F")
        pdf.set_x(18)
        pdf.set_font("DV", "B", 13)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 8, info["nazev"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DV", "", 9.5)
        pdf.set_text_color(71, 85, 105)
        radek = (f"Spotřeba {cislo(d['spotreba'], 0)} {info['jednotka']}"
                 + ("" if d["dni"] >= 360 else f" (data za {d['dni']} dní)")
                 + f" · průměr {cislo(d['prumer'], 2)} {info['jednotka']}/den"
                 + (f" · {d['zmena']:+.0f} % proti {rok - 1}" if d["zmena"] is not None else "")
                 + f" · náklad {kc(d['naklad'])}")
        pdf.multi_cell(0, 5.5, radek, new_x="LMARGIN", new_y="NEXT")

        df = d["r"].rename("h").to_frame()
        df["m"] = [x_.month for x_ in df.index]
        mes = df.groupby("m")["h"].sum()
        if not d["p"].empty:
            dfp = d["p"].rename("h").to_frame()
            dfp["m"] = [x_.month for x_ in dfp.index]
            mesp = dfp.groupby("m")["h"].sum()
        else:
            mesp = pd.Series(dtype=float)
        fig, ax = plt.subplots(figsize=(7.2, 2.1), dpi=150)
        x = list(range(1, 13))
        if not mesp.empty:
            ax.bar([i - 0.2 for i in x], [mesp.get(i, 0) for i in x], width=0.4, color="#cbd5e1", label=str(rok - 1))
        ax.bar([i + 0.2 for i in x], [mes.get(i, 0) for i in x], width=0.4, color=info["barva"], label=str(rok))
        ax.set_xticks(x)
        ax.set_xticklabels(nazvy_m, fontsize=8)
        ax.tick_params(axis="y", labelsize=8)
        ax.set_ylabel(info["jednotka"], fontsize=8)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", alpha=.25)
        ax.legend(fontsize=7, frameon=False, loc="lower right", bbox_to_anchor=(1, 1), ncol=2)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        pdf.image(buf, x=12, w=186)
        pdf.ln(3)

    if data:
        drz_pohromade(20)
        pdf.set_font("DV", "", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(0, 4.5, "Spotřeba mezi odečty je rozpočítaná podle typického průběhu roku. Náklady jsou "
                               "přepočtené aktuálními cenami s DPH včetně stálých plateb, aby šly roky srovnávat – "
                               f"skutečně zaplacené částky se mohou lišit. Autor: {AUTOR}, {EMAIL}")
    else:
        pdf.set_y(vyska_obr + 10)
        pdf.set_font("DV", "", 11)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(0, 8, f"Za rok {rok} zatím nejsou data.")
    return bytes(pdf.output())


# ─────────────────────────────────────────────
# VZHLED
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea {{ font-family: 'Inter', sans-serif !important; }}
.block-container {{ padding-top: 1rem; padding-bottom: 5rem; max-width: 1120px; }}
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

.platby {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }}
@media (max-width: 640px) {{ .platby {{ grid-template-columns: 1fr; }} }}
.platba {{ background: rgba(15,23,42,.55); border: 1px solid rgba(148,163,184,.15); border-top: 3px solid var(--acc);
  border-radius: 14px; padding: 10px 12px; }}
.p-hlava {{ font-size: .8rem; font-weight: 700; color: #e2e8f0; }}
.p-castka {{ font-size: 1.3rem; font-weight: 700; color: #f8fafc; font-variant-numeric: tabular-nums; margin-top: 2px; }}
.p-castka span {{ font-size: .75rem; font-weight: 500; color: {BARVA_TEXT_TLUMENY}; }}
.p-stav {{ display: flex; align-items: center; gap: 6px; font-size: .78rem; color: #e2e8f0; margin: 2px 0 6px; }}
.p-udaje {{ display: grid; grid-template-columns: auto 1fr; gap: 1px 10px; font-size: .78rem; }}
.p-udaje span {{ color: {BARVA_TEXT_TLUMENY}; }}
.p-udaje b {{ color: #e2e8f0; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; user-select: all; }}
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

.budiky {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 6px 0 10px; }}
.budik {{ background: rgba(30,41,59,.55); border: 1px solid rgba(148,163,184,.15); border-radius: 16px;
  padding: 12px 14px 14px; display: flex; flex-direction: column; align-items: center; }}
.b-titul {{ align-self: flex-start; font-size: .72rem; color: {BARVA_TEXT_TLUMENY}; text-transform: uppercase; letter-spacing: .06em; }}
.b-svg {{ max-width: 260px; margin-top: 4px; }}
.b-stitek {{ margin-top: 6px; padding: 3px 12px; border-radius: 999px; font-size: .78rem; font-weight: 700; border: 1px solid; }}
.radky-mini {{ display: grid; grid-template-columns: 1fr; gap: 2px; font-size: .88rem; color: #e2e8f0; padding-top: 18px; }}
.radky-mini b {{ font-weight: 700; font-size: 1.05rem; margin-bottom: 8px; font-variant-numeric: tabular-nums; }}
.mini-pozn {{ font-size: .76rem; color: {BARVA_TEXT_TLUMENY}; line-height: 1.5; }}
.smlouva {{ border: 1px solid var(--acc); border-left: 5px solid var(--acc); border-radius: 14px;
  background: rgba(30,41,59,.6); padding: 10px 14px; margin: 0 0 12px; font-size: .88rem; color: #e2e8f0; line-height: 1.5; }}
.cena-radek {{ display: flex; justify-content: space-between; gap: 12px; padding: 7px 2px;
  border-bottom: 1px solid rgba(148,163,184,.12); font-size: .92rem; }}
.cena-radek b {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
.misto-karta {{ background: rgba(30,41,59,.6); border: 1px solid rgba(148,163,184,.18); border-radius: 18px;
  padding: 18px 16px; margin-bottom: 10px; text-align: center; }}
.mk-ikona {{ font-size: 2.2rem; }}
.mk-nazev {{ font-size: 1.15rem; font-weight: 700; color: #f8fafc; margin-top: 4px; }}
.mk-obec {{ font-size: .82rem; color: {BARVA_TEXT_TLUMENY}; margin-top: 2px; }}
.mk-energie {{ font-size: 1.2rem; margin-top: 8px; letter-spacing: 4px; }}
div[class*="st-key-prepni_"] button {{ min-height: 3rem; border-radius: 14px; font-weight: 600; }}
div[class*="st-key-prepni_"] button:disabled {{ background: rgba(16,185,129,.18); border: 1px solid {BARVA_PRIMARNI};
  color: #6ee7b7; opacity: 1; cursor: default; }}
section[data-testid="stSidebar"] {{ background: #0c1424; border-right: 1px solid rgba(148,163,184,.12); }}
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: .4rem; }}
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {{ gap: .15rem; }}
.sb-logo {{ font-size: 1.45rem; font-weight: 800; letter-spacing: -.02em; color: #f8fafc; padding: 6px 6px 10px;
  border-bottom: 1px solid rgba(148,163,184,.12); margin-bottom: 4px; }}
.sb-logo-ikona {{ display: inline-flex; width: 34px; height: 34px; border-radius: 10px; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #10b981, #f97316); margin-right: 10px; font-size: 1.05rem; vertical-align: middle; }}
.sb-logo-tecka {{ color: #10b981; }}
.sb-sekce {{ font-size: .66rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #64748b;
  margin: 0 8px; padding: 14px 0 4px; line-height: 1.2; }}
section[data-testid="stSidebar"] [data-testid="stElementContainer"] {{ margin: 0; }}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ margin: 0; }}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
section[data-testid="stSidebar"] button {{ min-height: 2.25rem !important; height: 2.25rem; padding-top: 0; padding-bottom: 0; }}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 2px; }}
div[class*="st-key-menu_"] button, div[class*="st-key-prepni_"] button, div.st-key-odhlasit button {{
  justify-content: flex-start; background: transparent; border: 1px solid transparent; color: #cbd5e1;
  border-radius: 10px; min-height: 2.3rem; padding: 0 12px; font-weight: 500; box-shadow: none; }}
div[class*="st-key-menu_"] button p, div[class*="st-key-prepni_"] button p {{ font-size: .93rem; }}
div[class*="st-key-menu_"] button > div, div[class*="st-key-prepni_"] button > div {{ justify-content: flex-start; width: 100%; }}
div[class*="st-key-menu_"] button:hover, div[class*="st-key-prepni_"] button:hover {{ background: rgba(148,163,184,.08); color: #f1f5f9; border-color: transparent; }}
div[class*="st-key-menu_"] button[kind="primary"], div[class*="st-key-menu_"] button[data-testid="stBaseButton-primary"] {{
  background: rgba(16,185,129,.14); color: #6ee7b7; box-shadow: inset 3px 0 0 #10b981; }}
div[class*="st-key-prepni_"] button:disabled {{ background: rgba(16,185,129,.10); border: 1px solid rgba(16,185,129,.45);
  color: #6ee7b7; opacity: 1; cursor: default; }}
.sb-uzivatel {{ display: flex; align-items: center; gap: 10px; margin: 22px 4px 6px; padding: 10px;
  border-top: 1px solid rgba(148,163,184,.12); }}
.sb-avatar {{ width: 34px; height: 34px; border-radius: 50%; background: #10b981; color: #052e1f; font-weight: 800;
  display: flex; align-items: center; justify-content: center; }}
.sb-jmeno {{ font-weight: 600; color: #f1f5f9; font-size: .9rem; }}
.sb-role {{ font-size: .75rem; color: #64748b; }}
div.st-key-odhlasit button {{ color: #94a3b8; font-size: .85rem; min-height: 2rem; }}

.stranka-nadpis {{ font-size: 1.7rem; font-weight: 800; letter-spacing: -.02em; color: #f8fafc; margin: 2px 0 0; }}
.stranka-pod {{ font-size: .88rem; color: {BARVA_TEXT_TLUMENY}; margin: 2px 0 16px; }}
.platby-velke {{ margin: 6px 0 12px; }}

.scena {{ position: relative; aspect-ratio: 16 / 9; border-radius: 22px; overflow: hidden; margin: 6px 0 16px;
  border: 1px solid rgba(148,163,184,.18); box-shadow: 0 20px 50px rgba(0,0,0,.35); }}
.sc-svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
.sc-tok {{ animation: tok 1.4s linear infinite; }}
@keyframes tok {{ to {{ stroke-dashoffset: -24; }} }}
@media (prefers-reduced-motion: reduce) {{ .sc-tok {{ animation: none; }} }}
.sc-karta {{ position: absolute; background: rgba(15,23,42,.72); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(148,163,184,.28); border-radius: 12px; padding: 8px 12px; color: #f1f5f9; min-width: 9.5rem;
  box-shadow: 0 8px 24px rgba(0,0,0,.35); }}
.sc-karta[style*="--acc"] {{ border-top: 2px solid var(--acc); }}
.sc-hlava {{ font-size: .74rem; font-weight: 600; color: #cbd5e1; }}
.sc-hodnota {{ font-size: 1.15rem; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 1px; }}
.sc-pod {{ font-size: .7rem; color: #94a3b8; margin-top: 1px; }}
.sc-teplota {{ font-size: 1.25rem; font-weight: 800; margin-top: 2px; }}
.sc-pocasi {{ left: 2.5%; top: 4%; }}
.sc-plyn {{ left: 56%; top: 6%; }}
.sc-elektrina {{ left: 79%; top: 38%; }}
.sc-voda {{ left: 25%; bottom: 5%; }}
.sc-souhrn {{ left: 2.5%; top: 21%; min-width: 12.5rem; }}
.scena-pruhony .sc-plyn {{ left: 63%; top: 5%; }}
.scena-pruhony .sc-elektrina {{ left: auto; right: 2.5%; top: 50%; }}
.scena-pruhony .sc-voda {{ left: 33%; bottom: 4%; }}
.sc-r {{ display: flex; justify-content: space-between; gap: 14px; font-size: .74rem; color: #cbd5e1; margin-top: 4px; }}
.sc-r b {{ color: #f8fafc; font-variant-numeric: tabular-nums; }}
.sc-r2 {{ margin-top: 0; color: #94a3b8; }}
.sc-r2 b {{ color: #94a3b8; font-weight: 500; }}
.sc-celkem {{ border-top: 1px solid rgba(148,163,184,.25); padding-top: 5px; margin-top: 6px; font-weight: 700; }}
@media (max-width: 760px) {{
  .scena {{ aspect-ratio: auto; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 250px 10px 10px; }}
  .sc-svg {{ height: 260px; }}
  .scena .sc-karta {{ position: relative; left: auto; right: auto; top: auto; bottom: auto; min-width: 0; }}
  .sc-souhrn {{ grid-column: span 2; }}
  .sc-tok {{ display: none; }}
}}
div.st-key-scena_obal {{ position: relative; gap: 0; margin: 6px 0 16px; }}
div.st-key-scena_obal .scena {{ margin: 0; }}
div[class*="st-key-karta_"] {{ position: absolute; width: 11.5rem; gap: 0; z-index: 2; cursor: pointer;
  transition: transform .15s ease; }}
div[class*="st-key-karta_"]:hover {{ transform: translateY(-2px); z-index: 3; }}
div[class*="st-key-karta_"]:hover .sc-energie {{ border-color: var(--acc); box-shadow: 0 10px 30px rgba(0,0,0,.45), 0 0 0 1px var(--acc); }}
div[class*="st-key-karta_"] [data-testid="stElementContainer"] {{ margin: 0; }}
div[class*="st-key-skok_"] {{ position: absolute; inset: 0; z-index: 4; width: 100% !important; height: 100% !important; }}
div[class*="st-key-skok_"] > div {{ width: 100% !important; height: 100% !important; }}
div[class*="st-key-skok_"] button {{ position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
.sc-energie {{ position: relative; left: auto; top: auto; width: 100%; min-width: 0; transition: border-color .15s, box-shadow .15s; }}
.sc-detail {{ float: right; font-size: .66rem; color: #94a3b8; font-weight: 500; }}
.sc-dnes {{ max-height: 0; opacity: 0; overflow: hidden; transition: max-height .25s ease, opacity .2s ease, margin .2s; }}
div[class*="st-key-karta_"]:hover .sc-dnes {{ max-height: 140px; opacity: 1; margin-top: 8px; padding-top: 7px;
  border-top: 1px solid rgba(148,163,184,.25); }}
.sc-dnes-l {{ font-size: .66rem; text-transform: uppercase; letter-spacing: .06em; color: #94a3b8; }}
.sc-dnes-v {{ font-size: 1.05rem; font-weight: 800; font-variant-numeric: tabular-nums; margin: 1px 0 2px; }}
.sc-dnes-v span {{ font-size: .7rem; font-weight: 500; color: #94a3b8; }}
.sc-dnes-p {{ font-size: .64rem; color: #64748b; margin-top: 3px; }}
/* rozmístění karet – obecný domek */
div[class*="st-key-karta_"][class*="_plyn"] {{ left: 56%; top: 6%; }}
div[class*="st-key-karta_"][class*="_elektrina"] {{ left: 79%; top: 38%; }}
div[class*="st-key-karta_"][class*="_voda"] {{ left: 25%; bottom: 5%; }}
/* rozmístění karet – V Průhonech 384 */
div.st-key-scena_obal div.st-key-karta_pruhony_plyn {{ left: 63%; top: 5%; }}
div.st-key-scena_obal div.st-key-karta_pruhony_elektrina {{ left: auto; right: 2.5%; top: 50%; }}
div.st-key-scena_obal div.st-key-karta_pruhony_voda {{ left: 33%; top: auto; bottom: 4%; }}
div.st-key-scena_obal div.st-key-karta_strkov_elektrina {{ left: 69%; top: 5%; }}
div.st-key-scena_obal div.st-key-karta_strkov_voda {{ left: 33%; top: auto; bottom: 4%; }}
@media (max-width: 760px) {{
  div.st-key-scena_obal {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  div.st-key-scena_obal > div:first-child {{ grid-column: span 2; }}
  div.st-key-scena_obal div.st-key-scena_obal div[class*="st-key-karta_"], div.st-key-scena_obal div[class*="st-key-karta_"][class*="_"] {{
    position: relative; left: auto !important; right: auto !important; top: auto !important; bottom: auto !important; width: auto; }}
}}
.sc-mobil {{ display: none; }}
.sc-mobil summary {{ list-style: none; cursor: pointer; -webkit-tap-highlight-color: transparent; }}
.sc-mobil summary::-webkit-details-marker {{ display: none; }}
.sc-klepni {{ font-size: .68rem; color: #94a3b8; margin-top: 6px; }}
.sc-klepni span {{ display: inline-block; transition: transform .2s; }}
.sc-mobil[open] .sc-klepni {{ color: var(--acc); }}
.sc-mobil[open] .sc-klepni span {{ transform: rotate(180deg); }}
.sc-mobil .sc-dnes-m {{ max-height: none; opacity: 1; margin-top: 8px; padding-top: 7px; border-top: 1px solid rgba(148,163,184,.25);
  animation: rozbal .25s ease; }}
.sc-mobil[open] {{ border-color: var(--acc); box-shadow: 0 0 0 1px var(--acc); }}
@keyframes rozbal {{ from {{ opacity: 0; transform: translateY(-4px); }} to {{ opacity: 1; transform: none; }} }}
@media (hover: none), (max-width: 760px) {{
  .sc-pc {{ display: none; }}
  .sc-mobil {{ display: block; }}
  .sc-mobil .sc-detail {{ float: none; position: absolute; top: 8px; right: 8px; padding: 4px 10px; border-radius: 999px;
    background: rgba(148,163,184,.14); border: 1px solid rgba(148,163,184,.3); color: #e2e8f0; font-size: .72rem; font-weight: 600; }}
  div[class*="st-key-skok_"] {{ inset: auto; top: 4px; right: 4px; width: 92px !important; height: 34px !important; }}
  div[class*="st-key-karta_"]:hover {{ transform: none; }}
  div[class*="st-key-karta_"]:hover .sc-energie {{ box-shadow: 0 8px 24px rgba(0,0,0,.35); border-color: rgba(148,163,184,.28); }}
  div[class*="st-key-karta_"] .sc-mobil[open] {{ border-color: var(--acc); box-shadow: 0 0 0 1px var(--acc); }}
}}
/* ── mobilní navigace ── */
div.st-key-mobil_mista, div.st-key-mobil_lista, div.st-key-mobil_vice {{ display: none; }}
@media (max-width: 760px) {{
  section[data-testid="stSidebar"], [data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"],
  header[data-testid="stHeader"] {{ display: none !important; }}
  .block-container {{ padding-top: .6rem !important; padding-bottom: calc(7rem + var(--lista-navic, 0px)) !important; }}
  div.st-key-mobil_mista {{ display: flex; gap: 6px; margin-bottom: 4px; }}
  div.st-key-mobil_mista button {{ min-height: 2.4rem; border-radius: 999px; font-weight: 600; font-size: .85rem;
    background: rgba(30,41,59,.6); border: 1px solid rgba(148,163,184,.2); color: #cbd5e1; }}
  div.st-key-mobil_mista button:disabled {{ background: rgba(16,185,129,.16); border-color: rgba(16,185,129,.55);
    color: #6ee7b7; opacity: 1; }}
  div.st-key-mobil_lista {{ display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000; gap: 2px;
    background: rgba(10,16,30,.97); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border-top: 1px solid rgba(148,163,184,.18);
    padding: 6px 6px calc(6px + env(safe-area-inset-bottom) + var(--lista-navic, 0px)); }}
  div.st-key-mobil_lista > div {{ flex: 1 1 0; min-width: 0; }}
  div.st-key-mobil_lista button {{ width: 100%; min-height: 3.3rem; padding: 4px 2px; border: none; background: transparent;
    color: #94a3b8; border-radius: 12px; box-shadow: none; }}
  div.st-key-mobil_lista button > div, div.st-key-mobil_lista button span {{ flex-direction: column; gap: 1px; }}
  div.st-key-mobil_lista button > div {{ display: flex; align-items: center; }}
  div.st-key-mobil_lista button p {{ font-size: .68rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  div.st-key-mobil_lista button [data-testid="stIconEmoji"], div.st-key-mobil_lista button span[role="img"] {{ font-size: 1.25rem; margin: 0; }}
  div.st-key-mobil_lista button[kind="primary"], div.st-key-mobil_lista button[data-testid="stBaseButton-primary"] {{
    color: #6ee7b7; background: rgba(16,185,129,.14); }}
  div.st-key-mobil_vice {{ display: block; position: fixed; left: 8px; right: 8px; z-index: 999;
    bottom: calc(4.6rem + env(safe-area-inset-bottom) + var(--lista-navic, 0px));
    background: #111a2e; border: 1px solid rgba(148,163,184,.22); border-radius: 18px; padding: 12px;
    box-shadow: 0 -10px 40px rgba(0,0,0,.55); animation: vysun .2s ease; }}
  @keyframes vysun {{ from {{ transform: translateY(12px); opacity: 0; }} to {{ transform: none; opacity: 1; }} }}
  .mv-titul {{ font-size: .7rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #64748b; margin: 0 4px 6px; }}
  div.st-key-mobil_vice {{ box-sizing: border-box; width: auto !important; max-width: none; }}
  div.st-key-mobil_vice [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
  div.st-key-mobil_vice_mrizka {{ display: grid !important; grid-template-columns: 1fr 1fr; gap: 6px; width: 100%; }}
  div.st-key-mobil_vice_mrizka > div, div.st-key-mobil_vice_mrizka [data-testid="stElementContainer"],
  div.st-key-mobil_vice_mrizka .stButton {{ width: 100% !important; min-width: 0; }}
  div.st-key-mobil_vice_mrizka button {{ width: 100% !important; min-height: 3rem; justify-content: flex-start; border-radius: 12px;
    background: rgba(30,41,59,.7); border: 1px solid rgba(148,163,184,.15); color: #e2e8f0; font-size: .85rem; }}
  div.st-key-mobil_vice_mrizka button[kind="primary"], div.st-key-mobil_vice_mrizka button[data-testid="stBaseButton-primary"] {{
    background: rgba(16,185,129,.16); border-color: rgba(16,185,129,.55); color: #6ee7b7; }}
  div.st-key-m_odhlasit button {{ margin-top: 6px; background: transparent; border: 1px solid rgba(148,163,184,.15);
    color: #94a3b8; min-height: 2.4rem; border-radius: 12px; }}
}}
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

# ─────────────────────────────────────────────
# HESLO (nastavuje se ve Streamlit Secrets: heslo = "...")
# ─────────────────────────────────────────────
def spravne_heslo():
    try:
        return st.secrets["heslo"]
    except Exception:
        return None


def klic_z_hesla(heslo):
    """Otisk hesla, který si pamatuje nainstalovaná appka v telefonu (heslo samo se nikde neukládá)."""
    return hashlib.sha256(("energie:" + str(heslo)).encode("utf-8")).hexdigest()


def zprava_obalu(text):
    """Pošle zprávu obalu nainstalované appky (GitHub Pages), např. ať zapomene uložené přihlášení."""
    import streamlit.components.v1 as components
    components.html(f"<script>try{{window.top.postMessage({json.dumps(text)}, '*');}}catch(e){{}}</script>", height=0)


_heslo = spravne_heslo()
if _heslo and not st.session_state.get("prihlasen"):
    _klic = st.query_params.get("klic")
    if _klic:
        if hmac.compare_digest(str(_klic), klic_z_hesla(_heslo)):
            st.session_state["prihlasen"] = True
        else:
            st.session_state["spatny_klic"] = True
        del st.query_params["klic"]
if _heslo and not st.session_state.get("prihlasen"):
    if st.session_state.pop("spatny_klic", False):
        zprava_obalu("energie-zapomen-prihlaseni")
        st.warning("Uložené přihlášení už neplatí (heslo se změnilo) – zadej heslo znovu.")
    if st.session_state.pop("odhlaseno", False):
        zprava_obalu("energie-zapomen-prihlaseni")
    st.markdown("""
<div class="hero"><h1>⚡ Energie doma</h1>
<div class="sub">Pro vstup zadej heslo.</div></div>""", unsafe_allow_html=True)
    with st.form("prihlaseni"):
        zadane = st.text_input("Heslo", type="password")
        if st.form_submit_button("Vstoupit", type="primary", width="stretch"):
            if hmac.compare_digest(zadane.encode(), str(_heslo).encode()):
                st.session_state["prihlasen"] = True
                st.session_state["ulozit_klic"] = True
                st.rerun()
            st.error("Špatné heslo.")
    st.stop()

# ─────────────────────────────────────────────
# VÝBĚR ODBĚRNÉHO MÍSTA
# ─────────────────────────────────────────────
if "misto" not in st.session_state and st.query_params.get("misto") in MISTA:
    st.session_state["misto"] = st.query_params.get("misto")
if "misto" not in st.session_state:
    st.markdown("""
<div class="hero"><h1>⚡ Energie</h1>
<div class="sub">Vyber odběrné místo</div></div>""", unsafe_allow_html=True)
    sloupce = st.columns(len(MISTA))
    for sl, (klic, mm) in zip(sloupce, MISTA.items()):
        with sl:
            ikony = " ".join(ENERGIE[x]["ikona"] for x in mm["energie"])
            st.markdown(f"""
<div class="misto-karta">
  <div class="mk-ikona">{mm['ikona']}</div>
  <div class="mk-nazev">{mm['nazev']}</div>
  <div class="mk-obec">{mm['obec']} · {mm['popis']}</div>
  <div class="mk-energie">{ikony}</div>
</div>""", unsafe_allow_html=True)
            if st.button("Otevřít", key=f"vyber_{klic}", type="primary", width="stretch"):
                st.session_state["misto"] = klic
                st.query_params["misto"] = klic
                st.rerun()
    st.stop()

if _heslo and st.session_state.pop("ulozit_klic", False):
    zprava_obalu("energie-klic:" + klic_z_hesla(_heslo))

MISTO_KLIC = st.session_state["misto"]
MISTO = MISTA[MISTO_KLIC]
if st.session_state.get("misto_ohlaseno") != MISTO_KLIC:   # nainstalovaná appka si pamatuje poslední místo
    zprava_obalu("energie-misto:" + MISTO_KLIC)
    st.session_state["misto_ohlaseno"] = MISTO_KLIC
PORADI = MISTO["energie"]
L_ODECTY, L_TARIFY = MISTO["list_odecty"], MISTO["list_tarify"]

ul = Uloziste()
odecty, tarify = nacti_data(ul, MISTO_KLIC)
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


def _bod(hodnota, r=80, cx=100, cy=100):
    import math
    th = math.pi * (1 - max(0, min(hodnota, 200)) / 200)
    return cx + r * math.cos(th), cy - r * math.sin(th)


def _oblouk(v1, v2, r=80):
    x1, y1 = _bod(v1, r)
    x2, y2 = _bod(v2, r)
    return f"M {x1:.2f} {y1:.2f} A {r} {r} 0 0 1 {x2:.2f} {y2:.2f}"


def svg_budik(hodnota, zony, barva, velky_text, maly_text, popisky):
    """Moderní půlkruhový barometr jako SVG – tenké barevné zóny, svítící ukazatel, hodnota uprostřed."""
    h = max(0, min(hodnota, 200))
    casti = []
    for (z1, z2), c in zony:
        casti.append(f'<path d="{_oblouk(z1 + (0 if z1 == 0 else 1.2), z2 - (0 if z2 == 200 else 1.2))}" stroke="{c}" stroke-opacity=".30" '
                     f'stroke-width="10" fill="none" stroke-linecap="butt"/>')
    if h > 2:
        casti.append(f'<path d="{_oblouk(1.8, h)}" stroke="{barva}" stroke-width="10" fill="none" '
                     f'stroke-linecap="round" filter="url(#zare)"/>')
    x, y = _bod(h)
    casti.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="9" fill="#0b1220" stroke="{barva}" stroke-width="3.5" filter="url(#zare)"/>')
    casti.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="#f8fafc"/>')
    lx, _ = _bod(0)
    rx, _ = _bod(200)
    return (f'<svg viewBox="0 -4 200 126" width="100%" class="b-svg" role="img" aria-label="{velky_text}">'
            '<defs><filter id="zare" x="-50%" y="-50%" width="200%" height="200%">'
            '<feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/>'
            '<feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
            f'<path d="{_oblouk(0, 200)}" stroke="rgba(148,163,184,.10)" stroke-width="18" fill="none" stroke-linecap="round"/>'
            + "".join(casti) +
            f'<text x="100" y="86" text-anchor="middle" font-size="22" font-weight="700" fill="#f8fafc" font-family="Inter, sans-serif">{velky_text}</text>'
            f'<text x="100" y="103" text-anchor="middle" font-size="11" fill="#94a3b8" font-family="Inter, sans-serif">{maly_text}</text>'
            f'<text x="{lx:.0f}" y="119" text-anchor="middle" font-size="10" fill="#64748b" font-family="Inter, sans-serif">{popisky[0]}</text>'
            f'<text x="{rx:.0f}" y="119" text-anchor="middle" font-size="10" fill="#64748b" font-family="Inter, sans-serif">{popisky[1]}</text>'
            '</svg>')


ZONY_ZALOHA = [([0, 92], BARVA_ZLE), ([92, 108], BARVA_OK), ([108, 200], BARVA_MOC)]
ZONY_PLAN = [([0, 95], BARVA_OK), ([95, 115], BARVA_VAROVANI), ([115, 200], BARVA_ZLE)]

# ─────────────────────────────────────────────
# HERO – celkový přehled
# ─────────────────────────────────────────────
platne = [v for v in vysledky.values() if v]
tarif_podle = {r["energie"]: r for _, r in tarify.iterrows()}
zalohy_ted = sum(float(tarif_podle[e]["zaloha"]) for e in PORADI if e in tarif_podle)
zalohy_nulu = sum((vysledky[e]["doporucena"] if vysledky.get(e) and vysledky[e]["doporucena"] is not None
                   else float(tarif_podle[e]["zaloha"])) for e in PORADI if e in tarif_podle)
bilance_celkem = sum(v["bilance"] for v in platne)
mesicne_celkem = sum(v["mesicne"] for v in platne)
barva_bil = BARVA_OK if bilance_celkem >= 0 else BARVA_ZLE

# ─────────────────────────────────────────────
# BOČNÍ MENU
# ─────────────────────────────────────────────
MENU = [
    ("Přehled", [("prehled", "🏠", "Přehled"), ("platby", "💳", "Zálohy a platby")]),
    ("Energie", [(e, ENERGIE[e]["ikona"], ENERGIE[e]["nazev"]) for e in PORADI]),
    ("Nástroje", [("spotrebice", "🔌", "Co kolik stojí"), ("nabidky", "💡", "Porovnat nabídky"),
                  ("pdf", "📄", "Roční přehled PDF")]),
    ("Správa", [("historie", "📋", "Historie odečtů"), ("nastaveni", "⚙️", "Ceny a zálohy")]),
]
_platne_stranky = [p[0] for _, pol in MENU for p in pol]
if st.session_state.get("stranka") not in _platne_stranky:
    st.session_state["stranka"] = "prehled"

with st.sidebar:
    st.markdown('<div class="sb-logo"><span class="sb-logo-ikona">⚡</span>Energie<span class="sb-logo-tecka">.</span></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sb-sekce">Odběrné místo</div>', unsafe_allow_html=True)
    for klic, mm in MISTA.items():
        aktivni = klic == MISTO_KLIC
        if st.button(f"{mm['ikona']}  {mm['nazev']}", key=f"prepni_{klic}", width="stretch",
                     type="primary" if aktivni else "secondary", disabled=aktivni):
            st.session_state["misto"] = klic
            st.query_params["misto"] = klic
            for k in ["upravuji", "mazu", "pdf_data"]:
                st.session_state.pop(k, None)
            st.rerun()
    for sekce, polozky in MENU:
        st.markdown(f'<div class="sb-sekce">{sekce}</div>', unsafe_allow_html=True)
        for pid, ik, nazev in polozky:
            aktivni = st.session_state["stranka"] == pid
            if st.button(f"{ik}  {nazev}", key=f"menu_{pid}", width="stretch",
                         type="primary" if aktivni else "secondary"):
                st.session_state["stranka"] = pid
                st.session_state.pop("upravuji", None)
                st.session_state.pop("mazu", None)
                st.rerun()
    st.markdown(f"""
<div class="sb-uzivatel">
  <div class="sb-avatar">{AUTOR[:1]}</div>
  <div><div class="sb-jmeno">{AUTOR}</div><div class="sb-role">{MISTO['nazev']} · {MISTO['obec']}</div></div>
</div>""", unsafe_allow_html=True)
    if spravne_heslo() and st.button("↪  Odhlásit", key="odhlasit", width="stretch"):
        for k in ["prihlasen", "misto", "stranka", "misto_ohlaseno"]:
            st.session_state.pop(k, None)
        st.session_state["odhlaseno"] = True
        st.query_params.clear()
        st.rerun()

STRANKA = st.session_state["stranka"]

# ─────────────────────────────────────────────
# MOBILNÍ NAVIGACE – přepínač místa nahoře a spodní lišta (na počítači skrytá)
# ─────────────────────────────────────────────
def _prejdi(pid):
    st.session_state["stranka"] = pid
    st.session_state["vice_otevreno"] = False
    st.session_state.pop("upravuji", None)
    st.session_state.pop("mazu", None)


def _prepni_misto(klic):
    st.session_state["misto"] = klic
    st.query_params["misto"] = klic
    st.session_state["vice_otevreno"] = False
    for k in ["upravuji", "mazu", "pdf_data"]:
        st.session_state.pop(k, None)


if st.query_params.get("pwa") == "1":
    st.session_state["pwa"] = True
if st.session_state.get("pwa"):
    # v nainstalované appce je spodní okraj obrazovky o kousek níž (schovaná lišta Streamlit Cloudu)
    st.markdown("<style>:root { --lista-navic: 14px; }</style>", unsafe_allow_html=True)

with st.container(key="mobil_mista", horizontal=True):
    for klic, mm in MISTA.items():
        st.button(mm["nazev"], key=f"m_misto_{klic}", icon=mm["ikona"], on_click=_prepni_misto, args=(klic,),
                  type="primary" if klic == MISTO_KLIC else "secondary", disabled=klic == MISTO_KLIC, width="stretch")

VICE_STRANKY = [("platby", "💳", "Zálohy a platby"), ("spotrebice", "🔌", "Co kolik stojí"),
                ("nabidky", "💡", "Porovnat nabídky"), ("pdf", "📄", "Roční PDF"),
                ("historie", "📋", "Historie odečtů"), ("nastaveni", "⚙️", "Ceny a zálohy")]
if st.session_state.get("vice_otevreno"):
    with st.container(key="mobil_vice"):
        st.markdown('<div class="mv-titul">Další</div>', unsafe_allow_html=True)
        with st.container(key="mobil_vice_mrizka", horizontal=True):
            for pid, ik, nazev in VICE_STRANKY:
                st.button(nazev, key=f"m_vice_{pid}", icon=ik, on_click=_prejdi, args=(pid,),
                          type="primary" if STRANKA == pid else "secondary")
        if spravne_heslo() and st.button("Odhlásit", key="m_odhlasit", icon=":material/logout:", width="stretch"):
            for k in ["prihlasen", "misto", "stranka", "misto_ohlaseno"]:
                st.session_state.pop(k, None)
            st.session_state["odhlaseno"] = True
            st.query_params.clear()
            st.rerun()

with st.container(key="mobil_lista", horizontal=True):
    polozky_listy = [("prehled", "🏠", "Přehled")] + [(e, ENERGIE[e]["ikona"], ENERGIE[e]["nazev"]) for e in PORADI]
    for pid, ik, nazev in polozky_listy:
        st.button(nazev, key=f"m_lista_{pid}", icon=ik, on_click=_prejdi, args=(pid,),
                  type="primary" if STRANKA == pid and not st.session_state.get("vice_otevreno") else "secondary")
    vice_aktivni = st.session_state.get("vice_otevreno") or STRANKA in [p[0] for p in VICE_STRANKY]
    if st.button("Více", key="m_lista_vice", icon=":material/menu:", type="primary" if vice_aktivni else "secondary"):
        st.session_state["vice_otevreno"] = not st.session_state.get("vice_otevreno")
        st.rerun()


def nadpis(text, pod=None):
    st.markdown(f'<div class="stranka-nadpis">{text}</div>'
                + (f'<div class="stranka-pod">{pod}</div>' if pod else ""), unsafe_allow_html=True)


# ─────────────────────────────────────────────
# AKTUÁLNÍ POČASÍ PRO SCÉNU
# ─────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def aktualni_pocasi(lat, lon):
    try:
        url = ("https://api.open-meteo.com/v1/forecast?"
               f"latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,is_day&timezone=Europe%2FPrague")
        with urllib.request.urlopen(url, timeout=8) as r:
            c = json.loads(r.read().decode("utf-8"))["current"]
        return c["temperature_2m"], int(c["weather_code"]), int(c.get("is_day", 1))
    except Exception:
        return None


def ikona_pocasi(kod, den):
    if kod == 0:
        return "☀️" if den else "🌙"
    if kod in (1, 2, 3):
        return "⛅" if den else "☁️"
    if kod in (45, 48):
        return "🌫️"
    if 51 <= kod <= 67:
        return "🌧️"
    if 71 <= kod <= 77:
        return "❄️"
    if 80 <= kod <= 82:
        return "🌦️"
    return "⛈️" if kod >= 95 else "☁️"


def svg_obecny():
    """Obecný domek za soumraku (pro místa bez vlastní ilustrace)."""
    plyn_cara = ('<path class="sc-tok" d="M 820 205 C 840 180, 850 165, 870 150" stroke="#f97316"/>' if "plyn" in PORADI else "")
    return f"""<svg class="sc-svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="nebe" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0b1430"/><stop offset=".45" stop-color="#27325a"/>
    <stop offset=".72" stop-color="#7a4a6b"/><stop offset=".9" stop-color="#f08a4b"/><stop offset="1" stop-color="#f6b26b"/>
  </linearGradient>
  <linearGradient id="okno" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe2a3"/><stop offset="1" stop-color="#f59e0b"/></linearGradient>
  <linearGradient id="travnik" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1c3b2b"/><stop offset="1" stop-color="#0b1a14"/></linearGradient>
  <radialGradient id="zare" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffd27a" stop-opacity=".55"/><stop offset="1" stop-color="#ffd27a" stop-opacity="0"/></radialGradient>
  <linearGradient id="zed" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9e4dc"/><stop offset="1" stop-color="#b9b2a7"/></linearGradient>
</defs>
<rect width="1600" height="900" fill="url(#nebe)"/>
<g fill="#fff" opacity=".7"><circle cx="140" cy="80" r="1.6"/><circle cx="320" cy="140" r="1.2"/><circle cx="560" cy="60" r="1.4"/>
<circle cx="980" cy="90" r="1.3"/><circle cx="1220" cy="50" r="1.6"/><circle cx="1420" cy="120" r="1.1"/><circle cx="760" cy="130" r="1"/></g>
<circle cx="1330" cy="150" r="34" fill="#fde9c4" opacity=".9"/>
<path d="M0 560 C 200 500, 360 520, 520 540 S 900 500, 1100 530 S 1450 510, 1600 540 V 900 H 0 Z" fill="#1f2a44" opacity=".9"/>
<path d="M0 600 C 260 570, 520 590, 800 600 S 1300 580, 1600 600 V 900 H 0 Z" fill="url(#travnik)"/>
<!-- stromy -->
<g fill="#0e1b17"><ellipse cx="170" cy="470" rx="110" ry="150"/><rect x="160" y="560" width="18" height="80"/>
<ellipse cx="1470" cy="490" rx="90" ry="130"/><rect x="1462" y="570" width="16" height="70"/></g>
<!-- dům -->
<ellipse cx="800" cy="460" rx="430" ry="260" fill="url(#zare)"/>
<polygon points="470,330 800,160 1130,330" fill="#2b2f38"/>
<polygon points="490,330 800,175 1110,330" fill="#3a3f4b"/>
<rect x="840" y="150" width="46" height="110" fill="#4b4f5b"/><rect x="834" y="142" width="58" height="14" fill="#5a5f6b"/>
<rect x="505" y="330" width="590" height="290" fill="url(#zed)"/>
<rect x="505" y="330" width="590" height="16" fill="#00000022"/>
<rect x="545" y="380" width="200" height="200" rx="4" fill="url(#okno)"/>
<line x1="645" y1="380" x2="645" y2="580" stroke="#3a3f4b" stroke-width="6"/>
<rect x="790" y="380" width="120" height="110" rx="4" fill="url(#okno)"/>
<rect x="945" y="380" width="110" height="110" rx="4" fill="#ffd27a" opacity=".85"/>
<rect x="795" y="520" width="80" height="100" rx="3" fill="#3a3f4b"/><circle cx="862" cy="572" r="4" fill="#d4a24a"/>
<g fill="#2b2f38" opacity=".55"><rect x="560" y="470" width="40" height="70" rx="6"/><rect x="660" y="490" width="60" height="30" rx="6"/></g>
<!-- skříň elektroměru a plynoměru -->
<rect x="1110" y="470" width="70" height="95" rx="6" fill="#d8d3ca" stroke="#9a948a" stroke-width="3"/>
<rect x="1124" y="486" width="42" height="26" rx="3" fill="#1f2937"/><text x="1145" y="504" font-size="16" text-anchor="middle" fill="#facc15">⚡</text>
<rect x="1124" y="522" width="42" height="30" rx="3" fill="#f3efe8" stroke="#9a948a"/>
<!-- šachta vodoměru -->
<ellipse cx="640" cy="720" rx="54" ry="18" fill="#3d4654" stroke="#64748b" stroke-width="3"/>
<ellipse cx="640" cy="716" rx="36" ry="10" fill="#4b5563"/>
<!-- cesta a lampy -->
<path d="M835 620 L 760 900 L 980 900 L 880 620 Z" fill="#cfc6b6" opacity=".55"/>
<g><rect x="1000" y="650" width="8" height="60" fill="#111827"/><circle cx="1004" cy="646" r="10" fill="#ffd27a"/><circle cx="1004" cy="646" r="34" fill="url(#zare)"/>
<rect x="700" y="650" width="8" height="60" fill="#111827"/><circle cx="704" cy="646" r="10" fill="#ffd27a"/><circle cx="704" cy="646" r="34" fill="url(#zare)"/></g>
<!-- toky energie -->
<g fill="none" stroke-width="3" stroke-dasharray="2 10" stroke-linecap="round">
  {plyn_cara}
  <path class="sc-tok" d="M 1180 515 C 1230 500, 1260 480, 1290 455" stroke="#facc15"/>
  <path class="sc-tok" d="M 640 705 C 660 740, 680 770, 690 790" stroke="#38bdf8"/>
</g>
</svg>"""


def svg_strkov():
    """Ilustrace chalupy Strkov 9 (eternitová sedlová střecha, bílé zdi, dřevěný plot) za soumraku."""
    import random
    rnd = random.Random(9)
    skvrny = "".join(
        f'<polygon points="{x},{y - 9} {x + 9},{y} {x},{y + 9} {x - 9},{y}" fill="#b9bcb8" opacity="{rnd.uniform(.12, .3):.2f}"/>'
        for x, y in [(rnd.randint(640, 1380), rnd.randint(250, 440)) for _ in range(26)])
    latky = "".join(f'<rect x="{x}" y="664" width="13" height="{96 + (x % 3) * 4}" rx="2" fill="#5a3a2a"/>'
                    for x in range(0, 690, 22))
    latky += "".join(f'<rect x="{x}" y="664" width="13" height="{96 + (x % 3) * 4}" rx="2" fill="#5a3a2a"/>'
                     for x in range(912, 1190, 22))
    branka = "".join(f'<rect x="{x}" y="676" width="11" height="40" rx="2" fill="#6b4532"/>' for x in range(700, 900, 20))
    pletivo = "".join(f'<path d="M{x} 690 L{x + 30} 760 M{x + 30} 690 L{x} 760" stroke="#7d8a7c" stroke-width="1.2" opacity=".55"/>'
                      for x in range(1190, 1600, 30))
    return f"""<svg class="sc-svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="nebeS" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0d1734"/><stop offset=".42" stop-color="#2c3763"/>
    <stop offset=".66" stop-color="#8a5272"/><stop offset=".82" stop-color="#ee8c52"/><stop offset="1" stop-color="#f7c07a"/>
  </linearGradient>
  <linearGradient id="okenkoS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff0c2"/><stop offset="1" stop-color="#f4a43a"/></linearGradient>
  <linearGradient id="zedS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#eeeae3"/><stop offset="1" stop-color="#c9c4bb"/></linearGradient>
  <linearGradient id="stitS" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#cfd2d6"/><stop offset="1" stop-color="#e9e7e2"/></linearGradient>
  <radialGradient id="svitS" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffd27a" stop-opacity=".6"/><stop offset="1" stop-color="#ffd27a" stop-opacity="0"/></radialGradient>
  <pattern id="eternit" width="24" height="24" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="24" height="24" fill="#83878a"/><path d="M0 0 H24 M0 0 V24" stroke="#5f6366" stroke-width="2.2"/>
    <path d="M2 2 H22" stroke="#9a9ea1" stroke-width="1" opacity=".6"/>
  </pattern>
  <pattern id="trava" width="20" height="20" patternUnits="userSpaceOnUse"><rect width="20" height="20" fill="#2c4a2a"/>
    <path d="M3 20 L5 12 M10 20 L11 13 M16 20 L15 11" stroke="#3f6a37" stroke-width="2"/></pattern>
</defs>
<rect width="1600" height="900" fill="url(#nebeS)"/>
<g fill="#fff" opacity=".75"><circle cx="160" cy="70" r="1.6"/><circle cx="340" cy="130" r="1.2"/><circle cx="610" cy="60" r="1.4"/>
<circle cx="1000" cy="85" r="1.2"/><circle cx="1240" cy="45" r="1.6"/><circle cx="1500" cy="110" r="1.1"/></g>
<circle cx="1520" cy="105" r="30" fill="#fde9c4" opacity=".9"/>
<!-- elektrické vedení -->
<g stroke="#1f2533" stroke-width="2" fill="none" opacity=".8">
  <path d="M 1062 238 Q 1330 200, 1600 150"/><path d="M 1062 246 Q 1330 215, 1600 170"/>
  <path d="M 0 60 Q 400 130, 760 190"/>
</g>
<!-- sousední střechy -->
<polygon points="150,470 230,360 420,360 420,470" fill="#a0522d" opacity=".85"/>
<rect x="150" y="470" width="270" height="170" fill="#4a4652" opacity=".85"/>
<polygon points="1470,480 1520,390 1600,390 1600,480" fill="#a0522d" opacity=".85"/>
<rect x="1470" y="480" width="130" height="170" fill="#e2d6b8" opacity=".75"/>
<ellipse cx="900" cy="520" rx="640" ry="230" fill="url(#svitS)" opacity=".45"/>
<!-- štít -->
<polygon points="458,205 588,470 588,645 372,645 372,482" fill="url(#stitS)"/>
<rect x="420" y="320" width="30" height="52" fill="#2a2522"/><rect x="424" y="324" width="22" height="44" fill="url(#okenkoS)" opacity=".9"/>
<!-- přední zeď -->
<rect x="586" y="468" width="908" height="178" fill="url(#zedS)"/>
<!-- střecha eternit -->
<polygon points="458,198 1362,240 1502,470 588,470" fill="url(#eternit)"/>
{skvrny}
<polygon points="458,198 1362,240 1370,252 466,212" fill="#4b4f53"/>
<line x1="458" y1="198" x2="352" y2="486" stroke="#3b302a" stroke-width="10" stroke-linecap="round"/>
<line x1="1362" y1="240" x2="1502" y2="470" stroke="#3b302a" stroke-width="8" stroke-linecap="round"/>
<rect x="586" y="466" width="918" height="9" fill="#3d4044"/><rect x="586" y="475" width="908" height="7" fill="#000" opacity=".18"/>
<!-- anténa a střešník -->
<g stroke="#4b5563" stroke-width="3" fill="none"><line x1="760" y1="212" x2="760" y2="120"/>
<line x1="712" y1="128" x2="808" y2="128"/><line x1="722" y1="142" x2="798" y2="142"/><line x1="790" y1="118" x2="805" y2="104"/></g>
<line x1="1062" y1="388" x2="1056" y2="238" stroke="#7c4a2d" stroke-width="7"/>
<g fill="#d6d3cd"><rect x="1046" y="236" width="10" height="6" rx="2"/><rect x="1062" y="244" width="10" height="6" rx="2"/></g>
<!-- okna a dveře -->
<rect x="684" y="520" width="66" height="78" fill="#2a2522"/><rect x="690" y="526" width="54" height="66" fill="url(#okenkoS)"/>
<line x1="717" y1="526" x2="717" y2="592" stroke="#2a2522" stroke-width="3"/>
<rect x="872" y="504" width="50" height="142" fill="#4a2f22"/><rect x="878" y="512" width="38" height="56" fill="#f4c27a" opacity=".55"/>
<circle cx="900" cy="490" r="6" fill="#1c1c22"/><circle cx="900" cy="490" r="30" fill="url(#svitS)"/>
<rect x="1110" y="506" width="96" height="70" fill="#5a3b2a"/><rect x="1116" y="512" width="84" height="58" fill="url(#okenkoS)"/>
<line x1="1158" y1="512" x2="1158" y2="570" stroke="#5a3b2a" stroke-width="4"/><line x1="1116" y1="541" x2="1200" y2="541" stroke="#5a3b2a" stroke-width="3"/>
<rect x="1262" y="502" width="26" height="20" fill="#2a2522"/>
<rect x="1310" y="508" width="104" height="138" fill="#3a2a22"/>
<g stroke="#2a1d17" stroke-width="2">{''.join(f'<line x1="{x}" y1="508" x2="{x}" y2="646"/>' for x in range(1322, 1414, 13))}</g>
<!-- červený přístřešek vlevo -->
<polygon points="190,508 640,470 652,488 205,528" fill="#9a3a2a"/>
<polygon points="205,528 652,488 652,494 205,536" fill="#6e2a1f"/>
<g fill="#5a3a2a"><rect x="300" y="520" width="9" height="128"/><rect x="560" y="498" width="9" height="150"/></g>
<rect x="580" y="500" width="70" height="146" fill="#000" opacity=".18"/>
<!-- zeleň -->
<g><ellipse cx="230" cy="600" rx="90" ry="60" fill="#6b5a2a"/><ellipse cx="300" cy="610" rx="70" ry="45" fill="#8a6a2c"/>
<ellipse cx="190" cy="560" rx="60" ry="70" fill="#4d5a2a"/><ellipse cx="470" cy="640" rx="40" ry="26" fill="#3f6a37"/>
<ellipse cx="1520" cy="640" rx="60" ry="40" fill="#3f6a37"/></g>
<!-- tráva a plot -->
<rect x="0" y="640" width="1600" height="150" fill="url(#trava)"/>
{latky}
<rect x="0" y="684" width="690" height="6" fill="#4a2f22"/><rect x="0" y="736" width="690" height="6" fill="#4a2f22"/>
<rect x="912" y="684" width="278" height="6" fill="#4a2f22"/><rect x="912" y="736" width="278" height="6" fill="#4a2f22"/>
<rect x="690" y="656" width="12" height="114" fill="#3e281d"/><rect x="898" y="656" width="12" height="114" fill="#3e281d"/>
{branka}
<rect x="702" y="716" width="98" height="52" fill="#7a4a35" stroke="#5a3424" stroke-width="3"/>
<rect x="800" y="716" width="98" height="52" fill="#7a4a35" stroke="#5a3424" stroke-width="3"/>
<rect x="702" y="672" width="196" height="6" fill="#4a2f22"/>
<rect x="772" y="690" width="30" height="30" rx="4" fill="#3b3f46"/><rect x="777" y="698" width="20" height="4" fill="#111827"/>
<g stroke="#5b6b5a" stroke-width="5">{''.join(f'<line x1="{x}" y1="680" x2="{x}" y2="770"/>' for x in range(1190, 1600, 120))}</g>
<rect x="1190" y="688" width="410" height="74" fill="#6b7a6a" opacity=".12"/>{pletivo}
<line x1="1190" y1="688" x2="1600" y2="688" stroke="#7d8a7c" stroke-width="2"/>
<!-- cesta -->
<rect x="0" y="770" width="1600" height="26" fill="#3a5a33"/>
<rect x="0" y="796" width="1600" height="104" fill="#4b5058"/>
<rect x="0" y="796" width="1600" height="4" fill="#5f646c"/>
<ellipse cx="930" cy="842" rx="38" ry="10" fill="#3b4048" stroke="#94a3b8" stroke-width="2"/><ellipse cx="930" cy="840" rx="24" ry="5" fill="#64748b"/>
<!-- toky energie -->
<g fill="none" stroke-width="3" stroke-dasharray="2 10" stroke-linecap="round">
  <path class="sc-tok" d="M 1060 232 C 1080 190, 1095 160, 1100 130" stroke="#facc15"/>
  <path class="sc-tok" d="M 892 840 C 870 838, 860 832, 852 826" stroke="#38bdf8"/>
</g>
</svg>"""


def svg_pruhony():
    """Ilustrace domu V Průhonech 384 (bungalov s valbovou střechou, cihlový plot) za soumraku."""
    sloupky = [60, 460, 760, 1040, 1150, 1460]
    plot = []
    for a_, b_ in zip(sloupky, sloupky[1:]):
        if (a_, b_) == (1040, 1150):
            continue
        plot.append(f'<rect x="{a_ + 50}" y="672" width="{b_ - a_ - 50}" height="88" fill="url(#plot)"/>'
                    f'<rect x="{a_ + 50}" y="684" width="{b_ - a_ - 50}" height="5" fill="#3e281d"/>'
                    f'<rect x="{a_ + 50}" y="738" width="{b_ - a_ - 50}" height="5" fill="#3e281d"/>')
    plot.append('<rect x="0" y="672" width="60" height="88" fill="url(#plot)"/><rect x="1510" y="672" width="90" height="88" fill="url(#plot)"/>')
    pilire = "".join(
        f'<rect x="{x}" y="655" width="50" height="150" fill="url(#cihly)"/>'
        f'<rect x="{x - 5}" y="646" width="60" height="12" rx="2" fill="#c97a5c"/>'
        f'<rect x="{x}" y="658" width="50" height="147" fill="#000" opacity=".08"/>' for x in sloupky)
    return f"""<svg class="sc-svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="nebeP" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0d1734"/><stop offset=".42" stop-color="#2c3763"/>
    <stop offset=".66" stop-color="#8a5272"/><stop offset=".82" stop-color="#ee8c52"/><stop offset="1" stop-color="#f7c07a"/>
  </linearGradient>
  <linearGradient id="okenko" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff0c2"/><stop offset="1" stop-color="#f4a43a"/></linearGradient>
  <linearGradient id="zedP" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e2cba6"/><stop offset="1" stop-color="#b99a72"/></linearGradient>
  <linearGradient id="zedP2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cdb08a"/><stop offset="1" stop-color="#a5865f"/></linearGradient>
  <radialGradient id="svit" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffd27a" stop-opacity=".6"/><stop offset="1" stop-color="#ffd27a" stop-opacity="0"/></radialGradient>
  <pattern id="tasky" width="28" height="15" patternUnits="userSpaceOnUse">
    <rect width="28" height="15" fill="#2c2f37"/><path d="M0 14 H28" stroke="#1b1d23" stroke-width="2.4"/>
    <path d="M14 0 V14" stroke="#23262d" stroke-width="1.2"/><path d="M0 1.5 H28" stroke="#3a3e48" stroke-width="1"/>
  </pattern>
  <pattern id="cihly" width="40" height="16" patternUnits="userSpaceOnUse">
    <rect width="40" height="16" fill="#b8644a"/><path d="M0 15.5 H40 M20 0 V8 M0 8 H40 M10 8 V16 M30 8 V16" stroke="#9c4f39" stroke-width="1.2"/>
  </pattern>
  <pattern id="plot" width="24" height="88" patternUnits="userSpaceOnUse">
    <rect x="3" width="16" height="88" fill="#5c3b2b"/><rect x="3" width="3" height="88" fill="#6e4835"/>
  </pattern>
  <pattern id="dlazba" width="34" height="18" patternUnits="userSpaceOnUse">
    <rect width="34" height="18" fill="#3a3e46"/><path d="M0 17.5 H34 M17 0 V9 M0 9 H34 M8 9 V18" stroke="#2c2f36" stroke-width="1.4"/>
  </pattern>
</defs>
<rect width="1600" height="900" fill="url(#nebeP)"/>
<g fill="#fff" opacity=".75"><circle cx="160" cy="70" r="1.6"/><circle cx="340" cy="130" r="1.2"/><circle cx="600" cy="55" r="1.4"/>
<circle cx="1010" cy="80" r="1.2"/><circle cx="1240" cy="45" r="1.6"/><circle cx="1500" cy="110" r="1.1"/><circle cx="780" cy="120" r="1"/></g>
<circle cx="1360" cy="140" r="30" fill="#fde9c4" opacity=".9"/>
<!-- pozadí: soused a stromy -->
<polygon points="0,470 70,430 260,430 330,470" fill="#3b2f2f" opacity=".85"/><rect x="20" y="470" width="290" height="190" fill="#2a2a33" opacity=".85"/>
<rect x="60" y="500" width="40" height="40" fill="#f3b562" opacity=".7"/>
<g fill="#13211c"><ellipse cx="300" cy="560" rx="120" ry="120"/><ellipse cx="1560" cy="470" rx="90" ry="150"/><ellipse cx="1500" cy="520" rx="70" ry="90"/></g>
<ellipse cx="900" cy="520" rx="640" ry="230" fill="url(#svit)" opacity=".55"/>
<!-- hlavní část domu -->
<rect x="470" y="438" width="600" height="216" fill="url(#zedP)"/>
<rect x="476" y="438" width="6" height="216" fill="#7b7f86"/>
<!-- komín -->
<rect x="900" y="232" width="34" height="90" fill="url(#cihly)"/>
<rect x="895" y="222" width="44" height="12" fill="#8d9096"/><rect x="903" y="208" width="28" height="14" fill="#b6b9be"/>
<line x1="944" y1="214" x2="944" y2="250" stroke="#9aa0a8" stroke-width="2"/><circle cx="952" cy="232" r="8" fill="#c9cdd2"/>
<!-- střecha hlavní -->
<polygon points="420,422 680,288 935,288 1112,422" fill="url(#tasky)"/>
<polygon points="420,422 680,288 700,288 450,422" fill="#000" opacity=".18"/>
<line x1="680" y1="288" x2="935" y2="288" stroke="#1b1d23" stroke-width="6" stroke-linecap="round"/>
<line x1="680" y1="288" x2="420" y2="422" stroke="#1b1d23" stroke-width="5"/><line x1="935" y1="288" x2="1112" y2="422" stroke="#1b1d23" stroke-width="5"/>
<polygon points="845,302 878,302 882,312 841,312" fill="#aab3bf"/>
<g fill="#15171c">{''.join(f'<circle cx="{x}" cy="{330 + (abs(x - 808) // 25)}" r="2.6"/>' for x in range(600, 1020, 60))}</g>
<rect x="414" y="420" width="700" height="10" fill="#1d2027"/><rect x="430" y="430" width="672" height="10" fill="#efe4cf"/>
<!-- pravé křídlo -->
<rect x="1052" y="450" width="398" height="204" fill="url(#zedP2)"/>
<polygon points="1028,432 1138,300 1335,300 1498,432" fill="url(#tasky)"/>
<polygon points="1028,432 1138,300 1158,300 1058,432" fill="#000" opacity=".22"/>
<line x1="1138" y1="300" x2="1335" y2="300" stroke="#1b1d23" stroke-width="6" stroke-linecap="round"/>
<line x1="1138" y1="300" x2="1028" y2="432" stroke="#1b1d23" stroke-width="5"/><line x1="1335" y1="300" x2="1498" y2="432" stroke="#1b1d23" stroke-width="5"/>
<rect x="1022" y="430" width="482" height="10" fill="#1d2027"/><rect x="1040" y="440" width="448" height="10" fill="#e6d9c2"/>
<rect x="1262" y="482" width="82" height="76" fill="#2a211d"/><rect x="1268" y="488" width="70" height="64" fill="url(#okenko)"/>
<!-- okna a dveře -->
<g>
  <rect x="546" y="492" width="80" height="96" fill="#2a211d"/><rect x="553" y="499" width="66" height="82" fill="url(#okenko)"/>
  <line x1="586" y1="499" x2="586" y2="581" stroke="#2a211d" stroke-width="3"/>
  <rect x="553" y="499" width="66" height="30" fill="#fff" opacity=".18"/>
  <rect x="550" y="583" width="72" height="9" fill="#5a4636"/><g fill="#facc15"><circle cx="562" cy="582" r="4"/><circle cx="574" cy="580" r="4"/><circle cx="598" cy="582" r="4"/><circle cx="610" cy="580" r="4"/></g>
  <rect x="746" y="492" width="80" height="96" fill="#2a211d"/><rect x="753" y="499" width="66" height="82" fill="url(#okenko)"/>
  <line x1="786" y1="499" x2="786" y2="581" stroke="#2a211d" stroke-width="3"/>
  <rect x="753" y="499" width="66" height="30" fill="#fff" opacity=".18"/>
  <rect x="750" y="583" width="72" height="9" fill="#5a4636"/><g fill="#fb923c"><circle cx="766" cy="582" r="4"/><circle cx="780" cy="580" r="4"/><circle cx="794" cy="582" r="4"/></g>
  <rect x="938" y="492" width="70" height="162" fill="#2a1e19"/><rect x="944" y="498" width="58" height="156" fill="#3a2a23"/>
  <rect x="970" y="510" width="8" height="96" fill="#efe1c6" opacity=".85"/>
  <polygon points="952,572 994,548 994,560 952,584" fill="#efe1c6" opacity=".85"/>
  <rect x="950" y="574" width="6" height="16" rx="2" fill="#d4a24a"/>
  <circle cx="912" cy="470" r="7" fill="#1c1c22"/><circle cx="912" cy="470" r="34" fill="url(#svit)"/>
</g>
<!-- keře podzimní barvy -->
<g>
  <ellipse cx="1150" cy="560" rx="80" ry="78" fill="#7c9a2b"/><ellipse cx="1205" cy="540" rx="70" ry="88" fill="#d9752b"/>
  <ellipse cx="1255" cy="590" rx="80" ry="64" fill="#c2410c"/><ellipse cx="1110" cy="610" rx="60" ry="46" fill="#a3b236"/>
  <ellipse cx="1380" cy="585" rx="90" ry="70" fill="#e0662f"/><ellipse cx="1450" cy="560" rx="60" ry="80" fill="#b5401b"/>
  <ellipse cx="1220" cy="500" rx="30" ry="40" fill="#f59e0b" opacity=".8"/>
  <ellipse cx="1300" cy="560" rx="60" ry="50" fill="#ea8a34" opacity=".9"/>
</g>
<!-- plot -->
{''.join(plot)}
<rect x="1094" y="664" width="52" height="128" fill="#4a2f22"/><rect x="1094" y="664" width="52" height="128" fill="url(#plot)"/>
<rect x="0" y="758" width="1600" height="48" fill="url(#cihly)"/><rect x="0" y="752" width="1600" height="9" fill="#c97a5c"/>
<rect x="1094" y="752" width="52" height="54" fill="#4a2f22"/>
{pilire}
<text x="1175" y="690" font-size="20" font-weight="700" fill="#f1f5f9" text-anchor="middle" font-family="Inter, sans-serif">384</text>
<rect x="1158" y="702" width="34" height="34" rx="3" fill="#475569"/><rect x="1162" y="708" width="26" height="4" fill="#1e293b"/>
<rect x="1464" y="688" width="42" height="54" rx="3" fill="#d6d3cd" stroke="#8a8378" stroke-width="2"/>
<rect x="1471" y="696" width="28" height="18" rx="2" fill="#1f2937"/><text x="1485" y="710" font-size="13" text-anchor="middle" fill="#facc15">⚡</text>
<circle cx="1065" cy="640" r="6" fill="#ffe6a8"/><circle cx="1065" cy="640" r="36" fill="url(#svit)"/>
<circle cx="1175" cy="640" r="6" fill="#ffe6a8"/><circle cx="1175" cy="640" r="36" fill="url(#svit)"/>
<!-- štěrk a dlažba -->
<rect x="0" y="806" width="1600" height="30" fill="#8f8b84"/>
<g fill="#bdb8ae">{''.join(f'<circle cx="{(i * 37) % 1600}" cy="{812 + (i * 13) % 20}" r="3"/>' for i in range(90))}</g>
<rect x="1090" y="806" width="62" height="30" fill="#a8704f"/>
<rect x="0" y="836" width="1600" height="64" fill="url(#dlazba)"/>
<ellipse cx="1250" cy="868" rx="38" ry="10" fill="#4b5563" stroke="#94a3b8" stroke-width="2"/>
<ellipse cx="1250" cy="866" rx="24" ry="5" fill="#64748b"/>
<!-- toky energie -->
<g fill="none" stroke-width="3" stroke-dasharray="2 10" stroke-linecap="round">
  <path class="sc-tok" d="M 922 205 C 945 185, 975 175, 1005 168" stroke="#f97316"/>
  <path class="sc-tok" d="M 1485 686 C 1480 655, 1470 630, 1455 606" stroke="#facc15"/>
  <path class="sc-tok" d="M 1212 866 C 1100 880, 960 870, 860 830" stroke="#38bdf8"/>
</g>
</svg>"""


def scena_domu():
    """Ilustrace domu za soumraku s plovoucími kartami energií (ve stylu „Power Empire“)."""
    from zoneinfo import ZoneInfo
    ted = datetime.now(ZoneInfo("Europe/Prague"))
    dny_tydne = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
    poc = aktualni_pocasi(LAT, LON)
    poc_html = (f'<div class="sc-teplota">{ikona_pocasi(poc[1], poc[2])} {cislo(poc[0], 1)} °C</div>' if poc else "")

    karty, souhrn, celkem_den = [], [], 0.0
    pozice = {"plyn": ("sc-plyn", "#f97316"), "elektrina": ("sc-elektrina", "#facc15"), "voda": ("sc-voda", "#38bdf8")}
    for e in PORADI:
        v = vysledky.get(e)
        inf = ENERGIE[e]
        cls, barva = pozice[e]
        t = tarif_podle.get(e)
        if v and v["tempo"] is not None:
            kc_den = v["tempo"] * v["cena_jednotky"] + float(t["mesicni_platy"]) / 30.4
            celkem_den += kc_den
            txt, bz, _ = stav_zalohy(v)
            stav = {"Optimální": "záloha sedí", "Málo": "záloha malá", "Moc": "záloha velká"}.get(txt, "")
            hodnota = f"{cislo(v['tempo'], 2)} {inf['jednotka']}/den"
            pod = f"≈ {kc(kc_den)} / den"
            souhrn.append(f'<div class="sc-r"><span>{inf["ikona"]} {inf["nazev"]}</span><b>{hodnota}</b></div>'
                          f'<div class="sc-r sc-r2"><span>náklad</span><b>{kc(kc_den)} / den</b></div>')
        else:
            bz, stav, hodnota, pod = BARVA_PLAN, "", "–", "doplň aktuální stav"
        if v:
            bd = v["bilance_dosud"]
            dnes_html = (f'<div class="sc-dnes"><div class="sc-dnes-l">Kdyby vyúčtování bylo dnes</div>'
                         f'<div class="sc-dnes-v" style="color:{BARVA_OK if bd >= 0 else BARVA_ZLE}">{kc_znamenko(bd)}'
                         f' <span>{"přeplatek" if bd >= 0 else "nedoplatek"}</span></div>'
                         f'<div class="sc-r sc-r2"><span>spotřebováno</span><b>{kc(v["naklad_dosud"])}</b></div>'
                         f'<div class="sc-r sc-r2"><span>zaplaceno</span><b>{kc(v["zaplaceno_dosud"])}</b></div>'
                         f'<div class="sc-dnes-p">podle stavu z {datum_cz(v["posledni_datum"])}</div></div>')
        else:
            dnes_html = ""
        zaklad = (f'<div class="sc-hlava">{inf["ikona"]} {inf["nazev"]}<span class="sc-detail">detail ›</span></div>'
                  f'<div class="sc-hodnota">{hodnota}</div>'
                  f'<div class="sc-pod">{pod}' + (f' · <span style="color:{bz}">●</span> {stav}' if stav else '') + '</div>')
        # počítač: rozbalení najetím myší · telefon: rozbalení klepnutím (<details>)
        mobil = (f'<details class="sc-karta sc-energie sc-mobil" style="--acc:{barva}"><summary>{zaklad}'
                 + ('<div class="sc-klepni">Klepni pro vyúčtování dnes <span>▾</span></div>' if dnes_html else '')
                 + f'</summary>{dnes_html.replace("sc-dnes", "sc-dnes sc-dnes-m", 1)}</details>')
        karty.append((e, f'<div class="sc-karta sc-energie sc-pc" style="--acc:{barva}">{zaklad}{dnes_html}</div>' + mobil))

    svg = {"pruhony": svg_pruhony, "strkov": svg_strkov}.get(MISTO_KLIC, svg_obecny)()
    souhrn_html = "".join(souhrn) or '<div class="sc-r"><span>Zatím málo odečtů</span></div>'
    html = f"""
<div class="scena scena-{MISTO_KLIC}">
  {svg}
  <div class="sc-karta sc-pocasi">
    <div class="sc-hlava">{dny_tydne[ted.weekday()]} {datum_cz(ted.date())} · {ted.strftime('%H:%M')}</div>
    {poc_html}
    <div class="sc-pod">{MISTO['obec']}</div>
  </div>
  <div class="sc-karta sc-souhrn">
    <div class="sc-hlava">Denní tempo</div>
    {souhrn_html}
    <div class="sc-r sc-celkem"><span>Celkem</span><b>≈ {kc(celkem_den)} / den</b></div>
    <div class="sc-r sc-r2"><span>měsíčně</span><b>≈ {kc(celkem_den * 30.4)}</b></div>
  </div>
</div>"""
    return "".join(radek.strip() for radek in html.splitlines()), karty


platby_html = []
for e in PORADI:
    v = vysledky.get(e)
    t = tarif_podle.get(e)
    if t is None:
        continue
    if not v:
        txt, barva, stav_txt = "", BARVA_PLAN, "doplň aktuální stav"
    else:
        txt, barva, _ = stav_zalohy(v)
        if txt == "Optimální":
            stav_txt = "záloha sedí"
        elif txt == "Málo":
            stav_txt = f"zvednout na {kc(v['doporucena'])}"
        else:
            stav_txt = f"snížit na {kc(v['doporucena'])}"
    platby_html.append(f"""
    <div class="platba" style="--acc:{ENERGIE[e]['barva']}">
      <div class="p-hlava">{ENERGIE[e]['ikona']} {ENERGIE[e]['nazev']}</div>
      <div class="p-castka">{kc(float(t['zaloha']))}<span> / měs.</span></div>
      <div class="p-stav"><span class="dot" style="background:{barva}"></span>{stav_txt}</div>
      <div class="p-udaje">
        <span>Účet</span><b>{t['ucet'] or '–'}</b>
        <span>VS</span><b>{t['vs'] or '–'}</b>
        <span>Splatnost</span><b>{int(t['den_splatnosti'])}. v měsíci</b>
      </div>
    </div>""")

if STRANKA == "prehled":
  st.markdown(f"""
<div class="hero">
  <h1>{MISTO['ikona']} {MISTO['nazev']}</h1>
  <div class="sub">{MISTO['obec']} · {MISTO['popis']} · aktualizováno {datum_cz(max(v['posledni_datum'] for v in platne)) if platne else '–'}</div>
  <div class="hero-grid">
    <div class="hero-kpi"><div class="l">Zálohy teď</div><div class="v">{kc(zalohy_ted)}</div><div class="s">měsíčně celkem</div></div>
    <div class="hero-kpi"><div class="l">Zálohy na nulu</div><div class="v">{kc(zalohy_nulu)}</div><div class="s">rozdíl {kc_znamenko(zalohy_nulu - zalohy_ted)}</div></div>
    <div class="hero-kpi"><div class="l">Odhad vyúčtování</div><div class="v" style="color:{barva_bil}">{kc_znamenko(bilance_celkem)}</div><div class="s">≈ {kc(mesicne_celkem)} měsíčně skutečně</div></div>
  </div>
</div>
""", unsafe_allow_html=True)
  scena_html, karty_energii = scena_domu()
  with st.container(key="scena_obal"):
      st.markdown(scena_html, unsafe_allow_html=True)
      for e_, karta_html in karty_energii:
          with st.container(key=f"karta_{MISTO_KLIC}_{e_}"):
              st.markdown(karta_html, unsafe_allow_html=True)
              if st.button("Otevřít", key=f"skok_{e_}"):
                  st.session_state["stranka"] = e_
                  st.rerun()

if STRANKA == "platby":
    nadpis("💳 Zálohy a platby", f"{MISTO['nazev']} · měsíční zálohy, účty a QR platby")
    st.markdown(f'<div class="platby platby-velke">{"".join(platby_html)}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sekce">Zaplatit zálohu – QR kód</div>', unsafe_allow_html=True)
    qr_zal = st.tabs([f"{ENERGIE[e]['ikona']} {ENERGIE[e]['nazev']}" for e in PORADI])
    for e, tab in zip(PORADI, qr_zal):
        with tab:
            t = tarif_podle.get(e)
            if t is None or not t["ucet"]:
                st.caption("Platební údaje zatím chybí – doplň je v ⚙️ Ceny a zálohy.")
                continue
            castka = st.number_input("Částka (Kč)", value=float(t["zaloha"]), step=10.0, format="%.0f", key=f"qr_c_{e}")
            c1, c2 = st.columns([1, 1])
            with c1:
                png = qr_platba(t["ucet"], castka, t["vs"], f"Zaloha {ENERGIE[e]['nazev']}")
                if png:
                    st.image(png, width=220)
                    st.caption("Naskenuj v bankovní aplikaci (QR platba).")
                else:
                    st.caption("QR kód nejde vytvořit – zkontroluj číslo účtu v ⚙️ Ceny a zálohy.")
            with c2:
                st.caption("Účet")
                st.code(t["ucet"], language=None)
                st.caption("Variabilní symbol")
                st.code(t["vs"], language=None)
                st.caption(f"Splatnost {int(t['den_splatnosti'])}. v měsíci · {t['dodavatel']}")
            st.caption("Platíš-li trvalým příkazem, po změně zálohy uprav i jeho výši v bance.")

if "ulozeno" in st.session_state:
    st.success(st.session_state.pop("ulozeno"))

for e in (PORADI if STRANKA == "prehled" else []):
    t = tarif_podle.get(e)
    if t is None or not t["konec_smlouvy"]:
        continue
    konec_d = pd.to_datetime(t["konec_smlouvy"]).date()
    zbyva_dni = (konec_d - dnes).days
    if zbyva_dni <= 90:
        if zbyva_dni >= 0:
            kdy = f"za **{zbyva_dni} dní** ({datum_cz(konec_d)})"
        else:
            kdy = f"**{datum_cz(konec_d)}** (před {-zbyva_dni} dny)"
        st.markdown(f"""
<div class="smlouva" style="--acc:{ENERGIE[e]['barva']}">
  <div><b>{ENERGIE[e]['ikona']} {ENERGIE[e]['nazev']}: {t['konec_popis'] or 'konec smlouvy'} {kdy.replace('**', '')}</b></div>
  <div>{t['dodavatel']} · Mrkni na nabídky a porovnej je v menu Nástroje → Porovnat nabídky –
  při automatickém prodloužení zůstaneš na ceníku, který nemusí být výhodný.</div>
</div>""", unsafe_allow_html=True)

PRAHY_ANOMALIE = {"voda": 1.2, "elektrina": 1.25, "plyn": 1.3}
for e in (PORADI if STRANKA == "prehled" else []):
    an = anomalie(odecty, e)
    if not an:
        continue
    pomer, ted_d, lon_d = an
    inf = ENERGIE[e]
    if pomer >= PRAHY_ANOMALIE[e]:
        rada_tip = {
            "voda": "Zkontroluj splachovadla, kohoutky a průtok na vodoměru při zavřené vodě.",
            "elektrina": "Mrkni na nové spotřebiče, ohřev vody nebo něco, co zůstává zapnuté.",
            "plyn": "Část může jít na vrub počasí – zkontroluj nastavení termostatu a kotle. Cítíš-li plyn, volej 1239.",
        }[e]
        st.warning(f"{inf['ikona']} **{inf['nazev']}:** od posledního odečtu {cislo(ted_d, 2)} {inf['jednotka']}/den, "
                   f"loni ve stejném období {cislo(lon_d, 2)} – to je **{(pomer - 1) * 100:+.0f} %**. {rada_tip}")

def dvoutarif(e):
    t = tarif_podle.get(e)
    return t is not None and float(t["cena_nt_kwh"] or 0) > 0


def formular_stavu(e, v):
    info = ENERGIE[e]
    rs_all = platne_odecty(odecty, e)
    posl = rs_all.iloc[-1] if not rs_all.empty else None
    dvou = dvoutarif(e)
    with st.form(f"novy_{e}", clear_on_submit=True):
        st.markdown(f"**📝 Nový stav – {info['nazev'].lower()}**")
        if dvou:
            c1, c2, c3 = st.columns([2, 2, 2])
            vt = c1.number_input("VT – vysoký tarif (kWh)", min_value=0.0, value=None, step=0.1, format="%.1f",
                                 placeholder="T1", key=f"vt_{e}")
            nt = c2.number_input("NT – nízký tarif (kWh)", min_value=0.0, value=None, step=0.1, format="%.1f",
                                 placeholder="T2", key=f"nt_{e}")
            dat = c3.date_input("Datum", value=dnes, format="DD.MM.YYYY", key=f"dat_{e}")
            stav = (vt + nt) if vt is not None and nt is not None else None
        else:
            c1, c2 = st.columns([3, 2])
            stav = c1.number_input(f"Stav ({info['jednotka']})", min_value=0.0, value=None,
                                   step=0.1 if e == "elektrina" else 0.001,
                                   format="%.1f" if e == "elektrina" else "%.3f",
                                   placeholder="Opiš číslo z měřidla", key=f"stav_{e}")
            dat = c2.date_input("Datum", value=dnes, format="DD.MM.YYYY", key=f"dat_{e}")
            nt = None
        pozn = st.text_input("Poznámka (nepovinné)", placeholder="např. po dovolené", key=f"pozn_{e}")
        odeslat = st.form_submit_button("Uložit stav", type="primary", width="stretch")
    if not odeslat:
        return
    if stav is None:
        st.error("Zadej VT i NT." if dvou else "Zadej stav měřidla.")
        return
    if posl is not None and dat >= posl["datum"] and stav < posl["stav"]:
        st.error(f"Stav je nižší než poslední ({cislo(posl['stav'], info['desetiny'])}). Zkontroluj číslo.")
        return
    novy = pd.DataFrame([{"id": nove_id(), "datum": dat.isoformat(), "energie": e,
                          "stav": stav, "typ": "vlastní",
                          "poznamka": (f"VT {cislo(stav - nt, 1)} + NT {cislo(nt, 1)}" + (f" · {pozn}" if pozn else ""))
                          if dvou else pozn,
                          "meridlo": posledni_meridlo(odecty, e), "stav_nt": nt}])
    ven = pd.concat([odecty.assign(datum=odecty["datum"].astype(str)), novy], ignore_index=True)
    ul.uloz(L_ODECTY, ven[SLOUPCE_ODECTY])
    zprava = f"Uloženo: {info['nazev']} {cislo(stav, info['desetiny'])} {info['jednotka']}"
    if posl is not None and dat > posl["datum"]:
        rozdil = stav - posl["stav"]
        dni = (dat - posl["datum"]).days
        t_ = tarif_podle[e]
        if dvou and pd.notna(posl["stav_nt"]):
            d_nt = nt - posl["stav_nt"]
            cena_od_minule = (rozdil - d_nt) * float(t_["cena_za_kwh"]) + d_nt * float(t_["cena_nt_kwh"])
        else:
            cena_j = v["cena_jednotky"] if v else float(t_["cena_za_kwh"]) * float(t_["kwh_na_jednotku"])
            cena_od_minule = rozdil * cena_j
        zprava += (f" · od minule +{cislo(rozdil, info['desetiny'])} {info['jednotka']} za {dni} dní"
                   f" ≈ {kc(cena_od_minule)}")
    st.session_state["ulozeno"] = zprava
    st.rerun()


# ─────────────────────────────────────────────
# ZÁLOŽKY PO ENERGIÍCH
# ─────────────────────────────────────────────
if STRANKA in PORADI:
    nadpis(f"{ENERGIE[STRANKA]['ikona']} {ENERGIE[STRANKA]['nazev']}",
           f"{MISTO['nazev']} · {tarif_podle[STRANKA]['dodavatel'] if STRANKA in tarif_podle else ''}")
for e in [x for x in PORADI if x == STRANKA]:
    if True:
        v = vysledky.get(e)
        info = ENERGIE[e]
        acc = info["barva"]
        if not v:
            st.info(DUVOD.get(e, "Zatím žádná data."))
            formular_stavu(e, None)
            continue

        # Barometry
        txt, barva, pomer = stav_zalohy(v)
        pomer_plan = v["pouzito"] / v["plan"] * 100 if v["plan"] > 0 else 100
        if pomer_plan < 95:
            t2, b2 = "Pod plánem", BARVA_OK
        elif pomer_plan <= 115:
            t2, b2 = "Na plánu", BARVA_VAROVANI if pomer_plan > 105 else BARVA_OK
        else:
            t2, b2 = "Nad plánem", BARVA_ZLE
        dop_txt = kc(v["doporucena"]) if v["doporucena"] is not None else "–"
        g_zal = svg_budik(pomer, ZONY_ZALOHA, barva, kc(v["zaloha"]), f"potřeba {dop_txt}", ("Málo", "Moc"))
        odch = round(pomer_plan - 100)
        g_plan = svg_budik(pomer_plan, ZONY_PLAN, b2, f"{odch:+d} %" if odch else "0 %",
                           f"{cislo(v['pouzito'], 1)} / {cislo(v['plan'], 1)} {info['jednotka']}", ("Pod", "Nad"))
        st.markdown(f"""
<div class="budiky">
  <div class="budik"><div class="b-titul">Nastavení zálohy</div>{g_zal}
    <div class="b-stitek" style="color:{barva};background:{barva}1f;border-color:{barva}55">{txt}</div></div>
  <div class="budik"><div class="b-titul">Spotřeba vs plán</div>{g_plan}
    <div class="b-stitek" style="color:{b2};background:{b2}1f;border-color:{b2}55">{t2}</div></div>
</div>
""", unsafe_allow_html=True)

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

        formular_stavu(e, v)

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
                    f'plán {cislo(v["plan"], 1)} {info["jednotka"]}. Plán = roční odhad rozložený podle typického průběhu roku.'
                    + (f' Stav na začátku období ({cislo(v["stav_od"], 0)}) je dopočítaný z odečtů okolo.' if v["stav_od_odhad"] else '')
                    + (f' Cena je průměr VT/NT podle tvé spotřeby (NT {v["podil_nt"] * 100:.0f} %).' if v["podil_nt"] is not None else '')
                    + '</div>',
                    unsafe_allow_html=True)

        # Srovnání let
        st.markdown('<div class="sekce">Srovnání let</div>', unsafe_allow_html=True)
        rada = denni_rada(odecty, e)
        if rada.empty:
            st.caption("Zatím málo odečtů pro srovnání.")
        else:
            df_r = rada.rename("hodnota").to_frame()
            df_r["rok"] = [d.year for d in df_r.index]
            df_r["mesic"] = [d.month for d in df_r.index]
            mes = df_r.groupby(["rok", "mesic"])["hodnota"].agg(["mean", "count"]).reset_index()
            mes = mes[mes["count"] >= 10]
            roky = sorted(mes["rok"].unique())
            nazvy_m = ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"]
            fig2 = go.Figure()
            for j, rok in enumerate(roky):
                d = mes[mes["rok"] == rok]
                posledni = rok == roky[-1]
                fig2.add_trace(go.Scatter(
                    x=[nazvy_m[m - 1] for m in d["mesic"]], y=d["mean"], name=str(rok), mode="lines+markers",
                    line=dict(color=acc if posledni else None, width=3 if posledni else 2),
                    opacity=1 if posledni else 0.55,
                    hovertemplate=f"{rok} · " + "%{x}<br>%{y:.2f} " + info["jednotka"] + "/den<extra></extra>"))
            fig2.update_layout(height=260, margin=dict(l=6, r=6, t=6, b=6),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font=dict(color="#cbd5e1", family="Inter"),
                               legend=dict(orientation="h", y=1.12, x=0),
                               xaxis=dict(showgrid=False, categoryorder="array", categoryarray=nazvy_m),
                               yaxis=dict(gridcolor="rgba(148,163,184,.12)", zeroline=False,
                                          title=dict(text=f"{info['jednotka']}/den", font=dict(size=11))))
            st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False}, key=f"roky_{e}")

            rocni = df_r.groupby("rok")["hodnota"].agg(["sum", "count", "mean"]).reset_index()
            radky = []
            for _, r in rocni.iterrows():
                cely = r["count"] >= 360
                radky.append({
                    "Rok": str(int(r["rok"])) + ("" if cely else " *"),
                    "Spotřeba": f"{cislo(r['sum'], 0)} {info['jednotka']}",
                    "Průměr/den": f"{cislo(r['mean'], 2)}",
                    "Náklad (dnešní ceny)": kc(r["sum"] * v["cena_jednotky"]),
                    "Změna": "",
                })
            for k in range(1, len(radky)):
                pred, ted = rocni.iloc[k - 1]["mean"], rocni.iloc[k]["mean"]
                if pred > 0:
                    radky[k]["Změna"] = f"{(ted / pred - 1) * 100:+.0f} %"
            st.dataframe(pd.DataFrame(radky), hide_index=True, width="stretch")
            st.caption("* neúplný rok (data jen za část roku). Změna = průměr na den proti předchozímu roku. "
                       "Mezi odečty je spotřeba rozpočítaná podle typického průběhu roku.")

        if e == "plyn":
            st.markdown('<div class="sekce">Počasí, topení a teplá voda</div>', unsafe_allow_html=True)
            prvni = platne_odecty(odecty, "plyn")["datum"].min()
            teploty = nacti_teploty((prvni - timedelta(days=1)).isoformat(), dnes.isoformat())
            an = analyza_plynu(odecty, teploty)
            if not an:
                st.caption("Teploty se nepodařilo načíst nebo je zatím málo odečtů. Zkus to později.")
            else:
                cena_m3 = v["cena_jednotky"]
                konec = v["posledni_datum"]
                (dd_ted, ef_ted), (dd_pred, ef_pred) = srovnani_pocasi(an, teploty, konec)
                voda_rok = an["zaklad"] * 365
                rada_p = denni_rada(odecty, "plyn")
                skut_rok = rada_p[(rada_p.index >= konec - timedelta(days=365)) & (rada_p.index < konec)].sum()
                top_rok = max(0.0, skut_rok - voda_rok)
                celkem = voda_rok + top_rok
                podil_top = top_rok / celkem * 100 if celkem > 0 else 0

                vety = []
                if dd_pred > 0:
                    zm_pocasi = (dd_ted / dd_pred - 1) * 100
                    vety.append(f"Posledních 12 měsíců bylo **{abs(zm_pocasi):.0f} % {'chladněji' if zm_pocasi > 0 else 'tepleji'}** "
                                f"než rok předtím ({cislo(dd_ted, 0)} vs {cislo(dd_pred, 0)} denostupňů).")
                if ef_ted and ef_pred:
                    zm_ef = (ef_ted / ef_pred - 1) * 100
                    if abs(zm_ef) < 7:
                        vety.append("Na stejné počasí topíš **zhruba stejně** jako loni – rozdíl ve spotřebě dělá hlavně počasí.")
                    else:
                        vety.append(f"Na stejné počasí topíš o **{abs(zm_ef):.0f} % {'víc' if zm_ef > 0 else 'míň'}** než loni"
                                    f"{' – to už počasím nevysvětlíš, mrkni na termostat a kotel.' if zm_ef > 0 else '.'}")
                if vety:
                    st.markdown(" ".join(vety))

                c1, c2 = st.columns([1, 1])
                with c1:
                    pie = go.Figure(go.Pie(
                        labels=["Topení", "Teplá voda a vaření"], values=[top_rok, voda_rok], hole=.62, sort=False,
                        marker=dict(colors=[ENERGIE["plyn"]["barva"], BARVA_MOC], line=dict(color="#0b1220", width=3)),
                        textinfo="none",
                        hovertemplate="%{label}<br>%{value:.0f} m³ (%{percent})<extra></extra>"))
                    pie.add_annotation(text=f"<b>{podil_top:.0f} %</b><br><span style='font-size:11px'>topení</span>",
                                       showarrow=False, font=dict(size=20, color="#f8fafc"))
                    pie.update_layout(height=220, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"))
                    st.plotly_chart(pie, width="stretch", config={"displayModeBar": False}, key="kolac_plyn")
                with c2:
                    st.markdown(f"""
<div class="radky-mini">
  <div><span class="dot" style="background:{ENERGIE['plyn']['barva']}"></span> Topení</div>
  <b>{cislo(top_rok, 0)} m³ · {kc(top_rok * cena_m3)}</b>
  <div><span class="dot" style="background:{BARVA_MOC}"></span> Teplá voda a vaření</div>
  <b>{cislo(voda_rok, 0)} m³ · {kc(voda_rok * cena_m3)}</b>
  <div class="mini-pozn">Za posledních 12 měsíců, bez stálých plateb. Teplá voda ≈ {cislo(an['zaklad'], 2)} m³/den
  ≈ {kc(an['zaklad'] * 365 / 12 * cena_m3)} měsíčně. Topení ≈ {cislo(an['k'], 3)} m³ na denostupeň.</div>
</div>""", unsafe_allow_html=True)

                radky = []
                for u in an["useky"]:
                    radky.append({
                        "Období": f"{u['od'].strftime('%d.%m.%y')}–{u['do'].strftime('%d.%m.%y')}",
                        "Spotřeba": f"{cislo(u['m3'], 0)} m³",
                        "Topení": f"{cislo(u['topeni'], 0)} m³",
                        "Denostupně": cislo(u["dd"], 0),
                        "m³/denostupeň": cislo(u["na_dd"], 3) if u["na_dd"] else "–",
                    })
                st.dataframe(pd.DataFrame(radky[::-1]), hide_index=True, width="stretch")
                st.caption("Denostupně = součet (19 °C − venkovní teplota) za dny, kdy je venku 13 °C a méně – měřítko, jak "
                           "studené období bylo. Teploty pro Nasavrky z Open-Meteo. „m³/denostupeň“ ukazuje, kolik plynu stojí "
                           "topení při stejném počasí – když roste, topíš víc nebo hůř (termostat, kotel), ne kvůli zimě.")

# ─────────────────────────────────────────────
# HISTORIE ODEČTŮ – úprava a mazání s potvrzením
# ─────────────────────────────────────────────
if STRANKA == "spotrebice":
    nadpis("🔌 Co kolik stojí", "Spotřebiče, svícení a vlastní kalkulace podle tvých cen")
    t_el, t_pl, t_vo = tarif_podle.get("elektrina"), tarif_podle.get("plyn"), tarif_podle.get("voda")
    c_kwh = float(t_el["cena_za_kwh"]) if t_el is not None else 0
    c_nt = float(t_el["cena_nt_kwh"]) if t_el is not None and float(t_el["cena_nt_kwh"]) > 0 else c_kwh
    c_plyn = float(t_pl["cena_za_kwh"]) if t_pl is not None else 0
    c_voda = float(t_vo["cena_za_kwh"]) if t_vo is not None else 0
    if t_pl is not None:
        c_ohrev, ucin, ohrev_txt = c_plyn, 0.9, "teplá voda ohřátá plynovým kotlem o 30 °C"
    else:
        c_ohrev, ucin, ohrev_txt = c_nt, 0.95, ("teplá voda z elektrického bojleru v nízkém tarifu (NT)"
                                                 if c_nt != c_kwh else "teplá voda z elektrického bojleru")
    st.caption(f"Podle cen s DPH: elektřina {cislo(c_kwh, 2)} Kč/kWh"
               + (f" (NT {cislo(c_nt, 2)})" if c_nt != c_kwh else "")
               + (f", plyn {cislo(c_plyn, 2)} Kč/kWh" if t_pl is not None else "")
               + (f", voda {cislo(c_voda / 1000, 3)} Kč/litr" if c_voda else "")
               + ". Jen proměnná část – stálé platby zaplatíš tak jako tak.")

    def ohrev_plynem(litry, delta=30, ucinnost=None):
        return litry * 4.186 * delta / 3600 / (ucinnost or ucin)  # kWh energie na ohřev

    polozky = [
        ("🛁", "Vana teplé vody (150 l)", ohrev_plynem(150) * c_ohrev + 0.150 * c_voda),
        ("🚿", "Sprcha 5 min (50 l)", ohrev_plynem(50) * c_ohrev + 0.050 * c_voda),
        ("👕", "Praní 40 °C", 0.8 * c_kwh + 0.050 * c_voda),
        ("🌀", "Sušička – jedna dávka", 2.5 * c_kwh),
        ("🍽️", "Myčka – jeden cyklus", 1.0 * c_kwh + 0.012 * c_voda),
        ("🍕", "Trouba 1 hodina", 1.2 * c_kwh),
        ("☕", "Varná konvice 1 l", 0.11 * c_kwh),
        ("🔥", "Přímotop 2 kW – 1 hodina", 2.0 * c_kwh),
        ("💻", "Pracovní den u PC (notebook + monitor, 8 h)", 0.6 * c_kwh),
        ("📺", "Televize večer (3 h)", 0.3 * c_kwh),
        ("🧊", "Lednička – den", 0.7 * c_kwh),
        ("🚽", "Spláchnutí (6 l)", 0.006 * c_voda),
        ("📱", "Nabití telefonu", 0.015 * c_kwh),
        ("💡", "LED žárovka 9 W – večer (5 h)", 0.045 * c_kwh),
        ("💡", "Klasická žárovka 60 W – večer (5 h)", 0.3 * c_kwh),
        ("🔦", "Halogenová bodovka 35 W – večer (5 h)", 0.175 * c_kwh),
        ("🌙", "Venkovní světlo LED 10 W – celou noc (12 h)", 0.12 * c_kwh),
    ]
    st.markdown("".join(
        f'<div class="cena-radek"><span>{ik} {n}</span><b>{cislo(k, 2) if k < 10 else cislo(k, 0)} Kč</b></div>'
        for ik, n, k in polozky), unsafe_allow_html=True)
    st.caption(f"Orientační hodnoty pro běžné spotřebiče (ve vysokém tarifu); {ohrev_txt}.")

    st.markdown("**💡 Svícení doma**")
    st.caption("Spočítej světla po místnostech nebo celý dům najednou – a kolik by ušetřila výměna za LED.")
    TYPY_SVETEL = {"LED žárovka (9 W)": 9, "LED bodovka (5 W)": 5, "Úsporná zářivka (15 W)": 15,
                   "Halogenová bodovka (35 W)": 35, "Halogen (50 W)": 50, "Klasická žárovka (60 W)": 60,
                   "Klasická žárovka (100 W)": 100}
    if "svetla" not in st.session_state:
        st.session_state["svetla"] = [{"typ": "LED žárovka (9 W)", "kusu": 6, "hodin": 4.0}]
    for idx, sv in enumerate(st.session_state["svetla"]):
        c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
        sv["typ"] = c1.selectbox("Typ", list(TYPY_SVETEL), index=list(TYPY_SVETEL).index(sv["typ"]),
                                 key=f"sv_t_{idx}", label_visibility="collapsed" if idx else "visible")
        sv["kusu"] = c2.number_input("Kusů", min_value=0, value=int(sv["kusu"]), step=1, key=f"sv_k_{idx}",
                                     label_visibility="collapsed" if idx else "visible")
        sv["hodin"] = c3.number_input("Hodin/den", min_value=0.0, max_value=24.0, value=float(sv["hodin"]), step=0.5,
                                      key=f"sv_h_{idx}", label_visibility="collapsed" if idx else "visible")
        if idx and c4.button("✕", key=f"sv_x_{idx}", help="Odebrat řádek"):
            st.session_state["svetla"].pop(idx)
            st.rerun()
    if st.button("＋ Přidat další světla", key="sv_pridat"):
        st.session_state["svetla"].append({"typ": "Halogenová bodovka (35 W)", "kusu": 4, "hodin": 3.0})
        st.rerun()
    kwh_rok = sum(TYPY_SVETEL[x["typ"]] * x["kusu"] * x["hodin"] for x in st.session_state["svetla"]) / 1000 * 365
    kwh_rok_led = sum((TYPY_SVETEL[x["typ"]] if "LED" in x["typ"] else
                       max(5, round(TYPY_SVETEL[x["typ"]] * 0.15))) * x["kusu"] * x["hodin"]
                      for x in st.session_state["svetla"]) / 1000 * 365
    uspora = (kwh_rok - kwh_rok_led) * c_kwh
    st.markdown(f"""
<div class="dnes">
  <div class="l">Svícení stojí ročně</div>
  <div class="v">{kc(kwh_rok * c_kwh)}</div>
  <div class="s">≈ {kc(kwh_rok * c_kwh / 12)} měsíčně · {cislo(kwh_rok, 0)} kWh za rok</div>
  {f'<div class="s" style="color:{BARVA_OK};font-weight:600;margin-top:8px">Výměnou za LED bys ušetřil ≈ {kc(uspora)} ročně</div>' if uspora > 1 else ''}
</div>""", unsafe_allow_html=True)
    st.caption("LED náhrada počítá s ~15 % příkonu původní žárovky (např. 60 W → 9 W, 35 W bodovka → 5 W).")

    st.markdown("**Vlastní spotřebič**")
    c1, c2, c3 = st.columns(3)
    prikon = c1.number_input("Příkon (W)", min_value=0.0, value=None, step=10.0, placeholder="např. 2000", key="vl_w")
    hodin = c2.number_input("Hodin denně", min_value=0.0, value=None, step=0.5, placeholder="např. 1", key="vl_h")
    dni_t = c3.number_input("Dní v týdnu", min_value=0, max_value=7, value=7, step=1, key="vl_d")
    if prikon and hodin:
        kwh_den = prikon / 1000 * hodin
        rok = kwh_den * dni_t * 52.18
        st.markdown(f"Jeden den **{kc(kwh_den * c_kwh)}** · měsíčně **{kc(rok / 12 * c_kwh)}** · "
                    f"ročně **{kc(rok * c_kwh)}** ({cislo(rok, 0)} kWh)")

if STRANKA == "pdf":
    nadpis("📄 Roční přehled do PDF", f"{MISTO['nazev']} · souhrn roku ke stažení")
    roky_vse = set()
    for e in PORADI:
        r_ = denni_rada(odecty, e)
        roky_vse |= {d.year for d in r_.index}
    roky_vse = sorted(roky_vse, reverse=True)
    if not roky_vse:
        st.caption("Zatím málo dat.")
    else:
        rok_pdf = st.selectbox("Rok", roky_vse, key="rok_pdf")
        if st.button("Připravit PDF", key="pdf_btn", width="stretch"):
            with st.spinner("Chystám PDF…"):
                st.session_state["pdf_data"] = (MISTO_KLIC, rok_pdf,
                                                rocni_pdf(rok_pdf, odecty, tarif_podle, vysledky, MISTO_KLIC))
        pdf = st.session_state.get("pdf_data")
        if pdf and pdf[0] == MISTO_KLIC and pdf[1] == rok_pdf:
            st.download_button("⬇️ Stáhnout PDF", data=pdf[2], file_name=f"energie_{MISTO_KLIC}_{rok_pdf}.pdf",
                               mime="application/pdf", type="primary", width="stretch")

if STRANKA == "nabidky":
    nadpis("💡 Porovnat nabídky", "Kolik bys ušetřil u jiného dodavatele")
    st.caption("Dodavatel ovlivní jen obchodní část ceny (cena za kWh + stálý plat). Distribuce a poplatky "
               "státu jsou u všech stejné, proto se porovnává jen obchodní část – podle tvé skutečné roční spotřeby.")
    k_e = st.radio("Energie", [x for x in ["elektrina", "plyn"] if x in PORADI], horizontal=True, label_visibility="collapsed",
                   format_func=lambda x: f"{ENERGIE[x]['ikona']} {ENERGIE[x]['nazev']}", key="kalk_e")
    t = tarif_podle.get(k_e)
    v = vysledky.get(k_e)
    if t is not None and v:
        rocni_kwh = v["rocni"] * float(t["kwh_na_jednotku"])
        ted_mwh = float(t["obchodni_kwh"]) * 1000
        ted_mes = float(t["obchodni_mesic"])
        st.markdown(f"Tvoje roční spotřeba: **{cislo(rocni_kwh / 1000, 2)} MWh**. "
                    f"Teď platíš {t['dodavatel']}: **{cislo(ted_mwh, 2)} Kč/MWh** + **{cislo(ted_mes, 2)} Kč/měsíc** (s DPH).")
        bez_dph = st.toggle("Ceny v nabídce jsou bez DPH (přičíst 21 %)", value=True, key="kalk_dph")
        c1, c2 = st.columns(2)
        n_mwh = c1.number_input("Cena za MWh v nabídce (Kč)", min_value=0.0, value=None, step=10.0,
                                placeholder="např. 2 650", key="kalk_mwh")
        n_mes = c2.number_input("Stálý plat v nabídce (Kč/měsíc)", min_value=0.0, value=None, step=1.0,
                                placeholder="např. 99", key="kalk_mes")
        if n_mwh is not None and n_mes is not None:
            koef = 1.21 if bez_dph else 1.0
            ted_rok = rocni_kwh / 1000 * ted_mwh + 12 * ted_mes
            nova_rok = rocni_kwh / 1000 * n_mwh * koef + 12 * n_mes * koef
            rozdil = ted_rok - nova_rok
            barva_r = BARVA_OK if rozdil > 0 else BARVA_ZLE
            st.markdown(f"""
<div class="dnes">
  <div class="l">{'Ušetřil bys' if rozdil > 0 else 'Připlatil bys'} ročně</div>
  <div class="v" style="color:{barva_r}">{kc(abs(rozdil))}</div>
  <div class="s">≈ {kc(abs(rozdil) / 12)} měsíčně · obchodní část teď {kc(ted_rok)} / rok, s nabídkou {kc(nova_rok)} / rok</div>
</div>""", unsafe_allow_html=True)
            st.caption("Před podpisem zkontroluj i délku fixace, výpovědní lhůty a případné poplatky za předčasné ukončení.")
    st.caption("Aktuální obchodní ceny upravíš v ⚙️ Ceny a zálohy.")

if STRANKA == "historie":
    nadpis("📋 Historie odečtů", f"{MISTO['nazev']} · {len(odecty)} záznamů – úprava a mazání")
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
                    + (f" · VT {cislo(r['stav'] - r['stav_nt'], 1)} / NT {cislo(r['stav_nt'], 1)}" if pd.notna(r['stav_nt']) else "")
                    + f"  \n<span style='font-size:.8rem;color:{BARVA_TEXT_TLUMENY}'>{r['typ']}"
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
                ul.uloz(L_ODECTY, ven[SLOUPCE_ODECTY])
                st.session_state.pop("mazu", None)
                st.session_state["ulozeno"] = "Odečet smazán."
                st.rerun()
            if b.button("Ne", key=f"ne_{rid}", width="stretch"):
                st.session_state.pop("mazu", None)
                st.rerun()

        if st.session_state.get("upravuji") == rid:
            typy = ["vlastní", "odečet", "odhad"]
            with st.form(f"form_{rid}"):
                if pd.notna(r["stav_nt"]):
                    c1_, c2_ = st.columns(2)
                    n_vt = c1_.number_input("VT", value=float(r["stav"] - r["stav_nt"]), min_value=0.0, step=0.1, format="%.1f")
                    n_nt = c2_.number_input("NT", value=float(r["stav_nt"]), min_value=0.0, step=0.1, format="%.1f")
                    n_stav = n_vt + n_nt
                else:
                    n_nt = None
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
                ven.loc[m, ["stav", "datum", "typ", "poznamka", "stav_nt"]] = [n_stav, n_dat, n_typ, n_pozn, n_nt]
                ven["datum"] = ven["datum"].astype(str)
                ul.uloz(L_ODECTY, ven[SLOUPCE_ODECTY])
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
if STRANKA == "nastaveni":
    nadpis("⚙️ Ceny a zálohy", "Uprav po každém vyúčtování nebo změně ceny")
    st.caption("Uprav po každém vyúčtování nebo změně ceny či zálohy. Ceny vč. DPH. "
               "Plyn: cena za kWh a přepočet kWh na m³ z faktury (objemový koeficient × spalné teplo).")
    for e in PORADI:
        t = tarify[tarify["energie"] == e]
        if t.empty:
            continue
        t = t.iloc[0]
        info = ENERGIE[e]
        with st.form(f"tarif_{e}"):
            st.markdown(f"**{info['ikona']} {info['nazev']}**")
            c1, c2 = st.columns(2)
            dodavatel = c1.text_input("Dodavatel", value=str(t["dodavatel"]))
            zaloha = c2.number_input("Měsíční záloha (Kč)", value=float(t["zaloha"]), step=10.0, format="%.0f")
            c1, c2 = st.columns(2)
            cena = c1.number_input(("Cena za kWh – VT (Kč)" if e == "elektrina" else "Cena za kWh (Kč)")
                                   if e != "voda" else "Cena za m³ (Kč)",
                                   value=float(t["cena_za_kwh"]), step=0.01, format="%.5f")
            cena_nt = c2.number_input("Cena za kWh – NT (0 = jednotarif)", value=float(t["cena_nt_kwh"]),
                                      step=0.01, format="%.5f", disabled=(e != "elektrina"))
            c1, c2 = st.columns(2)
            mes = c1.number_input("Měsíční stálé platby (Kč)", value=float(t["mesicni_platy"]), step=1.0, format="%.2f")
            prepocet = c2.number_input("kWh na jednotku", value=float(t["kwh_na_jednotku"]), step=0.01, format="%.3f",
                                       disabled=(e != "plyn"))
            c1, c2, c3 = st.columns(3)
            od = c1.date_input("Období od", value=pd.to_datetime(t["obdobi_od"]).date(), format="DD.MM.YYYY")
            do = c2.date_input("Období do", value=pd.to_datetime(t["obdobi_do"]).date(), format="DD.MM.YYYY")
            stav_od = c3.number_input("Stav na začátku (0 = dopočítat)", value=float(t["stav_obdobi_od"]), step=0.001, format="%.3f")
            c1, c2 = st.columns(2)
            zaplaceno = c1.number_input("Zaplaceno v období (Kč)", value=float(t["zaplaceno"]), step=10.0, format="%.0f")
            k_datu = c2.date_input("…k datu", value=pd.to_datetime(t["zaplaceno_k_datu"]).date(), format="DD.MM.YYYY")
            c1, c2 = st.columns(2)
            rezerva = c1.number_input("Rezerva na zdražení (%)", value=float(t["rezerva_pct"]), step=1.0, format="%.0f")
            plati = c2.text_input("Cena platí", value=str(t["cena_plati"]))
            c1, c2, c3 = st.columns([3, 2, 1])
            ucet = c1.text_input("Účet pro zálohy", value=str(t["ucet"]), placeholder="předčíslí-číslo/banka")
            vs = c2.text_input("Variabilní symbol", value=str(t["vs"]))
            den = c3.number_input("Splatnost (den)", value=int(t["den_splatnosti"]), min_value=1, max_value=28, step=1)
            c1, c2 = st.columns(2)
            obch_kwh = c1.number_input("Obchodní cena za kWh (Kč, s DPH)", value=float(t["obchodni_kwh"]), step=0.01,
                                       format="%.5f", disabled=(e == "voda"))
            obch_mes = c2.number_input("Obchodní stálý plat (Kč/měs., s DPH)", value=float(t["obchodni_mesic"]),
                                       step=1.0, format="%.2f", disabled=(e == "voda"))
            c1, c2 = st.columns([2, 3])
            konec_val = pd.to_datetime(t["konec_smlouvy"]).date() if t["konec_smlouvy"] else None
            konec = c1.date_input("Konec smlouvy / fixace", value=konec_val, format="DD.MM.YYYY")
            konec_txt = c2.text_input("Popis", value=t["konec_popis"], placeholder="např. Konec fixace ceny")
            if st.form_submit_button("Uložit", width="stretch"):
                ven = tarify.copy()
                m = ven["energie"] == e
                ven.loc[m, ["zaloha", "cena_za_kwh", "mesicni_platy", "kwh_na_jednotku", "obdobi_od", "obdobi_do",
                            "stav_obdobi_od", "zaplaceno", "zaplaceno_k_datu", "rezerva_pct", "cena_plati",
                            "ucet", "vs", "den_splatnosti", "obchodni_kwh", "obchodni_mesic",
                            "konec_smlouvy", "konec_popis", "dodavatel", "cena_nt_kwh"]] = [
                    zaloha, cena, mes, prepocet, od.isoformat(), do.isoformat(), stav_od,
                    zaplaceno, k_datu.isoformat(), rezerva, plati, ucet.strip(), vs.strip(), den, obch_kwh, obch_mes,
                    konec.isoformat() if konec else "", konec_txt, dodavatel.strip(), cena_nt if e == "elektrina" else 0]
                ul.uloz(L_TARIFY, ven[SLOUPCE_TARIFY])
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
  <span style="font-size:.75rem">Odběrné místo: {MISTO['nazev']}, {MISTO['obec']} · data: {ul.popis}</span>
</div>
""", unsafe_allow_html=True)
