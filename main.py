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
st.set_page_config(page_title="UAV Pilot Cabinet v8.5", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ТА СПИСКИ ---
UNITS = [
    "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", 
    "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", 
    "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", 
    "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", 
    "віпс Гребеники", "впс Степанівка", "віпс Кучурган", 
    "віпс Лиманське", "віпс Лучинське", "УПЗ"
]
BASE_DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"
UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

MOTIVATION_MSGS = [
    "🇺🇦 Слава Україні! Героям Слава! Чудова робота, пілоте!",
    "💪 Сталевий кордон під надійним захистом! Дякуємо за службу!",
    "🚁 Вильоти зафіксовані. Повертайся живим і неушкодженим!",
    "✨ Робота виконана на високому рівні! Так тримати!",
    "🛡️ Ваш внесок у безпеку кордону безцінний. Спокійної зміни!",
    "🚀 Дані в архіві. Ви — очі наших підрозділів!",
    "🦾 Професійно, швидко, надійно. Ви справжній майстер БпЛА!",
    "👊 Ворог не пройде, доки ви в небі! Слава ДПСУ!",
    "🌅 Зміна зафіксована успішно. Відпочивайте, ви це заслужили!",
    "✌️ Разом до перемоги! Дякуємо за професійний облік!"
]

# --- 3. ІНІЦІАЛІЗАЦІЯ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
if 'reset_trigger' not in st.session_state: st.session_state.reset_trigger = 0

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

# --- 5. РОБОТА З БАЗОЮ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except: return pd.DataFrame()

# Завантаження бази БпЛА та історії для швидкого вводу
drones_db = load_data("DronesDB")
main_db = load_data("Sheet1")

def get_history_for_user(field_name, user_name):
    if main_db.empty or field_name not in main_db.columns: return []
    return main_db[main_db['Оператор'] == user_name][field_name].unique().tolist()

def get_unit_drones(unit_name):
    if drones_db.empty or "Підрозділ" not in drones_db.columns: return []
    return drones_db[drones_db['Підрозділ'] == unit_name].to_dict('records')

def send_telegram_complex(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    flights_txt = "\n".join([f"🚀 {f['Зліт']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for f in all_fl])
    report = (
        f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n"
        f"📅 **Дата:** {first['Дата']}\n⏰ **Час виконання завдання:** {first['Час завдання']}\n"
        f"🛡 **БпЛА:** {first['Дрон']}\n📍 **Маршрут:** {first['Маршрут']}\n━━━━━━━━━━━━━━━\n"
        f"📋 **Вильоти:**\n{flights_txt}\n━━━━━━━━━━━━━━━\n"
        f"✅ **Результат:** {first['Результат']}\n📝 **Примітки:** {first['Примітки'] if first['Примітки'] else '---'}"
    )
    all_photos = []
    for f in all_fl:
        if f.get('files'):
            for img in f['files']: all_photos.append(img)
    if all_photos:
        media = []
        files = {}
        for i, photo in enumerate(all_photos[:10]):
            file_key = f"photo{i}"
            media.append({"type": "photo", "media": f"attach://{file_key}", "caption": report if i == 0 else "", "parse_mode": "Markdown"})
            files[file_key] = (photo.name, photo.getvalue(), photo.type)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup", data={'chat_id': str(TG_CHAT_ID), 'media': json.dumps(media)}, files=files)
    else:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'})

# --- 6. ДИЗАЙН ---
st.markdown("""<style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #1b5e20; font-size: 1.2em; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black !important; }
    .contact-title { font-size: 1.1em; font-weight: bold; color: black !important; margin-bottom: 5px; }
    .contact-desc { font-size: 0.9em; color: black !important; font-style: italic; margin-bottom: 10px; }
    .helper-note { background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; border: 1px solid #ffeeba; margin-bottom: 20px; font-weight: bold; }
    </style>""", unsafe_allow_html=True)

# --- 7. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        st.markdown("<div style='text-align:center; margin-top:15%;'><h1>🛡️ UAV PILOT CABINET</h1><div style='color:#2E7D32; font-family:monospace; font-weight:bold; font-size:1.5em; border-top:2px solid #2E7D32; border-bottom:2px solid #2E7D32; padding:20px 0; margin:20px 0; letter-spacing:2px;'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Завантаження історії...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 8. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД У СИСТЕМУ</h2>", unsafe_allow_html=True)
    role = st.radio("Статус:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            # Історія для прізвища
            all_users_hist = main_db['Оператор'].unique().tolist() if not main_db.empty else []
            n_hist = st.selectbox("Оберіть з історії:", [""] + all_users_hist) if all_users_hist else None
            n = st.text_input("Звання та Прізвище:", value=n_hist if n_hist else "")
            if st.button("УВІЙТИ") and n:
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
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    # Порядок вкладок згідно з побажанням
    tab_f, tab_app, tab_cus, tab_hist, tab_stat, tab_info = st.tabs(["🚀 Польоти", "📋 Помічник формування заявки", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="m_start_val")
            m_end = c3.time_input("Зміна до", d_time(20,0), key="m_end_val")
            # Історія для маршруту
            route_hist = get_history_for_user("Маршрут", st.session_state.user['name'])
            sel_route = c4.selectbox("Історія маршрутів:", [""] + route_hist) if route_hist else None
            m_route = c4.text_input("Маршрут завдання", value=sel_route if sel_route else "", key="m_route_val")
            
            # БпЛА з серійними номерами
            my_u_d = get_unit_drones(st.session_state.user['unit'])
            my_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in my_u_d] if my_u_d else BASE_DRONES
            st.selectbox("🛡️ БпЛА НА ЗМІНУ:", my_o, key="sel_drone_val")

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            rt = st.session_state.reset_trigger
            col1, col2, col3, col4 = st.columns(4)
            t_o_s = col1.text_input("Зліт", key=f"zlit_{rt}", placeholder="09:00 або 900")
            t_l_s = col2.text_input("Посадка", key=f"land_{rt}", placeholder="09:30 або 930")
            p_o, p_l = smart_time_parse(t_o_s), smart_time_parse(t_l_s)
            dur = calculate_duration(p_o, p_l) if p_o and p_l else 0
            col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key=f"dist_{rt}")
            cb1, cb2 = st.columns(2)
            f_akb = cb1.text_input("Номер АКБ", key=f"akb_{rt}")
            f_cyc = cb2.number_input("Цикли АКБ", min_value=0, key=f"cyc_{rt}")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key=f"res_{rt}")
            
            # Історія для приміток
            note_hist = get_history_for_user("Примітки", st.session_state.user['name'])
            sel_note = st.selectbox("Вибрати з попередніх приміток:", [""] + note_hist) if note_hist else None
            f_note = st.text_area("Примітки", key=f"note_{rt}", value=sel_note if sel_note else "", placeholder="Напр-д: Польоти не здійснювались, у зв'язку з несприятливими погодними умовами...")
            
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            
            if st.button("✅ ДОДАТИ У СПИСОК") and p_o and p_l:
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
                send_telegram_complex(st.session_state.temp_flights)
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                st.session_state.temp_flights = []
                st.balloons(); st.success(random.choice(MOTIVATION_MSGS))
                time.sleep(3); st.rerun()

    # --- ВКЛАДКА ПОМІЧНИК ФОРМУВАННЯ ЗАЯВКИ ---
    with tab_app:
        st.header("📋 Помічник формування заявки")
        st.markdown("<div class='helper-note'>⚠️ УВАГА: Цей розділ не відправляє заявку автоматично. Він лише допомагає сформувати текст для копіювання у месенджери.</div>", unsafe_allow_html=True)
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            u_d = get_unit_drones(app_unit)
            d_opts = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_d] if u_d else BASE_DRONES
            sel_full = st.multiselect("2. Тип БпЛА:", d_opts)
            if u_d and sel_full:
                m_list = list(set([s.split(" (s/n:")[0] for s in sel_full]))
                s_list = [s.split("s/n: ")[1].replace(")", "") for s in sel_full]
                app_sn = ", ".join(s_list); app_models = ", ".join(m_list)
            else:
                app_sn = st.text_input("s/n (вручну):"); app_models = ", ".join(sel_full)
            app_dates = st.date_input("3. Дати польоту:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2); a_t1 = c_t1.time_input("4. Час з:", d_time(8,0)); a_t2 = c_t2.time_input("Час до:", d_time(20,0))
            
            route_hist_app = get_history_for_user("Маршрут", st.session_state.user['name'])
            sel_route_app = st.selectbox("Вибрати н.п. з історії:", [""] + route_hist_app)
            app_route = st.text_area("5. Населений пункт (маршрут):", value=sel_route_app if sel_route_app else "")
            
            c_h1, c_h2 = st.columns(2); a_h = c_h1.text_input("6. Висота (м):", "до 500 м"); a_r = c_h2.text_input("7. Радіус (км):", "до 5 км")
            app_purp = st.selectbox("8. Мета:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            app_cont = st.text_input("9. Контактна особа:", f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ СФОРМУВАТИ ТЕКСТ ЗАЯВКИ"):
            d_str = f"{app_models} ({app_sn})" if app_sn else app_models
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дати: {dt_r}\n4. Час роботи: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {a_h}\n7. Радіус роботи (км): {a_r}\n8. Мета польоту: {app_purp}\n9. Контактна особа: {app_cont}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if st.session_state.temp_flights:
            all_f = st.session_state.temp_flights; s_start = st.session_state.m_start_val; b_m, a_m, cr = [], [], False
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
        with c1: st.markdown("<div class='contact-card'><div class='contact-title'>🎓 Інструктор</div><div class='contact-desc'>Питання тактики застосування, налаштування систем та спеціалізованого ПЗ.</div><b>Олександр</b><br>+380502310609</div>", unsafe_allow_html=True)
        with c2: st.markdown("<div class='contact-card'><div class='contact-title'>🔧 Технік-майстер</div><div class='contact-desc'>Механічні пошкодження майна, ремонт корпусів, збої апаратної частини.</div><b>Сергій</b><br>+380997517054</div>", unsafe_allow_html=True)
        with c3: st.markdown("<div class='contact-card'><div class='contact-title'>📦 Начальник складу</div><div class='contact-desc'>Облік майна, оформлення актів списання, переміщення та передача обладнання.</div><b>Ірина</b><br>+380667869701</div>", unsafe_allow_html=True)
        st.write("---")
        st.subheader("📖 Повна документація")
        with st.expander("🛡️ ІНСТРУКЦІЯ КОРИСТУВАЧА"):
            st.markdown("""
            **1. 🔑 Вхід у систему**
            * Оберіть свій Підрозділ зі списку.
            * Введіть Звання та Прізвище (або оберіть з історії).

            **2. 🚀 Вкладка «Польоти»**
            * **Крок А:** Встановіть Дату та Час зміни. Оберіть БпЛА (з серійним номером).
            * **Крок Б (Виліт):** Вкажіть час Зльоту/Посадки, Відстань, Номер АКБ.
            * **Крок В:** Тисніть «➕ Додати у список». В кінці зміни обов'язково — «🚀 ВІДПРАВИТИ ВСІ ДАНІ».

            **3. 📋 Вкладка «Помічник формування заявки»**
            * Допомагає сформувати текст для месенджерів. Підтягує серійні номери автоматично.

            **4. 📡 Вкладка «ЦУС»**
            * Система сама розділить ваші польоти на вікна «До 00:00» та «Після 00:00».
            """)
        with st.expander("📲 ЯК ВСТАНОВИТИ НА СМАРТФОН"):
            st.markdown("**Android (Chrome):** Три крапки (⋮) -> «Додати на головний екран».\n**iPhone (Safari):** Поділитися -> «Додати на початковий екран».")
        st.write("---")
        st.markdown("<div style='text-align: center; color: black;'>Слава Україні! 🇺🇦</div>", unsafe_allow_html=True)
