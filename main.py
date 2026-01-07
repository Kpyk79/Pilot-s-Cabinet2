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

# Стилізація
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    </style>
    """, unsafe_allow_html=True)

# --- КОНСТАНТИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"
PARENT_FOLDER_ID = "1mqeXnoFcMpleZP-iuj5HkN_SETv3Zgzh"

# --- ПІДКЛЮЧЕННЯ GOOGLE SERVICES ---
def get_drive_service():
    info = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(info)
    scoped_credentials = credentials.with_scopes(['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=scoped_credentials)

def upload_to_drive(files, folder_name):
    service = get_drive_service()
    
    # 1. Створення підпапки в архіві
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [PARENT_FOLDER_ID]
    }
    try:
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
    except Exception as e:
        st.error(f"❌ Помилка доступу до Диску: {e}")
        return []

    # 2. Спроба відкрити доступ "всім з посиланням"
    try:
        public_permission = {'type': 'anyone', 'role': 'viewer'}
        service.permissions().create(fileId=folder_id, body=public_permission).execute()
    except:
        pass # Якщо політика організації забороняє публічність

    links = []
    # 3. Завантаження файлів (resumable=False для стабільності)
    for uploaded_file in files:
        try:
            file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
            media = MediaIoBaseUpload(io.BytesIO(uploaded_file.getvalue()), 
                                      mimetype=uploaded_file.type, resumable=False)
            file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            links.append(file.get('webViewLink'))
        except Exception as e:
            st.warning(f"⚠️ Не вдалося завантажити {uploaded_file.name}: {e}")
    
    return links

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read()
        return df.dropna(how="all")
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
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

# --- СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- ІНТЕРФЕЙС ВХОДУ ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Вхід як:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Дрон на зміну:", DRONES)
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
            st.header("Внесення польотних даних")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата завдання")
                m_start = c2.time_input("Початок зміни", value=time(8,0), step=60)
                m_end = c3.time_input("Кінець зміни", value=time(20,0), step=60)
                m_route = c4.text_input("Напрямок/Маршрут", placeholder="Круті - Плоть")

            st.write("---")
            with st.expander("📝 Деталі нового вильоту", expanded=True):
                col1, col2, col3, col4 = st.columns([1,1,1,1])
                t_off = col1.time_input("Взльот", value=time(9,0), step=60)
                t_land = col2.time_input("Посадка", value=time(9,30), step=60)
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ Тривалість:<br><b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Дистанція (м)", min_value=0, step=10)
                
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"])
                f_notes = st.text_area("Примітки")
                f_files = st.file_uploader("📸 Скріншоти", accept_multiple_files=True)

                if st.button("➕ Додати у список на відправку"):
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
                        "file_objs": f_files
                    })
                    st.rerun()

            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Вильоти у черзі:")
                df_temp = pd.DataFrame(st.session_state.temp_flights)
                st.dataframe(df_temp[["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)"]], use_container_width=True)
                
                if st.button("✅ ВІДПРАВИТИ ВСІ ДАНІ ТА ФОТО"):
                    with st.spinner("Зберігаємо на Диск та в Таблицю..."):
                        folder_name = f"{m_date.strftime('%d.%m.%Y')}_{st.session_state.user['unit']}"
                        
                        all_media = []
                        for fl in st.session_state.temp_flights: all_media.extend(fl['file_objs'])
                        
                        drive_links = upload_to_drive(all_media, folder_name) if all_media else []
                        
                        final_data = []
                        for fl in st.session_state.temp_flights:
                            row = fl.copy(); del row['file_objs']
                            row["Посилання на фото"] = "\n".join(drive_links) if drive_links else "Немає"
                            final_data.append(row)
                        
                        old_df = load_data()
                        updated_df = pd.concat([old_df, pd.DataFrame(final_data)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=updated_df)
                        
                        st.success("Успіх! Дані збережено, фото в архіві.")
                        st.session_state.temp_flights = []
                        st.rerun()

        with tab2:
            st.header("📜 Генерація донесення")
            rep_date = st.date_input("Дата звіту", datetime.now())
            df_all = load_data()
            if not df_all.empty:
                filt = df_all[(df_all['Дата'] == rep_date.strftime("%d.%m.%Y")) & (df_all['Підрозділ'] == st.session_state.user['unit'])]
                if not filt.empty:
                    st.success(f"Знайдено польотів: {len(filt)}")
                    buf = generate_docx(filt, "Донесення_УПЗ.docx")
                    if buf: st.download_button("📥 Завантажити DOCX", buf, f"Report_{rep_date.strftime('%d.%m.%Y')}.docx")
                else: st.warning("Даних на цю дату немає.")

        with tab3:
            st.header("📊 Аналітика підрозділу")
            df_stat = load_data()
            if not df_stat.empty:
                u_df = df_stat[df_stat['Підрозділ'] == st.session_state.user['unit']].copy()
                if not u_df.empty:
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'], errors='coerce')
                    st.plotly_chart(px.bar(u_df, x='Дата', y='Тривалість (хв)', color='Дрон', title="Наліт за період"))
                else: st.info("Ваших даних ще немає.")

    else:
        st.title("🛰️ Адміністратор: Загальна база")
        df_admin = load_data()
        if not df_admin.empty:
            st.dataframe(df_admin, use_container_width=True)
            csv = df_admin.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Завантажити всю базу (CSV)", csv, "uav_full_base.csv")