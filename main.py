import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time
import json
import random
from datetime import datetime, time as d_time, timedelta

# ======================================================
# 1. CONFIG
# ======================================================
st.set_page_config(
    page_title="UAV Pilot Cabinet v10.5",
    layout="wide",
    page_icon="🛡️"
)

def get_secret(key):
    try:
        return st.secrets.get(key) or st.secrets["connections"]["gsheets"].get(key)
    except Exception:
        return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# ======================================================
# 2. CONSTANTS
# ======================================================
UNITS = [
    "впс Кодима","віпс Шершенці","віпс Загнітків","впс Станіславка",
    "віпс Тимкове","віпс Чорна","впс Окни","віпс Ткаченкове",
    "віпс Гулянка","віпс Новосеменівка","впс Великокомарівка",
    "віпс Павлівка","впс Велика Михайлівка","віпс Слов'яносербка",
    "віпс Гребеники","впс Степанівка","віпс Кучурган",
    "віпс Лиманське","віпс Лучинське","УПЗ"
]

BASE_DRONES = [
    "DJI Mavic 3 Pro","DJI Mavic 3E","DJI Mavic 3T",
    "DJI Matrice 30T","DJI Matrice 300"
]

UKR_MONTHS = {
    1:"січень",2:"лютий",3:"березень",4:"квітень",5:"травень",6:"червень",
    7:"липень",8:"серпень",9:"вересень",10:"жовтень",11:"листопад",12:"грудень"
}

MOTIVATION_MSGS = [
    "Дякуємо за службу! 🇺🇦",
    "Все буде Україна! 🇺🇦",
    "Чудова робота, пілоте!",
    "Сталевий облік прийняв дані.",
    "Героям Слава!"
]

# ======================================================
# 3. SESSION STATE
# ======================================================
defaults = {
    "temp_flights": [],
    "logged_in": False,
    "splash_done": False,
    "reset_trigger": 0,
    "uploader_key": 0,
    "history": {"name": [], "phone": [], "route": [], "note": []},
    "last_unit": UNITS[0]
}

for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ======================================================
# 4. UTILS
# ======================================================
def smart_time_parse(val):
    val = "".join(filter(str.isdigit, val))
    if not val:
        return None
    try:
        if len(val) <= 2:
            h, m = int(val), 0
        elif len(val) == 3:
            h, m = int(val[0]), int(val[1:])
        elif len(val) == 4:
            h, m = int(val[:2]), int(val[2:])
        else:
            return None
        return d_time(h, m) if 0 <= h < 24 and 0 <= m < 60 else None
    except Exception:
        return None

def smart_date_parse(val):
    val = "".join(filter(str.isdigit, val))
    try:
        if len(val) == 6:
            return datetime.strptime(val, "%d%m%y").strftime("%d.%m.%Y")
    except Exception:
        return None
    return None

def calculate_duration(start, end):
    if not start or not end:
        return 0
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def add_to_history(key, value):
    if value and value.strip():
        lst = st.session_state.history[key]
        if value not in lst:
            lst.insert(0, value.strip())
            st.session_state.history[key] = lst[:15]

# ======================================================
# 5. DATABASE
# ======================================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1", ttl=60):
    try:
        df = conn.read(worksheet=ws, ttl=ttl)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

drones_db = load_data("DronesDB")

def get_unit_drones(unit):
    if drones_db.empty:
        return []
    return drones_db[drones_db["Підрозділ"] == unit].to_dict("records")

# ======================================================
# 6. TELEGRAM
# ======================================================
def send_telegram_master(flights):
    if not TG_TOKEN or not TG_CHAT_ID or not flights:
        return

    f = flights[0]
    flights_txt = "\n".join(
        [f"🚀 {x['Зліт']}-{x['Посадка']} ({x['Тривалість (хв)']} хв)" for x in flights]
    )

    text = (
        f"🚁 Донесення: {f['Підрозділ']}\n"
        f"👤 Пілот: {f['Оператор']}\n"
        f"📅 Дата: {f['Дата']}\n"
        f"⏰ Час: {f['Час завдання']}\n"
        f"🛡 БпЛА: {f['Дрон']}\n"
        f"📍 Маршрут: {f['Маршрут']}\n\n"
        f"{flights_txt}\n\n"
        f"📝 Примітки: {f['Примітки'] or '—'}"
    )

    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHAT_ID, "text": text}
    )

# ======================================================
# 7. SPLASH
# ======================================================
if not st.session_state.splash_done:
    st.markdown("<h1 style='text-align:center'>🛡️ UAV CABINET</h1>", unsafe_allow_html=True)
    bar = st.progress(0)
    for i in range(100):
        time.sleep(0.005)
        bar.progress(i + 1)
    st.session_state.splash_done = True
    st.rerun()

# ======================================================
# 8. LOGIN
# ======================================================
unit_index = UNITS.index(st.session_state.last_unit) if st.session_state.last_unit in UNITS else 0

if not st.session_state.logged_in:
    st.header("🛡️ ВХІД")
    unit = st.selectbox("Підрозділ:", UNITS, index=unit_index)
    name = st.text_input("Звання та Прізвище:")
    if st.button("УВІЙТИ") and name:
        add_to_history("name", name)
        st.session_state.logged_in = True
        st.session_state.user = {"unit": unit, "name": name}
        st.session_state.last_unit = unit
        st.rerun()
    st.stop()

# ======================================================
# 9. MAIN UI
# ======================================================
st.sidebar.success(f"👤 {st.session_state.user['name']}")
if st.sidebar.button("Вийти"):
    st.session_state.logged_in = False
    st.session_state.splash_done = False
    st.rerun()

tabs = st.tabs(["🚀 Польоти", "📊 Аналітика", "ℹ️ Довідка"])

# ------------------------------------------------------
# FLIGHTS
# ------------------------------------------------------
with tabs[0]:
    st.header("🚀 Внесення польотів")

    date_raw = st.text_input("Дата (ддммрр)")
    date = smart_date_parse(date_raw)

    t1 = st.text_input("Зміна з", "0800")
    t2 = st.text_input("Зміна до", "2000")

    route = st.text_input("Маршрут")

    drones = get_unit_drones(st.session_state.user["unit"])
    drone_opts = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in drones] or BASE_DRONES
    drone = st.selectbox("БпЛА", drone_opts)

    st.divider()

    z = smart_time_parse(st.text_input("Зліт"))
    p = smart_time_parse(st.text_input("Посадка"))
    dur = calculate_duration(z, p)

    st.info(f"⏳ {dur} хв")

    if st.button("➕ ДОДАТИ") and date and z and p:
        st.session_state.temp_flights.append({
            "Дата": date,
            "Час завдання": f"{t1}-{t2}",
            "Підрозділ": st.session_state.user["unit"],
            "Оператор": st.session_state.user["name"],
            "Дрон": drone,
            "Маршрут": route,
            "Зліт": z.strftime("%H:%M"),
            "Посадка": p.strftime("%H:%M"),
            "Тривалість (хв)": dur,
            "Примітки": ""
        })
        st.success("Додано")

    if st.session_state.temp_flights:
        st.dataframe(pd.DataFrame(st.session_state.temp_flights))
        if st.button("🚀 ВІДПРАВИТИ"):
            db = load_data("Sheet1", 0)
            df_new = pd.DataFrame(st.session_state.temp_flights)
            conn.update("Sheet1", pd.concat([db, df_new], ignore_index=True))
            send_telegram_master(st.session_state.temp_flights)
            st.session_state.temp_flights.clear()
            st.success(random.choice(MOTIVATION_MSGS))

# ------------------------------------------------------
# STATS
# ------------------------------------------------------
with tabs[1]:
    df = load_data("Sheet1")
    if not df.empty:
        df = df[df["Оператор"] == st.session_state.user["name"]]
        df["dt"] = pd.to_datetime(df["Дата"], format="%d.%m.%Y", errors="coerce")
        df["Y"] = df["dt"].dt.year
        df["M"] = df["dt"].dt.month
        g = df.groupby(["Y", "M"]).agg(
            Вильоти=("Дата", "count"),
            Наліт_хв=("Тривалість (хв)", "sum")
        ).reset_index()
        g["Місяць"] = g.apply(lambda x: f"{UKR_MONTHS.get(x.M)} {int(x.Y)}", axis=1)
        st.table(g[["Місяць", "Вильоти", "Наліт_хв"]])

# ------------------------------------------------------
# INFO
# ------------------------------------------------------
with tabs[2]:
    st.markdown("### ℹ️ Контакти")
    st.markdown("**Інструктор:** Олександр  \n📞 +380502310609")
    st.markdown("**Технік:** Сергій  \n📞 +380997517054")
    st.markdown("**Склад:** Ірина  \n📞 +380667869701")
    st.markdown("---\n🇺🇦 **Слава Україні!**")