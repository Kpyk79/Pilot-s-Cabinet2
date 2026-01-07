import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime

# --- КОНФІГУРАЦІЯ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Мілітарі стиль
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #344e41; color: white; height: 3em; }
    .flight-card { border: 1px solid #e6e9ef; padding: 15px; border-radius: 10px; background: white; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# ПІДКЛЮЧЕННЯ
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl="1m")

# СЕСІЯ ДЛЯ ПЕРЕЛІКУ ПОЛЬОТІВ
if 'temp_flights' not in st.session_state:
    st.session_state.temp_flights = []

# --- ЛОГІКА ВХОДУ ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    auth_mode = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if auth_mode == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Модель дрона:", DRONES)
            if st.button("Увійти"):
                if n:
                    st.session_state.logged_in, st.session_state.role, st.session_state.user_data = True, "Pilot", {"unit": u, "name": n, "drone": d}
                    st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("Увійти"):
                if p == ADMIN_PASSWORD:
                    st.session_state.logged_in, st.session_state.role = True, "Admin"
                    st.rerun()

else:
    # --- САЙДБАР ---
    st.sidebar.title("Навігація")
    if st.sidebar.button("Вийти з системи"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab_fly, tab_rep, tab_stat = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])

        # --- ВКЛАДКА: ДО ПОЛЬОТІВ ---
        with tab_fly:
            st.header("Внесення даних зміни")
            
            # 1. Загальні дані зміни
            with st.container(border=True):
                c1, c2, c3 = st.columns(3)
                f_date = c1.date_input("Дата завдання")
                f_task_time = c2.text_input("Час польотного завдання (напр. 08:00-20:00)")
                f_route = c3.text_input("Напрямок (маршрут)")

            st.write("---")

            # 2. Форма додавання окремих польотів
            st.subheader("Додати політ у список")
            with st.expander("Заповнити дані вильоту", expanded=True):
                col1, col2, col3 = st.columns(3)
                t_start = col1.time_input("Час взльоту")
                t_end = col2.time_input("Час посадки")
                dist = col3.number_input("Дистанція (м)", min_value=0)
                
                res = st.selectbox("Результат розвідки", ["Без ознак порушення", "Затримання"])
                notes = st.text_input("Коментар / Примітки")
                
                # Поле для фото
                uploaded_files = st.file_uploader("Додати скріншоти та фото", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
                
                if st.button("➕ Додати цей політ у список"):
                    # Зберігаємо дані (назви файлів для логу)
                    file_names = [f.name for f in uploaded_files] if uploaded_files else []
                    
                    flight_entry = {
                        "Дата": str(f_date),
                        "Час завдання": f_task_time,
                        "Підрозділ": st.session_state.user_data['unit'],
                        "Оператор": st.session_state.user_data['name'],
                        "Модель БпЛА": st.session_state.user_data['drone'],
                        "Маршрут": f_route,
                        "Час зльоту": t_start.strftime("%H:%M"),
                        "Час посадки": t_end.strftime("%H:%M"),
                        "Дистанція": dist,
                        "Результат": res,
                        "Примітки": notes,
                        "Фото": ", ".join(file_names) if file_names else "Немає"
                    }
                    st.session_state.temp_flights.append(flight_entry)
                    st.toast("Політ додано!")

            # 3. Список доданих польотів
            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("Польоти готові до відправки:")
                temp_df = pd.DataFrame(st.session_state.temp_flights)
                st.dataframe(temp_df[["Час зльоту", "Час посадки", "Дистанція", "Результат", "Фото"]], use_container_width=True)
                
                b1, b2 = st.columns(2)
                if b1.button("🗑️ Очистити весь список"):
                    st.session_state.temp_flights = []
                    st.rerun()
                
                if b2.button("✅ ВІДПРАВИТИ ВСІ ДАНІ В ТАБЛИЦЮ"):
                    # Логіка відправки (conn.update)
                    st.success(f"Дані про {len(st.session_state.temp_flights)} польотів успішно збережені!")
                    st.session_state.temp_flights = [] # Очищення після успіху

        # --- ВКЛАДКИ ЗВІТНІСТЬ ТА АНАЛІТИКА (аналогічно попередньому коду) ---
        with tab_rep:
            st.header("Формування звіту")
            st.write("Виберіть дату для генерації документа.")
            # Тут код для generate_report

        with tab_stat:
            st.header("Статистика підрозділу")
            # Тут графіки Plotly

    # --- ПАНЕЛЬ АДМІНІСТРАТОРА ---
    else:
        st.title("Глобальна аналітика")
        # Тут код для адміністратора (фільтри, графіки, перегляд всієї бази)