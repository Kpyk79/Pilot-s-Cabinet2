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
    "Твій підрозділ пишається тобою. 🇺🇦",
    "Мавік у руках — спокій у серці. 🦾",
    "Прогноз на зміну: 100% успішних повернень. ✅",
    "Стріми без лагів, АКБ без просадок! ⚡",
    "Ти сьогодні — володар неба. Працюй впевнено! 🌤️"
]

# --- 3. Persistence (Збереження входу через URL) ---
# Зчитуємо дані з URL при старті
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
    mapping = {"Дрон": "БпЛА"}
    export_df = df.copy().rename(columns=mapping)
    target_cols = ["Дата", "Час завдання", "Підрозділ", "Оператор", "БпЛА", "Маршрут", "Зліт", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Номер АКБ", "Цикли АКБ"]
    final_cols = [c for c in target_cols if c in export_df.columns]
    export_df = export_df[final_cols]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Архів')
        workbook, worksheet = writer.book, writer.sheets['Архів']
        border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#2E7D32', 'color': 'white', 'border': 1, 'align': 'center'})
        for col_num, value in enumerate(export_df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            column_len = max(export_df[value].astype(str).map(len).max(), len(value)) + 2
            worksheet.set_column(col_num, col_num, min(column_len, 30), border_format)
    return output.getvalue()

# --- 5. РОБОТА З БАЗОЮ ТА TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        cache_ttl = 60 if ws == "Drafts" else 300
        df = conn.read(worksheet=ws, ttl=cache_ttl)
        if df is None or df.empty: return pd.DataFrame()
        return df.dropna(how="all")
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def get_drones_for_unit(unit):
    try:
        df = load_data("DronesDB")
        if df.empty or "Підрозділ" not in df.columns: return []
        unit_drones = df[df['Підрозділ'] == unit]
        if unit_drones.empty: return []
        return [f"{r['Модель БпЛА']} (S/N: {r['s/n']})" if pd.notna(r['s/n']) else r['Модель БпЛА'] for _, r in unit_drones.iterrows()]
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
if 'flight_form_counter' not in st.session_state: st.session_state.flight_form_counter = 0

# --- 7. СТИЛІ ---
st.markdown("""<style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; color: #1b5e20; font-size: 1.2em; }
    .splash-container { text-align: center; margin-top: 15%; }
    .slogan-box { color: #2E7D32; font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.2em; border-top: 2px solid #2E7D32; border-bottom: 2px solid #2E7D32; padding: 20px 0; margin: 20px 0; font-style: italic; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black !important; }
</style>""", unsafe_allow_html=True)

# --- 8. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        quote = random.choice(QUOTES)
        st.markdown(f"<div class='splash-container'><h1 style='font-size: 4em;'>🛡️</h1><h1>UAV PILOT CABINET</h1><div class='slogan-box'>«{quote}»</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Завантаження систем...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 9. ВХІД ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД</h2>", unsafe_allow_html=True)
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS, index=UNITS.index(st.session_state.saved_unit) if st.session_state.saved_unit in UNITS else 0)
            n = st.text_input("Звання та Прізвище:", value=st.session_state.saved_name)
            if st.button("УВІЙТИ") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n}
                # Зберігаємо в URL
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
        available_drones = get_drones_for_unit(st.session_state.user['unit'])
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="m_start_val")
            m_end = c3.time_input("Зміна до", d_time(20,0), key="m_end_val")
            m_route = c4.text_input("Маршрут", key="m_route_val")
            selected_drone = st.selectbox("🛡️ БпЛА:", available_drones if available_drones else ["Немає дронів"], key="sel_drone_val")
        
        with st.expander("➕ ДОДАТИ ВИЛІТ", expanded=True):
            f_key = st.session_state.flight_form_counter
            col1, col2, col3, col4 = st.columns(4)
            t_off = col1.text_input("Зліт", placeholder="0900", key=f"t_off_{f_key}")
            t_land = col2.text_input("Посадка", placeholder="0930", key=f"t_land_{f_key}")
            p_off, p_land = smart_time_parse(t_off), smart_time_parse(t_land)
            if p_off and p_land:
                dur = calculate_duration(p_off, p_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
                if st.button("✅ ДОДАТИ"):
                    st.session_state.temp_flights.append({
                        "Дата": m_date.strftime("%d.%m.%Y"), "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'], "Дрон": selected_drone, "Маршрут": m_route,
                        "Зліт": p_off.strftime("%H:%M"), "Посадка": p_land.strftime("%H:%M"), "Тривалість (хв)": dur,
                        "Час завдання": f"{m_start.strftime('%H:%M')}-{m_end.strftime('%H:%M')}", "Результат": "Без ознак порушення"
                    })
                    st.session_state.flight_form_counter += 1; st.rerun()

        if st.session_state.temp_flights:
            st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Зліт", "Посадка", "Тривалість (хв)"]])
            if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                all_fl = st.session_state.temp_flights
                send_telegram_msg(all_fl)
                db_m = load_data("Sheet1")
                new_db = pd.concat([db_m, pd.DataFrame(all_fl)], ignore_index=True).astype(str).replace(['None', 'nan', '<NA>'], '')
                conn.update(worksheet="Sheet1", data=new_db)
                st.session_state.temp_flights = []
                st.balloons()
                st.success(f"✅ Надіслано! Пророцтво: *{random.choice(QUOTES)}*")
                time.sleep(2); st.rerun()

    with tab_app:
        st.header("📝 Формування заявки")
        with st.container(border=True):
            app_unit = st.selectbox("Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']))
            app_drones = st.multiselect("Тип БпЛА:", get_drones_for_unit(app_unit))
            app_route = st.text_area("Маршрут:")
            app_cont = st.text_input("Контактна особа:", value=st.session_state.user['name'])
        if st.button("✨ СФОРМУВАТИ"):
            f_txt = f"ЗАЯВКА НА ПОЛІТ\nЗаявник: {app_unit}\nТип БпЛА: {', '.join(app_drones)}\nМаршрут: {app_route}\nКонтакт: {app_cont}"
            st.code(f_txt, language="text")

    with tab_hist:
        st.header("📜 Мій журнал")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']]
            if not p_df.empty:
                st.download_button("📥 Excel", convert_df_to_excel(p_df), f"log_{datetime.now().date()}.xlsx")
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
                # ВИПРАВЛЕНО: Використовуємо Дата_dt для count, щоб уникнути KeyError стовпця Дата
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
