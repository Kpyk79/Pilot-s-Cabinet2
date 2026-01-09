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
st.set_page_config(page_title="UAV Pilot Cabinet v9.0", layout="wide", page_icon="🛡️")

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

MOTIVATION_MSGS = [
    "Дякуємо за службу! Разом до перемоги! 🇺🇦",
    "Все буде Україна! Ваша робота — очі нашого кордону!",
    "Чудова робота, пілоте! База оновлена.",
    "Сталевий облік прийняв дані. Героям Слава!",
    "Так тримати! Кожен виліт наближає нас до мети!",
    "Інформація успішно передана. Слава Україні!",
    "Ваш професіоналізм — запорука безпеки. Дякуємо!"
]

# --- 3. ІНІЦІАЛІЗАЦІЯ СТАНУ СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
if 'reset_trigger' not in st.session_state: st.session_state.reset_trigger = 0

# Історія для Autocomplete
if 'history' not in st.session_state:
    st.session_state.history = {
        'name': [],
        'phone': [],
        'route': [],
        'note': []
    }

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

def add_to_history(key, value):
    if value and value.strip() and value not in st.session_state.history[key]:
        st.session_state.history[key].insert(0, value)
        st.session_state.history[key] = st.session_state.history[key][:10] # Тримаємо 10 останніх

def send_telegram_msg(all_fl):
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
            for img in f['files']:
                all_media.append(img)

    if all_media:
        media_group = []
        files = {}
        for i, img in enumerate(all_media[:10]):
            file_key = f"photo{i}"
            media_group.append({
                "type": "photo",
                "media": f"attach://{file_key}",
                "caption": report if i == 0 else "",
                "parse_mode": "Markdown"
            })
            files[file_key] = (img.name, img.getvalue(), img.type)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup", data={"chat_id": str(TG_CHAT_ID), "media": json.dumps(media_group)}, files=files)
    else:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": str(TG_CHAT_ID), "text": report, "parse_mode": "Markdown"})

# --- 5. РОБОТА З БАЗОЮ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except: return pd.DataFrame()

drones_db = load_data("DronesDB")

def get_unit_drones(unit_name):
    if drones_db.empty or "Підрозділ" not in drones_db.columns: return []
    return drones_db[drones_db['Підрозділ'] == unit_name].to_dict('records')

# --- 6. СТИЛІ ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #1b5e20; font-size: 1.2em; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black !important; }
    .contact-title { font-size: 1.1em; font-weight: bold; color: black !important; margin-bottom: 5px; }
    .contact-desc { font-size: 0.9em; color: black !important; font-style: italic; margin-bottom: 10px; line-height: 1.3; }
    .disclaimer { font-size: 0.85em; color: #d32f2f; font-weight: bold; padding: 10px; border: 1px dashed #d32f2f; border-radius: 5px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 7. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        st.markdown("<div style='text-align:center; margin-top:15%;'><h1>🛡️ UAV PILOT CABINET</h1><div style='color:#2E7D32; font-family:monospace; font-weight:bold; font-size:1.5em; border-top:2px solid #2E7D32; border-bottom:2px solid #2E7D32; padding:20px 0; margin:20px 0; letter-spacing:2px;'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Завантаження конфігурації...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 8. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД У СИСТЕМУ</h2>", unsafe_allow_html=True)
    role = st.radio("Оберіть статус:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            
            # Autocomplete для імені
            hist_name = st.session_state.history['name']
            n_sel = st.selectbox("Варіанти з історії (Прізвище):", ["-- Ввести нове --"] + hist_name) if hist_name else None
            n = st.text_input("Введіть Звання та Прізвище:", value=n_sel if n_sel and n_sel != "-- Ввести нове --" else "")
            
            if st.button("УВІЙТИ") and n:
                add_to_history('name', n)
                st.session_state.logged_in, st.session_state.user = True, {"unit": u, "name": n}
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    st.session_state.temp_flights = df_d[df_d['Оператор'] == n].to_dict('records')
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.user = True, {"unit": "УПЗ", "name": "Адмін"}; st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Завершити сеанс"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tabs = st.tabs(["🚀 Польоти", "📋 Помічник формування заявки", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])
    tab_f, tab_app, tab_cus, tab_hist, tab_stat, tab_info = tabs

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("🚀 Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            # ПАМ'ЯТЬ СЕСІЇ ДЛЯ ДАТИ ТА ЧАСУ ЗМІНИ
            m_date = c1.date_input("Дата польоту (дд.мм.рррр)", value=st.session_state.get('session_date', datetime.now()), key="session_date")
            m_start = c2.time_input("Зміна з", value=st.session_state.get('session_start', d_time(8,0)), key="session_start")
            m_end = c3.time_input("Зміна до", value=st.session_state.get('session_end', d_time(20,0)), key="session_end")
            
            hist_route = st.session_state.history['route']
            r_sel = st.selectbox("Історія маршрутів:", ["-- Новий маршрут --"] + hist_route)
            m_route = c4.text_input("Маршрут завдання (н.п. та район):", value=r_sel if r_sel != "-- Новий маршрут --" else "", key="curr_route")
            
            my_u_d = get_unit_drones(st.session_state.user['unit'])
            my_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in my_u_d] if my_u_d else BASE_DRONES
            st.selectbox("🛡️ БпЛА НА ЗМІНУ (з серійним номером):", my_o, key="sel_drone_val")

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            rt = st.session_state.reset_trigger
            col1, col2, col3, col4 = st.columns(4)
            t_o_s = col1.text_input("Зліт", key=f"zlit_{rt}", value="", placeholder="09:00 або 900")
            t_l_s = col2.text_input("Посадка", key=f"land_{rt}", value="", placeholder="09:30 або 930")
            p_o, p_l = smart_time_parse(t_o_s), smart_time_parse(t_l_s)
            dur = calculate_duration(p_o, p_l) if p_o and p_l else 0
            col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key=f"dist_{rt}", value=0)
            
            cb1, cb2 = st.columns(2)
            f_akb = cb1.text_input("Номер АКБ", key=f"akb_{rt}", value="")
            f_cyc = cb2.number_input("Цикли АКБ", min_value=0, key=f"cyc_{rt}", value=0)
            
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key=f"res_{rt}")
            
            hist_note = st.session_state.history['note']
            n_sel = st.selectbox("Історія приміток:", ["-- Нова примітка --"] + hist_note)
            f_note = st.text_area("Примітки", key=f"note_{rt}", value=n_sel if n_sel != "-- Нова примітка --" else "", placeholder="Напр-д: Польоти не здійснювались, у зв'язку з несприятливими погодними умовами...")
            
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            
            if st.button("✅ ДОДАТИ У СПИСОК") and p_o and p_l:
                add_to_history('route', m_route)
                add_to_history('note', f_note)
                st.session_state.temp_flights.append({
                    "Дата": m_date.strftime("%d.%m.%Y"), "Час завдання": f"{m_start.strftime('%H:%M')} - {m_end.strftime('%H:%M')}",
                    "Підрозділ": st.session_state.user['unit'], "Оператор": st.session_state.user['name'], "Дрон": st.session_state.sel_drone_val,
                    "Маршрут": m_route, "Зліт": p_o.strftime("%H:%M"), "Посадка": p_l.strftime("%H:%M"),
                    "Тривалість (хв)": dur, "Дистанція (м)": f_dist, "Номер АКБ": f_akb, "Цикли АКБ": f_cyc, "Результат": f_res, "Примітки": f_note,
                    "files": f_imgs
                })
                st.session_state.reset_trigger += 1; st.session_state.uploader_key += 1; st.rerun()

        if st.session_state.temp_flights:
            df_curr = pd.DataFrame(st.session_state.temp_flights)
            st.dataframe(df_curr[["Зліт", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ"]], use_container_width=True)
            b1, b2, b3 = st.columns(3)
            if b1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            if b2.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True))
                st.success("💾 Збережено!")
            if b3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                db_m = load_data("Sheet1")
                final_to_db = []
                for f in st.session_state.temp_flights:
                    row = f.copy(); row.pop('files', None); final_to_db.append(row)
                conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(final_to_db)], ignore_index=True))
                send_telegram_msg(st.session_state.temp_flights)
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                st.session_state.temp_flights = []
                st.success(random.choice(MOTIVATION_MSGS))
                time.sleep(2); st.rerun()

    # --- ВКЛАДКА ПОМІЧНИК ФОРМУВАННЯ ЗАЯВКИ ---
    with tab_app:
        st.header("📋 Помічник формування заявки")
        st.markdown("<div class='disclaimer'>⚠️ Даний розділ НЕ ВІДПРАВЛЯЄ дані на ЦУС. Він призначений виключно для швидкої генерації тексту заявки для копіювання в месенджери.</div>", unsafe_allow_html=True)
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            u_d = get_unit_drones(app_unit)
            d_opts = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_d] if u_d else BASE_DRONES
            sel_full = st.multiselect("2. Тип БпЛА (з бази):", d_opts)
            if u_d and sel_full:
                m_list = list(set([s.split(" (s/n:")[0] for s in sel_full]))
                s_list = [s.split("s/n: ")[1].replace(")", "") for s in sel_full]
                app_sn = ", ".join(s_list); app_models = ", ".join(m_list)
            else:
                app_sn = st.text_input("s/n (якщо немає в базі):"); app_models = ", ".join(sel_full)
            
            app_dates = st.date_input("3. Дата здійснення польоту (період):", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2)
            a_t1 = c_t1.time_input("4. Час роботи з:", d_time(8,0))
            a_t2 = c_t2.time_input("до:", d_time(20,0))
            
            h_route = st.session_state.history['route']
            ar_sel = st.selectbox("Варіанти маршрутів:", ["-- Новий --"] + h_route)
            app_route = st.text_area("5. Населений пункт (маршрут):", value=ar_sel if ar_sel != "-- Новий --" else "")
            
            c_h1, c_h2 = st.columns(2); a_h = c_h1.text_input("6. Висота роботи (м):", "до 500 м"); a_r = c_h2.text_input("7. Радіус роботи (км):", "до 5 км")
            app_purp = st.selectbox("8. Мета польоту:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            
            hist_phone = st.session_state.history['phone']
            p_sel = st.selectbox("Минулі контакти:", ["-- Новий контакт --"] + hist_phone)
            app_cont_text = st.text_input("9. Контактна особа та телефон:", value=p_sel if p_sel != "-- Новий контакт --" else f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ СФОРМУВАТИ ТЕКСТ ЗАЯВКИ"):
            add_to_history('phone', app_cont_text)
            d_str = f"{app_models} ({app_sn})" if app_sn else app_models
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дата здійснення польоту: {dt_r}\n4. Час роботи: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {a_h}\n7. Радіус роботи (км): {a_r}\n8. Мета польоту: {app_purp}\n9. Контактна особа: {app_cont_text}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if st.session_state.temp_flights:
            all_f = st.session_state.temp_flights; s_start = st.session_state.get('session_start', d_time(8,0)); b_m, a_m, cr = [], [], False
            for f in all_f:
                fs = datetime.strptime(f['Зліт'], "%H:%M").time(); fe = datetime.strptime(f['Посадка'], "%H:%M").time()
                if cr or fe < fs or fs < s_start: cr = True; a_m.append(f)
                else: b_m.append(f)
            def fc(fls): return "\n".join([f"{f['Зліт']} - {f['Посадка']} - {f['Дистанція (м)']} м ({f['Тривалість (хв)']} хв)" for f in fls])
            st.subheader("🌙 До 00:00"); st.code(fc(b_m), language="text"); st.subheader("☀️ Після 00:00"); st.code(fc(a_m), language="text")

    # --- ВКЛАДКА АРХІВ ---
    with tab_hist:
        st.header("📜 Мій журнал")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']]
            if not p_df.empty: st.dataframe(p_df.sort_values(by="Дата", ascending=False), use_container_width=True)
            else: st.info("У вашому архіві ще немає записів.")

    # --- ВКЛАДКА АНАЛІТИКА ---
    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns and "Дата" in df_s.columns:
            df_s_p = df_s[df_s['Оператор'] == st.session_state.user['name']]
            if not df_s_p.empty:
                df_s_p['dt'] = pd.to_datetime(df_s_p['Дата'], format='%d.%m.%Y', errors='coerce'); df_s_p = df_s_p.dropna(subset=['dt'])
                df_s_p['Y'] = df_s_p['dt'].dt.year; df_s_p['M'] = df_s_p['dt'].dt.month
                rs = df_s_p.groupby(['Y', 'M']).agg(Польоти=('Дата', 'count'), Хв=('Тривалість (хв)', 'sum')).reset_index()
                rs['📅 Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['M']), '???')} {int(x['Y'])}", axis=1); rs['⏱ Наліт'] = rs['Хв'].apply(format_to_time_str)
                st.table(rs[['📅 Місяць', 'Польоти', '⏱ Наліт']].sort_values(by=['📅 Місяць'], ascending=False))

    # --- ВКЛАДКА ДОВІДКА (ВІДНОВЛЕНО 100%) ---
    with tab_info:
        st.header("ℹ️ Довідкова інформація")
        st.subheader("📞 Контакти та зони відповідальності")
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown("""<div class='contact-card'><div class='contact-title'>🎓 Інструктор</div><div class='contact-desc'>Питання тактики застосування, налаштування систем та спеціалізованого ПЗ.</div><b>Олександр</b><br>+380502310609</div>""", unsafe_allow_html=True)
        with c2: st.markdown("""<div class='contact-card'><div class='contact-title'>🔧 Технік-майстер</div><div class='contact-desc'>Механічні пошкодження майна, ремонт корпусів, збої апаратної частини.</div><b>Сергій</b><br>+380997517054</div>""", unsafe_allow_html=True)
        with c3: st.markdown("""<div class='contact-card'><div class='contact-title'>📦 Начальник складу</div><div class='contact-desc'>Облік майна, оформлення актів списання, переміщення та передача обладнання.</div><b>Ірина</b><br>+380667869701</div>""", unsafe_allow_html=True)
        st.write("---")
        st.subheader("📖 Повна документація")
        with st.expander("🛡️ ІНСТРУКЦІЯ КОРИСТУВАЧА"):
            st.markdown("""
            **1. 🔑 Вхід у систему**
            * Оберіть свій Підрозділ зі списку. Введіть Звання та Прізвище. Система запам'ятає ваші дані для наступних входів.

            **2. 🚀 Вкладка «Польоти»**
            * **Крок А:** Встановіть Дату та Час зміни. Дані збережуться на всю сесію. Оберіть конкретний БпЛА з s/n.
            * **Крок Б (Виліт):** Вкажіть час Зльоту/Посадки, Відстань, Номер АКБ. Тисніть «➕ Додати у список».
            * **Крок В:** Наприкінці зміни обов'язково — «🚀 ВІДПРАВИТИ ВСІ ДАНІ».

            **3. 📋 Вкладка «Помічник формування заявки»**
            * Допомагає швидко згенерувати текст для копіювання. Не відправляє дані офіційно.

            **4. 📡 Вкладка «ЦУС»**
            * Додаток сам розділить ваші польоти на вікна «До 00:00» та «Після 00:00». Просто копіюйте текст.
            """)
        with st.expander("📲 ЯК ВСТАНОВИТИ НА СМАРТФОН"):
            st.markdown("""
            **Android (Chrome):** Три крапки (⋮) -> «Додати на головний екран».
            **iPhone (Safari):** Поділитися -> «Додати на початковий екран».
            """)
        st.write("---")
        st.markdown("<div style='text-align: center; color: black;'>Слава Україні! 🇺🇦</div>", unsafe_allow_html=True)
