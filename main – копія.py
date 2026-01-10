import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import requests
from datetime import datetime, time

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v3.6", layout="wide", page_icon="🛡️")

# Функція для отримання секретів (корінь або gsheets)
def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try:
        return st.secrets["connections"]["gsheets"].get(key)
    except:
        return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# Стилізація
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. СЕРВІСИ ТЕЛЕГРАМ ---
def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return "❌ Ключі не налаштовані"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': text, 'parse_mode': 'Markdown'}, timeout=30)
        return "✅ Успішно" if r.json().get("ok") else f"❌ {r.json().get('description')}"
    except: return "❌ Помилка зв'язку (Timeout)"

def send_telegram_photo(file_obj, caption):
    if not TG_TOKEN or not TG_CHAT_ID: return "❌ Ключі не налаштовані"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        files = {'photo': (file_obj.name, file_obj.getvalue(), file_obj.type)}
        r = requests.post(url, files=files, data={'chat_id': str(TG_CHAT_ID), 'caption': caption, 'parse_mode': 'Markdown'}, timeout=60)
        return "✅ Фото надіслано" if r.json().get("ok") else f"❌ {r.json().get('description')}"
    except: return "❌ Помилка зв'язку (Timeout)"

# --- 4. ДАНІ ТА СЕСІЯ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read()
        return df.dropna(how="all")
    except:
        return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Медіа (статус)"])

def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- 5. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.title("🛡️ Вхід у систему БпЛА")
    role_choice = st.radio("Оберіть роль:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role_choice == "Пілот":
            u_select = st.selectbox("Підрозділ:", UNITS)
            n_input = st.text_input("Звання та прізвище:")
            d_select = st.selectbox("Дрон на зміну:", DRONES)
            if st.button("Увійти"):
                if n_input:
                    st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u_select, "name": n_input, "drone": d_select}
                    st.rerun()
        else:
            p_input = st.text_input("Пароль:", type="password")
            if st.button("Вхід") and p_input == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"
                st.rerun()
else:
    st.sidebar.markdown(f"**👤 {st.session_state.role}**")
    if st.sidebar.button("🧪 Тест зв'язку з TG"):
        st.sidebar.info(send_telegram_text("🔔 Тест зв'язку: ОК"))
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Донесення", "📊 Аналітика"])

        with tab1:
            st.header("Внесення польотних даних")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата завдання", datetime.now())
                m_start = c2.time_input("Початок зміни", value=time(8,0))
                m_end = c3.time_input("Кінець зміни", value=time(20,0))
                m_route = c4.text_input("Напрямок/Маршрут", placeholder="Вкажіть район")

            with st.expander("📝 Додати новий виліт", expanded=True):
                col1, col2, col3, col4 = st.columns(4)
                t_off = col1.time_input("Взльот", value=time(9,0))
                t_land = col2.time_input("Посадка", value=time(9,30))
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Дистанція (м)", min_value=0)
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"])
                f_note = st.text_area("Примітки")
                f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True)

                if st.button("➕ Додати у список"):
                    st.session_state.temp_flights.append({
                        "Дата": m_date.strftime("%d.%m.%Y"),
                        "Час завдання": f"{m_start.strftime('%H:%M')} - {m_end.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'],
                        "Дрон": st.session_state.user['drone'],
                        "Маршрут": m_route,
                        "Взльот": t_off.strftime("%H:%M"),
                        "Посадка": t_land.strftime("%H:%M"),
                        "Тривалість (хв)": f_dur,
                        "Дистанція (м)": f_dist,
                        "Результат": f_res,
                        "Примітки": f_note,
                        "files": f_imgs
                    })
                    st.rerun()

            if st.session_state.temp_flights:
                st.subheader("📋 Вильоти у черзі")
                df_view = pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)"]]
                df_view.columns = ["Зліт", "Посадка", "Тривалість", "Дистанція"]
                st.dataframe(df_view, use_container_width=True)
                
                if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                    with st.spinner("Формування звіту та відправка..."):
                        all_fl = st.session_state.temp_flights
                        first = all_fl[0]
                        flights_list = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for i, f in enumerate(all_fl)])
                        total_min = sum([f['Тривалість (хв)'] for f in all_fl])

                        report = (
                            f"🚁 **Донесення: {first['Підрозділ']}**\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"👤 **Пілот:** {first['Оператор']}\n"
                            f"📅 **Дата:** {first['Дата']}\n"
                            f"⏱ **Час завд.:** {first['Час завдання']}\n"
                            f"📍 **Маршрут:** {first['Маршрут']}\n"
                            f"🛡 **БпЛА:** {first['Дрон']}\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🚀 **Вильоти:**\n{flights_list}\n"
                            f"⏱ **Загальний наліт:** {total_min} хв\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🎯 **Результат:** {first['Результат']}\n"
                            f"📝 **Примітки:** {first['Примітки']}"
                        )

                        media_sent = False
                        final_rows = []
                        for fl in all_fl:
                            if fl['files']:
                                for img in fl['files']: send_telegram_photo(img, report)
                                media_sent = True
                            row = fl.copy(); del row['files']
                            row["Медіа (статус)"] = "З фото" if fl['files'] else "Текст"
                            final_rows.append(row)

                        if not media_sent: send_telegram_text(report)
                        
                        old_df = load_data()
                        conn.update(worksheet="Sheet1", data=pd.concat([old_df, pd.DataFrame(final_rows)], ignore_index=True))
                        st.success("Дані успішно відправлені!")
                        st.session_state.temp_flights = []
                        st.rerun()

        with tab2:
            st.header("📜 Генерація донесення")
            r_date = st.date_input("Оберіть дату")
            df_full = load_data()
            if not df_full.empty:
                filt = df_full[(df_full['Дата'] == r_date.strftime("%d.%m.%Y")) & (df_full['Підрозділ'] == st.session_state.user['unit'])]
                if not filt.empty:
                    st.success(f"Знайдено польотів: {len(filt)}")
                    # Функція generate_docx має бути визначена вище
                else: st.warning("Немає записів за цю дату.")

        with tab3:
            st.header("📊 Аналітика")
            df_full = load_data()
            if not df_full.empty:
                u_df = df_full[df_full['Підрозділ'] == st.session_state.user['unit']].copy()
                if not u_df.empty:
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'], errors='coerce')
                    st.plotly_chart(px.bar(u_df, x='Дата', y='Тривалість (хв)', color='Результат', title="Наліт підрозділу"), use_container_width=True)
    else:
        st.title("🛰️ Адмін-панель")
        all_data = load_data()
        if not all_data.empty:
            st.dataframe(all_data, use_container_width=True)
            csv = all_data.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Експорт бази CSV", csv, "uav_base.csv")