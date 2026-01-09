import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import os
import time
from datetime import datetime, time as d_time, timedelta

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v7.6", layout="wide", page_icon="🛡️")

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
    "віпс Гребеники", "впс Степанівка", "віпс Кучурган", 
    "віпс Лиманське", "віпс Лучинське", "УПЗ"
]
BASE_DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300"]
UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

# --- 3. ДОПОМІЖНІ ФУНКЦІЇ ---
def smart_time_parse(val):
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

# --- 4. РОБОТА З БАЗОЮ ТА TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# База БпЛА
drones_db = load_data("DronesDB")

def get_unit_drones(unit_name):
    if drones_db.empty or "Підрозділ" not in drones_db.columns: return []
    return drones_db[drones_db['Підрозділ'] == unit_name].to_dict('records')

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти надіслано в архів.**"
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'})

# --- 5. СТИЛІ ТА СТАН ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

st.markdown("""<style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #1b5e20; font-size: 1.2em; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black !important; }
    .contact-title { font-size: 1.1em; font-weight: bold; color: black !important; }
    .contact-desc { font-size: 0.9em; color: black !important; font-style: italic; }
    </style>""", unsafe_allow_html=True)

# --- 6. SPLASH SCREEN ---
if not st.session_state.splash_done:
    st.markdown("<h1 style='text-align:center;'>🛡️ UAV CABINET</h1>", unsafe_allow_html=True)
    my_bar = st.progress(0, text="Перевірка зв'язку з Google Sheets...")
    for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
    st.session_state.splash_done = True; st.rerun()

# --- 7. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    role = st.radio("Вхід:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та Прізвище:")
            if st.button("УВІЙТИ") and n:
                st.session_state.logged_in, st.session_state.user = True, {"unit": u, "name": n}
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    st.session_state.temp_flights = df_d[df_d['Оператор'] == n].to_dict('records')
                st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tab_app, tab_f, tab_cus, tab_hist, tab_info = st.tabs(["📋 Заявка", "🚀 Польоти", "📡 ЦУС", "📜 Архів", "ℹ️ Довідка"])

    # --- ВКЛАДКА ЗАЯВКА (Без змін) ---
    with tab_app:
        st.header("📝 Формування заявки")
        app_unit = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']))
        unit_drones = get_unit_drones(app_unit)
        drone_options = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in unit_drones] if unit_drones else BASE_DRONES
        sel_d = st.multiselect("2. Тип БпЛА:", drone_options)
        app_dates = st.date_input("3. Дата:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
        app_route = st.text_area("5. Маршрут:")
        if st.button("✨ СФОРМУВАТИ"):
            st.code(f"ЗАЯВКА\nЗаявник: {app_unit}\nБпЛА: {sel_d}\nМаршрут: {app_route}", language="text")

    # --- ВКЛАДКА ПОЛЬОТИ (ВИПРАВЛЕНО ЗБЕРЕЖЕННЯ) ---
    with tab_f:
        st.header("Внесення польотів")
        with st.container(border=True):
            col_d, col_b = st.columns(2)
            m_date = col_d.date_input("Дата", datetime.now(), key="m_date_val")
            my_drones = get_unit_drones(st.session_state.user['unit'])
            my_opts = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in my_drones] if my_drones else BASE_DRONES
            sel_drone = col_b.selectbox("🛡️ БпЛА:", my_opts)

        with st.expander("➕ ДОДАТИ ВИЛІТ", expanded=True):
            c1, c2, c3 = st.columns(3)
            t_off = c1.text_input("Взльот", "09:00")
            t_land = c2.text_input("Посадка", "09:30")
            p_o, p_l = smart_time_parse(t_off), smart_time_parse(t_land)
            if p_o and p_l:
                dur = calculate_duration(p_o, p_l)
                c3.markdown(f"<div class='duration-box'>⏳ {dur} хв</div>", unsafe_allow_html=True)
            
            if st.button("✅ ДОДАТИ У СПИСОК"):
                if p_o and p_l:
                    st.session_state.temp_flights.append({
                        "Дата": m_date.strftime("%d.%m.%Y"),
                        "Оператор": st.session_state.user['name'],
                        "Підрозділ": st.session_state.user['unit'],
                        "Дрон": sel_drone,
                        "Взльот": p_o.strftime("%H:%M"),
                        "Посадка": p_l.strftime("%H:%M"),
                        "Тривалість (хв)": dur,
                        "Результат": "Виконано"
                    })
                    st.rerun()

        if st.session_state.temp_flights:
            st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Тривалість (хв)"]], use_container_width=True)
            
            # --- БЛОК ЗБЕРЕЖЕННЯ В ХМАРУ ---
            if st.button("💾 Зберегти в Хмару (Drafts)"):
                try:
                    df_d = load_data("Drafts")
                    # Видаляємо старі записи цього оператора
                    if not df_d.empty and "Оператор" in df_d.columns:
                        df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                    
                    # Додаємо нові
                    new_rows = pd.DataFrame(st.session_state.temp_flights)
                    updated_df = pd.concat([df_d, new_rows], ignore_index=True)
                    
                    conn.update(worksheet="Drafts", data=updated_df)
                    st.success("💾 Чернетку збережено в Google Sheets!")
                except Exception as e:
                    st.error(f"Помилка доступу до аркуша 'Drafts'. Перевірте назву аркуша та права доступу. Деталі: {e}")

            # --- БЛОК ВІДПРАВКИ ---
            if st.button("🚀 ВІДПРАВИТИ ВСЕ В АРХІВ"):
                try:
                    # 1. Запис в основну базу
                    db_main = load_data("Sheet1")
                    final_df = pd.concat([db_main, pd.DataFrame(st.session_state.temp_flights)], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=final_df)
                    
                    # 2. Очищення чернетки в хмарі
                    df_d = load_data("Drafts")
                    if not df_d.empty and "Оператор" in df_d.columns:
                        cleaned_drafts = df_d[df_d['Оператор'] != st.session_state.user['name']]
                        conn.update(worksheet="Drafts", data=cleaned_drafts)
                    
                    send_telegram_msg(st.session_state.temp_flights)
                    st.session_state.temp_flights = []
                    st.success("✅ Дані в архіві, чернетку очищено!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Помилка відправки: {e}")

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 ЦУС")
        if st.session_state.temp_flights:
            txt = "\n".join([f"{f['Взльот']} - {f['Посадка']} ({f['Тривалість (хв)']} хв)" for f in st.session_state.temp_flights])
            st.code(txt, language="text")

    # --- ВКЛАДКА АРХІВ ---
    with tab_hist:
        st.header("📜 Архів")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            st.dataframe(df_h[df_h['Оператор'] == st.session_state.user['name']], use_container_width=True)

    # --- ВКЛАДКА ДОВІДКА ---
    with tab_info:
        st.header("ℹ️ Довідка")
        st.markdown("<div class='contact-card'><b class='contact-title'>🎓 Інструктор Олександр</b><br><span class='contact-desc'>+380502310609</span></div>", unsafe_allow_html=True)
        st.markdown("<div class='contact-card'><b class='contact-title'>🔧 Технік Сергій</b><br><span class='contact-desc'>+380997517054</span></div>", unsafe_allow_html=True)
