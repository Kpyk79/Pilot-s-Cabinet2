import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import os
import time
import json
import random
import re
from datetime import datetime, time as d_time, timedelta

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v10.0", layout="wide", page_icon="🛡️")

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
UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

MOTIVATION_MSGS = [
    "Дякуємо за службу! Разом до перемоги! 🇺🇦",
    "Все буде Україна! Ваша робота — очі нашого кордону!",
    "Чудова робота, пілоте! Дані в архіві.",
    "Сталевий облік прийняв дані. Героям Слава!",
    "Так тримати! Кожен виліт наближає нас до перемоги!",
    "Інформація успішно передана. Слава Україні!"
]

# --- 3. ІНІЦІАЛІЗАЦІЯ СТАНУ СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'reset_trigger' not in st.session_state: st.session_state.reset_trigger = 0
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 10000

# Історія (Persistent)
if 'history' not in st.session_state:
    st.session_state.history = {'name': [], 'phone': [], 'route': [], 'note': []}

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
    """Парсинг дати з формату 090126 або 9126 в 09.01.2026"""
    val = "".join(filter(str.isdigit, val))
    if not val: return None
    try:
        if len(val) == 4: # 9126 -> 09.01.2026
            d, m, y = int(val[0]), int(val[1]), int("20" + val[2:])
        elif len(val) == 5: # 09126 -> 09.01.2026
            d, m, y = int(val[:2]), int(val[2]), int("20" + val[3:])
        elif len(val) == 6: # 090126 -> 09.01.2026
            d, m, y = int(val[:2]), int(val[2:4]), int("20" + val[4:])
        elif len(val) == 8: # 09012026
            d, m, y = int(val[:2]), int(val[2:4]), int(val[4:])
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
    report = (
        f"🚁 **Донесення: {first['Підрозділ']}**\n"
        f"👤 **Пілот:** {first['Оператор']}\n"
        f"📅 **Дата:** {first['Дата']}\n"
        f"⏰ **Час завдання:** {first['Час завдання']}\n"
        f"🛡 **БпЛА:** {first['Дрон']}\n"
        f"📍 **Маршрут:** {first['Маршрут']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📋 **Вильоти:**\n{flights_txt}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"✅ **Результат:** {first['Результат']}\n"
        f"📝 **Примітки:** {first['Примітки'] if first['Примітки'] else '---'}"
    )
    all_media = []
    for f in all_fl:
        if f.get('files'):
            for img in f['files']: all_media.append(img)
    if all_media:
        media_group = []
        files = {}
        for i, img in enumerate(all_media[:10]):
            file_key = f"photo{i}"
            media_group.append({"type": "photo", "media": f"attach://{file_key}", "caption": report if i == 0 else "", "parse_mode": "Markdown"})
            files[file_key] = (img.name, img.getvalue(), img.type)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup", data={"chat_id": str(TG_CHAT_ID), "media": json.dumps(media_group)}, files=files)
    else:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": str(TG_CHAT_ID), "text": report, "parse_mode": "Markdown"})

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

# --- 6. СТИЛІ (Адаптація до теми) ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: rgba(46, 125, 50, 0.1); padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #2E7D32; font-size: 1.2em; font-weight: bold; }
    .contact-card { padding: 15px; border-radius: 12px; border-left: 6px solid #2E7D32; margin-bottom: 15px; background-color: rgba(46, 125, 50, 0.05); }
    .contact-title { font-size: 1.1em; font-weight: bold; margin-bottom: 5px; }
    .disclaimer { font-size: 0.9em; color: #d32f2f; font-weight: bold; padding: 12px; border: 1px dashed #d32f2f; border-radius: 8px; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 7. SPLASH SCREEN ---
if not st.session_state.splash_done:
    st.markdown("<div style='text-align:center; margin-top:20%;'><h1>🛡️ UAV CABINET</h1><p>ЗАВАНТАЖЕННЯ v10.0...</p></div>", unsafe_allow_html=True)
    my_bar = st.progress(0)
    for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
    st.session_state.splash_done = True; st.rerun()

# --- 8. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД</h2>", unsafe_allow_html=True)
    with st.container(border=True):
        u = st.selectbox("Підрозділ:", UNITS)
        h_names = st.session_state.history['name']
        n_sel = st.selectbox("Історія (Прізвище):", ["-- Нове --"] + h_names) if h_names else None
        n = st.text_input("Звання та Прізвище:", value=n_sel if n_sel and n_sel != "-- Нове --" else "", placeholder="Звання Прізвище")
        if st.button("УВІЙТИ") and n:
            add_to_history('name', n)
            st.session_state.logged_in, st.session_state.user = True, {"unit": u, "name": n}; st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tab_f, tab_app, tab_cus, tab_hist, tab_stat, tab_info = st.tabs(["🚀 Польоти", "📋 Помічник формування заявки", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("🚀 Внесення польотів")
        with st.container(border=True):
            c1, c2 = st.columns(2); c3, c4 = st.columns(2)
            
            # Новий спосіб вибору дати
            d_inp = c1.text_input("Дата польоту", value=st.session_state.get('s_date_raw', ""), placeholder="Напр: 090126")
            m_date_str = smart_date_parse(d_inp)
            if m_date_str: c1.caption(f"✅ Обрано: {m_date_str}")
            st.session_state.s_date_raw = d_inp
            
            t_start_raw = c2.text_input("Зміна з", value=st.session_state.get('s_start_raw', ""), placeholder="Напр: 0800")
            t_end_raw = c3.text_input("Зміна до", value=st.session_state.get('s_end_raw', ""), placeholder="Напр: 2000")
            
            h_routes = st.session_state.history['route']
            r_sel = st.selectbox("Історія маршрутів:", ["-- Новий --"] + h_routes)
            m_route = c4.text_input("Маршрут завдання:", value=r_sel if r_sel != "-- Новий --" else "", placeholder="Маршрут/напрямок")
            
            u_db = get_unit_drones(st.session_state.user['unit'])
            d_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_db] if u_db else ["DJI Mavic 3 Pro"]
            st.selectbox("🛡️ БпЛА НА ЗМІНУ (s/n):", d_o, key='s_drone')

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            rt = st.session_state.reset_trigger
            col1, col2 = st.columns(2)
            t_o_s = col1.text_input("Зліт", key=f"z_{rt}", placeholder="0900")
            t_l_s = col2.text_input("Посадка", key=f"l_{rt}", placeholder="0930")
            
            p_o, p_l = smart_time_parse(t_o_s), smart_time_parse(t_l_s)
            dur = calculate_duration(p_o, p_l) if p_o and p_l else 0
            st.markdown(f"<div class='duration-box'>⏳ {dur} хв</div>", unsafe_allow_html=True)
            
            col3, col4 = st.columns(2)
            f_dist = col3.number_input("Відстань (м)", min_value=0, key=f"d_{rt}", value=0)
            f_akb = col4.text_input("Номер АКБ", key=f"a_{rt}", placeholder="Напр: 01")
            
            f_cyc = st.number_input("Цикли АКБ", min_value=0, key=f"c_{rt}", value=0)
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key=f"r_{rt}")
            
            h_notes = st.session_state.history['note']
            n_sel_f = st.selectbox("Історія приміток:", ["-- Нова --"] + h_notes)
            f_note = st.text_area("Примітки", key=f"n_{rt}", value=n_sel_f if n_sel_f != "-- Нова --" else "", placeholder="Напр-д: Польоти не здійснювались, у зв'язку з несприятливими погодними умовами...")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")

            if st.button("✅ ДОДАТИ У СПИСОК") and p_o and p_l and m_date_str:
                add_to_history('route', m_route); add_to_history('note', f_note)
                st.session_state.temp_flights.append({
                    "Дата": m_date_str, "Час завдання": f"{t_start_raw} - {t_end_raw}",
                    "Підрозділ": st.session_state.user['unit'], "Оператор": st.session_state.user['name'], "Дрон": st.session_state.s_drone,
                    "Маршрут": m_route, "Зліт": p_o.strftime("%H:%M"), "Посадка": p_l.strftime("%H:%M"),
                    "Тривалість (хв)": dur, "Дистанція (м)": f_dist, "Номер АКБ": f_akb, "Цикли АКБ": f_cyc, "Результат": f_res, "Примітки": f_note, "files": f_imgs
                })
                st.session_state.reset_trigger += 1; st.session_state.uploader_key += 1; st.rerun()

        if st.session_state.temp_flights:
            st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Зліт", "Посадка", "Тривалість (хв)", "Номер АКБ"]], use_container_width=True)
            if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                db_m = load_data("Sheet1", 0)
                final_rows = []
                for f in st.session_state.temp_flights:
                    row = f.copy(); row.pop('files', None); final_rows.append(row)
                conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(final_rows)], ignore_index=True))
                send_telegram_master(st.session_state.temp_flights)
                st.success(random.choice(MOTIVATION_MSGS))
                st.session_state.temp_flights = []; time.sleep(2); st.rerun()

    # --- ВКЛАДКА ПОМІЧНИК ЗАЯВКИ ---
    with tab_app:
        st.header("📋 Помічник формування заявки")
        st.markdown("<div class='disclaimer'>⚠️ Даний розділ не відправляє заявки на ЦУС. Він лише допомагає сформувати текст.</div>", unsafe_allow_html=True)
        with st.container(border=True):
            a_u = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']))
            u_db = get_unit_drones(a_u)
            d_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_db] if u_db else ["DJI Mavic 3 Pro"]
            sel_f = st.multiselect("2. Тип БпЛА (з бази):", d_o)
            
            app_dates = st.date_input("3. Дати польоту:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            a_t1 = st.text_input("4. Час з:", placeholder="0800")
            a_t2 = st.text_input("до:", placeholder="2000")
            
            h_r = st.session_state.history['route']
            ar_sel = st.selectbox("Історія маршрутів (заявка):", ["-- Новий --"] + h_r)
            app_route = st.text_area("5. Маршрут:", value=ar_sel if ar_sel != "-- Новий --" else "")
            
            a_h = st.text_input("6. Висота (м):", "до 500 м"); a_r = st.text_input("7. Радіус (км):", "до 5 км")
            app_purp = st.selectbox("8. Мета:", ["патрулювання ділянки відповідальності", "оперативна необхідність", "навчально-тренувальні польоти"])
            
            h_p = st.session_state.history['phone']
            p_sel = st.selectbox("Історія контактів:", ["-- Новий --"] + h_p)
            app_cont = st.text_input("9. Контактна особа:", value=p_sel if p_sel != "-- Новий --" else f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ СФОРМУВАТИ ТЕКСТ"):
            add_to_history('phone', app_cont)
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}"
            st.code(f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({a_u})\n2. Тип: {sel_f}\n3. Дати: {dt_r}\n4. Час: {a_t1}-{a_t2}\n5. Маршрут: {app_route}\n6. Висота: {a_h}\n7. Радіус: {a_r}\n8. Мета: {app_purp}\n9. Контакт: {app_cont}", language="text")

    # --- ВКЛАДКА ДОВІДКА (Відновлено) ---
    with tab_info:
        st.header("ℹ️ Довідкова інформація")
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown("<div class='contact-card'><b class='contact-title'>🎓 Інструктор Олександр</b><br>Тактика, ПЗ, системи.<br>+380502310609</div>", unsafe_allow_html=True)
        with c2: st.markdown("<div class='contact-card'><b class='contact-title'>🔧 Технік Сергій</b><br>Ремонт, залізо.<br>+380997517054</div>", unsafe_allow_html=True)
        with c3: st.markdown("<div class='contact-card'><b class='contact-title'>📦 Склад Ірина</b><br>Облік майна.<br>+380667869701</div>", unsafe_allow_html=True)
        st.write("---")
        with st.expander("🛡️ ІНСТРУКЦІЯ"):
            st.markdown("**1. Вхід:** Оберіть підрозділ. Прізвище запам'ятовується автоматично.\n**2. Польоти:** Дата та зміна вводяться текстом (напр. 090126).\n**3. Очищення:** Поля вильоту очищаються самі після додавання.")

    # --- ВКЛАДКИ ЦУС, АРХІВ, АНАЛІТИКА (Стабільні) ---
    with tab_cus:
        if st.session_state.temp_flights:
            all_f = st.session_state.temp_flights
            st.code("\n".join([f"{f['Зліт']} - {f['Посадка']} - {f['Дистанція (м)']} м" for f in all_f]), language="text")
    
    with tab_hist:
        df_h = load_data("Sheet1")
        if not df_h.empty: st.dataframe(df_h[df_h['Оператор'] == st.session_state.user['name']], use_container_width=True)

    with tab_stat:
        df_s = load_data("Sheet1")
        if not df_s.empty:
            df_p = df_s[df_s['Оператор'] == st.session_state.user['name']]
            if not df_p.empty:
                df_p['dt'] = pd.to_datetime(df_p['Дата'], format='%d.%m.%Y', errors='coerce')
                rs = df_p.groupby([df_p['dt'].dt.year, df_p['dt'].dt.month]).agg(Польоти=('Дата', 'count')).reset_index()
                st.table(rs)
