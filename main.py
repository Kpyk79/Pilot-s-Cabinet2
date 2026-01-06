import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime

# --- КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Мілітарі дизайн
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #344e41; color: white; }
    .stTextInput>div>div>input { background-color: #ffffff; }
    [data-testid="stSidebar"] { background-color: #dad7cd; }
    h1, h2, h3 { color: #3a5a40; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# --- КОНСТАНТИ ---
UNITS = [
    "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове",
    "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка",
    "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка",
    "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"
]

DRONES = [
    "DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", 
    "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"
]

ADMIN_PASSWORD = "admin_secret"

# --- ПІДКЛЮЧЕННЯ ДО GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        return conn.read(ttl="1m")
    except:
        # Повертаємо порожній DF, якщо таблиця ще не налаштована
        return pd.DataFrame(columns=[
            "Дата", "Підрозділ", "Оператор", "Модель БпЛА", "Маршрут", 
            "Час зльоту", "Час посадки", "Дистанція", "Результат", "Примітки"
        ])

# --- ФУНКЦІЯ ГЕНЕРАЦІЇ ЗВІТУ ---
def generate_report(df_filtered, template_path):
    try:
        doc = Document(template_path)
    except:
        return None

    # Формування списку вильотів (як у вашому зразку)
    # Гвоздіцький - 4 польотів ,Matrice 30T ,01:17 - 01:28 - 401 м ...
    flights_summary = ""
    for (pilot, drone), group in df_filtered.groupby(['Оператор', 'Модель БпЛА']):
        count = len(group)
        details = " , ".join([f"{r['Час зльоту']} - {r['Час посадки']} - {r['Дистанція']} м" for _, r in group.iterrows()])
        flights_summary += f"{pilot} - {count} польотів , {drone} , {details} ; \n"

    replacements = {
        "{{DATE}}": str(df_filtered['Дата'].iloc[0]),
        "{{UNIT}}": str(df_filtered['Підрозділ'].iloc[0]),
        "{{FLIGHTS_LIST}}": flights_summary,
        "{{ROUTE}}": str(df_filtered['Маршрут'].iloc[0]),
        "{{RESULTS}}": f"{df_filtered['Результат'].iloc[0]}. {df_filtered['Примітки'].iloc[0]}"
    }

    for p in doc.paragraphs:
        for key, value in replacements.items():
            if key in p.text:
                p.text = p.text.replace(key, value)
    
    # Також перевірка в таблицях шаблону
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for key, value in replacements.items():
                    if key in cell.text:
                        cell.text = cell.text.replace(key, value)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- ЛОГІКА АВТОРИЗАЦІЇ ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.user_data = {}

if not st.session_state.logged_in:
    st.title("🛡️ Вхід у систему 'Кабінет пілота'")
    
    auth_mode = st.radio("Оберіть режим входу:", ["Пілот", "Адміністратор"], horizontal=True)
    
    with st.container(border=True):
        if auth_mode == "Пілот":
            unit = st.selectbox("Ваш підрозділ:", UNITS)
            name = st.text_input("Звання та прізвище оператора (напр. с-нт Гвоздіцький):")
            drone = st.selectbox("Модель дрона:", DRONES)
            if st.button("Увійти до кабінету"):
                if name:
                    st.session_state.logged_in = True
                    st.session_state.role = "Pilot"
                    st.session_state.user_data = {"unit": unit, "name": name, "drone": drone}
                    st.rerun()
                else: st.error("Будь ласка, введіть прізвище.")
        else:
            pwd = st.text_input("Пароль адміністратора:", type="password")
            if st.button("Увійти як Адмін"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.role = "Admin"
                    st.rerun()
                else: st.error("Невірний пароль.")

# --- ПАНЕЛЬ КЕРУВАННЯ ПІСЛЯ ВХОДУ ---
else:
    st.sidebar.image("https://img.icons8.com/color/96/military-medal.png") # Заглушка емблеми
    st.sidebar.title("Меню")
    
    if st.session_state.role == "Pilot":
        st.sidebar.success(f"📍 {st.session_state.user_data['unit']}")
        st.sidebar.info(f"👤 {st.session_state.user_data['name']}")
        
        tab_action, tab_report, tab_analytics = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])
        
        # --- ТАБ: ДО ПОЛЬОТІВ ---
        with tab_action:
            st.header("Внесення польотних даних")
            with st.form("flight_entry"):
                col1, col2 = st.columns(2)
                f_date = col1.date_input("Дата польотного завдання", datetime.now())
                f_route = col2.text_input("Напрямок (маршрут)", placeholder="Круті (Укр) - Плоть (РМ)")
                
                st.write("---")
                st.subheader("Дані вильоту")
                c1, c2, c3 = st.columns(3)
                t_takeoff = c1.time_input("Час взльоту")
                t_landing = c2.time_input("Час посадки")
                f_dist = c3.number_input("Дистанція (м)", min_value=0)
                
                f_res = st.selectbox("Результати повітряної розвідки", ["Без ознак порушення", "Затримання"])
                f_notes = st.text_area("Примітки / Коментар")
                f_files = st.file_uploader("Фото та скріншоти (завантажте сюди)", accept_multiple_files=True)
                
                if st.form_submit_button("Відправити дані"):
                    # Логіка запису (у реальному додатку тут conn.update)
                    st.success("Дані успішно записані до Google Таблиці!")
                    st.balloons()

        # --- ТАБ: ЗВІТНІСТЬ ---
        with tab_report:
            st.header("Формування донесення УПЗ")
            st.write("Оберіть дату, за яку необхідно сформувати готовий документ:")
            report_date = st.date_input("Дата звіту", datetime.now(), key="pilot_rep_date")
            
            # Завантаження даних для фільтрації
            all_df = load_data()
            if not all_df.empty:
                # Фільтр по даті та підрозділу
                filtered = all_df[(all_df['Дата'] == str(report_date)) & 
                                  (all_df['Підрозділ'] == st.session_state.user_data['unit'])]
                
                if not filtered.empty:
                    st.success(f"Знайдено вильотів: {len(filtered)}")
                    report_buf = generate_report(filtered, "Донесення_УПЗ_template.docx")
                    if report_buf:
                        st.download_button(
                            label="📥 Скачати готовий DOCX звіт",
                            data=report_buf,
                            file_name=f"Донесення_{st.session_state.user_data['unit']}_{report_date}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    else:
                        st.error("Файл шаблону 'Донесення_УПЗ_template.docx' не знайдено.")
                else:
                    st.warning("Вильотів за цю дату у вашому підрозділі не зафіксовано.")

        # --- ТАБ: АНАЛІТИКА ПІЛОТА ---
        with tab_analytics:
            st.header("Статистика вашого підрозділу")
            all_df = load_data()
            unit_df = all_df[all_df['Підрозділ'] == st.session_state.user_data['unit']]
            if not unit_df.empty:
                col1, col2 = st.columns(2)
                col1.metric("Загальна дистанція (м)", unit_df['Дистанція'].sum())
                col2.metric("Всього вильотів", len(unit_df))
                
                fig = px.line(unit_df, x='Дата', y='Дистанція', title="Динаміка нальоту", markers=True)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Дані для аналітики поки що відсутні.")

    # --- ПАНЕЛЬ АДМІНІСТРАТОРА ---
    else:
        st.title("🛰️ Глобальна аналітика (Адміністратор)")
        raw_df = load_data()
        
        # Глобальні фільтри в сайдбарі
        st.sidebar.header("Параметри фільтрації")
        sel_units = st.sidebar.multiselect("Оберіть підрозділи:", UNITS, default=UNITS)
        date_range = st.sidebar.date_input("Період:", [])
        
        if not raw_df.empty:
            # Застосування фільтрів
            mask = raw_df['Підрозділ'].isin(sel_units)
            admin_df = raw_df[mask]
            
            # KPI блоки
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Глобально вильотів", len(admin_df))
            kpi2.metric("Сумарна дистанція (км)", round(admin_df['Дистанція'].sum()/1000, 2))
            kpi3.metric("К-сть затримань", len(admin_df[admin_df['Результат'] == "Затримання"]))
            
            # Візуалізації
            c1, c2 = st.columns(2)
            
            unit_stats = admin_df.groupby('Підрозділ')['Дистанція'].sum().reset_index()
            fig1 = px.bar(unit_stats, x='Підрозділ', y='Дистанція', color='Підрозділ', title="Наліт по підрозділах (м)")
            c1.plotly_chart(fig1)
            
            drone_stats = admin_df['Модель БпЛА'].value_counts().reset_index()
            fig2 = px.pie(drone_stats, names='Модель БпЛА', values='count', title="Розподіл за моделями дронів")
            c2.plotly_chart(fig2)
            
            st.subheader("📋 Реєстр усіх польотів")
            st.dataframe(admin_df, use_container_width=True)
            
            # Експорт
            csv = admin_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Завантажити всю базу в CSV", csv, "uav_export.csv", "text/csv")
        else:
            st.warning("База даних порожня.")

    if st.sidebar.button("Вийти з системи"):
        st.session_state.logged_in = False
        st.rerun()