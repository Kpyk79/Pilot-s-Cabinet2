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
st.set_page_config(
    page_title="UAV Pilot Cabinet v9.3", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="collapsed"
)

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
    "Чудова робота, пілоте! Дані збережені.",
    "Сталевий облік прийняв дані. Героям Слава!",
    "Так тримати! Кожен виліт наближає нас до мети!",
    "Інформація успішно передана. Слава Україні!",
    "Ваш професіоналізм — запорука нашої безпеки!"
]

# --- 3. ІНІЦІАЛІЗАЦІЯ СТАНУ СЕСІЇ (Пам'ять та Очищення) ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'reset_trigger' not in st.session_state: st.session_state.reset_trigger = 0
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 5000

# Історія для Autocomplete
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
        f"⏰ **Час виконання завдання:** {first['Час завдання']}\n"
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

# --- 5. РОБОТА З БАЗОЮ (З кешуванням) ---
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

# --- 6. МОБІЛЬНИЙ CSS (Адаптація під смартфони) ---
st.markdown("""
    <style>
    /* Кнопки - великі та зручні */
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        background-color: #2E7D32; 
        color: white; 
        height: 4em; 
        font-weight: bold; 
        font-size: 1.1em;
        margin-top: 10px;
    }
    
    /* Відступи для полів введення на мобільних */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div {
        height: 3em !important;
        font-size: 1.1em !important;
    }

    /* Стилізація карток та блоків */
    .duration-box { background-color: #f1f3f5; padding: 15px; border-radius: 10px; text-align: center; color: #1b5e20; font-size: 1.3em; font-weight: bold; margin-bottom: 10px; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 12px; border-left: 6px solid #2E7D32; margin-bottom: 15px; color: black !important; }
    .disclaimer { font-size: 0.95em; color: #d32f2f; font-weight: bold; padding: 15px; border: 2px dashed #d32f2f; border-radius: 10px; margin-bottom: 15px; background-color: #fff5f5; }
    
    /* Оптимізація табів для прокрутки на смартфонах */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: nowrap;
        background-color: #f8f9fa;
        border-radius: 10px 10px 0 0;
        padding: 0 20px;
    }
    
    /* Чорний текст в алертах */
    .stAlert p { color: black !important; font-weight: 500; }
    </style>
    """, unsafe_allow_html=True)

# --- 7. SPLASH SCREEN ---
if not st.session_state.splash_done:
    st.markdown("<div style='text-align:center; margin-top:25%;'><h1>🛡️ UAV CABINET</h1><p style='color:#2E7D32; font-weight:bold; font-size:1.2em;'>ЗАВАНТАЖЕННЯ МОБІЛЬНОЇ ВЕРСІЇ...</p></div>", unsafe_allow_html=True)
    my_bar = st.progress(0)
    for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
    st.session_state.splash_done = True; st.rerun()

# --- 8. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД</h2>", unsafe_allow_html=True)
    with st.container(border=True):
        u = st.selectbox("Ваш підрозділ:", UNITS)
        h_names = st.session_state.history['name']
        n_sel = st.selectbox("Оберіть з історії:", ["-- Нове введення --"] + h_names) if h_names else None
        n = st.text_input("Звання та Прізвище:", value=n_sel if n_sel and n_sel != "-- Нове введення --" else "")
        if st.button("УВІЙТИ"):
            if n:
                add_to_history('name', n)
                st.session_state.logged_in, st.session_state.user = True, {"unit": u, "name": n}; st.rerun()
            else: st.error("Введіть прізвище")
else:
    # Sidebar компактний
    st.sidebar.markdown(f"👤 **{st.session_state.user['name']}**")
    if st.sidebar.button("Завершити роботу"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tabs = st.tabs(["🚀 Польоти", "📋 Помічник заявки", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])
    tab_f, tab_app, tab_cus, tab_hist, tab_stat, tab_info = tabs

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("🚀 Польоти")
        with st.container(border=True):
            # Адаптивні колонки
            c1, c2 = st.columns(2); c3, c4 = st.columns(2)
            m_date = c1.date_input("Дата польоту", value=st.session_state.get('s_date', datetime.now()), key='s_date')
            m_start = c2.time_input("Зміна з", value=st.session_state.get('s_start', d_time(8,0)), key='s_start')
            m_end = c3.time_input("Зміна до", value=st.session_state.get('s_end', d_time(20,0)), key='s_end')
            
            h_routes = st.session_state.history['route']
            r_sel = st.selectbox("Історія маршрутів:", ["-- Новий --"] + h_routes)
            m_route = c4.text_input("Маршрут завдання:", value=r_sel if r_sel != "-- Новий --" else "", key='cur_route')
            
            u_db = get_unit_drones(st.session_state.user['unit'])
            d_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_db] if u_db else BASE_DRONES
            st.selectbox("🛡️ БпЛА НА ЗМІНУ (s/n):", d_o, key='s_drone')

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            rt = st.session_state.reset_trigger
            col1, col2 = st.columns(2)
            t_o_s = col1.text_input("Зліт (напр. 930)", key=f"z_{rt}", value="", placeholder="09:00")
            t_l_s = col2.text_input("Посадка", key=f"l_{rt}", value="", placeholder="09:30")
            
            p_o, p_l = smart_time_parse(t_o_s), smart_time_parse(t_l_s)
            dur = calculate_duration(p_o, p_l) if p_o and p_l else 0
            st.markdown(f"<div class='duration-box'>⏳ {dur} хв</div>", unsafe_allow_html=True)
            
            col3, col4 = st.columns(2)
            f_dist = col3.number_input("Відстань (м)", min_value=0, key=f"d_{rt}", value=0)
            f_akb = col4.text_input("Номер АКБ", key=f"a_{rt}", value="")
            
            f_cyc = st.number_input("Цикли АКБ", min_value=0, key=f"c_{rt}", value=0)
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key=f"r_{rt}")
            
            h_notes = st.session_state.history['note']
            n_sel_f = st.selectbox("Історія приміток:", ["-- Нова --"] + h_notes)
            f_note = st.text_area("Примітки", key=f"n_{rt}", value=n_sel_f if n_sel_f != "-- Нова --" else "", placeholder="Напр-д: Польоти не здійснювались...")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")

            if st.button("✅ ДОДАТИ ВИЛІТ"):
                if p_o and p_l:
                    add_to_history('route', m_route); add_to_history('note', f_note)
                    st.session_state.temp_flights.append({
                        "Дата": m_date.strftime("%d.%m.%Y"), "Час завдання": f"{m_start.strftime('%H:%M')} - {m_end.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'], "Оператор": st.session_state.user['name'], "Дрон": st.session_state.s_drone,
                        "Маршрут": m_route, "Зліт": p_o.strftime("%H:%M"), "Посадка": p_l.strftime("%H:%M"),
                        "Тривалість (хв)": dur, "Дистанція (м)": f_dist, "Номер АКБ": f_akb, "Цикли АКБ": f_cyc, "Результат": f_res, "Примітки": f_note, "files": f_imgs
                    })
                    st.session_state.reset_trigger += 1; st.session_state.uploader_key += 1; st.rerun()
                else: st.warning("Перевірте час!")

        if st.session_state.temp_flights:
            st.write("📋 Поточний список вильотів:")
            st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Зліт", "Посадка", "Тривалість (хв)", "Номер АКБ"]], use_container_width=True)
            
            if st.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts", 0)
                if not df_d.empty and "Оператор" in df_d.columns:
                    df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True))
                st.success("💾 Збережено!")
            
            if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                db_m = load_data("Sheet1", 0)
                final_rows = []
                for f in st.session_state.temp_flights:
                    row = f.copy(); row.pop('files', None); final_rows.append(row)
                conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(final_rows)], ignore_index=True))
                send_telegram_master(st.session_state.temp_flights)
                # Очищення Drafts
                df_d = load_data("Drafts", 0)
                if not df_d.empty and "Оператор" in df_d.columns:
                    conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                st.success(random.choice(MOTIVATION_MSGS))
                st.session_state.temp_flights = []; time.sleep(2); st.rerun()
            
            if st.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()

    # --- ВКЛАДКА ПОМІЧНИК ЗАЯВКИ ---
    with tab_app:
        st.header("📋 Помічник заявки")
        st.markdown("<div class='disclaimer'>⚠️ Даний розділ НЕ ВІДПРАВЛЯЄ заявки офіційно. Він допомагає сформувати текст для месенджерів.</div>", unsafe_allow_html=True)
        with st.container(border=True):
            a_u = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']))
            u_db = get_unit_drones(a_u)
            d_o = [f"{d['Модель БпЛА']} (s/n: {d['s/n']})" for d in u_db] if u_db else BASE_DRONES
            sel_f = st.multiselect("2. Тип БпЛА (з бази):", d_o)
            if u_db and sel_f:
                s_list = [s.split("s/n: ")[1].replace(")", "") for s in sel_f]
                app_sn = ", ".join(s_list); app_models = ", ".join(list(set([s.split(" (s/n:")[0] for s in sel_f])))
            else: app_sn = st.text_input("s/n (вручну):"); app_models = ", ".join(sel_f)
            
            app_dates = st.date_input("3. Дати:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2); a_t1 = c_t1.time_input("Час з:", d_time(8,0)); a_t2 = c_t2.time_input("Час до:", d_time(20,0))
            
            h_r = st.session_state.history['route']
            ar_sel = st.selectbox("Минулі маршрути (заявка):", ["-- Новий --"] + h_r)
            app_route = st.text_area("Маршрут завдання:", value=ar_sel if ar_sel != "-- Новий --" else "")
            
            a_h = st.text_input("Висота (м):", "до 500 м"); a_r = st.text_input("Радіус (км):", "до 5 км")
            app_purp = st.selectbox("Мета:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            
            h_p = st.session_state.history['phone']
            p_sel = st.selectbox("Минулі контакти (заявка):", ["-- Новий --"] + h_p)
            app_cont = st.text_input("Контактна особа:", value=p_sel if p_sel != "-- Новий --" else f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ СФОРМУВАТИ ЗАЯВКУ"):
            add_to_history('phone', app_cont)
            d_s = f"{app_models} ({app_sn})" if app_sn else app_models
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({a_u})\n2. Тип БпЛА: {d_s}\n3. Дата здійснення польоту: {dt_r}\n4. Час роботи: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {a_h}\n7. Радіус роботи (км): {a_r}\n8. Мета польоту: {app_purp}\n9. Контактна особа: {app_cont}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if st.session_state.temp_flights:
            all_f = st.session_state.temp_flights; s_start = st.session_state.get('s_start', d_time(8,0)); b_m, a_m, cr = [], [], False
            for f in all_f:
                fs = datetime.strptime(f['Зліт'], "%H:%M").time(); fe = datetime.strptime(f['Посадка'], "%H:%M").time()
                if cr or fe < fs or fs < s_start: cr = True; a_m.append(f)
                else: b_m.append(f)
            def fc(fls): return "\n".join([f"{f['Зліт']} - {f['Посадка']} - {f['Дистанція (м)']} м ({f['Тривалість (хв)']} хв)" for f in fls])
            st.subheader("🌙 До 00:00"); st.code(fc(b_m), language="text"); st.subheader("☀️ Після 00:00"); st.code(fc(a_m), language="text")

    # --- ВКЛАДКА АРХІВ ТА АНАЛІТИКА ---
    with tab_hist:
        st.header("📜 Мій журнал"); df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']]
            if not p_df.empty: st.dataframe(p_df.sort_values(by="Дата", ascending=False), use_container_width=True)

    with tab_stat:
        st.header("📊 Аналітика"); df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns:
            df_p = df_s[df_s['Оператор'] == st.session_state.user['name']]
            if not df_p.empty:
                df_p['dt'] = pd.to_datetime(df_p['Дата'], format='%d.%m.%Y', errors='coerce'); df_p = df_p.dropna(subset=['dt'])
                df_p['Y'] = df_p['dt'].dt.year; df_p['M'] = df_p['dt'].dt.month
                rs = df_p.groupby(['Y', 'M']).agg(Польоти=('Дата', 'count'), Хв=('Тривалість (хв)', 'sum')).reset_index()
                rs['📅 Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['M']), '???')} {int(x['Y'])}", axis=1)
                rs['⏱ Наліт'] = rs['Хв'].apply(lambda x: f"{int(x//60):02d}:{int(x%60):02d}")
                st.table(rs[['📅 Місяць', 'Польоти', '⏱ Наліт']].sort_values(by=['📅 Місяць'], ascending=False))

    # --- ВКЛАДКА ДОВІДКА ---
    with tab_info:
        st.header("ℹ️ Довідка")
        st.subheader("📞 Контакти")
        st.markdown("""<div class='contact-card'><div class='contact-title'>🎓 Інструктор Олександр</div><div class='contact-desc'>Тактика, ПЗ, спеціальні системи.</div><b>+380502310609</b></div>""", unsafe_allow_html=True)
        st.markdown("""<div class='contact-card'><div class='contact-title'>🔧 Технік Сергій</div><div class='contact-desc'>Ремонт, залізо, пошкодження.</div><b>+380997517054</b></div>""", unsafe_allow_html=True)
        st.markdown("""<div class='contact-card'><div class='contact-title'>📦 Склад Ірина</div><div class='contact-desc'>Облік, акти списання.</div><b>+380667869701</b></div>""", unsafe_allow_html=True)
        
        st.subheader("📖 Інструкції")
        with st.expander("🛡️ ЯК ПРАЦЮВАТИ З ДОДАТКОМ"):
            st.markdown("""**1. Вхід:** Оберіть підрозділ. Прізвище запам'ятовується автоматично.\n**2. Зміна:** Дату та Час зміни достатньо ввести один раз на всю сесію.\n**3. Польоти:** Кожен виліт додається окремо. Поля очищаються для нового запису.\n**4. Відправка:** Тисніть 'Відправити' в кінці зміни, щоб дані потрапили в офіційний архів.""")
        
        with st.expander("📲 ВСТАНОВИТИ НА ГОЛОВНИЙ ЕКРАН"):
            st.markdown("""**Для Android (Chrome):** Натисніть три крапки (⋮) у браузері -> «Додати на головний екран».\n\n**Для iPhone (Safari):** Натисніть кнопку «Поділитися» (квадрат зі стрілкою) -> «Додати на початковий екран».""")
        st.write("---")
        st.markdown("<div style='text-align: center; color: black;'>Слава Україні! 🇺🇦</div>", unsafe_allow_html=True)
