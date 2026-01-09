import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import os
import time
import json
import random
from datetime import datetime, time as d_time, timedelta

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v10.3", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ТА СЛОВНИКИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
BASE_DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300"]
UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

MOTIVATION_MSGS = ["Дякуємо за службу! 🇺🇦", "Все буде Україна! 🇺🇦", "Чудова робота, пілоте!", "Сталевий облік прийняв дані.", "Героям Слава!"]

# --- 3. ІНІЦІАЛІЗАЦІЯ СТАНУ СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'reset_trigger' not in st.session_state: st.session_state.reset_trigger = 0
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 5000
if 'history' not in st.session_state: st.session_state.history = {'name': [], 'phone': [], 'route': [], 'note': []}
if 'last_unit' not in st.session_state: st.session_state.last_unit = UNITS[0]

# --- 4. ДОПОМІЖНІ ФУНКЦІЇ ---
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

def smart_date_parse(val):
    val = "".join(filter(str.isdigit, val))
    if not val: return None
    try:
        if len(val) == 6: d, m, y = int(val[:2]), int(val[2:4]), int("20" + val[4:])
        elif len(val) == 4: d, m, y = int(val[0]), int(val[1]), int("20" + val[2:])
        else: return None
        return datetime(y, m, d).strftime("%d.%m.%Y")
    except: return None

def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def add_to_history(key, value):
    if value and value.strip() and value not in st.session_state.history[key]:
        st.session_state.history[key].insert(0, value.strip())
        st.session_state.history[key] = st.session_state.history[key][:15]

def send_telegram_master(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    flights_txt = "\n".join([f"🚀 {f['Зліт']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for f in all_fl])
    report = (f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n⏰ **Час виконання завдання:** {first['Час завдання']}\n🛡 **БпЛА:** {first['Дрон']}\n📍 **Маршрут:** {first['Маршрут']}\n━━━━━━━━━━━━━━━\n📋 **Вильоти:**\n{flights_txt}\n━━━━━━━━━━━━━━━\n✅ **Результат:** {first['Результат']}\n📝 **Примітки:** {first['Примітки'] if first['Примітки'] else '---'}")
    all_media = []
    for f in all_fl:
        if f.get('files'):
            for img in f['files']: all_media.append(img)
    if all_media:
        media_group = []
        files = {}
        for i, img in enumerate(all_media[:10]):
            file_key = f"photo{i}"; media_group.append({"type": "photo", "media": f"attach://{file_key}", "caption": report if i == 0 else "", "parse_mode": "Markdown"}); files[file_key] = (img.name, img.getvalue(), img.type)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup", data={"chat_id": str(TG_CHAT_ID), "media": json.dumps(media_group)}, files=files)
    else: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": str(TG_CHAT_ID), "text": report, "parse_mode": "Markdown"})

# --- 5. РОБОТА З БАЗОЮ ---
conn = st.connection("gsheets", type=GSheetsConnection)
def load_data(ws="Sheet1", ttl_val=60):
    try:
        df = conn.read(worksheet=ws, ttl=ttl_val)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except: return pd.DataFrame()

drones_db = load_data("DronesDB")
def get_unit_drones(unit_name):
    if drones_db.empty or "Підрозділ" not in drones_db.columns: return []
    return drones_db[drones_db['Підрозділ'] == unit_name].to_dict('records')

# --- 6. СТИЛІ ---
st.markdown("""<style>
    .stButton>button { width: 100%; border-radius: 10px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .duration-box { background-color: rgba(46, 125, 50, 0.1); padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #2E7D32; font-size: 1.2em; font-weight: bold; }
    .contact-card { background-color: rgba(46, 125, 50, 0.05); padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; }
    .disclaimer { font-size: 0.9em; color: #d32f2f; font-weight: bold; padding: 12px; border: 1px dashed #d32f2f; border-radius: 8px; margin-bottom: 15px; }
    </style>""", unsafe_allow_html=True)

# --- 7. SPLASH SCREEN ---
if not st.session_state.splash_done:
    st.markdown("<div style='text-align:center; margin-top:20%;'><h1>🛡️ UAV CABINET</h1><p>ЗАВАНТАЖЕННЯ v10.3...</p></div>", unsafe_allow_html=True)
    my_bar = st.progress(0)
    for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
    st.session_state.splash_done = True; st.rerun()

# --- 8. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД</h2>", unsafe_allow_html=True)
    with st.container(border=True):
        # Пам'ять підрозділу
        idx = UNITS.index(st.session_state.last_unit) if st.session_state.last_unit in UNITS else 0
        u = st.selectbox("Підрозділ:", UNITS, index=idx)
        st.session_state.last_unit = u
        
        # Вибір з історії
        h_names = st.session_state.history['name']
        n_choice = st.selectbox("Оберіть з історії (Прізвище):", ["-- Ввести нове --"] + h_names) if h_names else None
        n = st.text_input("Звання та Прізвище:", value=n_choice if n_choice and n_choice != "-- Ввести нове --" else "", placeholder="Напр: сержант Петренко")
        
        if st.button("УВІЙТИ") and n:
            add_to_history('name', n)
            st.session_state.logged_in, st.session_state.user = True, {"unit": u, "name": n}; st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tab_f, tab_app, tab_cus, tab_hist, tab_stat, tab_info = st.tabs(["🚀 Польоти", "📋 Помічник формування заявки", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    with tab_f:
        st.header("🚀 Внесення польотів")
        with st.container(border=True):
            c1, c2 = st.columns(2); c3, c4 = st.columns(2)
            d_inp = c1.text_input("Дата польоту (ддммрр)", value=st.session_state.get('cur_date_raw', ""), placeholder="Напр: 090126")
            st.session_state.cur_date_raw = d_inp
            parsed_d = smart_date_parse(d_inp)
            if parsed_d: c1.caption(f"✅ {parsed_d}")
            t_s_raw = c2.text_input("Зміна з", value=st.session_state.get('cur_t_s', ""), placeholder="0800")
            st.session_state.cur_t_s = t_s_raw
            t_e_raw = c3.text_input("Зміна до", value=st.session_state.get('cur_t_e', ""), placeholder="2000")
            st.session_state.cur_t_e = t_e_raw
            h_routes = st.session_state.history['route']
            r_hist = st.selectbox("Історія маршрутів:", ["-- Новий --"] + h_routes)
            m_route = c4.text_input("Маршрут завдання:", value=r_hist if r_hist != "-- Новий --" else "", placeholder="Напрямок")
            u_d = get_unit_drones(st.session_state.user['unit'])
            d_opts = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_d] if u_d else BASE_DRONES
            sel_drone = st.selectbox("🛡️ БпЛА НА ЗМІНУ (s/n):", d_opts)

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            rt = st.session_state.reset_trigger
            col1, col2 = st.columns(2)
            t_z = col1.text_input("Зліт", key=f"z_{rt}", placeholder="0900")
            t_p = col2.text_input("Посадка", key=f"p_{rt}", placeholder="0930")
            p_z, p_p = smart_time_parse(t_z), smart_time_parse(t_p)
            dur = calculate_duration(p_z, p_p) if p_z and p_p else 0
            st.markdown(f"<div class='duration-box'>⏳ {dur} хв</div>", unsafe_allow_html=True)
            col3, col4 = st.columns(2)
            f_dst = col3.number_input("Відстань (м)", min_value=0, key=f"d_{rt}", value=0)
            f_akb = col4.text_input("Номер АКБ", key=f"a_{rt}", placeholder="01")
            f_cyc = st.number_input("Цикли АКБ", min_value=0, key=f"c_{rt}", value=0)
            h_notes = st.session_state.history['note']
            n_hist_note = st.selectbox("Історія приміток:", ["-- Нова --"] + h_notes)
            f_note = st.text_area("Примітки", key=f"n_{rt}", value=n_hist_note if n_hist_note != "-- Нова --" else "", placeholder="Напр: Польоти не здійснювались...")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")

            if st.button("✅ ДОДАТИ У СПИСОК") and p_z and p_p and parsed_d:
                add_to_history('route', m_route); add_to_history('note', f_note)
                st.session_state.temp_flights.append({"Дата": parsed_d, "Час завдання": f"{t_s_raw} - {t_e_raw}", "Підрозділ": st.session_state.user['unit'], "Оператор": st.session_state.user['name'], "Дрон": sel_drone, "Маршрут": m_route, "Зліт": p_z.strftime("%H:%M"), "Посадка": p_p.strftime("%H:%M"), "Тривалість (хв)": dur, "Дистанція (м)": f_dst, "Номер АКБ": f_akb, "Цикли АКБ": f_cyc, "Результат": "Виконано", "Примітки": f_note, "files": f_imgs})
                st.session_state.reset_trigger += 1; st.session_state.uploader_key += 1; st.rerun()

        if st.session_state.temp_flights:
            st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Зліт", "Посадка", "Тривалість (хв)", "Номер АКБ"]], use_container_width=True)
            if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                db = load_data("Sheet1", 0)
                final = [{k: v for k, v in f.items() if k != 'files'} for f in st.session_state.temp_flights]
                conn.update(worksheet="Sheet1", data=pd.concat([db, pd.DataFrame(final)], ignore_index=True))
                send_telegram_master(st.session_state.temp_flights)
                st.success(random.choice(MOTIVATION_MSGS))
                st.session_state.temp_flights = []; time.sleep(2); st.rerun()

    with tab_app:
        st.header("📋 Помічник формування заявки")
        st.markdown("<div class='disclaimer'>⚠️ Даний розділ не відправляє заявку на ЦУС.</div>", unsafe_allow_html=True)
        with st.container(border=True):
            a_u = st.selectbox("Заявник:", UNITS, index=idx)
            u_db = get_unit_drones(a_u)
            d_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_db] if u_db else BASE_DRONES
            sel_d = st.multiselect("Типи БпЛА:", d_o)
            a_dt = st.date_input("Дати:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2); a_t1 = c_t1.text_input("Час з:", "0800"); a_t2 = c_t2.text_input("Час до:", "2000")
            h_r = st.session_state.history['route']
            ar_h = st.selectbox("Історія маршрутів (заявка):", ["-- Новий --"] + h_r)
            app_r = st.text_area("Маршрут:", value=ar_h if ar_h != "-- Новий --" else "")
            
            # НОВЕ ПОЛЕ ТЕЛЕФОНУ
            h_p = st.session_state.history['phone']
            p_h_choice = st.selectbox("Минулі контакти:", ["-- Новий --"] + h_p)
            app_contact_name = st.text_input("9. Контактна особа (Прізвище):", value=st.session_state.user['name'])
            app_phone = st.text_input("Номер телефону для зворотного зв'язку:", value=p_h_choice if p_h_choice != "-- Новий --" else "", placeholder="+380...")
            
            if st.button("✨ СФОРМУВАТИ"):
                add_to_history('phone', app_phone)
                dt_str = f"з {a_dt[0].strftime('%d.%m.%Y')} по {a_dt[1].strftime('%d.%m.%Y')}" if isinstance(a_dt, tuple) and len(a_dt)==2 else a_dt[0].strftime('%d.%m.%Y')
                st.code(f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({a_u})\n2. Тип: {sel_d}\n3. Дати: {dt_str}\n4. Час: {a_t1}-{a_t2}\n5. Маршрут: {app_r}\n8. Мета: патрулювання\n9. Контактна особа: {app_contact_name}, тел: {app_phone}", language="text")

    with tab_cus:
        if st.session_state.temp_flights:
            st.code("\n".join([f"{f['Зліт']} - {f['Посадка']} ({f['Тривалість (хв)']} хв)" for f in st.session_state.temp_flights]), language="text")
    
    with tab_hist:
        df_h = load_data("Sheet1")
        if not df_h.empty: st.dataframe(df_h[df_h['Оператор'] == st.session_state.user['name']].sort_values(by="Дата", ascending=False), use_container_width=True)
    
    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty:
            df_p = df_s[df_s['Оператор'] == st.session_state.user['name']].copy()
            if not df_p.empty:
                df_p['dt'] = pd.to_datetime(df_p['Дата'], format='%d.%m.%Y', errors='coerce')
                # ВИПРАВЛЕННЯ ValueError: Групуємо через змінні
                df_p['Year'] = df_p['dt'].dt.year
                df_p['Month'] = df_p['dt'].dt.month
                rs = df_p.groupby(['Year', 'Month']).agg(Вильоти=('Дата', 'count'), Наліт_хв=('Тривалість (хв)', 'sum')).reset_index()
                rs['Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['Month']), '???')} {int(x['Year'])}", axis=1)
                st.table(rs[['Місяць', 'Вильоти', 'Наліт_хв']])

    with tab_info:
        st.header("ℹ️ Довідка")
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown("<div class='contact-card'><b>🎓 Олександр</b><br>Інструктор<br>+380502310609</div>", unsafe_allow_html=True)
        with c2: st.markdown("<div class='contact-card'><b>🔧 Сергій</b><br>Технік<br>+380997517054</div>", unsafe_allow_html=True)
        with c3: st.markdown("<div class='contact-card'><b>📦 Ірина</b><br>Склад<br>+380667869701</div>", unsafe_allow_html=True)
