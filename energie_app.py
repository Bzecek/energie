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
def rocni_pdf(rok, odecty, tarif_podle, vysledky, misto):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fpdf import FPDF

    font = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
    font_b = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    class Prehled(FPDF):
        def footer(self):
            self.set_y(-11)
            self.set_font("DV", "", 8)
            self.set_text_color(148, 163, 184)
            self.cell(0, 5, f"Energie · {MISTA[misto]['nazev']} · přehled roku {rok}", align="L")
            self.set_x(-40)
            self.cell(26, 5, f"Strana {self.page_no()} / {{nb}}", align="R")

    pdf = Prehled(format="A4")
    pdf.set_auto_page_break(True, margin=16)

    def drz_pohromade(vyska_mm):
        """Když se blok nevejde na zbytek stránky, začni novou – sekce se nerozdělí."""
        if pdf.get_y() + vyska_mm > pdf.h - 16:
            pdf.add_page()
            pdf.set_y(16)
    pdf.add_font("DV", "", font)
    pdf.add_font("DV", "B", font_b)
    pdf.add_page()
    zelena = (16, 185, 129)

    pdf.set_fill_color(17, 24, 39)
    pdf.rect(0, 0, 210, 34, "F")
    pdf.set_text_color(248, 250, 252)
    pdf.set_font("DV", "B", 20)
    pdf.set_xy(14, 10)
    pdf.cell(0, 9, f"{MISTA[misto]['nazev']} – přehled roku {rok}")
    pdf.set_font("DV", "", 9.5)
    pdf.set_xy(14, 21)
    pdf.cell(0, 6, f"{MISTA[misto]['nazev']}, {MISTA[misto]['obec']} · vytvořeno {datum_cz(date.today())}")
    pdf.set_text_color(30, 41, 59)
    pdf.set_y(42)

    nazvy_m = ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"]
    souhrn = []
    for e in PORADI:
        info = ENERGIE[e]
        t = tarif_podle.get(e)
        v = vysledky.get(e)
        rada = denni_rada(odecty, e)
        if t is None or not v or rada.empty:
            continue
        r = rada[[d.year == rok for d in rada.index]]
        if r.empty:
            continue
        p = rada[[d.year == rok - 1 for d in rada.index]]
        spotreba = r.sum()
        dni = len(r)
        prumer = r.mean()
        zmena = (prumer / p.mean() - 1) * 100 if not p.empty and p.mean() > 0 else None
        naklad = spotreba * v["cena_jednotky"] + dni / 365 * 12 * float(t["mesicni_platy"])
        souhrn.append((e, spotreba, dni, prumer, zmena, naklad))

        drz_pohromade(8 + 4 * 6 + 186 * 2.1 / 7.2 + 6)
        pdf.set_font("DV", "B", 13)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 8, info["nazev"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DV", "", 10)
        radky = [
            ("Spotřeba", f"{cislo(spotreba, 0)} {info['jednotka']}" + ("" if dni >= 360 else f"  (data za {dni} dní)")),
            ("Průměr na den", f"{cislo(prumer, 2)} {info['jednotka']}"),
            ("Změna proti roku " + str(rok - 1), f"{zmena:+.0f} %" if zmena is not None else "–"),
            ("Náklad (dnešní ceny vč. stálých plateb)", kc(naklad)),
        ]
        for a, b in radky:
            pdf.cell(95, 6, a)
            pdf.cell(0, 6, b, new_x="LMARGIN", new_y="NEXT")

        df = r.rename("h").to_frame()
        df["m"] = [d.month for d in df.index]
        mes = df.groupby("m")["h"].sum()
        dfp = p.rename("h").to_frame()
        if not dfp.empty:
            dfp["m"] = [d.month for d in dfp.index]
            mesp = dfp.groupby("m")["h"].sum()
        else:
            mesp = pd.Series(dtype=float)
        fig, ax = plt.subplots(figsize=(7.2, 2.1), dpi=150)
        x = list(range(1, 13))
        ax.bar([i + 0.2 for i in x], [mes.get(i, 0) for i in x], width=0.4, color=info["barva"], label=str(rok))
        if not mesp.empty:
            ax.bar([i - 0.2 for i in x], [mesp.get(i, 0) for i in x], width=0.4, color="#94a3b8", label=str(rok - 1))
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

    if souhrn:
        drz_pohromade(48)
        pdf.set_draw_color(*zelena)
        pdf.set_line_width(0.6)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(3)
        pdf.set_font("DV", "B", 12)
        pdf.cell(0, 8, "Celkem", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DV", "", 10)
        pdf.cell(95, 6, "Náklady za energie a vodu (dnešní ceny)")
        pdf.cell(0, 6, kc(sum(x[5] for x in souhrn)), new_x="LMARGIN", new_y="NEXT")
        pdf.cell(95, 6, "Měsíčně v průměru")
        pdf.cell(0, 6, kc(sum(x[5] for x in souhrn) / 12), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("DV", "", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(0, 4.5, "Spotřeba mezi odečty je rozpočítaná podle typického průběhu roku. Náklady jsou "
                               "přepočtené aktuálními cenami s DPH, aby šly roky srovnávat – skutečně zaplacené "
                               f"částky se mohou lišit. Autor: {AUTOR}, {EMAIL}")
    return bytes(pdf.output())


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


_heslo = spravne_heslo()
if _heslo and not st.session_state.get("prihlasen"):
    st.markdown("""
<div class="hero"><h1>⚡ Energie doma</h1>
<div class="sub">Pro vstup zadej heslo.</div></div>""", unsafe_allow_html=True)
    with st.form("prihlaseni"):
        zadane = st.text_input("Heslo", type="password")
        if st.form_submit_button("Vstoupit", type="primary", width="stretch"):
            if hmac.compare_digest(zadane.encode(), str(_heslo).encode()):
                st.session_state["prihlasen"] = True
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

MISTO_KLIC = st.session_state["misto"]
MISTO = MISTA[MISTO_KLIC]
PORADI = MISTO["energie"]
L_ODECTY, L_TARIFY = MISTO["list_odecty"], MISTO["list_tarify"]

sloupce_mist = st.columns(len(MISTA), gap="small")
for sl, (klic, mm) in zip(sloupce_mist, MISTA.items()):
    aktivni = klic == MISTO_KLIC
    if sl.button(f"{mm['ikona']} {mm['nazev']}", key=f"prepni_{klic}", width="stretch",
                 type="primary" if aktivni else "secondary", disabled=aktivni):
        st.session_state["misto"] = klic
        st.query_params["misto"] = klic
        for k in ["upravuji", "mazu", "pdf_data"]:
            st.session_state.pop(k, None)
        st.rerun()

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

st.markdown(f"""
<div class="hero">
  <h1>{MISTO['ikona']} {MISTO['nazev']}</h1>
  <div class="sub">{MISTO['obec']} · {MISTO['popis']} · aktualizováno {datum_cz(max(v['posledni_datum'] for v in platne)) if platne else '–'}</div>
  <div class="hero-grid">
    <div class="hero-kpi"><div class="l">Zálohy teď</div><div class="v">{kc(zalohy_ted)}</div><div class="s">měsíčně celkem</div></div>
    <div class="hero-kpi"><div class="l">Zálohy na nulu</div><div class="v">{kc(zalohy_nulu)}</div><div class="s">rozdíl {kc_znamenko(zalohy_nulu - zalohy_ted)}</div></div>
    <div class="hero-kpi"><div class="l">Odhad vyúčtování</div><div class="v" style="color:{barva_bil}">{kc_znamenko(bilance_celkem)}</div><div class="s">≈ {kc(mesicne_celkem)} měsíčně skutečně</div></div>
  </div>
  <div class="platby">{"".join(platby_html)}</div>
</div>
""", unsafe_allow_html=True)

with st.expander("📱 Zaplatit zálohu – QR kód a údaje ke zkopírování"):
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

for e in PORADI:
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
  <div>{t['dodavatel']} · Mrkni na nabídky a porovnej je v kalkulačce dole ve Správě –
  při automatickém prodloužení zůstaneš na ceníku, který nemusí být výhodný.</div>
</div>""", unsafe_allow_html=True)

PRAHY_ANOMALIE = {"voda": 1.2, "elektrina": 1.25, "plyn": 1.3}
for e in PORADI:
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
zalozky = st.tabs([f"{ENERGIE[e]['ikona']} {ENERGIE[e]['nazev']}" for e in PORADI])
for e, tab in zip(PORADI, zalozky):
    with tab:
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
st.markdown('<div class="sekce">Správa</div>', unsafe_allow_html=True)
with st.expander("🔌 Co kolik stojí"):
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

with st.expander("📄 Roční přehled do PDF"):
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

with st.expander("💡 Porovnat nabídku jiného dodavatele"):
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
