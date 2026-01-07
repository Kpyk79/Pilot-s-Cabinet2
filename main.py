import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime, time
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account

# --- КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Мілітарі стиль
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    </style>
    """, unsafe_allow_html=True)

# --- КОНСТАНТИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# ID ВАШОЇ ПАПКИ АРХІВУ
PARENT_FOLDER_ID = "1mqeXnoFcMpleZP-iuj5HkN_SETv3Zgzh"

# --- ПІДКЛЮЧЕННЯ GOOGLE DRIVE API ---
def get_drive_service():
    info = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(info)
    scoped_credentials = credentials.with_scopes(['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=scoped_credentials)

def upload_to_drive(files, folder_name):
    service = get_drive_service()
    
    # 1. Створення підпапки
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [PARENT_FOLDER_ID]
    }
    try:
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
    except Exception as e:
        st.error(f"Помилка створення папки: {e}")
        return []
    
    # 2. Спроба надати доступ (якщо не вийде — ідемо далі)
    try:
        public_permission = {'type': 'anyone', 'role': 'viewer'}
        service.permissions().create(fileId=folder_id, body=public_permission).execute()
    except:
        pass # Пропускаємо, якщо політика безпеки забороняє публічність
    
    links = []
    for uploaded_file in files:
        file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
        # ЗМІНА ТУТ: resumable=False робить завантаження простішим і надійнішим для фото
        media = MediaIoBaseUpload(
            io.BytesIO(uploaded_file.getvalue()), 
            mimetype=uploaded_file.type, 
            resumable=False 
        )
        try:
            file = service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            links.append(file.get('webViewLink'))
        except Exception as e:
            st.warning(f"Не вдалося завантажити файл {uploaded_file.name}: {e}")
    
    return links

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        return conn.read()
    except:
        return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Посилання на фото"])

def calculate_duration(start, end):
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def generate_docx(df_filtered, template_path):
    try:
        doc = Document(template_path)
        flights_summary = ""
        for (pilot, drone), group in df_filtered.groupby(['Оператор', 'Дрон']):
            details = " , ".join([f"{r['Взльот']}-{r['Посадка']}-{r['Дистанція (м)']}м" for _, r in group.iterrows()])
            flights_summary += f"{pilot} - {len(group)} польотів, {drone}, {details}; \n"

        replacements = {
            "{{DATE}}": str(df_filtered['Дата'].iloc[0]),
            "{{UNIT}}": str(df_filtered['Підрозділ'].iloc[0]),
            "{{FLIGHTS_LIST}}": flights_summary,
            "{{ROUTE}}": str(df_filtered['Маршрут'].iloc[0]),
            "{{RESULTS}}": f"{df_filtered['Результат'].iloc[0]}. {df_filtered['Примітки'].iloc[0]}"
        }
        for p in doc.paragraphs:
            for k, v in replacements.items():
                if k in p.text: p.text = p.text.replace(k, v)
        
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except:
        return None

# --- СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state:
    st.session_state.temp_flights = []
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- ВХІД ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Вхід як:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Прізвище:")
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
    # --- ГОЛОВНИЙ ІНТЕРФЕЙС ---
    st.sidebar.title(f"👤 {st.session_state.role}")
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])

        with tab1:
            st.header("Дані зміни")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата")
                m_start = c2.time_input("З", value=time(8,0))
                m_end = c3.time_input("До", value=time(20,0))
                m_route = c4.text_input("Маршрут")

            st.divider()
            with st.expander("📝 Додати виліт", expanded=True):
                col1, col2, col3, col4 = st.columns([1,1,1,1])
                t_off = col1.time_input("Взльот", value=time(9,0), step=60)
                t_land = col2.time_input("Посадка", value=time(9,30), step=60)
                dur = calculate_duration(t_off, t_land)
                col3.info(f"⏳ {dur} хв")
                dist = col4.number_input("Дистанція (м)", min_value=0)
                res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"])
                note = st.text_area("Примітки")
                files = st.file_uploader("📸 Скріншоти", accept_multiple_files=True)

                if st.button("➕ Додати у чергу"):
                    st.session_state.temp_flights.append({
                        "Дата": m_date.strftime("%d.%m.%Y"),
                        "Час завдання": f"{m_start.strftime('%H:%M')}-{m_end.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'],
                        "Дрон": st.session_state.user['drone'],
                        "Маршрут": m_route,
                        "Взльот": t_off.strftime("%H:%M"),
                        "Посадка": t_land.strftime("%H:%M"),
                        "Тривалість (хв)": dur,
                        "Дистанція (м)": dist,
                        "Результат": res,
                        "Примітки": note,
                        "files": files 
                    })
                    st.rerun()

            if st.session_state.temp_flights:
                st.subheader("Вильоти до відправки")
                st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Результат"]])
                
                if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ В БАЗУ ТА НА ДИСК"):
                    with st.spinner("Завантаження даних та фото..."):
                        # Назва папки для конкретного звіту
                        folder_name = f"{m_date.strftime('%d.%m.%Y')}_{st.session_state.user['unit']}"
                        
                        all_files = []
                        for f in st.session_state.temp_flights: 
                            all_files.extend(f['files'])
                        
                        drive_links = []
                        if all_files:
                            # Завантаження в підпапку архіву
                            drive_links = upload_to_drive(all_files, folder_name)
                        
                        final_rows = []
                        for f in st.session_state.temp_flights:
                            row = f.copy()
                            del row['files']
                            row["Посилання на фото"] = "\n".join(drive_links) if drive_links else "Немає"
                            final_rows.append(row)
                        
                        # Запис у Таблицю
                        old_df = load_data()
                        updated_df = pd.concat([old_df, pd.DataFrame(final_rows)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=updated_df)
                        
                        st.success("Дані та фото збережено в архів! Доступ відкрито.")
                        st.session_state.temp_flights = []
                        st.rerun()

        with tab2:
            st.header("Звітність")
            r_date = st.date_input("Оберіть дату")
            df = load_data()
            if not df.empty:
                filt = df[(df['Дата'] == r_date.strftime("%d.%m.%Y")) & (df['Підрозділ'] == st.session_state.user['unit'])]
                if not filt.empty:
                    buf = generate_docx(filt, "Донесення_УПЗ.docx")
                    if buf: 
                        st.download_button("📥 Завантажити DOCX", buf, f"Report_{r_date.strftime('%d.%m.%Y')}.docx")
                else: 
                    st.warning("Даних немає.")

        with tab3:
            st.header("📊 Статистика")
            df = load_data()
            if not df.empty:
                u_df = df[df['Підрозділ'] == st.session_state.user['unit']].copy()
                if not u_df.empty:
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'])
                    st.plotly_chart(px.bar(u_df.groupby('Дата')['Тривалість (хв)'].sum().reset_index(), x='Дата', y='Тривалість (хв)', title="Наліт (хв)"))
    
    else:
        st.title("🛰️ Адмін-панель")
        df_all = load_data()
        if not df_all.empty:
            st.dataframe(df_all, use_container_width=True)
            csv = df_all.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Експорт бази CSV", csv, "base_export.csv")