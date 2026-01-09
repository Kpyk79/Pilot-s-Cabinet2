import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time
from datetime import datetime, time as d_time, timedelta

# --- 1. КОНФІГУРАЦІЯ ---
st.set_page_config(
    page_title="UAV Pilot Cabinet v7.2",
    layout="wide",
    page_icon="🛡️"
)

def get_secret(key):
    val = st.secrets.get(key)
    if val:
        return val
    try:
        return st.secrets["connections"]["gsheets"].get(key)
    except:
        return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ---
UNITS = [
    "впс Кодима","віпс Шершенці","віпс Загнітків","впс Станіславка",
    "віпс Тимкове","віпс Чорна","впс Окни","віпс Ткаченкове",
    "віпс Гулянка","віпс Новосеменівка","впс Великокомарівка",
    "віпс Павлівка","впс Велика Михайлівка","віпс Слов'яносербка",
    "віпс Гребеники","впс Степанівка","віпс Кучурган",
    "віпс Лиманське","віпс Лучинське","УПЗ"
]

DRONES = [
    "DJI Mavic 3 Pro","DJI Mavic 3E","DJI Mavic 3T",
    "DJI Matrice 30T","DJI Matrice 300",
    "Autel Evo Max 4T","Skydio X2D","Puma LE"
]

ADMIN_PASSWORD = "admin_secret"

UKR_MONTHS = {
    1:"січень",2:"лютий",3:"березень",4:"квітень",
    5:"травень",6:"червень",7:"липень",8:"серпень",
    9:"вересень",10:"жовтень",11:"листопад",12:"грудень"
}

# --- 3. ДОПОМІЖНІ ---
def calculate_duration(start, end):
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def format_to_time_str(total_minutes):
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{int(h):02d}:{int(m):02d}"

# --- 4. БАЗА + TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID:
        return

    first = all_fl[0]
    flights_txt = "\n".join(
        [f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)"
         for i, f in enumerate(all_fl)]
    )

    report = (
        f"🚁 **Донесення: {first['Підрозділ']}**\n"
        f"👤 **Пілот:** {first['Оператор']}\n"
        f"📅 **Дата:** {first['Дата']}\n"
        f"🛡 **БпЛА:** {first['Дрон']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🚀 **Вильоти:**\n{flights_txt}"
    )

    sent_media = False
    for fl in all_fl:
        for img in fl.get("files", []):
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                files={"photo": (img.name, img.getvalue(), img.type)},
                data={"chat_id": TG_CHAT_ID, "caption": report, "parse_mode": "Markdown"}
            )
            sent_media = True

    if not sent_media:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": report, "parse_mode": "Markdown"}
        )

# --- 5. STATE ---
for k, v in {
    "temp_flights": [],
    "logged_in": False,
    "splash_done": False,
    "uploader_key": 0
}.items():
    st.session_state.setdefault(k, v)

# --- PERSISTENT USER MEMORY ---
qp = st.experimental_get_query_params()
st.session_state.setdefault("last_unit", qp.get("unit", [None])[0])
st.session_state.setdefault("last_name", qp.get("name", [None])[0])

# --- 6. SPLASH ---
if not st.session_state.splash_done:
    st.markdown(
        "<h1 style='text-align:center'>🛡️ UAV PILOT CABINET</h1>",
        unsafe_allow_html=True
    )
    bar = st.progress(0)
    for i in range(100):
        time.sleep(0.01)
        bar.progress(i+1)
    st.session_state.splash_done = True
    st.rerun()

# --- 7. LOGIN ---
if not st.session_state.logged_in:
    st.header("🛡️ ВХІД У СИСТЕМУ")
    role = st.radio("Режим", ["Пілот", "Адміністратор"], horizontal=True)

    if role == "Пілот":
        unit = st.selectbox(
            "Підрозділ",
            UNITS,
            index=UNITS.index(st.session_state.last_unit)
            if st.session_state.last_unit in UNITS else 0
        )

        name = st.text_input(
            "Звання та Прізвище",
            value=st.session_state.last_name or ""
        )

        if st.button("УВІЙТИ") and name:
            st.session_state.logged_in = True
            st.session_state.role = "Pilot"
            st.session_state.user = {"unit": unit, "name": name}

            st.session_state.last_unit = unit
            st.session_state.last_name = name
            st.experimental_set_query_params(unit=unit, name=name)

            df_d = load_data("Drafts")
            if not df_d.empty and "Оператор" in df_d.columns:
                st.session_state.temp_flights = df_d[
                    df_d["Оператор"] == name
                ].to_dict("records")

            st.rerun()

    else:
        pwd = st.text_input("Пароль", type="password")
        if st.button("ВХІД") and pwd == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.role = "Admin"
            st.rerun()

# --- 8. MAIN ---
else:
    st.sidebar.write(f"👤 {st.session_state.user['name']}")
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.splash_done = False
        st.rerun()

    tab_app, tab_f, tab_cus, tab_hist, tab_stat = st.tabs(
        ["📋 Заявка","🚀 Польоти","📡 ЦУС","📜 Архів","📊 Аналітика"]
    )

    # ---------- ПОЛЬОТИ ----------
    with tab_f:
        st.header("🚀 Польоти")

        c1, c2, c3 = st.columns(3)
        m_date = c1.date_input("Дата завдання", datetime.now())
        m_start = c2.time_input("Зміна з", d_time(8,0))
        m_end = c3.time_input("Зміна до", d_time(20,0))

        st.selectbox("БпЛА на зміну", DRONES, key="sel_drone_val")

        with st.expander("➕ ДОДАТИ ВИЛІТ", expanded=True):
            c1, c2, c3 = st.columns(3)
            t_off = c1.time_input("Взльот", d_time(9,0))
            t_land = c2.time_input("Посадка", d_time(9,30))

            dur = calculate_duration(t_off, t_land)
            c3.markdown(f"⏳ **{dur} хв**")

            dist = st.number_input("Дистанція (м)", 0)
            akb = st.text_input("Номер АКБ")
            cyc = st.number_input("Цикли АКБ", 0)
            res = st.selectbox("Результат", ["Без ознак порушення","Затримання","Виявлення цілі"])
            note = st.text_area("Примітки")
            files = st.file_uploader(
                "Скріншоти",
                accept_multiple_files=True,
                key=f"up_{st.session_state.uploader_key}"
            )

            if st.button("✅ ДОДАТИ"):
                st.session_state.temp_flights.append({
                    "Дата": m_date.strftime("%d.%m.%Y"),
                    "Підрозділ": st.session_state.user["unit"],
                    "Оператор": st.session_state.user["name"],
                    "Дрон": st.session_state.sel_drone_val,
                    "Взльот": t_off.strftime("%H:%M"),
                    "Посадка": t_land.strftime("%H:%M"),
                    "Тривалість (хв)": dur,
                    "Дистанція (м)": dist,
                    "Номер АКБ": akb,
                    "Цикли АКБ": cyc,
                    "Результат": res,
                    "Примітки": note,
                    "files": files
                })
                st.session_state.uploader_key += 1
                st.rerun()

        if st.session_state.temp_flights:
            st.dataframe(pd.DataFrame(st.session_state.temp_flights))

            if st.button("💾 Зберегти в Хмару"):
                df = load_data("Drafts")
                df = df[df["Оператор"] != st.session_state.user["name"]] if not df.empty else df
                conn.update(
                    worksheet="Drafts",
                    data=pd.concat(
                        [df, pd.DataFrame(st.session_state.temp_flights).drop(columns=["files"], errors="ignore")]
                    )
                )
                st.success("Збережено")

            if st.button("🚀 ВІДПРАВИТИ"):
                send_telegram_msg(st.session_state.temp_flights)
                st.session_state.temp_flights = []
                st.success("Надіслано")