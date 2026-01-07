import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import os
from datetime import datetime, time
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account

# --- НАЛАШТУВАННЯ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Константи
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# --- ПІДКЛЮЧЕННЯ ДО GOOGLE SERVICES ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_drive_service():
    """Створення сервісу Google Drive через Secrets"""
    info = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(info)
    scoped_credentials = credentials.with_scopes(['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=scoped_credentials)

def create_drive_folder(folder_name):
    """Створює папку на Диску та повертає її ID"""
    service = get_drive_service()
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')

def upload_files_to_drive(files, folder_id):
    """Завантажує список файлів у вказану папку"""
    service = get_drive_service()
    links = []
    for uploaded_file in files:
        file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(uploaded_file.getvalue()), 
                                  mimetype=uploaded_file.type, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        links.append(file.get('webViewLink'))
    return links

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
def load_data():
    try: return conn.read()
    except: return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Посилання на фото"])

def calculate_duration(start, end):
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

# --- СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state:
    st.session_state.temp_flights = []
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- ЛОГІКА ВХОДУ ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Дрон:", DRONES)
            if st.button("Увійти"):
                if n:
                    st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                    st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("Вхід"):
                if p == ADMIN_PASSWORD:
                    st.session_state.logged_in, st.session_state.role = True, "Admin"
                    st.rerun()

else:
    st.sidebar.title(f"👤 {st.session_state.role}")
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])

        with tab1:
            st.header("Нова зміна")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата")
                m_start = c2.time_input("З", value=time(8, 0))
                m_end = c3.time_input("До", value=time(20, 0))
                m_route = c4.text_input("Маршрут")

            st.write("---")
            with st.expander("📝 Додати новий виліт", expanded=True):
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                t_off = col1.time_input("Взльот", value=time(9, 0), step=60)
                t_land = col2.time_input("Посадка", value=time(9, 30), step=60)
                f_dur = calculate_duration(t_off, t_land)
                col3.info(f"⏳ {f_dur} хв")
                f_dist = col4.number_input("Дистанція (м)", min_value=0)
                
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"])
                f_notes = st.text_area("Коментар")
                f_files = st.file_uploader("📸 Скріншоти польоту", accept_multiple_files=True)

                if st.button("➕ Додати виліт у чергу"):
                    # Зберігаємо дані + об'єкти файлів у сесію
                    st.session_state.temp_flights.append({
                        "Дата": m_date.strftime("%d.%m.%Y"),
                        "Час завдання": f"{m_start.strftime('%H:%M')}-{m_end.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'],
                        "Дрон": st.session_state.user['drone'],
                        "Маршрут": m_route,
                        "Взльот": t_off.strftime("%H:%M"),
                        "Посадка": t_land.strftime("%H:%M"),
                        "Тривалість (хв)": f_dur,
                        "Дистанція (м)": f_dist,
                        "Результат": f_res,
                        "Примітки": f_notes,
                        "file_objs": f_files # Тимчасово тримаємо файли тут
                    })
                    st.rerun()

            if st.session_state.temp_flights:
                st.subheader("Черга на завантаження")
                tmp_df = pd.DataFrame(st.session_state.temp_flights)
                st.dataframe(tmp_df[["Взльот", "Посадка", "Тривалість (хв)", "Результат"]], use_container_width=True)
                
                if st.button("🚀 ВІДПРАВИТИ ВСЕ В БАЗУ ТА НА ДИСК"):
                    with st.spinner("Завантаження файлів на Google Drive..."):
                        # 1. Створюємо папку для всієї зміни
                        folder_name = f"{m_date.strftime('%d.%m.%Y')}_{st.session_state.user['unit']}"
                        folder_id = create_drive_folder(folder_name)
                        
                        final_rows = []
                        for flight in st.session_state.temp_flights:
                            # 2. Завантажуємо фото конкретного вильоту
                            links = []
                            if flight["file_objs"]:
                                links = upload_files_to_drive(flight["file_objs"], folder_id)
                            
                            # Формуємо фінальний рядок для Таблиці
                            row = flight.copy()
                            del row["file_objs"] # прибираємо об'єкти файлів перед записом
                            row["Посилання на фото"] = "\n".join(links) if links else "Немає"
                            final_rows.append(row)
                        
                        # 3. Запис у Таблицю
                        old_df = load_data()
                        updated_df = pd.concat([old_df, pd.DataFrame(final_rows)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=updated_df)
                        
                        st.success(f"Готово! Створено папку на Диску, фото завантажено, дані в таблиці.")
                        st.session_state.temp_flights = []
                        st.rerun()

        # Блоки Аналітики та Звітності (як у попередньому коді)
        with tab3:
            st.header("📊 Статистика")
            df = load_data()
            if not df.empty:
                u_df = df[df['Підрозділ'] == st.session_state.user['unit']]
                st.plotly_chart(px.bar(u_df, x='Дата', y='Тривалість (хв)', color='Дрон'))