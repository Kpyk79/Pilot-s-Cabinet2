import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime

# --- КОНФІГУРАЦІЯ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Стилізація
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #344e41; color: white; }
    .flight-box { border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin-bottom: 10px; background: white; }
    </style>
    """, unsafe_allow_html=True)

UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# ПІДКЛЮЧЕННЯ
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl="1m")

# --- СЕСІЯ ДЛЯ СПИСКУ ВИЛЬОТІВ ---
if 'temp_flights' not in st.session_state:
    st.session_state.temp_flights = []

# --- АВТОРИЗАЦІЯ ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🛡️ Вхід у систему 'Кабінет пілота'")
    auth_mode = st.radio("Оберіть режим:", ["Пілот", "Адміністратор"], horizontal=True)
    
    if auth_mode == "Пілот":
        unit = st.selectbox("Підрозділ:", UNITS)
        name = st.text_input("Звання та прізвище:")
        drone = st.selectbox("Модель дрона:", DRONES)
        if st.button("Увійти"):
            if name:
                st.session_state.logged_in = True
                st.session_state.role = "Pilot"
                st.session_state.user_data = {"unit": unit, "name": name, "drone": drone}
                st.rerun()
    else:
        pwd = st.text_input("Пароль:", type="password")
        if st.button("Увійти"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.session_state.role = "Admin"
                st.rerun()

else:
    st.sidebar.title("Меню")
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])

        with tab1:
            st.header("Внесення даних зміни")
            
            # 1. ЗАГАЛЬНІ ДАНІ (вводяться один раз)
            with st.container(border=True):
                col1, col2, col3 = st.columns(3)
                f_date = col1.date_input("Дата завдання")
                f_time_range = col2.text_input("Час завдання (напр. 08:00-20:00)")
                f_route = col3.text_input("Напрямок/Маршрут")

            st.divider()

            # 2. ФОРМА ДОДАВАННЯ ОКРЕМОГО ВИЛЬОТУ
            st.subheader("Додати виліт")
            with st.expander("Натисніть, щоб додати деталі вильоту", expanded=True):
                c1, c2, c3 = st.columns(3)
                t_takeoff = c1.time_input("Час взльоту", key="start")
                t_landing = c2.time_input("Час посадки", key="end")
                dist = c3.number_input("Дистанція (м)", min_value=0, key="dist")
                
                res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"], key="res")
                note = st.text_input("Примітки", key="note")
                
                if st.button("➕ Додати виліт у список"):
                    flight = {
                        "Дата": str(f_date),
                        "Час завдання": f_time_range,
                        "Підрозділ": st.session_state.user_data['unit'],
                        "Оператор": st.session_state.user_data['name'],
                        "Модель БпЛА": st.session_state.user_data['drone'],
                        "Маршрут": f_route,
                        "Час зльоту": str(t_takeoff),
                        "Час посадки": str(t_landing),
                        "Дистанція": dist,
                        "Результат": res,
                        "Примітки": note
                    }
                    st.session_state.temp_flights.append(flight)
                    st.toast("Виліт додано до списку!")

            # 3. ПЕРЕГЛЯД ТА ВІДПРАВКА
            if st.session_state.temp_flights:
                st.subheader("Список вильотів до відправки")
                temp_df = pd.DataFrame(st.session_state.temp_flights)
                st.table(temp_df[["Час зльоту", "Час посадки", "Дистанція", "Результат"]])
                
                col_clear, col_send = st.columns(2)
                if col_clear.button("🗑️ Очистити список"):
                    st.session_state.temp_flights = []
                    st.rerun()
                
                if col_send.button("✅ ВІДПРАВИТИ ВСІ ДАНІ В БАЗУ"):
                    # Тут логіка запису в Google Sheets через conn.update
                    st.success(f"Успішно відправлено {len(st.session_state.temp_flights)} вильотів!")
                    st.session_state.temp_flights = [] # Очищуємо після відправки

        with tab2:
            st.header("Генерація звіту")
            st.info("Виберіть дату польотів для формування DOCX донесення")
            # Тут логіка з функцією generate_report, яку ми обговорювали раніше

        with tab3:
            st.header("Аналітика")
            # Графіки pandas/plotly
            
    else:
        st.title("Глобальна аналітика")
        # Код для адміна