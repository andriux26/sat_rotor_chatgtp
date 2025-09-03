# -*- coding: utf-8 -*-
"""
Satellite tracking + SatDump + Gallery + Conflicts + Web UI + I18N + Gallery cleanup
Now with:
- Language palette (LT/EN) in top navbar. Endpoint: /api/lang?code=lt|en
- Gallery page fully uses translations (and some extra labels localized)
"""

import requests
import time
import subprocess
import os
import sys
import select
import serial
import shutil
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta, timezone
from skyfield.api import load, wgs84, EarthSatellite
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from glob import glob
import numpy as np

# ---------------- Paths ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEKIMAS_TXT     = os.path.join(BASE_DIR, "sekimas.txt")
SELECTION_JSON  = os.path.join(BASE_DIR, "selection.json")
CURRENT_JSON    = os.path.join(BASE_DIR, "current.json")
NUSTATYMAI_TXT  = os.path.join(BASE_DIR, "nustatymai.txt")
TLE_FILENAME    = os.path.join(BASE_DIR, "tle.txt")
LAIKAI_FILENAME = os.path.join(BASE_DIR, "laikai.txt")
KALBOS_DIR      = os.path.join(BASE_DIR, "kalbos")

# ---------------- Default settings ----------------
DEFAULT_SETTINGS = {
    "LANG": "lt",
    "TLE_URL": "http://192.168.1.64/tle.txt",
    "KOORD_LAT": 55.57,
    "KOORD_LON": 24.25,
    "SERIAL_PORT": "/dev/ttyACM0",
    "BAUDRATE": 9600,
    "UPDATE_INTERVAL": 5,
    "ALTITUDE_LIMIT": 0.0,
    "HTTP_PORT": 8089,
    "NUOTRAUKU_KATALOGAS": "nuotraukos",
    "SATDUMP_SOURCE": "rtlsdr",
    "SATDUMP_RATE": 2400000,
    "SATDUMP_DEVICE_ARGS": "index=0,ppm=0,gain=49.6",
    "SATDUMP_MODE": "start",
    "SATDUMP_LEAD": 10,
    "SATDUMP_TAIL": 120,
    "USE_MANUAL_TLE": 0,
    "GALLERY_KEEP_DAYS": 0
}

SETTINGS = DEFAULT_SETTINGS.copy()

# Mirrors (populated by apply_settings)
LANG = DEFAULT_SETTINGS["LANG"]
TLE_URL = DEFAULT_SETTINGS["TLE_URL"]
KOORD_LAT = DEFAULT_SETTINGS["KOORD_LAT"]
KOORD_LON = DEFAULT_SETTINGS["KOORD_LON"]
SERIAL_PORT = DEFAULT_SETTINGS["SERIAL_PORT"]
BAUDRATE = DEFAULT_SETTINGS["BAUDRATE"]
UPDATE_INTERVAL = DEFAULT_SETTINGS["UPDATE_INTERVAL"]
ALTITUDE_LIMIT = DEFAULT_SETTINGS["ALTITUDE_LIMIT"]
HTTP_PORT = DEFAULT_SETTINGS["HTTP_PORT"]
NUOTRAUKU_KATALOGAS = os.path.join(BASE_DIR, DEFAULT_SETTINGS["NUOTRAUKU_KATALOGAS"])
SATDUMP_MODE   = DEFAULT_SETTINGS["SATDUMP_MODE"]
SATDUMP_LEAD   = DEFAULT_SETTINGS["SATDUMP_LEAD"]
SATDUMP_TAIL   = DEFAULT_SETTINGS["SATDUMP_TAIL"]
SATDUMP_SOURCE = DEFAULT_SETTINGS["SATDUMP_SOURCE"]
SATDUMP_RATE   = DEFAULT_SETTINGS["SATDUMP_RATE"]
SATDUMP_RATE_ARG = "-s"
SATDUMP_DEVICE_ARGS = DEFAULT_SETTINGS["SATDUMP_DEVICE_ARGS"]
SATDUMP_OUT_ROOT = ""
GALLERY_KEEP_DAYS = DEFAULT_SETTINGS["GALLERY_KEEP_DAYS"]

# Aliases for SatDump satellite names
SATDUMP_ALIASES = {
    "NOAA 15": "NOAA-15", "NOAA 18": "NOAA-18", "NOAA 19": "NOAA-19",
    "METOP-B": "METOP-B", "METOP-C": "METOP-C",
    "METEOR-M 2-3": "METEOR-M 2-3",
    "ISS (ZARYA)": "ISS",
}

THUMB_SIZE = 300

# Local time zone
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Vilnius")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=3))

# Thumbnails (optional)
try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

# ---------------- I18N: translations ----------------
SEED_LT = {
    "nav_laikai": "Laikai",
    "nav_galerija": "Galerija",
    "nav_nustatymai": "Nustatymai",
    "nav_local_time": "Vietos laikas",
    "nav_lang_lt": "LT",
    "nav_lang_en": "EN",
    "h2_laikai": "Sekimo langai (vietiniu laiku)",
    "legend_conflict": "Konfliktinis laikas",
    "tbl_satellite": "Palydovas",
    "tbl_aos": "Pasirodymas",
    "tbl_los": "Pasislepimas",
    "tbl_maxelev": "Maks. elevacija",
    "badge_conflict": "Konfliktas",
    "follow": "Sekti",
    "recent_passes": "Paskutiniai praejimai",
    "gallery_title": "Galerija",
    "settings_title": "Nustatymai",
    "btn_save": "Issaugoti",
    "saved_alert": "Nustatymai issaugoti. Kai kurie pokyciai isigalios po skripto perkrovimo.",
    "save_err_alert": "Nepavyko issaugoti nustatymu.",
    "replan_button": "Perplanuoti",
    "replan_processing": "Perplanuojama...",
    "replan_done": "Perplanuota",
    "replan_error": "Klaida",
    "replan_note": "Atverk Laikai puslapi.",
    "manual_tle_title": "Rankinis TLE",
    "manual_tle_hint": "Pasirink faila arba redaguok teksta. Po irasymo ijungiama Naudoti rankini TLE. Tuomet spausk Perplanuoti.",
    "manual_tle_upload": "Ikelti TLE faila...",
    "manual_tle_save_text": "Issaugoti TLE (is teksto)",
    "manual_tle_saved": "TLE irasytas i tle.txt. Ijungta rankinis TLE. Spausk Perplanuoti.",
    "manual_tle_failed": "Nepavyko irasyti TLE.",
    "satlist_title": "Palydovu sarasas (laikai.txt)",
    "search_placeholder": "Ieskoti TLE pavadinimo...",
    "current_list_label": "Dabartinis sarasas (laikai.txt)",
    "list_empty": "Sarasas tuscias",
    "no_matches": "Nerasta atitikmenu",
    "note_text": "* Po pakeitimu spausk Perplanuoti.",
    "lang_label": "Kalba",
    "lang_lt": "Lietuviu",
    "lang_en": "English",
    "use_manual_tle": "Naudoti rankini TLE (neatsiusti is URL)",
    "tle_url_label": "TLE URL",
    "coord_lat": "Koordinate LAT",
    "coord_lon": "Koordinate LON",
    "serial_port": "Serijinis portas",
    "baudrate": "BAUDRATE",
    "upd_interval": "Atnaujinimo intervalas (s)",
    "alt_limit": "Horizonto riba (deg)",
    "http_port": "HTTP portas",
    "out_dir": "Isvesties katalogas (nuotraukos)",
    "sd_source": "SatDump saltinis",
    "sd_rate": "SatDump emimo daznis (S/s)",
    "sd_devargs": "SatDump irenginio argumentai",
    "sd_mode": "SatDump rezimas",
    "sd_lead": "SatDump pradzia iki AOS (s)",
    "sd_tail": "SatDump pabaiga po LOS (s)",
    "mode_hint": "start (sekimo metu) arba end (po sekimo)",
    "cleanup_title": "Galerijos valymas",
    "cleanup_keep": "Laikyti (dienomis)",
    "cleanup_now": "Valyti dabar",
    "cleanup_off": "Isjungta",
    "cleanup_done": "Istrinta katalogu: {n}",
    "btn_add": "Prideti",
    "btn_remove": "Salinti",
}
SEED_EN = {
    "nav_laikai": "Passes",
    "nav_galerija": "Gallery",
    "nav_nustatymai": "Settings",
    "nav_local_time": "Local time",
    "nav_lang_lt": "LT",
    "nav_lang_en": "EN",
    "h2_laikai": "Pass windows (local time)",
    "legend_conflict": "Conflicting time",
    "tbl_satellite": "Satellite",
    "tbl_aos": "AOS",
    "tbl_los": "LOS",
    "tbl_maxelev": "Max elevation",
    "badge_conflict": "Conflict",
    "follow": "Follow",
    "recent_passes": "Recent passes",
    "gallery_title": "Gallery",
    "settings_title": "Settings",
    "btn_save": "Save",
    "saved_alert": "Settings saved. Some changes apply after script restart.",
    "save_err_alert": "Failed to save settings.",
    "replan_button": "Replan",
    "replan_processing": "Replanning...",
    "replan_done": "Replanned",
    "replan_error": "Error",
    "replan_note": "Open the Passes page.",
    "manual_tle_title": "Manual TLE",
    "manual_tle_hint": "Pick a file or edit text. After saving, manual mode is enabled. Then click Replan.",
    "manual_tle_upload": "Upload TLE file...",
    "manual_tle_save_text": "Save TLE (from text)",
    "manual_tle_saved": "TLE saved to tle.txt. Manual TLE enabled. Click Replan.",
    "manual_tle_failed": "Failed to save TLE.",
    "satlist_title": "Satellite list (laikai.txt)",
    "search_placeholder": "Search TLE name...",
    "current_list_label": "Current list (stored to laikai.txt)",
    "list_empty": "List is empty",
    "no_matches": "No matches",
    "note_text": "* After changes, click Replan to refresh Passes page.",
    "lang_label": "Language",
    "lang_lt": "Lithuanian",
    "lang_en": "English",
    "use_manual_tle": "Use manual TLE (do not download from URL)",
    "tle_url_label": "TLE URL",
    "coord_lat": "Coordinate LAT",
    "coord_lon": "Coordinate LON",
    "serial_port": "Serial port",
    "baudrate": "BAUDRATE",
    "upd_interval": "Update interval (s)",
    "alt_limit": "Horizon limit (deg)",
    "http_port": "HTTP port",
    "out_dir": "Output directory (images)",
    "sd_source": "SatDump source",
    "sd_rate": "SatDump sample rate (S/s)",
    "sd_devargs": "SatDump device-args",
    "sd_mode": "SatDump mode",
    "sd_lead": "SatDump lead (s)",
    "sd_tail": "SatDump tail (s)",
    "mode_hint": "start (during pass) or end (after pass)",
    "cleanup_title": "Gallery cleanup",
    "cleanup_keep": "Keep (days)",
    "cleanup_now": "Clean now",
    "cleanup_off": "Off",
    "cleanup_done": "Deleted folders: {n}",
    "btn_add": "Add",
    "btn_remove": "Remove",
}

def ensure_language_files():
    os.makedirs(KALBOS_DIR, exist_ok=True)
    def write_if_missing(code, data):
        path = os.path.join(KALBOS_DIR, f"{code}.txt")
        if not os.path.isfile(path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("# key=value (UTF-8)\n")
                    for k, v in sorted(data.items()):
                        f.write(f"{k}={v}\n")
                print(f"[I18N] Created {path}")
            except Exception as e:
                print("[I18N] Failed to write", path, e)
    write_if_missing("lt", SEED_LT)
    write_if_missing("en", SEED_EN)

def load_language(lang_code):
    d = {}
    path = os.path.join(KALBOS_DIR, f"{lang_code}.txt")
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line=line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k,v = line.split("=",1)
                    d[k.strip()] = v.strip()
    except Exception as e:
        print("[I18N] read error:", e)
    if lang_code != "en":
        d_en = {}
        en_path = os.path.join(KALBOS_DIR, "en.txt")
        try:
            if os.path.isfile(en_path):
                with open(en_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line=line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k,v = line.split("=",1)
                        d_en[k.strip()] = v.strip()
        except Exception:
            d_en = {}
        for k,v in d_en.items():
            d.setdefault(k, v)
    return d

L = {}
def t(key, default_str): return L.get(key, default_str)

# ---------------- Settings load/save/apply ----------------
def _to_number(val, typ):
    try: return typ(val)
    except Exception: return None

def load_settings_file():
    cfg = DEFAULT_SETTINGS.copy()
    if not os.path.isfile(NUSTATYMAI_TXT):
        return cfg
    try:
        with open(NUSTATYMAI_TXT, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip(); v = v.strip()
                if k not in cfg:
                    continue
                if k in ("HTTP_PORT","BAUDRATE","UPDATE_INTERVAL","SATDUMP_RATE","SATDUMP_LEAD","SATDUMP_TAIL","USE_MANUAL_TLE","GALLERY_KEEP_DAYS"):
                    try: cfg[k] = int(float(v.replace("_","")))
                    except Exception: pass
                elif k in ("KOORD_LAT","KOORD_LON","ALTITUDE_LIMIT"):
                    num = _to_number(v.replace(",", "."), float)
                    if num is not None: cfg[k] = num
                else:
                    cfg[k] = v
    except Exception as e:
        print("Failed to read nustatymai.txt:", e)
    return cfg

def save_settings_file(cfg: dict):
    try:
        with open(NUSTATYMAI_TXT, "w", encoding="utf-8") as f:
            f.write("# Settings (edited via web)\n")
            for k in DEFAULT_SETTINGS.keys():
                v = cfg.get(k, DEFAULT_SETTINGS[k])
                f.write(f"{k}={v}\n")
    except Exception as e:
        print("[ERR] save_settings_file:", e)

def apply_settings(cfg: dict):
    global SETTINGS, LANG, L
    SETTINGS = cfg.copy()
    LANG = (cfg.get("LANG") or "lt").lower()
    ensure_language_files()
    L = load_language(LANG)

    global TLE_URL, KOORD_LAT, KOORD_LON, SERIAL_PORT, BAUDRATE
    global UPDATE_INTERVAL, ALTITUDE_LIMIT, HTTP_PORT, NUOTRAUKU_KATALOGAS
    global SATDUMP_MODE, SATDUMP_LEAD, SATDUMP_TAIL, SATDUMP_SOURCE, SATDUMP_RATE, SATDUMP_DEVICE_ARGS
    global GALLERY_KEEP_DAYS

    TLE_URL = cfg["TLE_URL"]
    KOORD_LAT = float(cfg["KOORD_LAT"])
    KOORD_LON = float(cfg["KOORD_LON"])
    SERIAL_PORT = cfg["SERIAL_PORT"]
    BAUDRATE = int(cfg["BAUDRATE"])
    UPDATE_INTERVAL = int(cfg["UPDATE_INTERVAL"])
    ALTITUDE_LIMIT = float(cfg["ALTITUDE_LIMIT"])
    HTTP_PORT = int(cfg["HTTP_PORT"])

    out_dir = cfg["NUOTRAUKU_KATALOGAS"]
    NUOTRAUKU_KATALOGAS = out_dir if os.path.isabs(out_dir) else os.path.join(BASE_DIR, out_dir)

    SATDUMP_MODE = cfg["SATDUMP_MODE"].strip().lower()
    if SATDUMP_MODE not in ("start", "end"):
        SATDUMP_MODE = "start"
    SATDUMP_LEAD = int(cfg["SATDUMP_LEAD"])
    SATDUMP_TAIL = int(cfg["SATDUMP_TAIL"])
    SATDUMP_SOURCE = cfg["SATDUMP_SOURCE"]
    SATDUMP_RATE = int(cfg["SATDUMP_RATE"])
    SATDUMP_DEVICE_ARGS = cfg["SATDUMP_DEVICE_ARGS"]
    GALLERY_KEEP_DAYS = int(cfg.get("GALLERY_KEEP_DAYS", 0))

# ---------------- Helpers ----------------
def now_utc():
    return datetime.now(timezone.utc)

def to_local_naive(dt_utc: datetime):
    return dt_utc.astimezone(LOCAL_TZ).replace(tzinfo=None)

def sanitize_name(s: str) -> str:
    s = s.strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    return s[:64] if len(s) > 64 else s

def get_current_pass_id():
    try:
        with open(CURRENT_JSON, "r", encoding="utf-8") as f:
            j = json.load(f)
            return j.get("id") or ""
    except Exception:
        return ""

# ---- TLE and satellites list (laikai.txt) ----
def atsisiusti_tle():
    if SETTINGS.get("USE_MANUAL_TLE"):
        print("USE_MANUAL_TLE=1 -> using local tle.txt (skip download).")
        if not os.path.exists(TLE_FILENAME):
            print("Local tle.txt not found.")
        return
    try:
        r = requests.get(TLE_URL, timeout=8)
        r.raise_for_status()
        with open(TLE_FILENAME, "w", encoding="utf-8") as f:
            f.write(r.text)
        print("TLE downloaded.")
    except Exception as e:
        print("Failed to download TLE:", e)
        if not os.path.exists(TLE_FILENAME):
            print("No local TLE file. Exiting.")
            sys.exit(1)

def read_tle_names():
    names = []
    if not os.path.isfile(TLE_FILENAME):
        return names
    with open(TLE_FILENAME, "r", encoding="utf-8", errors="replace") as f:
        lines = [line.strip() for line in f if line.strip()]
    for i in range(0, len(lines), 3):
        names.append(lines[i])
    return names

def laikai_read_list():
    lst = []
    if os.path.exists(LAIKAI_FILENAME):
        with open(LAIKAI_FILENAME, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("Pasirinkti"):
                    lst.append(s)
    return lst

def laikai_write_list(lst):
    try:
        with open(LAIKAI_FILENAME, "w", encoding="utf-8") as f:
            f.write("Pasirinkti palydovai:\n")
            for p in lst:
                f.write(p + "\n")
        return True
    except Exception as e:
        print("[ERR] laikai_write_list:", e)
        return False

def pasirinkti_palydovus():
    selected = laikai_read_list()
    print("Wait 30 s or press Enter for menu...")
    for _ in range(30):
        if sys.stdin in select.select([sys.stdin], [], [], 1)[0]:
            try: input()
            except EOFError: pass
            break
    else:
        return selected

    while True:
        print("\nSATELLITES MENU")
        print("1. Add satellite")
        print("2. Remove satellite")
        print("3. Start tracking")
        print("0. Exit")
        print("\nCurrent list:")
        for i, p in enumerate(selected, 1):
            print(f"{i}. {p}")
        cmd = input("\nChoose: ").strip()

        if cmd == "1":
            names = read_tle_names()
            pref = input("Enter search prefix: ").strip().upper()
            candidates = [n for n in names if pref in n.upper()]
            if not candidates:
                print("No matches.")
                continue
            for i, k in enumerate(candidates, 1):
                print(f"{i}. {k}")
            try:
                nr = int(input("Pick number: ")) - 1
                if 0 <= nr < len(candidates) and candidates[nr] not in selected:
                    selected.append(candidates[nr])
            except Exception:
                print("Selection error.")

        elif cmd == "2":
            for i, p in enumerate(selected, 1):
                print(f"{i}. {p}")
            try:
                nr = int(input("Pick number to remove: ")) - 1
                if 0 <= nr < len(selected):
                    selected.pop(nr)
            except Exception:
                print("Removal error.")

        elif cmd == "3":
            laikai_write_list(selected)
            return selected
        elif cmd == "0":
            sys.exit()

def gauti_tle(pav):
    with open(TLE_FILENAME, "r", encoding="utf-8", errors="replace") as f:
        lines = [line.strip() for line in f if line.strip()]
    for i in range(0, len(lines), 3):
        if lines[i] == pav:
            return lines[i+1], lines[i+2]
    return None, None

def rasti_langus(sat: EarthSatellite, ts, vieta, pav):
    t0 = ts.from_datetime(now_utc())
    t1 = ts.from_datetime(now_utc() + timedelta(hours=24))
    t, e = sat.find_events(vieta, t0, t1, altitude_degrees=ALTITUDE_LIMIT)
    out = []
    i = 0
    while i + 2 < len(e):
        if e[i] == 0 and e[i+1] == 1 and e[i+2] == 2:
            tr, tc, te = t[i], t[i+1], t[i+2]
            alt_c, _, _ = (sat - vieta).at(tc).altaz()
            max_elev = float(alt_c.degrees)
            out.append((tr, te, pav, sat, tc, max_elev))
            i += 3
        else:
            i += 1
    return out

# ---------------- SatDump ----------------
def _satdump_name(pav: str) -> str:
    return SATDUMP_ALIASES.get(pav, pav)

def satdump_start(pav: str, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    name = _satdump_name(pav)
    try:
        cmd = [
            "satdump", "--no-gui", "--auto",
            "--source", SATDUMP_SOURCE,
            "--satellite", name,
            SATDUMP_RATE_ARG, str(SATDUMP_RATE),
            "-o", outdir
        ]
        if SATDUMP_DEVICE_ARGS:
            cmd += ["--device-args", SATDUMP_DEVICE_ARGS]
        print("SatDump START:", " ".join(cmd))
        return subprocess.Popen(cmd)
    except FileNotFoundError:
        print("SatDump not found.")
        return None
    except Exception as e:
        print("SatDump start error:", e)
        return None

def dekoduoti_satdump(pav, t1, t2, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    dur = max(0, int((t2.utc_datetime() - t1.utc_datetime()).total_seconds()))
    timeout = dur + 120
    name = _satdump_name(pav)
    print(f"SatDump END {name} ~{timeout}s -> {outdir}")
    try:
        cmd = [
            "satdump", "--no-gui", "--auto",
            "--source", SATDUMP_SOURCE,
            "--satellite", name,
            SATDUMP_RATE_ARG, str(SATDUMP_RATE),
            "-o", outdir
        ]
        if SATDUMP_DEVICE_ARGS:
            cmd += ["--device-args", SATDUMP_DEVICE_ARGS]
        subprocess.run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("SatDump finished by timeout.")
    except FileNotFoundError:
        print("SatDump not found.")
    except Exception as e:
        print("SatDump error:", e)

def satdump_stop(proc):
    if not proc:
        return
    try:
        print("SatDump STOP")
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try: proc.kill()
        except Exception: pass

# ---------------- Thumbs ----------------
VALID_EXTS = {".png", ".jpg", ".jpeg"}

def _make_thumb(src: str, dst: str, size=THUMB_SIZE):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if PIL_OK:
        try:
            with Image.open(src) as im:
                w, h = im.size
                if w != h:
                    side = min(w, h)
                    left = (w - side) // 2
                    top = (h - side) // 2
                    im = im.crop((left, top, left + side, top + side))
                im = im.resize((size, size), Image.LANCZOS)
                im.save(dst)
                return
        except Exception as e:
            print("Thumb error:", src, e)

def generate_thumbs_in_place(pass_dir: str):
    thumbs_dir = os.path.join(pass_dir, "_thumbs")
    os.makedirs(thumbs_dir, exist_ok=True)
    for dirpath, _, files in os.walk(pass_dir):
        if os.path.basename(dirpath) == "_thumbs":
            continue
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in VALID_EXTS:
                src = os.path.join(dirpath, fn)
                dst = os.path.join(thumbs_dir, fn)
                if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
                    _make_thumb(src, dst, THUMB_SIZE)

def rasyti_praejo_meta(pass_dir: str, sat: str, t1_local: datetime, t2_local: datetime):
    meta = {
        "satellite": sat,
        "start_local": t1_local.isoformat(timespec="seconds"),
        "end_local": t2_local.isoformat(timespec="seconds"),
        "created_utc": now_utc().isoformat(timespec="seconds"),
    }
    with open(os.path.join(pass_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def nuskaityti_praejimus():
    out = []
    if not os.path.isdir(NUOTRAUKU_KATALOGAS):
        return out
    for name in sorted(os.listdir(NUOTRAUKU_KATALOGAS), reverse=True):
        d = os.path.join(NUOTRAUKU_KATALOGAS, name)
        if not os.path.isdir(d):
            continue
        meta_path = os.path.join(d, "meta.json")
        thumbs = sorted(glob(os.path.join(d, "_thumbs", "*")))
        images = sorted([p for p in glob(os.path.join(d, "*")) if os.path.splitext(p)[1].lower() in VALID_EXTS])
        meta = None
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = None
        out.append({
            "dir": d, "name": name, "meta": meta,
            "thumbs": thumbs, "images": images,
        })
    def keyfun(item):
        try:
            return item["meta"]["start_local"]
        except Exception:
            return item["name"]
    out.sort(key=keyfun, reverse=True)
    return out

# ---------------- Gallery cleanup ----------------
def _pass_datetime_local(pass_dir):
    meta_path = os.path.join(pass_dir, "meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            s = meta.get("start_local")
            if s:
                try:
                    return datetime.fromisoformat(s)
                except Exception:
                    pass
        except Exception:
            pass
    newest = 0.0
    for dirpath, _, files in os.walk(pass_dir):
        for fn in files:
            try:
                m = os.path.getmtime(os.path.join(dirpath, fn))
                if m > newest: newest = m
            except Exception:
                pass
    if newest > 0:
        return datetime.fromtimestamp(newest)
    try:
        return datetime.fromtimestamp(os.path.getmtime(pass_dir))
    except Exception:
        return None

def cleanup_gallery(days: int):
    if days is None or days <= 0:
        return {"deleted": 0, "kept": 0, "scanned": 0, "skipped_current": 0}
    if not os.path.isdir(NUOTRAUKU_KATALOGAS):
        return {"deleted": 0, "kept": 0, "scanned": 0, "skipped_current": 0}
    cutoff = to_local_naive(now_utc()) - timedelta(days=days)
    current_id = get_current_pass_id()
    deleted = kept = scanned = skipped_current = 0
    for name in os.listdir(NUOTRAUKU_KATALOGAS):
        d = os.path.join(NUOTRAUKU_KATALOGAS, name)
        if not os.path.isdir(d):
            continue
        scanned += 1
        if name == current_id and current_id:
            skipped_current += 1
            kept += 1
            continue
        dt = _pass_datetime_local(d)
        if dt is None:
            kept += 1
            continue
        if dt < cutoff:
            try:
                shutil.rmtree(d)
                deleted += 1
            except Exception as e:
                print("[CLEANUP] remove error:", d, e)
                kept += 1
        else:
            kept += 1
    print(f"[CLEANUP] days={days} deleted={deleted} kept={kept} scanned={scanned} skip_current={skipped_current}")
    return {"deleted": deleted, "kept": kept, "scanned": scanned, "skipped_current": skipped_current}

# ---------------- Conflict choices ----------------
def set_current_pass(pass_id: str):
    try:
        with open(CURRENT_JSON, "w", encoding="utf-8") as f:
            json.dump({"id": pass_id}, f)
    except Exception as e:
        print("[ERR] set_current_pass:", e)

def save_selected_list_to_file(ids):
    try:
        with open(SEKIMAS_TXT, "w", encoding="utf-8") as f:
            for pid in ids:
                f.write(pid.strip() + "\n")
    except Exception as e:
        print("[ERR] save_selected_list_to_file:", e)

def load_selected_list_from_file():
    ids = []
    try:
        with open(SEKIMAS_TXT, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    ids.append(s)
    except Exception:
        pass
    return ids

def get_selected_ids():
    try:
        with open(SELECTION_JSON, "r", encoding="utf-8") as f:
            j = json.load(f)
            ids = j.get("ids") or []
            if not ids and j.get("id"):
                ids = [j["id"]]
            return list(dict.fromkeys(ids))
    except Exception:
        pass
    return load_selected_list_from_file()

def set_selected_ids(ids):
    ids = [i.strip() for i in ids if i and i.strip()]
    ids = list(dict.fromkeys(ids))
    try:
        with open(SELECTION_JSON, "w", encoding="utf-8") as f:
            json.dump({"ids": ids, "updated": now_utc().isoformat()}, f)
    except Exception as e:
        print("[ERR] set_selected_ids (json):", e)
    save_selected_list_to_file(ids)
    print(f"[API] Updated selection: {ids}")

def add_selected_id(pid):
    ids = set(get_selected_ids())
    if pid:
        ids.add(pid)
    set_selected_ids(sorted(ids))

def remove_selected_id(pid):
    ids = [i for i in get_selected_ids() if i != pid]
    set_selected_ids(ids)

def clear_selected_ids():
    set_selected_ids([])

# ---------------- Planning ----------------
def compute_passes_next_24h():
    ts = load.timescale()
    vieta = wgs84.latlon(latitude_degrees=KOORD_LAT, longitude_degrees=KOORD_LON)
    selected = laikai_read_list()

    all_passes = []
    for name in selected:
        l1, l2 = gauti_tle(name)
        if not l1 or not l2:
            print("No TLE for:", name)
            continue
        sat = EarthSatellite(l1, l2, name, ts)
        all_passes.extend(rasti_langus(sat, ts, vieta, name))

    all_passes.sort(key=lambda x: x[0].utc_datetime())
    return ts, vieta, all_passes

def build_pass_index(langai):
    idx = {}
    for t1, t2, pav, sat, tculm, max_elev in langai:
        st_loc = to_local_naive(t1.utc_datetime())
        pid = f"{st_loc.strftime('%Y%m%d_%H%M')}_{sanitize_name(pav)}"
        idx[pid] = {
            "st": t1.utc_datetime().timestamp(),
            "en": t2.utc_datetime().timestamp(),
            "max": float(max_elev)
        }
    return idx

REPLAN_LOCK = threading.Lock()

def replan_and_refresh():
    with REPLAN_LOCK:
        print("[REPLAN] start")
        if GALLERY_KEEP_DAYS and GALLERY_KEEP_DAYS > 0:
            cleanup_gallery(GALLERY_KEEP_DAYS)

        atsisiusti_tle()
        ts, vieta, all_passes = compute_passes_next_24h()
        nubraizyti_elevaciju_grafika(all_passes, ts, vieta)
        atnaujinti_galerija(all_passes, ts, vieta)
        print(f"[REPLAN] done. passes={len(all_passes)}")
        return len(all_passes)

# ---------------- HTTP server ----------------
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/select":
            qs = parse_qs(parsed.query)
            pid = (qs.get("id") or [""])[0]
            op  = (qs.get("op") or ["add"])[0]
            print(f"[API] /api/select?op={op}&id={pid}")
            if op == "clear":
                clear_selected_ids()
            elif op == "remove":
                remove_selected_id(pid)
            else:
                add_selected_id(pid)
            data = json.dumps({"ok": True, "ids": get_selected_ids()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/settings":
            data = json.dumps(SETTINGS).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/tle_names":
            qs = parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0].strip().upper()
            names = read_tle_names()
            if q:
                names = [n for n in names if q in n.upper()]
            data = json.dumps({"ok": True, "names": names[:200]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/satlist":
            lst = laikai_read_list()
            data = json.dumps({"ok": True, "list": lst}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/replan":
            try:
                count = replan_and_refresh()
                data = json.dumps({"ok": True, "count": count}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                msg = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            return

        if parsed.path == "/api/tle_txt":
            text = ""
            ok = True
            try:
                if os.path.isfile(TLE_FILENAME):
                    with open(TLE_FILENAME, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                else:
                    ok = False
            except Exception as e:
                ok = False
                text = f"ERROR: {e}"
            data = json.dumps({"ok": ok, "text": text}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/cleanup":
            qs = parse_qs(parsed.query)
            try:
                days = int(qs.get("days", [str(GALLERY_KEEP_DAYS)])[0])
            except Exception:
                days = GALLERY_KEEP_DAYS
            res = cleanup_gallery(days)
            try:
                ts, vieta, all_passes = compute_passes_next_24h()
                atnaujinti_galerija(all_passes, ts, vieta)
            except Exception as e:
                print("[CLEANUP] refresh pages error:", e)
            data = json.dumps({"ok": True, "days": days, "result": res}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # NEW: quick language switch
        if parsed.path == "/api/lang":
            qs = parse_qs(parsed.query)
            code = (qs.get("code") or ["lt"])[0].lower()
            if code not in ("lt", "en"):
                code = "lt"
            new_cfg = SETTINGS.copy()
            new_cfg["LANG"] = code
            save_settings_file(new_cfg)
            apply_settings(new_cfg)
            referer = self.headers.get("Referer") or "/index.html"
            self.send_response(302)
            self.send_header("Location", referer)
            self.end_headers()
            return

        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/settings":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            qs = parse_qs(body)

            new_cfg = SETTINGS.copy()

            for key, dv in DEFAULT_SETTINGS.items():
                if key in ("USE_MANUAL_TLE",):
                    continue
                if key in qs:
                    raw = qs[key][0].strip()
                    raw_norm = raw.replace(",", ".")
                    if key in ("HTTP_PORT","BAUDRATE","UPDATE_INTERVAL","SATDUMP_RATE","SATDUMP_LEAD","SATDUMP_TAIL","GALLERY_KEEP_DAYS"):
                        try: new_cfg[key] = int(float(raw_norm.replace("_","")))
                        except Exception: pass
                    elif key in ("KOORD_LAT","KOORD_LON","ALTITUDE_LIMIT"):
                        try: new_cfg[key] = float(raw_norm)
                        except Exception: pass
                    else:
                        new_cfg[key] = raw

            if "USE_MANUAL_TLE" in qs:
                val = qs["USE_MANUAL_TLE"][0].strip()
                new_cfg["USE_MANUAL_TLE"] = 1 if val in ("1","true","on","yes") else 0

            if "LANG" in qs:
                lang = qs["LANG"][0].strip().lower()
                if lang not in ("lt","en"): lang = "lt"
                new_cfg["LANG"] = lang

            save_settings_file(new_cfg)
            apply_settings(new_cfg)

            resp = json.dumps({"ok": True, "saved": new_cfg, "note": "restart_maybe"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if parsed.path == "/api/satlist":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            qs = parse_qs(body)
            op = (qs.get("op") or [""])[0]
            name = (qs.get("name") or [""])[0].strip()
            cur = laikai_read_list()
            changed = False

            if op == "add" and name:
                if name not in cur and name in read_tle_names():
                    cur.append(name); changed = True
            elif op == "remove" and name:
                if name in cur:
                    cur = [x for x in cur if x != name]; changed = True

            ok = True
            if changed:
                ok = laikai_write_list(cur)

            data = json.dumps({"ok": ok, "list": cur}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/tle_manual":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            qs = parse_qs(body)
            text = (qs.get("data") or [""])[0]
            ok = True
            msg = "saved"
            try:
                with open(TLE_FILENAME, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                ok = False; msg = str(e)
            resp = json.dumps({"ok": ok, "msg": msg}).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_response(404)
        self.end_headers()

def start_server():
    os.chdir(BASE_DIR)
    httpd = ThreadingHTTPServer(("", HTTP_PORT), Handler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    print(f"HTTP server running on port {HTTP_PORT} (dir={BASE_DIR})")

# ---------------- NAV bar ----------------
def nav_html(active: str) -> str:
    def li(href, label, key):
        cls = "navlink active" if active == key else "navlink"
        return f'<a class="{cls}" href="{href}">{label}</a>'
    # lang palette
    lang_lt_active = ' active' if LANG == 'lt' else ''
    lang_en_active = ' active' if LANG == 'en' else ''
    return (
        '<div class="navbar"><div class="navwrap">'
        '<div class="links">'
        + li("index.html", t("nav_laikai","Passes"), "laikai")
        + li("galerija.html", t("nav_galerija","Gallery"), "galerija")
        + li("nustatymai.html", t("nav_nustatymai","Settings"), "nustatymai")
        + '</div>'
        f'<div class="navclock"><span class="lbl">{t("nav_local_time","Local time")}:</span> '
        '<span id="nav-clock">--:--:--</span></div>'
        f'<div class="langset">'
        f'<a class="lang{lang_lt_active}" href="/api/lang?code=lt">{t("nav_lang_lt","LT")}</a>'
        f'<a class="lang{lang_en_active}" href="/api/lang?code=en">{t("nav_lang_en","EN")}</a>'
        '</div>'
        '</div></div>'
    )

def nav_css() -> str:
    return (
        ".navbar{position:sticky;top:0;z-index:1000;background:#1a1a1a;border-bottom:1px solid #333;}"
        ".navwrap{width:95%;margin:0 auto;display:flex;align-items:center;justify-content:space-between;padding:10px 0;gap:14px;}"
        ".links{display:flex;gap:14px;align-items:center;}"
        ".navlink{color:#ddd;text-decoration:none;padding:6px 10px;border-radius:8px;border:1px solid transparent;}"
        ".navlink:hover{background:#242424;border-color:#333;color:#fff}"
        ".navlink.active{background:#0b640b;color:#dfffdc;border-color:#0b640b;font-weight:700}"
        ".navclock{margin-left:auto;font-family:monospace;color:#0f0;}"
        ".navclock .lbl{color:#9f9;opacity:.9;margin-right:6px;}"
        ".langset{display:flex;gap:6px;align-items:center;}"
        ".lang{display:inline-block;padding:4px 8px;border-radius:6px;border:1px solid #333;background:#222;color:#ddd;text-decoration:none;font-weight:700;font-size:12px;}"
        ".lang:hover{background:#2a2a2a;border-color:#444;color:#fff}"
        ".lang.active{background:#0b640b;border-color:#0b640b;color:#dfffdc}"
    )

# ---------------- Conflict logic and tracking ----------------
def choose_best_id(candidates, pass_index):
    best_pid = None; best_tuple = None
    for pid in candidates:
        info = pass_index.get(pid, {})
        cand = (float(info.get("max", 0.0)), -float(info.get("st", 0.0)))
        if (best_tuple is None) or (cand > best_tuple):
            best_tuple = cand; best_pid = pid
    return best_pid

def find_overlappers(pass_id, pass_index):
    if pass_id not in pass_index:
        return [pass_id]
    st = pass_index[pass_id]["st"]; en = pass_index[pass_id]["en"]
    out = []
    for pid, info in pass_index.items():
        if info["st"] < en and info["en"] > st:
            out.append(pid)
    return out

def sekti(sat: EarthSatellite, t1, t2, vieta, ts, pav, ser=None, pass_index=None):
    local_start = to_local_naive(t1.utc_datetime())
    local_end = to_local_naive(t2.utc_datetime())
    pass_id = f"{local_start.strftime('%Y%m%d_%H%M')}_{sanitize_name(pav)}"
    pass_dir = os.path.join(NUOTRAUKU_KATALOGAS, pass_id)
    os.makedirs(pass_dir, exist_ok=True)
    print(f"Candidate: {pav} {local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')} -> {pass_id}")

    overlappers = find_overlappers(pass_id, pass_index or {})
    selected = set(get_selected_ids())
    selected_in_group = [pid for pid in overlappers if pid in selected]

    if len(overlappers) > 1:
        if selected_in_group:
            best = choose_best_id(selected_in_group, pass_index or {})
            if pass_id != best:
                print(f"Skip {pass_id} (conflict: user-selected {best}).")
                return
        else:
            best = choose_best_id(overlappers, pass_index or {})
            if pass_id != best:
                print(f"Skip {pass_id} (conflict: prefer {best} by max elevation).")
                return

    t_start = (t1.utc_datetime() - timedelta(seconds=20)).replace(tzinfo=None)
    t_end = t2.utc_datetime().replace(tzinfo=None)

    satdump_proc = None
    if SATDUMP_MODE == "start":
        lead = timedelta(seconds=SATDUMP_LEAD)
        while datetime.utcnow() < (t_start - lead):
            time.sleep(0.5)
        satdump_proc = satdump_start(pav, pass_dir)

    while datetime.utcnow() < t_start:
        time.sleep(0.5)

    set_current_pass(pass_id)
    print(f"START: {pass_id}")

    while datetime.utcnow() < t_end:
        t = ts.now()
        alt, az, _ = (sat - vieta).at(t).altaz()
        if alt.degrees >= 0:
            cmd = f"AZ{az.degrees:06.1f} EL{alt.degrees:05.1f}\r\n"
            if ser:
                try: ser.write(cmd.encode("ascii"))
                except Exception as e: print("Serial write error:", e, "cmd:", cmd.strip())
            else:
                print(cmd.strip())
        time.sleep(UPDATE_INTERVAL)

    print(f"STOP: {pass_id}")

    if SATDUMP_MODE == "start":
        time.sleep(SATDUMP_TAIL)
        satdump_stop(satdump_proc)
    elif SATDUMP_MODE == "end":
        dekoduoti_satdump(pav, t1, t2, pass_dir)

    generate_thumbs_in_place(pass_dir)
    rasyti_praejo_meta(pass_dir, pav, local_start, local_end)

    set_current_pass("")

# ---------------- HTML generation ----------------
def write_gallery_page(passes):
    with open(os.path.join(BASE_DIR, "galerija.html"), "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='UTF-8'><style>")
        f.write("body{background:#111;color:#eee;font-family:sans-serif;text-align:center;}")
        f.write(nav_css())
        f.write("h2{text-align:center;margin:20px 0 12px;}")
        f.write(".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;width:95%;margin:20px auto;}")
        f.write(".card{background:#1b1b1b;border:1px solid #333;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.3);}")
        f.write(".thumbwrap{width:100%;height:300px;display:block;overflow:hidden;background:#000;}")
        f.write(".thumbwrap img{width:100%;height:100%;object-fit:cover;display:block;}")
        f.write(".meta{padding:10px 12px;font-size:14px;color:#ddd;}")
        f.write(".meta .title{font-weight:600;color:#fff;margin-bottom:4px;text-align:center;}")
        f.write(".meta .time{opacity:.8;text-align:center;}")
        f.write("a{color:#0f0;text-decoration:none}")
        f.write("</style>")
        f.write("<script>document.addEventListener('DOMContentLoaded',()=>{"
                "const tick=()=>{const e=document.getElementById('nav-clock'); if(e){e.textContent=new Date().toLocaleTimeString();}};"
                "tick(); setInterval(tick,1000);"
                "});</script></head><body>")
        f.write(nav_html("galerija"))
        f.write(f"<h2>{t('gallery_title','Gallery')}</h2>")
        f.write("<div class='grid'>")
        for p in passes:
            thumb_rel = None
            if p["thumbs"]:
                thumb_rel = p["thumbs"][0]
            elif p["images"]:
                thumb_rel = p["images"][0]
            if not thumb_rel:
                continue
            thumb_rel = os.path.relpath(thumb_rel, BASE_DIR).replace("\\", "/")
            sat = (p["meta"] or {}).get("satellite", p["name"].split("_", 1)[-1])
            start_local_str = (p["meta"] or {}).get("start_local", "")
            pass_page = f"pass-{p['name']}.html"
            f.write("<div class='card'>")
            f.write(f"<a class='thumbwrap' href='{pass_page}'><img src='{thumb_rel}' alt='thumb'></a>")
            f.write("<div class='meta'>")
            f.write(f"<div class='title'>{sat}</div>")
            if start_local_str:
                try:
                    dt = datetime.fromisoformat(start_local_str)
                    f.write(f"<div class='time'>{dt.strftime('%Y-%m-%d %H:%M')}</div>")
                except Exception:
                    f.write(f"<div class='time'>{start_local_str}</div>")
            f.write("</div></div>")
        f.write("</div></body></html>")

def write_settings_page():
    with open(os.path.join(BASE_DIR, "nustatymai.html"), "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='UTF-8'><style>")
        f.write("body{background:#111;color:#eee;font-family:sans-serif;}")
        f.write(nav_css())
        f.write("h2{text-align:center;margin:20px 0 12px;}")
        f.write("form{width:90%;max-width:900px;margin:10px auto 24px;background:#1b1b1b;border:1px solid #333;border-radius:10px;padding:16px;}")
        f.write(".row{display:grid;grid-template-columns:1fr 2fr;gap:10px;margin-bottom:10px;align-items:center;}")
        f.write(".row label{color:#ccc;}")
        f.write(".row input, .row textarea, .row select{width:100%;padding:8px 10px;border:1px solid #444;border-radius:6px;background:#111;color:#eee;}")
        f.write(".hint{color:#aaa;font-size:12px;margin-top:-6px;margin-bottom:12px;}")
        f.write(".actions{display:flex;gap:10px;justify-content:flex-start;margin-top:12px;flex-wrap:wrap}")
        f.write(".btn{padding:10px 14px;border-radius:8px;border:1px solid #0b640b;background:#0b640b;color:#dfffdc;cursor:pointer;font-weight:700;}")
        f.write(".btn.secondary{border-color:#444;background:#222;color:#eee}")
        f.write(".btn.confirm{border-color:#0b640b;background:#0b640b;color:#dfffdc;}")
        f.write(".note{width:90%;max-width:900px;margin:0 auto;color:#bbb;}")
        f.write(".panel{width:90%;max-width:900px;margin:0 auto 24px;background:#1b1b1b;border:1px solid #333;border-radius:10px;padding:16px;}")
        f.write(".panel h3{margin:0 0 12px 0;}")
        f.write(".sat-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}")
        f.write(".listbox{border:1px solid #333;background:#111;border-radius:8px;min-height:220px;max-height:340px;overflow:auto;padding:8px;}")
        f.write(".item{display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid #222;}")
        f.write(".item:last-child{border-bottom:none}")
        f.write(".item .name{color:#eee;font-size:14px;}")
        f.write(".item button{border:1px solid #444;background:#222;color:#eee;border-radius:6px;padding:4px 8px;cursor:pointer}")
        f.write(".item button:hover{background:#333}")
        f.write(".searchbar{display:flex;gap:8px;margin-bottom:10px}")
        f.write(".searchbar input{flex:1}")
        f.write("a{color:#0f0;text-decoration:none}")
        f.write("</style>")
        f.write("<script>")
        f.write("const STR_SAVED="+json.dumps(t("saved_alert","Settings saved. Some changes apply after script restart."))+";")
        f.write("const STR_SAVEERR="+json.dumps(t("save_err_alert","Failed to save settings."))+";")
        f.write("const STR_REPLAN_PROC="+json.dumps(t("replan_processing","Replanning..."))+";")
        f.write("const STR_REPLAN_DONE="+json.dumps(t("replan_done","Replanned"))+";")
        f.write("const STR_REPLAN_ERR="+json.dumps(t("replan_error","Error"))+";")
        f.write("const STR_REPLAN_NOTE="+json.dumps(t("replan_note","Open the Passes page."))+";")
        f.write("const STR_LIST_EMPTY="+json.dumps(t("list_empty","List is empty"))+";")
        f.write("const STR_NO_MATCHES="+json.dumps(t("no_matches","No matches"))+";")
        f.write("const STR_CLEAN_DONE="+json.dumps(t("cleanup_done","Deleted folders: {n}"))+";")
        f.write("const STR_BTN_ADD="+json.dumps(t("btn_add","Add"))+";")
        f.write("const STR_BTN_REMOVE="+json.dumps(t("btn_remove","Remove"))+";")
        f.write(r"""
document.addEventListener('DOMContentLoaded',()=>{
  const tick=()=>{const el=document.getElementById('nav-clock'); if(el){el.textContent=new Date().toLocaleTimeString();}};
  tick(); setInterval(tick,1000);

  function fillForm(data){
    for(const k in data){
      const el=document.querySelector(`[name="${k}"]`);
      if(!el) continue;
      if(el.type==='checkbox'){
        const v = data[k];
        el.checked = (v===1 || v==='1' || v===true || v==='true');
      }else{
        el.value = String(data[k]);
      }
    }
  }
  fetch('/api/settings',{cache:'no-store'}).then(r=>r.json()).then(fillForm);

  const form=document.getElementById('settings-form');
  form.addEventListener('submit',async (e)=>{
    e.preventDefault();
    const floatKeys = ['KOORD_LAT','KOORD_LON','ALTITUDE_LIMIT'];
    floatKeys.forEach(k=>{
      const el=form.querySelector(`[name="${k}"]`);
      if(el && el.value){ el.value = el.value.replace(',', '.'); }
    });
    const params=new URLSearchParams();
    const inputs = form.querySelectorAll('input:not([type="checkbox"]), textarea, select');
    inputs.forEach(el=>{ if(el.name) params.append(el.name, el.value); });
    const useManual = form.querySelector('#USE_MANUAL_TLE');
    params.append('USE_MANUAL_TLE', useManual && useManual.checked ? '1' : '0');

    const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:params});
    if(r.ok){ await r.json(); alert(STR_SAVED); }
    else{ alert(STR_SAVEERR); }
  });

  // Manual TLE controls
  const tleText   = document.getElementById('tle-text');
  const tleFile   = document.getElementById('tle-file');
  const tleUpload = document.getElementById('tle-upload');
  const tleSave   = document.getElementById('tle-save');
  const tleStatus = document.getElementById('tle-status');
  const cbManual  = document.getElementById('USE_MANUAL_TLE');

  async function loadTLE(){
    try{
      const j = await (await fetch('/api/tle_txt',{cache:'no-store'})).json();
      if(j.ok){ tleText.value = j.text || ''; }
    }catch(e){}
  }
  loadTLE();

  async function saveManualText(text){
    const params = new URLSearchParams();
    params.append('data', text || '');
    tleStatus.textContent = '';
    const r = await fetch('/api/tle_manual',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:params});
    const j = await r.json();
    if(j.ok){
      tleStatus.textContent = """ + json.dumps(t("manual_tle_saved","TLE saved to tle.txt. Manual TLE enabled. Click Replan.")) + r""";
      cbManual.checked = true;
    }else{
      tleStatus.textContent = """ + json.dumps(t("manual_tle_failed","Failed to save TLE.")) + r""" + (j.msg?(' '+j.msg):'');
    }
    return j.ok;
  }

  tleUpload.addEventListener('click', ()=>{ tleFile.click(); });
  tleFile.addEventListener('change', async ()=>{
    const f = tleFile.files && tleFile.files[0];
    if(!f) return;
    const reader = new FileReader();
    reader.onload = async (ev)=>{
      const text = ev.target.result || '';
      tleText.value = text;
      tleUpload.classList.add('confirm');
      tleUpload.textContent = '...';
      const ok = await saveManualText(text);
      tleUpload.textContent = ok ? 'OK' : 'ERR';
      setTimeout(()=>{ tleUpload.classList.remove('confirm'); tleUpload.textContent=""" + json.dumps(t("manual_tle_upload","Upload TLE file...")) + r"""; }, 1200);
    };
    reader.readAsText(f);
  });

  tleSave.addEventListener('click', async ()=>{
    tleSave.classList.add('confirm'); const old=tleSave.textContent;
    tleSave.textContent = '...';
    const ok = await saveManualText(tleText.value || '');
    tleSave.textContent = ok ? 'OK' : 'ERR';
    setTimeout(()=>{ tleSave.classList.remove('confirm'); tleSave.textContent=old; }, 1200);
  });

  // Satellite list management
  const resultsBox = document.getElementById('sat-results');
  const chosenBox  = document.getElementById('sat-chosen');
  const qInput     = document.getElementById('sat-q');
  const replanBtn  = document.getElementById('btn-replan-settings');
  const replanMsg  = document.getElementById('replan-status');

  async function refreshChosen(){
    const j = await (await fetch('/api/satlist',{cache:'no-store'})).json();
    renderChosen(j.list||[]);
  }

  function renderChosen(list){
    chosenBox.innerHTML='';
    if(!list.length){ chosenBox.innerHTML='<div class="item"><div class="name">'+""" + json.dumps(t("list_empty","List is empty")) + r"""+'</div></div>'; return; }
    list.forEach(name=>{
      const div=document.createElement('div'); div.className='item';
      const left=document.createElement('div'); left.className='name'; left.textContent=name;
      const btn=document.createElement('button'); btn.textContent=STR_BTN_REMOVE;
      btn.addEventListener('click', async ()=>{
        const p=new URLSearchParams(); p.append('op','remove'); p.append('name',name);
        await fetch('/api/satlist',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p});
        refreshChosen();
      });
      div.appendChild(left); div.appendChild(btn); chosenBox.appendChild(div);
    });
  }

  async function doSearch(){
    const j = await (await fetch('/api/tle_names?q='+encodeURIComponent((qInput.value||'').trim()),{cache:'no-store'})).json();
    renderResults(j.names||[]);
  }

  function renderResults(list){
    resultsBox.innerHTML='';
    if(!list.length){ resultsBox.innerHTML='<div class="item"><div class="name">'+""" + json.dumps(t("no_matches","No matches")) + r"""+'</div></div>'; return; }
    list.forEach(name=>{
      const div=document.createElement('div'); div.className='item';
      const left=document.createElement('div'); left.className='name'; left.textContent=name;
      const btn=document.createElement('button'); btn.textContent=STR_BTN_ADD;
      btn.addEventListener('click', async ()=>{
        const p=new URLSearchParams(); p.append('op','add'); p.append('name',name);
        await fetch('/api/satlist',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p});
        refreshChosen();
      });
      div.appendChild(left); div.appendChild(btn); resultsBox.appendChild(div);
    });
  }

  replanBtn.addEventListener('click', async ()=>{
    const orig = replanBtn.textContent;
    replanBtn.classList.add('confirm');
    replanBtn.textContent = """ + json.dumps(t("replan_processing","Replanning...")) + r""";
    replanMsg.textContent = '';
    try{
      const r = await fetch('/api/replan?ts='+Date.now(), {cache:'no-store'});
      const j = await r.json();
      if(j.ok){
        replanBtn.textContent = """ + json.dumps(t("replan_done","Replanned")) + r""";
        replanMsg.textContent = 'Passes: ' + j.count + '. ' + """ + json.dumps(t("replan_note","Open the Passes page.")) + r""";
      }else{
        replanBtn.textContent = """ + json.dumps(t("replan_error","Error")) + r""";
        replanMsg.textContent = 'Failed: ' + (j.error||'');
      }
    }catch(e){
      replanBtn.textContent = """ + json.dumps(t("replan_error","Error")) + r""";
      replanMsg.textContent = 'Request failed.';
    }
    setTimeout(()=>{ replanBtn.classList.remove('confirm'); replanBtn.textContent = orig; }, 2000);
  });

  qInput.addEventListener('input',()=>{ doSearch(); });
  refreshChosen(); doSearch();

  // Cleanup now
  const cleanBtn = document.getElementById('btn-clean-now');
  const daysSel  = document.getElementById('GALLERY_KEEP_DAYS');
  const cleanMsg = document.getElementById('clean-status');
  cleanBtn.addEventListener('click', async ()=>{
    const days = parseInt(daysSel.value || '0', 10) || 0;
    cleanBtn.classList.add('confirm');
    const orig = cleanBtn.textContent;
    cleanBtn.textContent = '...';
    try{
      const j = await (await fetch('/api/cleanup?days='+days,{cache:'no-store'})).json();
      const n = (j.result && j.result.deleted) || 0;
      cleanMsg.textContent = (""" + json.dumps(t("cleanup_done","Deleted folders: {n}")) + r""").replace('{n}', String(n));
    }catch(e){
      cleanMsg.textContent = 'Cleanup failed';
    }
    setTimeout(()=>{ cleanBtn.classList.remove('confirm'); cleanBtn.textContent = orig; }, 1200);
  });

});
        """)
        f.write("</script></head><body>")
        f.write(nav_html("nustatymai"))
        f.write(f"<h2>{t('settings_title','Settings')}</h2>")

        # Settings form
        f.write("<form id='settings-form' novalidate>")

        def row(name,label,input_html, hint=""):
            f.write("<div class='row'>")
            f.write(f"<label for='{name}'>{label}</label>")
            f.write(input_html)
            f.write("</div>")
            if hint:
                f.write(f"<div class='hint'>{hint}</div>")

        row("LANG", t("lang_label","Language"),
            "<select id='LANG' name='LANG'>"
            f"<option value='lt'>{t('lang_lt','Lithuanian')}</option>"
            f"<option value='en'>{t('lang_en','English')}</option>"
            "</select>","")

        row("TLE_URL", t("tle_url_label","TLE URL"),
            "<input type='text' id='TLE_URL' name='TLE_URL' required>",
            "URL or local path")

        row("USE_MANUAL_TLE", t("use_manual_tle","Use manual TLE (do not download from URL)"),
            "<input type='checkbox' id='USE_MANUAL_TLE' name='USE_MANUAL_TLE'>","")

        row("KOORD_LAT", t("coord_lat","Coordinate LAT"),
            "<input type='text' id='KOORD_LAT' name='KOORD_LAT' inputmode='decimal' pattern='[-+]?[0-9]*[.,]?[0-9]+' required>",
            "e.g., 55.57 or 55,57")

        row("KOORD_LON", t("coord_lon","Coordinate LON"),
            "<input type='text' id='KOORD_LON' name='KOORD_LON' inputmode='decimal' pattern='[-+]?[0-9]*[.,]?[0-9]+' required>",
            "e.g., 24.25 or 24,25")

        row("SERIAL_PORT", t("serial_port","Serial port"),
            "<input type='text' id='SERIAL_PORT' name='SERIAL_PORT' required>","/dev/ttyACM0")

        row("BAUDRATE", t("baudrate","BAUDRATE"),
            "<input type='number' id='BAUDRATE' name='BAUDRATE' step='1' required>","9600, etc.")

        row("UPDATE_INTERVAL", t("upd_interval","Update interval (s)"),
            "<input type='number' id='UPDATE_INTERVAL' name='UPDATE_INTERVAL' step='1' required>","")

        row("ALTITUDE_LIMIT", t("alt_limit","Horizon limit (deg)"),
            "<input type='text' id='ALTITUDE_LIMIT' name='ALTITUDE_LIMIT' inputmode='decimal' pattern='[-+]?[0-9]*[.,]?[0-9]+' required>",
            "0.0 = from horizon")

        row("HTTP_PORT", t("http_port","HTTP port"),
            "<input type='number' id='HTTP_PORT' name='HTTP_PORT' step='1' required>","")

        row("NUOTRAUKU_KATALOGAS", t("out_dir","Output directory (images)"),
            "<input type='text' id='NUOTRAUKU_KATALOGAS' name='NUOTRAUKU_KATALOGAS' required>","")

        row("SATDUMP_SOURCE", t("sd_source","SatDump source"),
            "<input type='text' id='SATDUMP_SOURCE' name='SATDUMP_SOURCE' required>",
            "rtlsdr, rtl_tcp, airspy ...")

        row("SATDUMP_RATE", t("sd_rate","SatDump sample rate (S/s)"),
            "<input type='number' id='SATDUMP_RATE' name='SATDUMP_RATE' step='1' required>","e.g., 2400000")

        row("SATDUMP_DEVICE_ARGS", t("sd_devargs","SatDump device-args"),
            "<input type='text' id='SATDUMP_DEVICE_ARGS' name='SATDUMP_DEVICE_ARGS' required>",
            "index=0,ppm=0,gain=49.6")

        row("SATDUMP_MODE", t("sd_mode","SatDump mode"),
            "<input type='text' id='SATDUMP_MODE' name='SATDUMP_MODE' required>",
            t("mode_hint","start (during pass) or end (after pass)"))

        row("SATDUMP_LEAD", t("sd_lead","SatDump lead (s)"),
            "<input type='number' id='SATDUMP_LEAD' name='SATDUMP_LEAD' step='1' required>","")

        row("SATDUMP_TAIL", t("sd_tail","SatDump tail (s)"),
            "<input type='number' id='SATDUMP_TAIL' name='SATDUMP_TAIL' step='1' required>","")

        # Gallery cleanup controls
        f.write("<div class='panel'>")
        f.write(f"<h3>{t('cleanup_title','Gallery cleanup')}</h3>")
        row("GALLERY_KEEP_DAYS", t("cleanup_keep","Keep (days)"),
            "<select id='GALLERY_KEEP_DAYS' name='GALLERY_KEEP_DAYS'>"
            f"<option value='0'>{t('cleanup_off','Off')}</option>"
            + "".join([f"<option value='{i}'>{i}</option>" for i in range(1,11)])
            + "</select>",
            "* If set > 0, older passes are deleted on startup and on Replan."
        )
        f.write("<div class='actions'>"
                f"<button class='btn' id='btn-clean-now' type='button'>{t('cleanup_now','Clean now')}</button>"
                "<span id='clean-status' style='margin-left:10px;color:#ccc;'></span>"
                "</div>")
        f.write("</div>")

        f.write("<div class='actions'>"
                f"<button class='btn' type='submit'>{t('btn_save','Save')}</button>"
                "</div>")
        f.write("</form>")

        # Manual TLE editor
        f.write("<div class='panel'>")
        f.write(f"<h3>{t('manual_tle_title','Manual TLE')}</h3>")
        f.write(f"<div class='hint'>{t('manual_tle_hint','Pick a file or edit text. After saving, manual mode is enabled. Then click Replan.')}</div>")
        f.write("<div class='row'><label>File</label>"
                "<div class='actions'>"
                "<input type='file' id='tle-file' accept='.txt' style='display:none'>"
                f"<button class='btn secondary' id='tle-upload' type='button'>{t('manual_tle_upload','Upload TLE file...')}</button>"
                "<span id='tle-status' style='margin-left:10px;color:#ccc;'></span>"
                "</div></div>")
        f.write("<div class='row'><label for='tle-text'>TLE</label>"
                "<textarea id='tle-text' name='TLE_TEXT' rows='12' spellcheck='false' style='font-family:monospace;'></textarea></div>")
        f.write("<div class='actions'>"
                f"<button class='btn' id='tle-save' type='button'>{t('manual_tle_save_text','Save TLE (from text)')}</button>"
                "</div>")
        f.write("</div>")

        # Satellite selection + Replan
        f.write("<div class='panel'>")
        f.write(f"<h3>{t('satlist_title','Satellite list (laikai.txt)')}</h3>")
        f.write("<div class='sat-grid'>")
        f.write("<div>")
        f.write(f"<div class='searchbar'><input id='sat-q' type='text' placeholder='{t('search_placeholder','Search TLE name...')}'></div>")
        f.write("<div id='sat-results' class='listbox'></div>")
        f.write("</div>")
        f.write("<div>")
        f.write(f"<div style='margin-bottom:10px;color:#ccc;'>{t('current_list_label','Current list (stored to laikai.txt)')}</div>")
        f.write("<div id='sat-chosen' class='listbox'></div>")
        f.write("</div>")
        f.write("</div>")
        f.write("<div class='actions' style='margin-top:14px;'>"
                f"<button class='btn' id='btn-replan-settings' type='button'>{t('replan_button','Replan')}</button>"
                "<span id='replan-status' style='margin-left:10px;color:#ccc;'></span>"
                "</div>")
        f.write("</div>")

        f.write(f"<div class='note'>{t('note_text','* After changes, click Replan to refresh Passes page.')}</div>")
        f.write("</body></html>")

def atnaujinti_galerija(langai, ts, vieta):
    os.makedirs(NUOTRAUKU_KATALOGAS, exist_ok=True)
    now_local = to_local_naive(now_utc())
    passes = nuskaityti_praejimus()

    rows = []
    for t1, t2, pav, sat, tculm, max_elev in langai:
        start_local = to_local_naive(t1.utc_datetime())
        end_local   = to_local_naive(t2.utc_datetime())
        pass_id = f"{start_local.strftime('%Y%m%d_%H%M')}_{sanitize_name(pav)}"
        rows.append({
            "id": pass_id,
            "pav": pav,
            "st_loc": start_local,
            "en_loc": end_local,
            "st_iso": t1.utc_datetime().isoformat().replace("+00:00","Z"),
            "en_iso": t2.utc_datetime().isoformat().replace("+00:00","Z"),
            "st": t1.utc_datetime().timestamp(),
            "en": t2.utc_datetime().timestamp(),
            "max": max_elev
        })

    overlap_ids = set()
    n = len(rows)
    for i in range(n):
        for j in range(i+1, n):
            if rows[i]["st"] < rows[j]["en"] and rows[i]["en"] > rows[j]["st"]:
                overlap_ids.add(rows[i]["id"])
                overlap_ids.add(rows[j]["id"])

    selected_now = set(get_selected_ids())

    # index.html
    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='UTF-8'><style>")
        f.write("body{background:#111;color:#eee;font-family:sans-serif;text-align:center;}")
        f.write(nav_css())
        f.write("h2{text-align:center;margin:20px 0 6px;}")
        f.write(".legend{font-size:12px;opacity:.9;margin-bottom:10px;}")
        f.write(".legend .swatch{display:inline-block;width:10px;height:10px;border-radius:50%;background:#ffd54f;margin:0 6px -1px 0;box-shadow:0 0 8px rgba(255,213,79,.5);}")
        f.write("table{margin:auto;border-collapse:collapse;width:95%;}")
        f.write("th,td{border:1px solid #444;padding:8px;}th{background:#333;}")
        f.write(".visible{background:#223322;transition:background .3s,color .3s;}")
        f.write(".tracking{background:#0b640b;color:#dfffdc;font-weight:bold;}")
        f.write(".chosen{outline:2px solid #0f0;}")
        f.write(".past{opacity:0.45;transition:opacity .3s;}")
        f.write("td:nth-child(2),td:nth-child(3),td:nth-child(4),th:nth-child(2),th:nth-child(3),th:nth-child(4){text-align:center;}")
        f.write(".pick{display:inline-flex;align-items:center;gap:6px;margin-right:8px;font-size:12px;opacity:.9}")
        f.write(".badge-warn{display:inline-flex;align-items:center;gap:6px;background:#ffd54f;color:#111;font-weight:700;border-radius:999px;padding:2px 8px;font-size:11px;box-shadow:0 0 8px rgba(255,213,79,.5);margin-right:8px;}")
        f.write(".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;width:95%;margin:20px auto;}")
        f.write(".card{background:#1b1b1b;border:1px solid #333;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.3);}")
        f.write(".thumbwrap{width:100%;height:300px;display:block;overflow:hidden;background:#000;}")
        f.write(".thumbwrap img{width:100%;height:100%;object-fit:cover;display:block;}")
        f.write(".meta{padding:10px 12px;font-size:14px;color:#ddd;}")
        f.write(".meta .title{font-weight:600;color:#fff;margin-bottom:4px;text-align:center;}")
        f.write(".meta .time{opacity:.8;text-align:center;}")
        f.write("a{color:#0f0;text-decoration:none}")
        f.write("</style>")
        f.write("<script>")
        f.write("function updateClock(){var el=document.getElementById('nav-clock'); if(el){el.textContent=new Date().toLocaleTimeString();}}")
        f.write("function updateRows(){const now=Date.now();document.querySelectorAll('tr[data-start][data-end]').forEach(tr=>{const t1=Date.parse(tr.dataset.start);const t2=Date.parse(tr.dataset.end);tr.classList.remove('visible','past');if(now>=t1&&now<=t2){tr.classList.add('visible')}else if(now>t2){tr.classList.add('past')}});}")
        f.write("async function pollTracking(){try{const r=await fetch('current.json?ts='+Date.now(),{cache:'no-store'});const j=await r.json();const id=(j&&j.id)||'';document.querySelectorAll('tr[data-id]').forEach(tr=>{tr.classList.toggle('tracking',tr.dataset.id===id);});}catch(e){}}")
        f.write("async function pollSelection(){try{const r=await fetch('selection.json?ts='+Date.now(),{cache:'no-store'});const j=await r.json();const ids=(j&&j.ids)||[];document.querySelectorAll('tr[data-id]').forEach(tr=>{tr.classList.toggle('chosen',ids.includes(tr.dataset.id));});document.addEventListener('change',onPick);document.querySelectorAll('input.choose').forEach(cb=>{cb.checked=ids.includes(cb.dataset.id);});}catch(e){}}")
        f.write("async function onPick(e){const cb=e.target; if(!cb || !cb.matches('input.choose')) return; const id=cb.dataset.id; const op=cb.checked?'add':'remove'; try{const resp=await fetch('/api/select?op='+op+'&id='+encodeURIComponent(id),{cache:'no-store'}); if(!resp.ok) throw new Error('HTTP '+resp.status);}catch(err){alert('Save failed');} }")
        f.write("document.addEventListener('DOMContentLoaded',()=>{updateClock();updateRows();pollTracking();pollSelection();setInterval(updateClock,1000);setInterval(updateRows,1000);setInterval(pollTracking,2000);setInterval(pollSelection,2000);});")
        f.write("</script></head><body>")
        f.write(nav_html("laikai"))
        f.write(f"<h2>{t('h2_laikai','Pass windows (local time)')}</h2>")
        f.write(f"<div class='legend'><span class='swatch'></span> {t('legend_conflict','Conflicting time')}</div>")
        f.write("<table>")
        f.write(f"<tr><th>{t('tbl_satellite','Satellite')}</th><th>{t('tbl_aos','AOS')}</th><th>{t('tbl_los','LOS')}</th><th>{t('tbl_maxelev','Max elevation')}</th></tr>")

        for r in rows:
            cls = ""
            if r["st_loc"] <= now_local <= r["en_loc"]:
                cls = "visible"
            elif r["en_loc"] < now_local:
                cls = "past"
            chosen_cls = " chosen" if r["id"] in selected_now else ""
            f.write(f'<tr class="{cls}{chosen_cls}" data-id="{r["id"]}" data-start="{r["st_iso"]}" data-end="{r["en_iso"]}">')
            if r["id"] in overlap_ids:
                checked_attr = ' checked' if r["id"] in selected_now else ''
                f.write("<td>")
                f.write(f'<span class="badge-warn" title="{t("badge_conflict","Conflict")}">[!] {t("badge_conflict","Conflict")}</span>')
                f.write(f'<label class="pick"><input class="choose" type="checkbox" data-id="{r["id"]}"{checked_attr}> {t("follow","Follow")}</label>')
                f.write(f"{r['pav']}</td>")
            else:
                f.write(f"<td>{r['pav']}</td>")
            f.write(f"<td>{r['st_loc'].strftime('%H:%M')}</td>")
            f.write(f"<td>{r['en_loc'].strftime('%H:%M')}</td>")
            f.write(f"<td>{r['max']:.0f}</td>")
            f.write("</tr>")

        f.write("</table>")
        f.write("<img src='palydovai_elevacijos_grafikas.png' style='margin-top:10px;max-width:95%;'>")

        f.write(f"<h2 style='margin-top:20px'>{t('recent_passes','Recent passes')}</h2>")
        f.write("<div class='grid'>")
        for p in passes[:8]:
            thumb_rel = None
            if p["thumbs"]:
                thumb_rel = p["thumbs"][0]
            elif p["images"]:
                thumb_rel = p["images"][0]
            if not thumb_rel:
                continue
            thumb_rel = os.path.relpath(thumb_rel, BASE_DIR).replace("\\", "/")
            sat = (p["meta"] or {}).get("satellite", p["name"].split("_", 1)[-1])
            start_local_str = (p["meta"] or {}).get("start_local", "")
            pass_page = f"pass-{p['name']}.html"
            f.write("<div class='card'>")
            f.write(f"<a class='thumbwrap' href='{pass_page}'><img src='{thumb_rel}' alt='thumb'></a>")
            f.write("<div class='meta'>")
            f.write(f"<div class='title'>{sat}</div>")
            if start_local_str:
                try:
                    dt = datetime.fromisoformat(start_local_str)
                    f.write(f"<div class='time'>{dt.strftime('%Y-%m-%d %H:%M')}</div>")
                except Exception:
                    f.write(f"<div class='time'>{start_local_str}</div>")
            f.write("</div></div>")
        f.write("</div></body></html>")

    # gallery + settings
    write_gallery_page(passes)
    write_settings_page()

    # pass pages with lightbox
    for p in passes:
        pass_page = os.path.join(BASE_DIR, f"pass-{p['name']}.html")
        sat = (p["meta"] or {}).get("satellite", p["name"].split("_", 1)[-1])
        start_local_str = (p["meta"] or {}).get("start_local", p["name"][:13])
        imgs = p["images"]
        with open(pass_page, "w", encoding="utf-8") as f2:
            f2.write("<html><head><meta charset='UTF-8'><style>")
            f2.write("body{background:#111;color:#eee;font-family:sans-serif;}")
            f2.write(nav_css())
            f2.write("a{color:#0f0;text-decoration:none}")
            f2.write(".wrap{width:95%;margin:12px auto 20px;text-align:center;}")
            f2.write(".title{font-size:22px;font-weight:700;margin:8px 0 2px;}")
            f2.write(".time{opacity:.85;margin-bottom:16px;}")
            f2.write(".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;}")
            f2.write(".item{background:#1b1b1b;border:1px solid #333;border-radius:8px;overflow:hidden;}")
            f2.write(".item img{width:100%;height:auto;display:block;cursor:zoom-in;}")
            f2.write(".viewer{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;align-items:center;justify-content:center;z-index:9999;}")
            f2.write(".viewer.show{display:flex;}")
            f2.write(".viewer img{max-width:95%;max-height:95%;box-shadow:0 0 24px rgba(0,0,0,.8);}")
            f2.write(".viewer .close{position:absolute;top:14px;right:22px;font-size:20px;cursor:pointer;color:#fff;opacity:.9}")
            f2.write("</style>")
            f2.write("<script>")
            f2.write("document.addEventListener('DOMContentLoaded',function(){")
            f2.write("  const v=document.getElementById('viewer');")
            f2.write("  const vi=document.getElementById('viewer-img');")
            f2.write("  function show(src){vi.src=src;v.classList.add('show');}")
            f2.write("  function hide(){v.classList.remove('show');vi.src='';}")
            f2.write("  document.querySelectorAll('a.img-link').forEach(a=>{")
            f2.write("    a.addEventListener('click',e=>{e.preventDefault();show(a.getAttribute('href'));});")
            f2.write("  });")
            f2.write("  v.addEventListener('click',hide);")
            f2.write("  document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});")
            f2.write("  const tick=()=>{const e=document.getElementById('nav-clock'); if(e){e.textContent=new Date().toLocaleTimeString();}};")
            f2.write("  tick(); setInterval(tick,1000);")
            f2.write("});")
            f2.write("</script></head><body>")
            f2.write(nav_html("galerija"))
            f2.write("<div class='wrap'>")
            f2.write(f"<div class='title'>{sat}</div>")
            f2.write(f"<div class='time'>{start_local_str}</div>")
            f2.write("<div class='grid'>")
            for img in imgs:
                rel = os.path.relpath(img, BASE_DIR).replace("\\", "/")
                f2.write(f"<div class='item'><a href='{rel}' class='img-link'><img src='{rel}' alt='img'></a></div>")
            f2.write("</div></div>")
            f2.write("<div id='viewer' class='viewer'><span class='close'>x</span><img id='viewer-img' src=''></div>")
            f2.write("</body></html>")

def nubraizyti_elevaciju_grafika(langai, ts, vieta):
    if not langai:
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.set_title("No planned passes")
        plt.tight_layout()
        plt.savefig(os.path.join(BASE_DIR, "palydovai_elevacijos_grafikas.png"))
        plt.close()
        return

    times = []; sats = []; elevs = []
    for t1, t2, pav, sat, tculm, max_elev in langai:
        times.append(to_local_naive(t1.utc_datetime()).strftime("%H:%M"))
        sats.append(pav)
        elevs.append(max_elev)

    x = np.arange(len(elevs))
    fig, ax = plt.subplots(figsize=(12, 5))
    bars = ax.bar(x, elevs, width=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}\n{s}" for t, s in zip(times, sats)], fontsize=10, rotation=90)
    ax.set_ylabel("Max elevation (deg)")
    ax.set_title("Pass start times and their max elevation")
    ax.set_ylim(0, max(elevs) + 10)
    for bar, elev in zip(bars, elevs):
        height = bar.get_height()
        ax.annotate(f"{elev:.1f}", xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom")
    plt.tight_layout()
    plt.savefig(os.path.join(BASE_DIR, "palydovai_elevacijos_grafikas.png"))
    plt.close()

# ---------------- MAIN ----------------
def main():
    ensure_language_files()
    cfg = load_settings_file()
    apply_settings(cfg)

    os.makedirs(NUOTRAUKU_KATALOGAS, exist_ok=True)

    http_thread = threading.Thread(target=start_server, daemon=True)
    http_thread.start()
    set_current_pass("")

    if GALLERY_KEEP_DAYS and GALLERY_KEEP_DAYS > 0:
        cleanup_gallery(GALLERY_KEEP_DAYS)

    prev_list = load_selected_list_from_file()
    if prev_list:
        set_selected_ids(prev_list)
        print(f"Restored selection from sekimas.txt: {prev_list}")
    else:
        set_selected_ids([])

    atsisiusti_tle()
    selected = pasirinkti_palydovus()

    ts = load.timescale()
    vieta = wgs84.latlon(latitude_degrees=KOORD_LAT, longitude_degrees=KOORD_LON)

    all_passes = []
    for name in selected:
        l1, l2 = gauti_tle(name)
        if not l1 or not l2:
            print("No TLE for:", name)
            continue
        sat = EarthSatellite(l1, l2, name, ts)
        all_passes.extend(rasti_langus(sat, ts, vieta, name))

    all_passes.sort(key=lambda x: x[0].utc_datetime())
    pass_index = build_pass_index(all_passes)

    nubraizyti_elevaciju_grafika(all_passes, ts, vieta)
    atnaujinti_galerija(all_passes, ts, vieta)

    ser = None
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        time.sleep(2)
        print(f"Serial open {SERIAL_PORT} @ {BAUDRATE}")
    except Exception as e:
        print("Cannot open serial:", e)
        print("Will track without sending.")

    for t1, t2, pav, sat, tculm, max_elev in all_passes:
        sekti(sat, t1, t2, vieta, ts, pav, ser, pass_index=pass_index)
        atnaujinti_galerija(all_passes, ts, vieta)
        nubraizyti_elevaciju_grafika(all_passes, ts, vieta)

    if ser:
        ser.close()

if __name__ == "__main__":
    main()
