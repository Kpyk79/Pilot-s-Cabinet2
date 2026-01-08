import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import os
import time
from datetime import datetime, time as d_time, timedelta

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v7.0", layout="wide", page_icon="🛡️")

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
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

# --- 3. РОЗУМНЕ ПАРСИНГУ ЧАСУ ---
def smart_time_parse(val):
    """Перетворює 930 на 09:30, 9 на 09:00 і т.д."""
    val = "".join(filter(str.isdigit, val))
    if not val: return None
    try:
        if len(val) <= 2: # "9" або "09"
            h, m = int(val), 0
        elif len(val) == 3: # "930"
            h, m = int(val[0]), int(val[1:])
        elif len(val) == 4: # "0930" або "1420"
            h, m = int(val[:2]), int(val[2:])
        else: return None
        
        if 0 <= h < 24 and 0 <= m < 60:
            return d_time(h, m)
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
        if df is None or df.empty: return pd.DataFrame()
        return df.dropna(how="all")
    except: return pd.DataFrame()

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    flights_txt = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for i, f in enumerate(all_fl)])
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n🛡 **БпЛА:** {first['Дрон']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}"
    for fl in all_fl:
        if fl.get('files'):
            for img in fl['files']:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", files={'photo': (img.name, img.getvalue(), img.type)}, data={'chat_id': str(TG_CHAT_ID), 'caption': report, 'parse_mode': 'Markdown'})
    if not any(f.get('files') for f in all_fl):
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'})

# --- 5. СТАН СЕСІЇ ТА ДИЗАЙН ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .stButton>button:hover { background-color: #1B5E20; color: white; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #1b5e20; font-size: 1.2em; }
    .splash-container { text-align: center; margin-top: 15%; }
    .slogan-box { color: #2E7D32; font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.5em; border-top: 2px solid #2E7D32; border-bottom: 2px solid #2E7D32; padding: 20px 0; margin: 20px 0; letter-spacing: 2px; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black !important; }
    .contact-title { font-size: 1.1em; font-weight: bold; color: black !important; margin-bottom: 5px; }
    .contact-desc { font-size: 0.9em; color: black !important; font-style: italic; margin-bottom: 10px; line-height: 1.3; }
    .stAlert { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 6. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        st.markdown("<div class='splash-container'><h1 style='font-size: 4em;'>🛡️</h1><h1>UAV PILOT CABINET</h1><div class='slogan-box'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Ініціалізація...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 7. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД У СИСТЕМУ</h2>", unsafe_allow_html=True)
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS); n = st.text_input("Звання та Прізвище:")
            if st.button("УВІЙТИ") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n}
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    my_d = df_d[df_d['Оператор'] == n].to_dict('records')
                    st.session_state.temp_flights.extend(my_d)
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"; st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name'] if st.session_state.role=='Pilot' else 'Адмін'}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.session_state.splash_done = False; st.rerun()

    tab_app, tab_f, tab_cus, tab_hist, tab_stat, tab_info = st.tabs(["📋 Заявка", "🚀 Польоти", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    # --- ВКЛАДКА ПОЛЬОТИ (ГНУЧКИЙ ЧАС) ---
    with tab_f:
        st.header("Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4); m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="m_start_val"); m_end = c3.time_input("Зміна до", d_time(20,0), key="m_end_val")
            m_route = c4.text_input("Маршрут завдання", key="m_route_val"); st.selectbox("🛡️ БпЛА НА ЗМІНУ:", DRONES, key="sel_drone_val")
        
        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            # ТУТ ГНУЧКИЙ ВВОД ЧАСУ
            t_off_str = col1.text_input("Взльот (напр. 930 або 09:30)", value="09:00")
            t_land_str = col2.text_input("Посадка (напр. 1015 або 10:15)", value="09:30")
            
            p_off = smart_time_parse(t_off_str)
            p_land = smart_time_parse(t_land_str)
            
            if p_off and p_land:
                dur = calculate_duration(p_off, p_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            else:
                col3.warning("Невірний час")
                
            f_dist = col4.number_input("Відстань (м)", min_value=0, key="f_dist")
            cb1, cb2 = st.columns(2); f_akb = cb1.text_input("Номер АКБ", key="f_akb"); f_cyc = cb2.number_input("Цикли АКБ", min_value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res"); f_note = st.text_area("Примітки", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            
            if st.button("✅ ДОДАТИ У СПИСОК"):
                if p_off and p_land:
                    st.session_state.temp_flights.append({
                        "Дата": st.session_state.m_date_val.strftime("%d.%m.%Y"),
                        "Час завдання": f"{st.session_state.m_start_val.strftime('%H:%M')} - {st.session_state.m_end_val.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'],
                        "Дрон": st.session_state.sel_drone_val,
                        "Маршрут": st.session_state.m_route_val,
                        "Взльот": p_off.strftime("%H:%M"),
                        "Посадка": p_land.strftime("%H:%M"),
                        "Тривалість (хв)": calculate_duration(p_off, p_land),
                        "Дистанція (м)": st.session_state.f_dist,
                        "Номер АКБ": st.session_state.f_akb,
                        "Цикли АКБ": st.session_state.f_cyc,
                        "Результат": f_res,
                        "Примітки": f_note,
                        "files": st.session_state[f"uploader_{st.session_state.uploader_key}"]
                    })
                    st.session_state.uploader_key += 1; st.rerun()

        if st.session_state.temp_flights:
            df_t = pd.DataFrame(st.session_state.temp_flights); c_sh = ["Взльот", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ", "Цикли АКБ"]; df_v = df_t[c_sh]; df_v.columns = ["Зліт", "Посадка", "Відстань", "Хв", "№ АКБ", "Цикли"]; st.dataframe(df_v, use_container_width=True)
            cb1, cb2, cb3 = st.columns(3)
            if cb1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            if cb2.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts"); df_d = df_d[df_d['Оператор'] != st.session_state.user['name']] if not df_d.empty and "Оператор" in df_d.columns else df_d
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True)); st.success("💾 Збережено!")
            if cb3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                all_fl = st.session_state.temp_flights; send_telegram_msg(all_fl); final_to_db = []
                for f in all_fl: row = f.copy(); row.pop('files', None); row["Медіа (статус)"] = "З фото" if f.get('files') else "Текст"; final_to_db.append(row)
                db_m = load_data("Sheet1"); conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(final_to_db)], ignore_index=True))
                st.success("✅ Надіслано!"); st.session_state.temp_flights = []; st.rerun()

    # --- ВКЛАДКА АРХІВ (ЗАХИСТ ВІД ПОМИЛОК) ---
    with tab_hist:
        st.header("📜 Мій журнал")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']] if st.session_state.role == "Pilot" else df_h
            if not p_df.empty:
                cols = ["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Медіа (статус)", "Номер АКБ", "Цикли АКБ"]
                st.dataframe(p_df[[c for c in cols if c in p_df.columns]].sort_values(by="Дата", ascending=False), use_container_width=True)
            else: st.info("Архів порожній.")
        else: st.info("База даних ще не містить записів.")

    # --- ВКЛАДКА АНАЛІТИКА (ЗАХИСТ ВІД ПОМИЛОК) ---
    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns and "Дата" in df_s.columns:
            if st.session_state.role == "Pilot": df_s = df_s[df_s['Оператор'] == st.session_state.user['name']]
            if not df_s.empty:
                df_s['Дата_dt'] = pd.to_datetime(df_s['Дата'], format='%d.%m.%Y', errors='coerce')
                df_s = df_s.dropna(subset=['Дата_dt'])
                if not df_s.empty:
                    df_s['M_num'] = df_s['Дата_dt'].dt.month; df_s['Y_num'] = df_s['Дата_dt'].dt.year
                    rs = df_s.groupby(['Y_num', 'M_num']).agg(Польоти=('Дата', 'count'), Затримання=('Результат', lambda x: (x == "Затримання").sum()), Хв=('Тривалість (хв)', 'sum')).reset_index()
                    if not rs.empty:
                        rs['📅 Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['M_num']), '???')} {int(x['Y_num'])}", axis=1); rs['⏱ Наліт (ГГ:ХХ)'] = rs['Хв'].apply(format_to_time_str)
                        st.table(rs.sort_values(by=['Y_num', 'M_num'], ascending=False)[['📅 Місяць', 'Польоти', 'Затримання', '⏱ Наліт (ГГ:ХХ)']])
                    else: st.info("Дані відсутні.")
                else: st.info("Немає коректних дат.")
            else: st.info("Немає польотів.")
        else: st.info("Загальна аналітика поки недоступна.")

    # --- ВКЛАДКА ДЛЯ ДОВІДКИ ---
    with tab_info:
        st.header("ℹ️ Довідкова інформація")
        st.subheader("📞 Контакти та відповідальність")
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown("""<div class='contact-card'><div class='contact-title'>🎓 Інструктор</div><div class='contact-desc'>Питання тактики застосування, налаштування системи та спеціалізованого ПЗ БпАС.</div><b>Олександр</b><br>+380502310609</div>""", unsafe_allow_html=True)
        with c2: st.markdown("""<div class='contact-card'><div class='contact-title'>🔧 Технік-майстер</div><div class='contact-desc'>Механічні пошкодження майна, ремонт, збої апаратної частини.</div><b>Сергій</b><br>+380997517054</div>""", unsafe_allow_html=True)
        with c3: st.markdown("""<div class='contact-card'><div class='contact-title'>📦 Начальник складу</div><div class='contact-desc'>Облік майна, оформлення актів переміщення та передача обладнання.</div><b>Ірина</b><br>+380667869701</div>""", unsafe_allow_html=True)
        
        st.write("---"); st.subheader("📖 Документація")
        with st.expander("🛡️ ІНСТРУКЦІЯ КОРИСТУВАЧА"): st.markdown("""**1. Вхід:** Оберіть підрозділ та введіть прізвище.\n**2. Заявка:** Оберіть БпЛА, s/n, маршрут. Скопіюйте текст.\n**3. Польоти:** Тепер можна вводити час текстом (напр. 930 або 9).\n**4. ЦУС:** Система сама розбиває польоти на «До» та «Після» 00:00.""")
        with st.expander("📲 ВСТАНОВЛЕННЯ НА СМАРТФОН"): st.markdown("""**Android:** Chrome -> Додати на головний екран.\n**iPhone:** Safari -> Поділитися -> Додати на початковий екран.""")

    # Решта вкладок (Заявка, ЦУС) залишені без змін для стабільності