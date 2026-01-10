import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time
from datetime import datetime, time as d_time, timedelta
import json

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

# --- 3. ЗБЕРЕЖЕННЯ ТА ЗАВАНТАЖЕННЯ ДАНИХ (LocalStorage емуляція) ---
def save_user_credentials(unit, name):
    try:
        credentials = {"unit": unit, "name": name, "timestamp": datetime.now().isoformat()}
        st.session_state.saved_credentials = credentials
    except: pass

def load_user_credentials():
    return st.session_state.get('saved_credentials', {"unit": UNITS[0], "name": ""})

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

# --- 5. РОБОТА З БАЗОЮ ТА TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        return df.dropna(how="all")
    except: return pd.DataFrame()

def get_drones_for_unit(unit):
    try:
        df = load_data("DronesDB")
        if df.empty or "Підрозділ" not in df.columns: return []
        unit_drones = df[df['Підрозділ'] == unit]
        if unit_drones.empty: return []
        drones_list = []
        for _, row in unit_drones.iterrows():
            model = row.get('Модель', '')
            sn = row.get('S/N', '')
            if model:
                display = f"{model} (S/N: {sn})" if sn else model
                drones_list.append(display)
        return drones_list if drones_list else []
    except:
        return []

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    
    # Формуємо детальний текст з усіма польотами
    flights_details = []
    for i, f in enumerate(all_fl):
        flight_text = f"{i+1}. {f['Зліт']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)"
        if f.get('Результат'):
            flight_text += f"\n   Результат: {f['Результат']}"
        if f.get('Примітки'):
            flight_text += f"\n   Примітки: {f['Примітки']}"
        flights_details.append(flight_text)
    
    flights_txt = "\n".join(flights_details)
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n⏰ **Час завдання:** {first['Час завдання']}\n🛡 **БпЛА:** {first['Дрон']}\n🗺 **Маршрут:** {first['Маршрут']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}"
    
    # Збираємо всі фото в одну медіагрупу
    all_photos = []
    for fl in all_fl:
        if fl.get('files'):
            for img in fl['files']:
                all_photos.append(img)
    
    # Відправляємо медіагрупу якщо є фото
    if all_photos:
        try:
            files = {}
            media = []
            for idx, img in enumerate(all_photos):
                files[f'photo{idx}'] = (img.name, img.getvalue(), img.type)
                media_item = {
                    'type': 'photo',
                    'media': f'attach://photo{idx}'
                }
                if idx == 0:
                    media_item['caption'] = report
                    media_item['parse_mode'] = 'Markdown'
                media.append(media_item)
            
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup",
                data={'chat_id': str(TG_CHAT_ID), 'media': json.dumps(media)},
                files=files
            )
        except:
            # Якщо медіагрупа не працює, відправляємо по одному
            for img in all_photos:
                requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                    files={'photo': (img.name, img.getvalue(), img.type)},
                    data={'chat_id': str(TG_CHAT_ID), 'caption': report, 'parse_mode': 'Markdown'}
                )
    else:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'}
        )

# --- 6. ІНІЦІАЛІЗАЦІЯ СТАНУ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
if 'saved_credentials' not in st.session_state: st.session_state.saved_credentials = {"unit": UNITS[0], "name": ""}
if 'app_contact' not in st.session_state: st.session_state.app_contact = ""
if 'app_phone' not in st.session_state: st.session_state.app_phone = ""
if 'clear_flight_form' not in st.session_state: st.session_state.clear_flight_form = False

# --- 7. СТИЛІ ---
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
    .stAlert p { color: black !important; }
    .login-hint { font-size: 0.85em; color: #666; font-style: italic; margin-top: -10px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 8. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        st.markdown("<div class='splash-container'><h1 style='font-size: 4em;'>🛡️</h1><h1>UAV PILOT CABINET</h1><div class='slogan-box'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Ініціалізація...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 9. ІНТЕРФЕЙС ВХОДУ ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД У СИСТЕМУ</h2>", unsafe_allow_html=True)
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    
    with st.container(border=True):
        if role == "Пілот":
            # Завантажуємо збережені дані
            saved = load_user_credentials()
            
            unit_index = UNITS.index(saved['unit']) if saved['unit'] in UNITS else 0
            u = st.selectbox("Підрозділ:", UNITS, index=unit_index)
            n = st.text_input("Звання та Прізвище:", value=saved['name'], placeholder="наприклад: ст.с-т Іваненко")
            
            if saved['name']:
                st.markdown("<p class='login-hint'>💡 Дані автоматично збережено з попереднього входу</p>", unsafe_allow_html=True)
            
            if st.button("УВІЙТИ") and n:
                # Зберігаємо облікові дані
                save_user_credentials(u, n)
                
                st.session_state.logged_in = True
                st.session_state.role = "Pilot"
                st.session_state.user = {"unit": u, "name": n}
                
                # Завантаження чернеток
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    my_d = df_d[df_d['Оператор'] == n].to_dict('records')
                    st.session_state.temp_flights.extend(my_d)
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.session_state.role = "Admin"
                st.session_state.user = {"unit": "Адміністрація", "name": "Адміністратор"}
                st.rerun()

# --- 10. ОСНОВНИЙ ІНТЕРФЕЙС ---
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name'] if st.session_state.role=='Pilot' else 'Адмін'}**")
    if st.sidebar.button("Вийти"): 
        st.session_state.logged_in = False
        st.session_state.splash_done = False
        st.rerun()

    tab_f, tab_cus, tab_app, tab_hist, tab_stat, tab_info = st.tabs(["🚀 Польоти", "📡 ЦУС", "📋 Заявка", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("Внесення польотів")
        
        # Отримуємо дрони для поточного підрозділу
        available_drones = get_drones_for_unit(st.session_state.user['unit'])
        if not available_drones:
            st.warning(f"⚠️ У базі даних немає дронів для підрозділу '{st.session_state.user['unit']}'. Зверніться до адміністратора.")
            available_drones = ["Дрон не вказано"]
        
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата завдання", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="m_start_val")
            m_end = c3.time_input("Зміна до", d_time(20,0), key="m_end_val")
            m_route = c4.text_input("Маршрут", key="m_route_val", placeholder="Введіть маршрут")
            selected_drone = st.selectbox("🛡️ БпЛА НА ЗМІНУ:", available_drones, key="sel_drone_val")
        
        # Очищення форми після додавання
        if st.session_state.clear_flight_form:
            st.session_state.clear_flight_form = False
            st.rerun()
        
        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            
            # Використовуємо порожні значення за замовчуванням
            t_off_str = col1.text_input("Зліт", value="", placeholder="09:00 або 0930", help="Можна 930 або 0930", key="t_off_input")
            t_land_str = col2.text_input("Посадка", value="", placeholder="09:30", key="t_land_input")
            
            p_off, p_land = smart_time_parse(t_off_str), smart_time_parse(t_land_str)
            if p_off and p_land:
                dur = calculate_duration(p_off, p_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            else:
                col3.info("⏳ Час?")
            
            f_dist = col4.number_input("Відстань (м)", min_value=0, value=0, key="f_dist", help="Відстань польоту в метрах")
            
            cb1, cb2 = st.columns(2)
            f_akb = cb1.text_input("Номер АКБ", value="", placeholder="Введіть номер", key="f_akb")
            f_cyc = cb2.number_input("Цикли АКБ", min_value=0, value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
            f_note = st.text_area("Примітки", value="", placeholder="Додаткова інформація (необов'язково)", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            
            if st.button("✅ ДОДАТИ У СПИСОК"):
                if p_off and p_land:
                    st.session_state.temp_flights.append({
                        "Дата": st.session_state.m_date_val.strftime("%d.%m.%Y"),
                        "Час завдання": f"{st.session_state.m_start_val.strftime('%H:%M')} - {st.session_state.m_end_val.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'],
                        "Дрон": selected_drone,
                        "Маршрут": st.session_state.m_route_val,
                        "Зліт": p_off.strftime("%H:%M"),
                        "Посадка": p_land.strftime("%H:%M"),
                        "Тривалість (хв)": calculate_duration(p_off, p_land),
                        "Дистанція (м)": f_dist,
                        "Номер АКБ": f_akb,
                        "Цикли АКБ": f_cyc,
                        "Результат": f_res,
                        "Примітки": f_note,
                        "files": f_imgs
                    })
                    # Збільшуємо ключ для uploader та очищуємо форму
                    st.session_state.uploader_key += 1
                    st.session_state.clear_flight_form = True
                    st.rerun()
                else:
                    st.error("⚠️ Будь ласка, введіть коректний час зльоту та посадки")

        if st.session_state.temp_flights:
            df_t = pd.DataFrame(st.session_state.temp_flights)
            # Перевіряємо які колонки є в датафреймі
            cols_to_show = []
            col_mapping = {}
            if "Зліт" in df_t.columns:
                cols_to_show.extend(["Зліт", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ", "Цикли АКБ"])
                col_mapping = {"Зліт": "Зліт", "Посадка": "Посадка", "Дистанція (м)": "Відстань", "Тривалість (хв)": "Хв", "Номер АКБ": "№ АКБ", "Цикли АКБ": "Цикли"}
            else:
                # Для старих записів з "Взльот"
                cols_to_show.extend(["Взльот", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ", "Цикли АКБ"])
                col_mapping = {"Взльот": "Зліт", "Посадка": "Посадка", "Дистанція (м)": "Відстань", "Тривалість (хв)": "Хв", "Номер АКБ": "№ АКБ", "Цикли АКБ": "Цикли"}
            
            df_v = df_t[[c for c in cols_to_show if c in df_t.columns]]
            df_v = df_v.rename(columns=col_mapping)
            st.dataframe(df_v, use_container_width=True)
            
            cb1, cb2, cb3 = st.columns(3)
            if cb1.button("🗑️ Видалити останній"):
                st.session_state.temp_flights.pop()
                st.rerun()
            
            if cb2.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts")
                df_d = df_d[df_d['Оператор'] != st.session_state.user['name']] if not df_d.empty and "Оператор" in df_d.columns else df_d
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True))
                st.success("💾 Збережено!")
            
            if cb3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                all_fl = st.session_state.temp_flights
                send_telegram_msg(all_fl)
                final_to_db = []
                for f in all_fl:
                    row = f.copy()
                    row.pop('files', None)
                    row["Медіа (статус)"] = "З фото" if f.get('files') else "Текст"
                    final_to_db.append(row)
                db_m = load_data("Sheet1")
                conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(final_to_db)], ignore_index=True))
                
                # Очищуємо Drafts після успішної відправки
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                    conn.update(worksheet="Drafts", data=df_d)
                
                st.success("✅ Надіслано!")
                st.session_state.temp_flights = []
                st.rerun()

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if not st.session_state.temp_flights:
            st.info("Додайте польоти.")
        else:
            all_f = st.session_state.temp_flights
            s_start = st.session_state.m_start_val
            b_m, a_m, cr = [], [], False
            for f in all_f:
                # Підтримка старих і нових записів
                takeoff_key = "Зліт" if "Зліт" in f else "Взльот"
                fs = datetime.strptime(f[takeoff_key], "%H:%M").time()
                fe = datetime.strptime(f['Посадка'], "%H:%M").time()
                if cr or fe < fs or fs < s_start:
                    cr = True
                    a_m.append(f)
                else:
                    b_m.append(f)
            def fc(fls):
                result = []
                for f in fls:
                    takeoff_key = "Зліт" if "Зліт" in f else "Взльот"
                    result.append(f"{f[takeoff_key]} - {f['Посадка']} - {f['Дистанція (м)']} м ({f['Тривалість (хв)']} хв)")
                return "\n".join(result)
            st.subheader("🌙 До 00:00")
            st.code(fc(b_m), language="text")
            st.subheader("☀️ Після 00:00")
            st.code(fc(a_m), language="text")

    # --- ВКЛАДКА ЗАЯВКА ---
    with tab_app:
        st.header("📝 Формування заявки")
        
        st.warning("⚠️ **УВАГА:** Даний розділ НЕ відправляє заявки автоматично на ЦУС! Він лише допомагає швидко сформувати текст заявки. Після формування скопіюйте текст та відправте його самостійно через месенджери.")
        
        # Отримуємо дрони для поточного підрозділу
        available_drones = get_drones_for_unit(st.session_state.user['unit'])
        if not available_drones:
            st.warning(f"⚠️ У базі даних немає дронів для підрозділу '{st.session_state.user['unit']}'.")
            available_drones = ["Дрон не вказано"]
        
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            app_drones = st.multiselect("2. Тип БпЛА:", available_drones, default=None)
            app_dates = st.date_input("3. Дата здійснення польоту:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2)
            a_t1 = c_t1.time_input("4. Час роботи з:", d_time(8,0))
            a_t2 = c_t2.time_input("до:", d_time(20,0))
            app_route = st.text_area("5. Населений пункт (маршрут):")
            c_h1, c_h2 = st.columns(2)
            a_h = c_h1.text_input("6. Висота (м):", "до 500 м")
            a_r = c_h2.text_input("7. Радіус (км):", "до 5 км")
            app_purp = st.selectbox("8. Мета:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            
            c_cont, c_phone = st.columns(2)
            app_cont = c_cont.text_input("9. Контактна особа:", value=st.session_state.app_contact if st.session_state.app_contact else st.session_state.user['name'], placeholder="Прізвище Ім'я")
            app_phone = c_phone.text_input("10. Номер телефону:", value=st.session_state.app_phone, placeholder="+380...")
            
        if st.button("✨ СФОРМУВАТИ ТЕКСТ ЗАЯВКИ"):
            # Зберігаємо введені контактні дані
            st.session_state.app_contact = app_cont
            st.session_state.app_phone = app_phone
            
            d_str = ", ".join(app_drones) if app_drones else "не вказано"
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            contact_info = f"{app_cont}, тел: {app_phone}" if app_phone else app_cont
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дата здійснення польоту: {dt_r}\n4. Час роботи: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {a_h}\n7. Радіус роботи (км): {a_r}\n8. Мета польоту: {app_purp}\n9. Контактна особа: {contact_info}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА АРХІВ ---
    with tab_hist:
        st.header("📜 Мій журнал")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']] if st.session_state.role == "Pilot" else df_h
            if not p_df.empty:
                cols = ["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Зліт", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Медіа (статус)", "Номер АКБ", "Цикли АКБ"]
                st.dataframe(p_df[[c for c in cols if c in p_df.columns]].sort_values(by="Дата", ascending=False), use_container_width=True)
            else:
                st.info("Архів порожній.")
        else:
            st.info("База даних ще не містить записів.")

    # --- ВКЛАДКА АНАЛІТИКА ---
    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns and "Дата" in df_s.columns:
            if st.session_state.role == "Pilot":
                df_s = df_s[df_s['Оператор'] == st.session_state.user['name']]
            if not df_s.empty:
                df_s['Дата_dt'] = pd.to_datetime(df_s['Дата'], format='%d.%m.%Y', errors='coerce')
                df_s = df_s.dropna(subset=['Дата_dt'])
                if not df_s.empty:
                    df_s['M_num'] = df_s['Дата_dt'].dt.month
                    df_s['Y_num'] = df_s['Дата_dt'].dt.year
                    rs = df_s.groupby(['Y_num', 'M_num']).agg(
                        Польоти=('Дата', 'count'),
                        Затримання=('Результат', lambda x: (x == "Затримання").sum()),
                        Хв=('Тривалість (хв)', 'sum')
                    ).reset_index()
                    if not rs.empty:
                        rs['Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['M_num']), '???')} {int(x['Y_num'])}", axis=1)
                        rs['Наліт'] = rs['Хв'].apply(format_to_time_str)
                        st.table(rs.sort_values(by=['Y_num', 'M_num'], ascending=False)[['Місяць', 'Польоти', 'Затримання', 'Наліт']])
            else:
                st.info("Немає польотів.")

    # --- ВКЛАДКА ДОВІДКА ---
    with tab_info:
        st.header("ℹ️ Довідка")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("<div class='contact-card'><div class='contact-title'>🎓 Інструктор</div><div class='contact-desc'>Питання тактики застосування, налаштування системи та спеціалізованого ПЗ БпАС.</div><b>Олександр</b><br>+380502310609</div>", unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='contact-card'><div class='contact-title'>🔧 Технік-майстер</div><div class='contact-desc'>Механічні пошкодження майна, ремонт, збої апаратної частини.</div><b>Сергій</b><br>+380997517054</div>", unsafe_allow_html=True)
        with c3:
            st.markdown("<div class='contact-card'><div class='contact-title'>📦 Начальник складу</div><div class='contact-desc'>Облік майна, оформлення актів переміщення та передача обладнання.</div><b>Ірина</b><br>+380667869701</div>", unsafe_allow_html=True)
        st.write("---")
        st.subheader("📖 Повна документація")
        with st.expander("🛡️ ІНСТРУКЦІЯ КОРИСТУВАЧА", expanded=False):
            st.markdown("""**1. 🔑 Вхід у систему**
* Оберіть Підрозділ, введіть Звання та Прізвище.
* При повторному вході дані автоматично підставляться.
* Натисніть «Увійти».

**2. 🚀 Вкладка «Польоти»**
* **Крок А (Завдання):** Встановіть Дату, Час зміни та оберіть БпЛА на зміну.
* **Крок Б (Виліт):** Вкажіть час Зльоту/Посадки, Відстань, Номер АКБ та Цикли.
* **Крок В (Управління):** Тисніть «➕ Додати у список». В кінці зміни — «🚀 ВІДПРАВИТИ ВСІ ДАНІ».

**3. 📡 Вкладка «ЦУС»**
* Система сама розбиває польоти на вікна «До 00:00» та «Після 00:00».

**4. 📋 Вкладка «Заявка»**
* УВАГА: Розділ НЕ відправляє заявки автоматично!
* Оберіть параметри польоту та натисніть «Сформувати текст заявки».
* Скопіюйте текст та відправте самостійно через месенджери.

**💡 Поради:**
* При слабкому інтернеті тисніть «Зберегти в Хмару».
* Для нічної зміни вказуйте дату, якою зміна почалася.
* Система автоматично запам'ятовує ваші дані входу.""")
        with st.expander("📲 ЯК ВСТАНОВИТИ НА СМАРТФОН", expanded=False):
            st.markdown("""**Android (Chrome):** Три крапки (⋮) -> «Додати на головний екран».
**iPhone (Safari):** Поділитися -> «Додати на початковий екран».""")
        st.write("---")
        st.markdown("<div style='text-align: center; color: black;'>Слава Україні! 🇺🇦</div>", unsafe_allow_html=True)