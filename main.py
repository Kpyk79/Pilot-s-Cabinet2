import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import requests
import os
from datetime import datetime, time

# --- 1. КОНФІГУРАЦІЯ ---
st.set_page_config(page_title="UAV Pilot Cabinet v4.6", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# --- 3. ФУНКЦІЇ ---
def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

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

conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try: return conn.read(worksheet=ws).dropna(how="all")
    except: return pd.DataFrame()

# --- 4. СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

# --- 5. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота v4.6")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS); n = st.text_input("Звання та Прізвище"); d = st.selectbox("Дрон:", DRONES)
            if st.button("Увійти") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                # ПІДТЯГУВАННЯ ЧЕРНЕТОК
                df_d = load_data("Drafts")
                if not df_d.empty:
                    st.session_state.temp_flights.extend(df_d[df_d['Оператор'] == n].to_dict('records'))
                st.rerun()
        else:
            if st.text_input("Пароль:", type="password") == ADMIN_PASSWORD and st.button("Вхід"):
                st.session_state.logged_in, st.session_state.role = True, "Admin"; st.rerun()
else:
    # --- ОСНОВНИЙ ЕКРАН ---
    tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Архів та Звіти", "📊 Аналітика"])

    with tab1:
        # (Тут блок внесення даних, як у v4.5)
        st.header("Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Початок зміні", value=time(8,0), key="m_start_val")
            m_end = c3.time_input("Кінець зміні", value=time(20,0), key="m_end_val")
            m_route = c4.text_input("Маршрут", key="m_route_val")

        with st.expander("📝 Новий виліт", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            t_o = col1.time_input("Зліт", value=time(9,0), step=60, key="t_off")
            t_l = col2.time_input("Посадка", value=time(9,30), step=60, key="t_land")
            col3.info(f"⏳ {calculate_duration(t_o, t_l)} хв")
            f_dist = col4.number_input("Відстань (м)", min_value=0, key="f_dist")
            cb1, cb2 = st.columns(2); f_akb = cb1.text_input("№ АКБ", key="f_akb"); f_cyc = cb2.number_input("Цикли", min_value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
            f_note = st.text_area("Примітки", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            st.button("➕ Додати у список", on_click=add_flight_callback)

        if st.session_state.temp_flights:
            st.write("---")
            st.subheader("📋 Вильоти у черзі")
            st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Тривалість (хв)", "Номер АКБ"]], use_container_width=True)
            
            c_b1, c_b2, c_b3 = st.columns(3)
            if c_b1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            
            if c_b2.button("💾 Зберегти чернетку в Хмару"):
                with st.spinner("💾 Зберігаємо..."):
                    df_d = load_data("Drafts")
                    df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                    new_d = pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')
                    conn.update(worksheet="Drafts", data=pd.concat([df_d, new_d], ignore_index=True))
                    st.success("💾 Збережено!")

            if c_b3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                # (Логіка відправки з v4.5)
                st.success("✅ Надіслано!")
                # Очищення хмарної чернетки після відправки
                df_d = load_data("Drafts")
                conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                st.session_state.temp_flights = []; st.rerun()

    with tab2:
        st.header("📜 Мій архів польотів")
        df_all = load_data("Sheet1")
        if not df_all.empty:
            my_df = df_all[df_all['Оператор'] == st.session_state.user['name']].sort_values(by="Дата", ascending=False)
            st.dataframe(my_df[["Дата", "Взльот", "Посадка", "Результат", "Примітки"]], use_container_width=True)
        else: st.info("Архів порожній.")

    with tab3:
        st.header("📊 Аналітика")
        # (Ваш код аналітики)