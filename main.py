import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import requests
import os
from datetime import datetime, time

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v4.6", layout="wide", page_icon="🛡️")

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

# --- 3. ДОПОМІЖНІ ФУНКЦІЇ ---
def calculate_duration(start, end):
    s_min = start.hour * 60 + start.minute
    e_min = end.hour * 60 + end.minute
    diff = e_min - s_min
    return diff if diff >= 0 else diff + 1440

def add_flight_callback():
    duration = calculate_duration(st.session_state.t_off, st.session_state.t_land)
    new_flight = {
        "Дата": st.session_state.m_date_val.strftime("%d.%m.%Y"),
        "Час завдання": f"{st.session_state.m_start_val.strftime('%H:%M')} - {st.session_state.m_end_val.strftime('%H:%M')}",
        "Підрозділ": st.session_state.user['unit'],
        "Оператор": st.session_state.user['name'],
        "Дрон": st.session_state.user['drone'],
        "Маршрут": st.session_state.m_route_val,
        "Взльот": st.session_state.t_off.strftime("%H:%M"),
        "Посадка": st.session_state.t_land.strftime("%H:%M"),
        "Тривалість (хв)": duration,
        "Дистанція (м)": st.session_state.f_dist,
        "Номер АКБ": st.session_state.f_akb,
        "Цикли АКБ": st.session_state.f_cyc,
        "Результат": st.session_state.f_res,
        "Примітки": st.session_state.f_note,
        "files": st.session_state[f"uploader_{st.session_state.uploader_key}"]
    }
    st.session_state.temp_flights.append(new_flight)
    st.session_state.f_dist = 0
    st.session_state.f_akb = ""
    st.session_state.f_cyc = 0
    st.session_state.f_note = ""
    st.session_state.uploader_key += 1

# --- 4. СЕРВІСИ ТЕЛЕГРАМ ТА ТАБЛИЦЬ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet="Sheet1"):
    try:
        df = conn.read(worksheet=worksheet)
        return df.dropna(how="all")
    except:
        return pd.DataFrame()

def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return "❌ Помилка налаштувань"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': text, 'parse_mode': 'Markdown'}, timeout=30)
        return "✅ Успішно" if r.json().get("ok") else f"❌ {r.json().get('description')}"
    except: return "❌ Помилка зв'язку"

def send_telegram_photo(file_obj, caption):
    if not TG_TOKEN or not TG_CHAT_ID: return "❌ Помилка налаштувань"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        files = {'photo': (file_obj.name, file_obj.getvalue(), file_obj.type)}
        r = requests.post(url, files=files, data={'chat_id': str(TG_CHAT_ID), 'caption': caption, 'parse_mode': 'Markdown'}, timeout=60)
        return "✅ Фото надіслано" if r.json().get("ok") else f"❌ {r.json().get('description')}"
    except: return "❌ Помилка зв'язку"

# --- 5. СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

# --- 6. ІНТЕРФЕЙС ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; font-size: 1.2em; }
    </style>
    """, unsafe_allow_html=True)

if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Дрон на зміну:", DRONES)
            if st.button("Увійти") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                # Автоматичне завантаження хмарних чернеток
                df_drafts = load_data(worksheet="Drafts")
                if not df_drafts.empty:
                    my_drafts = df_drafts[df_drafts['Оператор'] == n].to_dict('records')
                    st.session_state.temp_flights.extend(my_drafts)
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("Вхід") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"
                st.rerun()
else:
    st.sidebar.markdown(f"**👤 {st.session_state.role}**")
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Архів та Звіти", "📊 Аналітика"])

        with tab1:
            st.header("Внесення даних зміні")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                m_date = c1.date_input("Дата завдання", datetime.now(), key="m_date_val")
                m_start = c2.time_input("Зміна з", value=time(8,0), step=60, key="m_start_val")
                m_end = c3.time_input("Зміна до", value=time(20,0), step=60, key="m_end_val")
                m_route = c4.text_input("Маршрут", key="m_route_val")

            with st.expander("📝 Додати політ", expanded=True):
                col1, col2, col3, col4 = st.columns(4)
                t_off_i = col1.time_input("Взльот", value=time(9,0), step=60, key="t_off")
                t_land_i = col2.time_input("Посадка", value=time(9,30), step=60, key="t_land")
                current_dur = calculate_duration(t_off_i, t_land_i)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{current_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Відстань (м)", min_value=0, step=10, key="f_dist")
                cb1, cb2 = st.columns(2); f_akb = cb1.text_input("№ АКБ", key="f_akb"); f_cyc = cb2.number_input("Цикли", min_value=0, key="f_cyc")
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
                f_note = st.text_area("Примітки", key="f_note")
                f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
                st.button("➕ Додати у список", on_click=add_flight_callback)

            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Вильоти у черзі")
                raw_df = pd.DataFrame(st.session_state.temp_flights)
                cols = ["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Номер АКБ"]
                st.dataframe(raw_df[[c for c in cols if c in raw_df.columns]], use_container_width=True)
                
                c_btn1, c_btn2, c_btn3 = st.columns(3)
                if c_btn1.button("🗑️ Видалити останній"):
                    st.session_state.temp_flights.pop(); st.rerun()
                
                if c_btn2.button("💾 Зберегти чернетку в Хмару"):
                    with st.spinner("Зберігаємо..."):
                        # Очищаємо старі чернетки пілота і пишемо нові
                        df_d = load_data(worksheet="Drafts")
                        df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                        new_drafts = pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')
                        final_d = pd.concat([df_d, new_drafts], ignore_index=True)
                        conn.update(worksheet="Drafts", data=final_d)
                        st.success("Чернетка збережена в Google Sheets!")

                if c_btn3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                    with st.spinner("Відправка звіту..."):
                        all_fl = st.session_state.temp_flights
                        first = all_fl[0]
                        flights_txt = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for i, f in enumerate(all_fl)])
                        report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}\n🎯 **Результат:** {first['Результат']}"
                        
                        media_sent = False; final_rows = []
                        for fl in all_fl:
                            if fl.get('files'):
                                for img in fl['files']: send_telegram_photo(img, report)
                                media_sent = True
                            row = fl.copy(); row.pop('files', None); row["Медіа (статус)"] = "З фото" if fl.get('files') else "Текст"
                            final_rows.append(row)
                        if not media_sent: send_telegram_text(report)
                        
                        # Запис в основну базу і очищення чернеток
                        conn.update(worksheet="Sheet1", data=pd.concat([load_data(), pd.DataFrame(final_rows)], ignore_index=True))
                        df_d = load_data(worksheet="Drafts")
                        conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                        st.success("Дані відправлені! Хмарна чернетка очищена."); st.session_state.temp_flights = []; st.rerun()

        with tab2:
            st.header("📜 Мій журнал польотів")
            df_hist = load_data(worksheet="Sheet1")
            if not df_hist.empty:
                my_history = df_hist[df_hist['Оператор'] == st.session_state.user['name']].sort_values(by="Дата", ascending=False)
                if not my_history.empty:
                    st.dataframe(my_history[["Дата", "Взльот", "Посадка", "Тривалість (хв)", "Результат", "Примітки"]], use_container_width=True)
                else: st.info("У вас ще немає надісланих польотів.")
            
            st.write("---")
            st.subheader("📄 Генерація офіційного донесення")
            r_date = st.date_input("Дата звіту", datetime.now())
            if st.button("Сформувати DOCX"):
                target = r_date.strftime("%d.%m.%Y")
                filt = df_hist[(df_hist['Дата'] == target) & (df_hist['Підрозділ'] == st.session_state.user['unit'])]
                if not filt.empty:
                    st.success(f"Знайдено польотів: {len(filt)}")
                    # Тут функція generate_docx (аналогічна v4.5)
                else: st.warning("Даних за цю дату немає.")

        with tab3:
            st.header("📊 Моя статистика")
            if not df_hist.empty:
                u_df = df_hist[df_hist['Оператор'] == st.session_state.user['name']].copy()
                if not u_df.empty:
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'], errors='coerce')
                    st.plotly_chart(px.bar(u_df, x='Дата', y='Тривалість (хв)', color='Результат', title="Ваш наліт"), use_container_width=True)