import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time
from datetime import datetime, time as d_time, timedelta
import json
import io
import random

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v7.3", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ТА СЛОВНИКИ ---
UNITS = [
    "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", 
    "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", 
    "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", 
    "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", 
    "віпс Гребеники", "впс Степанівка", "впс Кучурган", 
    "віпс Лиманське", "віпс Лучинське", "УПЗ"
]
ADMIN_PASSWORD = "admin_secret"

UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

QUOTES = [
    "Сьогодні твій сигнал буде чистим, як совість інструктора. 📡",
    "Наліт сам себе не налітає, а ти — зможеш! 🚀",
    "Пророцтво: АКБ триматиме на 2 хвилини довше, ніж зазвичай. 🔋",
    "Нехай вітер завжди буде в хвіст, а РЕБ — у відпустці. 💨",
    "Твої очі бачать далі, ніж найтепліший тепловізор. 👀",
    "Дрон — це птах, але з твоїми руками — це кара небесна. 🛡️",
    "Сьогодні буде знахідка, яка варта премії. 🏆",
    "Пам'ятай: м'яка посадка — це не везіння, а твій скіл. 🛬",
    "Бажаю, щоб супутники ловилися швидше, ніж кава вранці. 🛰️",
    "Мавік у руках — спокій у серці. 🦾",
    "Прогноз на зміну: 100% успішних повернень. ✅",
    "Стріми без лагів, АКБ без просадок! ⚡",
    "Ти сьогодні — володар неба. Працюй впевнено! 🌤️"
]

# --- 3. Persistence (Збереження входу через URL) ---
params = st.query_params
if 'saved_unit' not in st.session_state:
    st.session_state.saved_unit = params.get("unit", UNITS[0])
if 'saved_name' not in st.session_state:
    st.session_state.saved_name = params.get("name", "")

# --- 4. ДОПОМІЖНІ ФУНКЦІЇ ---
def smart_time_parse(val):
    if not val: return None
    val = "".join(filter(str.isdigit, val))
    if not val: return None
    try:
        if len(val) <= 2: h, m = int(val), 0
        elif len(val) == 3: h, m = int(val[0]), int(val[1:])
        elif len(val) == 4: h, m = int(val[:2]), int(val[2:])
        else: return None
        if 0 <= h < 24 and 0 <= m < 60: return d_time(h, m)
    except: pass
    return None

def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def format_to_time_str(total_minutes):
    try:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{int(hours):02d}:{int(minutes):02d}"
    except: return "00:00"

@st.cache_data
def convert_df_to_excel(df):
    target_cols = ["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Зліт", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Номер АКБ", "Цикли АКБ"]
    export_df = df.copy()
    if "Модель БпЛА" in export_df.columns: export_df = export_df.rename(columns={"Модель БпЛА": "Дрон"})
    
    final_cols = [c for c in target_cols if c in export_df.columns]
    export_df = export_df[final_cols].rename(columns={"Дрон": "БпЛА"})

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Архів')
        workbook, worksheet = writer.book, writer.sheets['Архів']
        f_cell = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        f_head = workbook.add_format({'bold': True, 'bg_color': '#2E7D32', 'color': 'white', 'border': 1, 'align': 'center'})
        
        for i, col in enumerate(export_df.columns):
            worksheet.write(0, i, col, f_head)
            width = max(export_df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, width, f_cell)
    return output.getvalue()

# --- 5. РОБОТА З БАЗОЮ ТА TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        cache_ttl = 60 if ws == "Drafts" else 300
        df = conn.read(worksheet=ws, ttl=cache_ttl)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def get_drones_for_unit(unit):
    try:
        df = load_data("DronesDB")
        if df.empty or "Підрозділ" not in df.columns: return []
        ud = df[df['Підрозділ'] == unit]
        return [f"{r['Модель БпЛА']} (S/N: {r['s/n']})" if pd.notna(r['s/n']) else r['Модель БпЛА'] for _, r in ud.iterrows()]
    except: return []

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    f = all_fl[0]
    flights_txt = "\n".join([f"{i+1}. {x['Зліт']}-{x['Посадка']} ({x['Тривалість (хв)']} хв)" for i, x in enumerate(all_fl)])
    report = f"🚁 **Донесення: {f['Підрозділ']}**\n👤 **Пілот:** {f['Оператор']}\n📅 **Дата:** {f['Дата']}\n🛡 **БпЛА:** {f['Дрон']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}"
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'})

# --- 6. ІНІЦІАЛІЗАЦІЯ СТАНУ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

# --- 7. СТИЛІ ---
st.markdown("""<style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; font-weight: bold; height: 3.5em; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; color: #1b5e20; font-size: 1.2em; border: 1px solid #dee2e6; }
    .splash-container { text-align: center; margin-top: 15%; }
    .slogan-box { color: #2E7D32; font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.3em; border-top: 2px solid #2E7D32; border-bottom: 2px solid #2E7D32; padding: 20px 0; margin: 20px 0; font-style: italic; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black; }
</style>""", unsafe_allow_html=True)

# --- 8. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        q = random.choice(QUOTES)
        st.markdown(f"<div class='splash-container'><h1 style='font-size: 4em;'>🛡️</h1><h1>UAV PILOT CABINET</h1><div class='slogan-box'>«{q}»</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Завантаження систем...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 9. ВХІД ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД У СИСТЕМУ</h2>", unsafe_allow_html=True)
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS, index=UNITS.index(st.session_state.saved_unit) if st.session_state.saved_unit in UNITS else 0)
            n = st.text_input("Звання та Прізвище:", value=st.session_state.saved_name)
            if st.button("УВІЙТИ") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n}
                st.query_params.update(unit=u, name=n)
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    st.session_state.temp_flights.extend(df_d[df_d['Оператор'] == n].to_dict('records'))
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Admin", {"unit": "Адмін", "name": "Адмін"}
                st.rerun()

# --- 10. ОСНОВНИЙ ІНТЕРФЕЙС ---
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Вийти"): 
        st.session_state.logged_in, st.session_state.splash_done = False, False
        st.rerun()

    tab_f, tab_cus, tab_app, tab_hist, tab_stat, tab_info = st.tabs(["🚀 Польоти", "📡 ЦУС", "📋 Заявка", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    with tab_f:
        st.header("Внесення польотів")
        drones = get_drones_for_unit(st.session_state.user['unit'])
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата завдання", datetime.now(), key="f_date")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="f_s")
            m_end = c3.time_input("Зміна до", d_time(20,0), key="f_e")
            m_route = c4.text_input("Маршрут", placeholder="Маршрут польоту")
            sel_drone = st.selectbox("🛡️ БпЛА:", drones if drones else ["Дрон не вказано"])
        
        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            f_k = st.session_state.flight_form_counter
            col1, col2, col3, col4 = st.columns(4)
            t_o = col1.text_input("Зліт (ЧЧММ)", key=f"to_{f_k}")
            t_l = col2.text_input("Посадка (ЧЧММ)", key=f"tl_{f_k}")
            p_o, p_l = smart_time_parse(t_o), smart_time_parse(t_l)
            if p_o and p_l:
                dur = calculate_duration(p_o, p_l)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key=f"dist_{f_k}")
            cb1, cb2 = st.columns(2)
            f_akb, f_cyc = cb1.text_input("№ АКБ", key=f"akb_{f_k}"), cb2.number_input("Цикли", min_value=0, key=f"cyc_{f_k}")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key=f"res_{f_k}")
            f_note = st.text_area("Примітки", key=f"note_{f_k}")
            
            if st.button("✅ ДОДАТИ У СПИСОК") and p_o and p_l:
                st.session_state.temp_flights.append({
                    "Дата": m_date.strftime("%d.%m.%Y"), "Час завдання": f"{m_start.strftime('%H:%M')}-{m_end.strftime('%H:%M')}",
                    "Підрозділ": st.session_state.user['unit'], "Оператор": st.session_state.user['name'],
                    "Дрон": sel_drone, "Маршрут": m_route, "Зліт": p_o.strftime("%H:%M"), "Посадка": p_l.strftime("%H:%M"),
                    "Тривалість (хв)": calculate_duration(p_o, p_l), "Дистанція (м)": f_dist,
                    "Номер АКБ": f_akb, "Цикли АКБ": f_cyc, "Результат": f_res, "Примітки": f_note
                })
                st.session_state.flight_form_counter += 1; st.rerun()

        if st.session_state.temp_flights:
            df_t = pd.DataFrame(st.session_state.temp_flights)
            st.dataframe(df_t[["Зліт", "Посадка", "Тривалість (хв)", "Номер АКБ"]], width=1000)
            if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                send_telegram_msg(st.session_state.temp_flights)
                db_m = load_data("Sheet1")
                new_db = pd.concat([db_m, pd.DataFrame(st.session_state.temp_flights)], ignore_index=True).astype(str).replace(['None', 'nan', '<NA>'], '')
                conn.update(worksheet="Sheet1", data=new_db)
                st.session_state.temp_flights = []
                st.balloons()
                st.success(f"✅ Надіслано! Пророцтво: *{random.choice(QUOTES)}*")
                time.sleep(2); st.rerun()

    with tab_app:
        st.header("📝 Формування заявки")
        with st.container(border=True):
            a_u = st.selectbox("Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            a_d = st.multiselect("Тип БпЛА:", get_drones_for_unit(a_u))
            a_dt = st.date_input("Дата польоту", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            a_r = st.text_area("Маршрут (НП)")
            a_c = st.text_input("Контактна особа", value=st.session_state.user['name'])
            a_p = st.text_input("Телефон")
        if st.button("✨ СФОРМУВАТИ"):
            d_s = ", ".join(a_d) if a_d else "не вказано"
            dt_s = f"з {a_dt[0].strftime('%d.%m.%Y')} по {a_dt[1].strftime('%d.%m.%Y')}" if isinstance(a_dt, tuple) and len(a_dt)==2 else a_dt[0].strftime('%d.%m.%Y')
            f_txt = f"ЗАЯВКА НА ПОЛІТ\nЗаявник: в/ч 2196 ({a_u})\nТип БпЛА: {d_s}\nДата: {dt_s}\nМаршрут: {a_r}\nКонтакт: {a_c}, тел: {a_p}"
            st.code(f_txt, language="text")

    with tab_hist:
        st.header("📜 Мій журнал")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']]
            if not p_df.empty:
                st.download_button("📥 Завантажити в Excel", convert_df_to_excel(p_df), f"log_{datetime.now().date()}.xlsx")
                st.dataframe(p_df.sort_values(by="Дата", ascending=False))

    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns:
            df_s = df_s[df_s['Оператор'] == st.session_state.user['name']]
            df_s['Дата_dt'] = pd.to_datetime(df_s['Дата'], format='%d.%m.%Y', errors='coerce')
            df_s = df_s.dropna(subset=['Дата_dt'])
            if not df_s.empty:
                df_s['Рік'] = df_s['Дата_dt'].dt.year
                df_s['Місяць_№'] = df_s['Дата_dt'].dt.month
                rs = df_s.groupby(['Рік', 'Місяць_№']).agg(Польоти=('Дата_dt', 'count'), Хв=('Тривалість (хв)', 'sum')).reset_index()
                rs['Період'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['Місяць_№']), '???')} {int(x['Рік'])}", axis=1)
                rs['Наліт'] = rs['Хв'].apply(format_to_time_str)
                st.table(rs.sort_values(by=['Рік', 'Місяць_№'], ascending=False)[['Період', 'Польоти', 'Наліт']])

    with tab_info:
        st.header("ℹ️ Довідка")
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown("<div class='contact-card'>🎓 **Інструктор**<br>Олександр<br>+380502310609</div>", unsafe_allow_html=True)
        with c2: st.markdown("<div class='contact-card'>🔧 **Технік**<br>Сергій<br>+380997517054</div>", unsafe_allow_html=True)
        with c3: st.markdown("<div class='contact-card'>📦 **Склад**<br>Ірина<br>+380667869701</div>", unsafe_allow_html=True)
        st.write("---")
        with st.expander("🛡️ ПОВНА ІНСТРУКЦІЯ"):
            st.markdown("1. **Вхід:** Оберіть підрозділ та прізвище.\n2. **Польоти:** Додайте кожен виліт окремо, в кінці зміни натисніть 'Відправити'.\n3. **Архів:** Тут можна скачати історію у форматі Excel.")
