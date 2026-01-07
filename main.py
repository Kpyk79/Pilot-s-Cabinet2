import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime, time, timedelta

# --- НАЛАШТУВАННЯ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Стилізація
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #e9ecef; padding: 10px; border-radius: 5px; text-align: center; border: 1px solid #ced4da; }
    </style>
    """, unsafe_allow_html=True)

UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# ПІДКЛЮЧЕННЯ
conn = st.connection("gsheets", type=GSheetsConnection)

# СЕСІЯ ДЛЯ ТИМЧАСОВОГО СПИСКУ
if 'temp_flights' not in st.session_state:
    st.session_state.temp_flights = []

# --- ФУНКЦІЯ ПІДРАХУНКУ ТРИВАЛОСТІ ---
def calculate_duration(start, end):
    # Перетворюємо час у хвилини від початку доби
    start_mins = start.hour * 60 + start.minute
    end_mins = end.hour * 60 + end.minute
    
    duration = end_mins - start_mins
    if duration < 0:  # Якщо політ перейшов через північ
        duration += 1440 # Додаємо 24 години
    return duration

# --- ВХІД ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🛡️ Система логування БпЛА")
    role = st.radio("Режим входу:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Ваш підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Дрон (основний на зміну):", DRONES)
            if st.button("Вхід"):
                if n:
                    st.session_state.logged_in, st.session_state.role, st.session_state.user_data = True, "Pilot", {"unit": u, "name": n, "drone": d}
                    st.rerun()
        else:
            p = st.text_input("Пароль адміна:", type="password")
            if st.button("Вхід як Адмін"):
                if p == ADMIN_PASSWORD:
                    st.session_state.logged_in, st.session_state.role = True, "Admin"
                    st.rerun()

else:
    st.sidebar.title("Керування")
    if st.sidebar.button("Вийти з системи"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab_add, tab_docx, tab_stats = st.tabs(["🚀 До польотів", "📜 Формування звітів", "📊 Аналітика"])

        with tab_add:
            st.header("Дані польотного завдання (Зміна)")
            
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                mission_date = c1.date_input("Дата завдання")
                mission_start = c2.time_input("Початок зміни", value=time(8, 0), step=60)
                mission_end = c3.time_input("Кінець зміни", value=time(20, 0), step=60)
                mission_route = c4.text_input("Напрямок (маршрут)", placeholder="напр. впс Кодима - межа")

            st.write("---")
            st.subheader("📝 Додати окремий виліт")
            
            with st.expander("Заповнити деталі нового вильоту", expanded=True):
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                t_takeoff = col1.time_input("Час взльоту", value=time(9, 0), step=60)
                t_landing = col2.time_input("Час посадки", value=time(9, 30), step=60)
                
                # АВТОМАТИЧНИЙ ПІДРАХУНОК
                flight_duration = calculate_duration(t_takeoff, t_landing)
                col3.markdown(f"<div class='duration-box'>⏳ Тривалість:<br><b>{flight_duration} хв</b></div>", unsafe_allow_html=True)
                
                f_dist = col4.number_input("Дистанція (м)", min_value=0, step=10)
                
                res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"])
                f_notes = st.text_area("Примітки до цього вильоту")
                f_photos = st.file_uploader("Завантажити фото/скріншоти", accept_multiple_files=True)
                
                if st.button("➕ Додати політ у список"):
                    flight_data = {
                        "Дата": str(mission_date),
                        "Час завдання": f"{mission_start.strftime('%H:%M')} - {mission_end.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user_data['unit'],
                        "Оператор": st.session_state.user_data['name'],
                        "Дрон": st.session_state.user_data['drone'],
                        "Маршрут": mission_route,
                        "Взльот": t_takeoff.strftime("%H:%M"),
                        "Посадка": t_landing.strftime("%H:%M"),
                        "Тривалість (хв)": flight_duration,
                        "Дистанція (м)": f_dist,
                        "Результат": f_res,
                        "Примітки": f_notes,
                        "Файлів": len(f_photos) if f_photos else 0
                    }
                    st.session_state.temp_flights.append(flight_data)
                    st.toast(f"Виліт додано! ({flight_duration} хв)")

            # Попередній перегляд перед відправкою
            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Польоти готові до відправки")
                preview_df = pd.DataFrame(st.session_state.temp_flights)
                st.dataframe(preview_df[["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат"]], use_container_width=True)
                
                b_clear, b_send = st.columns(2)
                if b_clear.button("🗑️ Очистити все"):
                    st.session_state.temp_flights = []
                    st.rerun()
                if b_send.button("✅ ВІДПРАВИТИ ВСІ ПОЛЬОТИ В GOOGLE SHEETS"):
                    # Логіка відправки даних
                    st.success(f"Записано {len(st.session_state.temp_flights)} польотів. Сумарний наліт: {preview_df['Тривалість (хв)'].sum()} хв.")
                    st.session_state.temp_flights = []

        # --- ТАБИ ЗВІТНІСТЬ ТА АНАЛІТИКА ---
        with tab_docx:
            st.header("Генерація офіційного звіту")
            # Логіка DOCX
            
        with tab_stats:
            st.header("Ваш наліт")
            # Графіки Plotly

    # --- ПАНЕЛЬ АДМІНА ---
    else:
        st.title("Глобальна аналітика")
        # Глобальні графіки та фільтри