import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import os
import time
from datetime import datetime, time as d_time, timedelta

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v7.7", layout="wide", page_icon="🛡️")

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
    except:
        return pd.DataFrame()

# Завантажуємо БД дронів
drones_db = load_data("DronesDB")

def get_unit_drones(unit_name):
    if drones_db.empty or "Підрозділ" not in drones_db.columns: return []
    return drones_db[drones_db['Підрозділ'] == unit_name].to_dict('records')

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    flights_txt = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for i, f in enumerate(all_fl)])
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n🛡 **БпЛА:** {first['Дрон']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}"
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
    .stAlert p { color: black !important; }
    </style>""", unsafe_allow_html=True)

# --- 6. SPLASH SCREEN ---
if not st.session_state.splash_done:
    st.markdown("<div style='text-align:center; margin-top:15%;'><h1>🛡️ UAV PILOT CABINET</h1><p style='color:#2E7D32; font-weight:bold;'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</p></div>", unsafe_allow_html=True)
    my_bar = st.progress(0, text="Завантаження конфігурації...")
    for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
    st.session_state.splash_done = True; st.rerun()

# --- 7. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД</h2>", unsafe_allow_html=True)
    role = st.radio("Статус:", ["Пілот", "Адміністратор"], horizontal=True)
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
            p = st.text_input("Пароль:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in = True; st.session_state.user = {"unit": "Адмін", "name": "Адмін"}; st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tab_app, tab_f, tab_cus, tab_hist, tab_stat, tab_info = st.tabs(["📋 Заявка", "🚀 Польоти", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    # --- ВКЛАДКА ЗАЯВКА (ПОВНА) ---
    with tab_app:
        st.header("📝 Формування заявки")
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            unit_d = get_unit_drones(app_unit)
            d_opts = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in unit_d] if unit_d else BASE_DRONES
            sel_full = st.multiselect("2. Тип БпЛА:", d_opts)
            
            if unit_d and sel_full:
                m_list = list(set([s.split(" (s/n:")[0] for s in sel_full]))
                s_list = [s.split("s/n: ")[1].replace(")", "") for s in sel_full]
                app_sn = ", ".join(s_list); app_models = ", ".join(m_list)
            else:
                app_sn = st.text_input("s/n (вручну):"); app_models = ", ".join(sel_full)
            
            app_dates = st.date_input("3. Дати польоту:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2); a_t1 = c_t1.time_input("4. Час з:", d_time(8,0)); a_t2 = c_t2.time_input("Час до:", d_time(20,0))
            app_route = st.text_area("5. Маршрут (н.п. та район):")
            c_h1, c_h2 = st.columns(2); a_h = c_h1.text_input("6. Висота (м):", "до 500 м"); a_r = c_h2.text_input("7. Радіус (км):", "до 5 км")
            app_purp = st.selectbox("8. Мета:", ["патрулювання ділянки", "оперативна необхідність", "навчальні польоти"])
            app_cont = st.text_input("9. Контактна особа:", f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ СФОРМУВАТИ ТЕКСТ"):
            d_str = f"{app_models} ({app_sn})" if app_sn else app_models
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дати: {dt_r}\n4. Час: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Маршрут: {app_route}\n6. Висота: {a_h}\n7. Радіус: {a_r}\n8. Мета: {app_purp}\n9. Контакт: {app_cont}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА ПОЛЬОТИ (З ГНУЧКИМ ЧАСОМ ТА ХМАРОЮ) ---
    with tab_f:
        st.header("Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="m_start_val")
            m_end = c3.time_input("Зміна до", d_time(20,0), key="m_end_val")
            m_route = c4.text_input("Загальний маршрут", key="m_route_val")
            my_d = get_unit_drones(st.session_state.user['unit'])
            my_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in my_d] if my_d else BASE_DRONES
            st.selectbox("🛡️ БпЛА НА ЗМІНУ:", my_o, key="sel_drone_val")

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            t_o_s = col1.text_input("Взльот", "09:00", help="930 -> 09:30")
            t_l_s = col2.text_input("Посадка", "09:30")
            p_o, p_l = smart_time_parse(t_o_s), smart_time_parse(t_l_s)
            if p_o and p_l:
                dur = calculate_duration(p_o, p_l); col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key="f_dist")
            cb1, cb2 = st.columns(2); f_akb = cb1.text_input("АКБ №", key="f_akb"); f_cyc = cb2.number_input("Цикли", min_value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"])
            f_note = st.text_area("Примітки")
            if st.button("✅ ДОДАТИ У СПИСОК") and p_o and p_l:
                st.session_state.temp_flights.append({
                    "Дата": m_date.strftime("%d.%m.%Y"), "Час завдання": f"{m_start.strftime('%H:%M')}-{m_end.strftime('%H:%M')}",
                    "Підрозділ": st.session_state.user['unit'], "Оператор": st.session_state.user['name'], "Дрон": st.session_state.sel_drone_val,
                    "Маршрут": m_route, "Взльот": p_o.strftime("%H:%M"), "Посадка": p_l.strftime("%H:%M"),
                    "Тривалість (хв)": dur, "Дистанція (м)": f_dist, "Номер АКБ": f_akb, "Цикли АКБ": f_cyc, "Результат": f_res, "Примітки": f_note
                }); st.rerun()

        if st.session_state.temp_flights:
            df_curr = pd.DataFrame(st.session_state.temp_flights)
            st.dataframe(df_curr[["Взльот", "Посадка", "Тривалість (хв)", "Номер АКБ"]], use_container_width=True)
            b1, b2, b3 = st.columns(3)
            if b1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            
            if b2.button("💾 Зберегти в Хмару"):
                try:
                    df_d = load_data("Drafts")
                    if not df_d.empty and "Оператор" in df_d.columns:
                        df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                    conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights)], ignore_index=True))
                    st.success("💾 Збережено!")
                except Exception as e: st.error(f"Помилка аркуша Drafts: {e}")

            if b3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                try:
                    db_m = load_data("Sheet1")
                    conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(st.session_state.temp_flights)], ignore_index=True))
                    # Очищення чернетки
                    df_d = load_data("Drafts")
                    if not df_d.empty and "Оператор" in df_d.columns:
                        cleaned = df_d[df_d['Оператор'] != st.session_state.user['name']]
                        conn.update(worksheet="Drafts", data=cleaned)
                    send_telegram_msg(st.session_state.temp_flights)
                    st.session_state.temp_flights = []; st.success("✅ Надіслано!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Помилка відправки: {e}")

    # --- ВКЛАДКА ЦУС (ПОВНА) ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if st.session_state.temp_flights:
            all_f = st.session_state.temp_flights; s_start = st.session_state.m_start_val; b_m, a_m, cr = [], [], False
            for f in all_f:
                fs = datetime.strptime(f['Взльот'], "%H:%M").time(); fe = datetime.strptime(f['Посадка'], "%H:%M").time()
                if cr or fe < fs or fs < s_start: cr = True; a_m.append(f)
                else: b_m.append(f)
            def fc(fls): return "\n".join([f"{f['Взльот']} - {f['Посадка']} - {f['Дистанція (м)']} м ({f['Тривалість (хв)']} хв)" for f in fls])
            st.subheader("🌙 До 00:00"); st.code(fc(b_m), language="text"); st.subheader("☀️ Після 00:00"); st.code(fc(a_m), language="text")

    # --- ВКЛАДКИ АРХІВ ТА АНАЛІТИКА ---
    with tab_hist:
        st.header("📜 Архів")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']]
            if not p_df.empty: st.dataframe(p_df.sort_values(by="Дата", ascending=False), use_container_width=True)

    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns and "Дата" in df_s.columns:
            df_s = df_s[df_s['Оператор'] == st.session_state.user['name']]
            if not df_s.empty:
                df_s['dt'] = pd.to_datetime(df_s['Дата'], format='%d.%m.%Y', errors='coerce')
                df_s = df_s.dropna(subset=['dt'])
                rs = df_s.groupby([df_s['dt'].dt.year, df_s['dt'].dt.month]).agg(Польоти=('Дата', 'count'), Хв=('Тривалість (хв)', 'sum')).reset_index()
                rs['⏱ Наліт'] = rs['Хв'].apply(format_to_time_str)
                st.table(rs[['dt', 'Польоти', '⏱ Наліт']])

    # --- ВКЛАДКА ДОВІДКА (ЧОРНИЙ ШРИФТ) ---
    with tab_info:
        st.header("ℹ️ Для довідки")
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown("<div class='contact-card'><b class='contact-title'>🎓 Інструктор Олександр</b><br><span class='contact-desc'>+380502310609</span></div>", unsafe_allow_html=True)
        with c2: st.markdown("<div class='contact-card'><b class='contact-title'>🔧 Технік Сергій</b><br><span class='contact-desc'>+380997517054</span></div>", unsafe_allow_html=True)
        with c3: st.markdown("<div class='contact-card'><b class='contact-title'>📦 Склад Ірина</b><br><span class='contact-desc'>+380667869701</span></div>", unsafe_allow_html=True)
        with st.expander("🛡️ ІНСТРУКЦІЯ ПІЛОТА"): st.markdown("**1. Вхід:** Підрозділ + Прізвище.\n**2. Заявка:** Текст для месенджера.\n**3. Польоти:** Введення часу текстом (напр. 930).")
