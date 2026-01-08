import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from docx import Document
import io
import requests
import os
from datetime import datetime, time, timedelta

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v6.1", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ТА СЛОВНИКИ ---
UNITS = ["впс Окни", "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "віпс Ткаченкове", "віпс Гандрабури", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

UKR_MONTHS = {
    1: "січень", 2: "лютий", 3: "березень", 4: "квітень",
    5: "травень", 6: "червень", 7: "липень", 8: "серпень",
    9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"
}

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
        "Дрон": st.session_state.sel_drone_val,
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
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n⏱ **Час завд.:** {first['Час завдання']}\n🛡 **БпЛА:** {first['Дрон']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}\n🎯 **Результат:** {first['Результат']}"
    for fl in all_fl:
        if fl.get('files'):
            for img in fl['files']:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                requests.post(url, files={'photo': (img.name, img.getvalue(), img.type)}, data={'chat_id': str(TG_CHAT_ID), 'caption': report, 'parse_mode': 'Markdown'}, timeout=60)
    if not any(f.get('files') for f in all_fl):
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'}, timeout=30)

# --- 5. СТАН СЕСІЇ ТА СТИЛІ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .stButton>button:hover { background-color: #1B5E20; color: white; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #1b5e20; font-size: 1.2em; }
    .splash-text { text-align: center; color: #2E7D32; font-family: 'Courier New', Courier, monospace; font-weight: bold; border-top: 2px solid #2E7D32; border-bottom: 2px solid #2E7D32; padding: 10px 0; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 6. ЛОГІКА ІНТЕРФЕЙСУ ---
if not st.session_state.logged_in:
    # --- СТОРІНКА ВХОДУ (ЗАСТАВКА) ---
    st.markdown("<h1 style='text-align: center;'>🛡️ UAV PILOT CABINET</h1>", unsafe_allow_html=True)
    st.markdown("<div class='splash-text'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</div>", unsafe_allow_html=True)
    
    role = st.radio("Режим доступу:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ (впс/віпс):", UNITS); n = st.text_input("Звання та Прізвище пілота:")
            if st.button("УВІЙТИ В КАБІНЕТ") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n}
                df_d = load_data("Drafts")
                if not df_d.empty:
                    my_d = df_d[df_d['Оператор'] == n].to_dict('records')
                    st.session_state.temp_flights.extend(my_d)
                st.rerun()
        else:
            p = st.text_input("Пароль адміністратора:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"; st.rerun()
else:
    # --- ОСНОВНИЙ ЕКРАН ---
    st.sidebar.markdown(f"👤 **{st.session_state.user['name'] if st.session_state.role=='Pilot' else 'Адмін'}**")
    if st.sidebar.button("Вийти з системи"): st.session_state.logged_in = False; st.rerun()

    tab_app, tab_f, tab_cus, tab_hist, tab_stat = st.tabs([
        "📋 Заявка", "🚀 Польоти", "📡 ЦУС", "📜 Архів", "📊 Аналітика"
    ])

    # --- ВКЛАДКА ЗАЯВКА ---
    with tab_app:
        st.header("📝 Створення заявки")
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник (підрозділ):", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            c_drone = st.session_state.get('sel_drone_val', DRONES[0])
            app_drones = st.multiselect("2. Тип БпЛА:", DRONES, default=[c_drone] if c_drone in DRONES else None)
            app_sn = st.text_input("s/n (якщо декілька - через кому):", placeholder="s/n: 123, 456")
            app_dates = st.date_input("3. Дата здійснення польоту (період):", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2); a_t1 = c_t1.time_input("4. Час з:", value=time(8,0)); a_t2 = c_t2.time_input("Час до:", value=time(20,0))
            app_route = st.text_area("5. Маршрут (н.п. та район):")
            c_h1, c_h2 = st.columns(2); app_h = c_h1.text_input("6. Висота роботи (м):", value="до 500 м"); app_r = c_h2.text_input("7. Радіус (км):", value="до 5 км")
            app_purp = st.selectbox("8. Мета польоту:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            app_cont = st.text_input("9. Контактна особа (Прізвище та тел):", value=f"{st.session_state.user['name']}, тел: ")

        if st.button("✨ СФОРМУВАТИ ТЕКСТ"):
            d_str = ", ".join(app_drones) + (f" ({app_sn})" if app_sn else "")
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дата здійснення польоту: {dt_r}\n4. Час роботи: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {app_h}\n7. Радіус роботи (км): {app_r}\n8. Мета польоту: {app_purp}\n9. Контактна особа: {app_cont}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", value=time(8,0), step=60, key="m_start_val")
            m_end = c3.time_input("Зміна до", value=time(20,0), step=60, key="m_end_val")
            m_route = c4.text_input("Маршрут завдання", key="m_route_val")
            st.selectbox("🛡️ ОБЕРІТЬ БпЛА НА ЗМІНУ:", DRONES, key="sel_drone_val")

        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            t_o = col1.time_input("Взльот", value=time(9,0), key="t_off")
            t_l = col2.time_input("Посадка", value=time(9,30), key="t_land")
            dur = calculate_duration(t_o, t_l)
            col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key="f_dist")
            cb1, cb2 = st.columns(2); f_akb = cb1.text_input("Номер АКБ", key="f_akb"); f_cyc = cb2.number_input("Цикли АКБ", min_value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
            f_note = st.text_area("Примітки", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти польоту", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            st.button("✅ ДОДАТИ У СПИСОК", on_click=add_flight_callback)

        if st.session_state.temp_flights:
            st.write("---")
            st.subheader("📋 Поточний список (чернетка)")
            df_t = pd.DataFrame(st.session_state.temp_flights)
            c_sh = ["Взльот", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ", "Цикли АКБ"]
            df_v = df_t[c_sh]; df_v.columns = ["Зліт", "Посадка", "Відстань", "Хв", "№ АКБ", "Цикли"]
            st.dataframe(df_v, use_container_width=True)
            
            cb1, cb2, cb3 = st.columns(3)
            if cb1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            if cb2.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts")
                df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True))
                st.success("💾 Збережено!")
            if cb3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                with st.spinner("Завантаження..."):
                    all_fl = st.session_state.temp_flights; send_telegram_msg(all_fl)
                    final_to_db = []
                    for f in all_fl:
                        row = f.copy(); row.pop('files', None); row["Медіа (статус)"] = "З фото" if f.get('files') else "Текст"
                        final_to_db.append(row)
                    db_m = load_data("Sheet1")
                    conn.update(worksheet="Sheet1", data=pd.concat([db_m, pd.DataFrame(final_to_db)], ignore_index=True))
                    df_d = load_data("Drafts"); conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                    st.success("✅ Успішно надіслано!"); st.session_state.temp_flights = []; st.rerun()

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if not st.session_state.temp_flights: st.info("Список порожній.")
        else:
            all_f = st.session_state.temp_flights; s_start = st.session_state.m_start_val
            b_m, a_m, cr = [], [], False
            for f in all_f:
                fs = datetime.strptime(f['Взльот'], "%H:%M").time(); fe = datetime.strptime(f['Посадка'], "%H:%M").time()
                if cr or fe < fs or fs < s_start: cr = True; a_m.append(f)
                else: b_m.append(f)
            def fc(fls): return "\n".join([f"{f['Взльот']} - {f['Посадка']} - {f['Дистанція (м)']} м ({f['Тривалість (хв)']} хв)" for f in fls])
            st.subheader("🌙 Вікно 1: Польоти до 00:00"); st.code(fc(b_m), language="text")
            st.subheader("☀️ Вікно 2: Польоти після 00:00"); st.code(fc(a_m), language="text")

    # --- ВКЛАДКА АРХІВ ---
    with tab_hist:
        st.header("📜 Мій журнал польотів")
        df_h = load_data("Sheet1")
        if not df_h.empty:
            p_df = df_h[df_h['Оператор'] == st.session_state.user['name']] if st.session_state.role == "Pilot" else df_h
            cols = ["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Медіа (статус)", "Номер АКБ", "Цикли АКБ"]
            ex_cols = [c for c in cols if c in p_df.columns]
            st.dataframe(p_df[ex_cols].sort_values(by="Дата", ascending=False), use_container_width=True)
        else: st.info("Архів порожній.")

    # --- ВКЛАДКА АНАЛІТИКА ---
    with tab_stat:
        st.header("📊 Статистика нальоту")
        df_s = load_data("Sheet1")
        if not df_s.empty:
            if st.session_state.role == "Pilot": df_s = df_s[df_s['Оператор'] == st.session_state.user['name']]
            df_s['Дата_dt'] = pd.to_datetime(df_s['Дата'], format='%d.%m.%Y', errors='coerce')
            df_s['M_num'] = df_s['Дата_dt'].dt.month; df_s['Y_num'] = df_s['Дата_dt'].dt.year
            rs = df_s.groupby(['Y_num', 'M_num']).agg(Польоти=('Дата', 'count'), Затримання=('Результат', lambda x: (x == "Затримання").sum()), Хв=('Тривалість (хв)', 'sum')).reset_index()
            rs['📅 Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS[int(x['M_num'])]} {int(x['Y_num'])}", axis=1)
            rs['⏱ Наліт (ГГ:ХХ)'] = rs['Хв'].apply(format_to_time_str)
            st.table(rs.sort_values(by=['Y_num', 'M_num'], ascending=False)[['📅 Місяць', 'Польоти', 'Затримання', '⏱ Наліт (ГГ:ХХ)']])