import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from docx import Document
import io
import requests
import os
from datetime import datetime, time, timedelta

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v5.6", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ---
UNITS = ["впс Окни", "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "віпс Ткаченкове", "віпс Гандрабури", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# --- 3. ДОПОМІЖНІ ФУНКЦІЇ ---
def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def format_to_time_str(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{int(hours):02d}:{int(minutes):02d}"

def add_flight_callback():
    dur = calculate_duration(st.session_state.t_off, st.session_state.t_land)
    st.session_state.temp_flights.append({
        "Дата": st.session_state.m_date_val.strftime("%d.%m.%Y"),
        "Час завдання": f"{st.session_state.m_start_val.strftime('%H:%M')} - {st.session_state.m_end_val.strftime('%H:%M')}",
        "Підрозділ": st.session_state.user['unit'],
        "Оператор": st.session_state.user['name'],
        "Дрон": st.session_state.user['drone'],
        "Маршрут": st.session_state.m_route_val,
        "Взльот": st.session_state.t_off.strftime("%H:%M"),
        "Посадка": st.session_state.t_land.strftime("%H:%M"),
        "Тривалість (хв)": dur,
        "Дистанція (м)": st.session_state.f_dist,
        "Номер АКБ": st.session_state.f_akb,
        "Цикли АКБ": st.session_state.f_cyc,
        "Результат": st.session_state.f_res,
        "Примітки": st.session_state.f_note,
        "files": st.session_state[f"uploader_{st.session_state.uploader_key}"]
    })
    st.session_state.f_dist = 0; st.session_state.f_akb = ""; st.session_state.f_cyc = 0; st.session_state.f_note = ""
    st.session_state.uploader_key += 1

# --- 4. РОБОТА З БАЗОЮ ТА TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try: return conn.read(worksheet=ws, ttl=0).dropna(how="all")
    except: return pd.DataFrame()

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    flights_txt = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for i, f in enumerate(all_fl)])
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n⏱ **Час завд.:** {first['Час завдання']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}\n🎯 **Результат:** {first['Результат']}"
    media_sent = False
    for fl in all_fl:
        if fl.get('files'):
            for img in fl['files']:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                requests.post(url, files={'photo': (img.name, img.getvalue(), img.type)}, data={'chat_id': str(TG_CHAT_ID), 'caption': report, 'parse_mode': 'Markdown'}, timeout=60)
            media_sent = True
    if not media_sent:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'}, timeout=30)

# --- 5. СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

st.markdown("<style>.stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; } .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; font-size: 1.2em; }</style>", unsafe_allow_html=True)

# --- 6. ЛОГІКА ІНТЕРФЕЙСУ ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS); n = st.text_input("Звання та прізвище:"); d = st.selectbox("Дрон:", DRONES)
            if st.button("Увійти") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                df_d = load_data("Drafts")
                if not df_d.empty:
                    my_d = df_d[df_d['Оператор'] == n].to_dict('records')
                    st.session_state.temp_flights.extend(my_d)
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("Вхід") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"
                st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name'] if st.session_state.role=='Pilot' else 'Адмін'}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.rerun()

    tab_app, tab_f, tab_cus, tab_hist, tab_stat = st.tabs([
        "📋 Заявка на політ", "🚀 Польоти", "📡 Польоти на ЦУС", "📜 Архів та Звіти", "📊 Аналітика"
    ])

    # --- ВКЛАДКА ЗАЯВКА ---
    with tab_app:
        st.header("📝 Формування заявки")
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник (підрозділ):", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            app_drones = st.multiselect("2. Тип БпЛА:", DRONES, default=[st.session_state.user['drone']] if st.session_state.user['drone'] in DRONES else None)
            app_sn = st.text_input("s/n:", placeholder="s/n: 123, 456")
            app_dates = st.date_input("3. Дата здійснення польоту:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            app_t_f = st.time_input("4. Час роботи з:", value=time(8,0)); app_t_t = st.time_input("до:", value=time(20,0))
            app_route = st.text_area("5. Маршрут:")
            app_h = st.text_input("6. Висота (м):", value="до 500 м"); app_r = st.text_input("7. Радіус (км):", value="до 5 км")
            app_purpose = st.selectbox("8. Мета:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            app_contact = st.text_input("9. Контактна особа:", value=f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ Сформувати текст заявки"):
            d_str = ", ".join(app_drones) + (f" ({app_sn})" if app_sn else "")
            date_range = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            final_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дата здійснення польоту: {date_range}\n4. Час роботи: з {app_t_f.strftime('%H:%M')} по {app_t_t.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {app_h}\n7. Радіус роботи (км): {app_r}\n8. Мета польоту: {app_purpose}\n9. Контактна особа: {app_contact}"
            st.code(final_txt, language="text")

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("Внесення даних зміні")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата завдання", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", value=time(8,0), step=60, key="m_start_val")
            m_end = c3.time_input("Зміна до", value=time(20,0), step=60, key="m_end_val")
            m_route = c4.text_input("Маршрут", key="m_route_val")

        with st.expander("📝 Додати новий виліт", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            t_o = col1.time_input("Взльот", value=time(9,0), step=60, key="t_off")
            t_l = col2.time_input("Посадка", value=time(9,30), step=60, key="t_land")
            dur_calc = calculate_duration(t_o, t_l)
            col3.markdown(f"<div class='duration-box'>⏳ <b>{dur_calc} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key="f_dist")
            cb1, cb2 = st.columns(2); f_akb = cb1.text_input("Номер АКБ", key="f_akb"); f_cyc = cb2.number_input("Цикли", min_value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
            f_note = st.text_area("Примітки", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            st.button("➕ Додати у список", on_click=add_flight_callback)

        if st.session_state.temp_flights:
            st.subheader("📋 Список польотів (чернетка)")
            df_temp = pd.DataFrame(st.session_state.temp_flights)
            cols_show = ["Взльот", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ"]
            df_v = df_temp[cols_show]; df_v.columns = ["Зліт", "Посадка", "Відстань", "Хв", "№ АКБ"]
            st.dataframe(df_v, use_container_width=True)
            c_b1, c_b2, c_b3 = st.columns(3)
            if c_b1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            if c_b2.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts")
                df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True))
                st.success("💾 Збережено!")
            if c_b3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                with st.spinner("Відправка..."):
                    all_fl = st.session_state.temp_flights
                    send_telegram_msg(all_fl)
                    final_to_db = []
                    for f in all_fl:
                        row = f.copy(); row.pop('files', None); row["Медіа (статус)"] = "З фото" if f.get('files') else "Текст"
                        final_to_db.append(row)
                    db_main = load_data("Sheet1")
                    conn.update(worksheet="Sheet1", data=pd.concat([db_main, pd.DataFrame(final_to_db)], ignore_index=True))
                    df_d = load_data("Drafts"); conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                    st.success("✅ Надіслано!"); st.session_state.temp_flights = []; st.rerun()

    # --- ВКЛАДКА ПОЛЬОТИ НА ЦУС (ОНОВЛЕНО ЛОГІКУ) ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if not st.session_state.temp_flights:
            st.info("Додайте польоти у вкладці '🚀 Польоти', щоб сформувати дані.")
        else:
            all_f = st.session_state.temp_flights
            shift_start_t = st.session_state.m_start_val # Час початку зміни
            
            before_midnight = []
            after_midnight = []
            midnight_crossed = False
            
            for f in all_f:
                f_start = datetime.strptime(f['Взльот'], "%H:%M").time()
                f_end = datetime.strptime(f['Посадка'], "%H:%M").time()
                
                # ТРИГЕР ПЕРЕХОДУ ПІСЛЯ 00:00:
                # 1. Якщо посадка раніше зльоту (політ через північ)
                # 2. Якщо зліт раніше початку зміни (вже наступна доба)
                # 3. Якщо будь-який попередній політ уже перетнув північ
                if midnight_crossed or f_end < f_start or f_start < shift_start_t:
                    midnight_crossed = True
                    after_midnight.append(f)
                else:
                    before_midnight.append(f)
            
            def format_cus(flights):
                return "\n".join([f"{f['Взльот']} - {f['Посадка']} - {f['Дистанція (м)']} м ({f['Тривалість (хв)']} хв)" for f in flights])
            
            st.subheader("🌙 Вікно 1: Польоти до 00:00")
            txt_before = format_cus(before_midnight)
            if txt_before: st.code(txt_before, language="text")
            else: st.write("Немає записів")
                
            st.subheader("☀️ Вікно 2: Польоти після 00:00")
            txt_after = format_cus(after_midnight)
            if txt_after: st.code(txt_after, language="text")
            else: st.write("Немає записів")

    # --- ВКЛАДКА АРХІВ ---
    with tab_hist:
        st.header("📜 Мій журнал")
        df_hist = load_data("Sheet1")
        if not df_hist.empty:
            personal_df = df_hist[df_hist['Оператор'] == st.session_state.user['name']] if st.session_state.role == "Pilot" else df_hist
            st.dataframe(personal_df.sort_values(by="Дата", ascending=False), use_container_width=True)

    # --- ВКЛАДКА АНАЛІТИКА ---
    with tab_stat:
        st.header("📊 Статистика")
        df_st = load_data("Sheet1")
        if not df_st.empty:
            if st.session_state.role == "Pilot": df_st = df_st[df_st['Оператор'] == st.session_state.user['name']]
            if not df_st.empty:
                df_st['Дата_dt'] = pd.to_datetime(df_st['Дата'], format='%d.%m.%Y', errors='coerce')
                df_st['Місяць'] = df_st['Дата_dt'].dt.strftime('%Y-%m')
                res = df_st.groupby('Місяць').agg(Польоти=('Дата', 'count'), Затримання=('Результат', lambda x: (x == "Затримання").sum()), Хв=('Тривалість (хв)', 'sum')).reset_index()
                res['Наліт (ГГ:ХХ)'] = res['Хв'].apply(format_to_time_str)
                st.table(res[['Місяць', 'Польоти', 'Затримання', 'Наліт (ГГ:ХХ)']])