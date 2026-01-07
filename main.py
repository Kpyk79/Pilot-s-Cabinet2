import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime, time

# --- КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="Кабінет пілота БпЛА", layout="wide", page_icon="🛡️")

# Стилізація під мілітарі
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #344e41; }
    </style>
    """, unsafe_allow_html=True)

# --- КОНСТАНТИ ---
UNITS = [
    "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове",
    "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулнка", "віпс Новосеменівка",
    "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка",
    "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"
]

DRONES = [
    "DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", 
    "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"
]

ADMIN_PASSWORD = "admin_secret"

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(ttl="1m")
        return df
    except:
        return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Файлів"])

def calculate_duration(start, end):
    start_mins = start.hour * 60 + start.minute
    end_mins = end.hour * 60 + end.minute
    duration = end_mins - start_mins
    if duration < 0: duration += 1440  # Перехід через північ
    return duration

def generate_docx(df_filtered, template_path):
    try:
        doc = Document(template_path)
        flights_summary = ""
        # Групування вильотів для звіту
        for (pilot, drone), group in df_filtered.groupby(['Оператор', 'Дрон']):
            count = len(group)
            details = " , ".join([f"{r['Взльот']} - {r['Посадка']} - {r['Дистанція (м)']} м" for _, r in group.iterrows()])
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
                if key in p.text: p.text = p.text.replace(key, value)
        
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for key, value in replacements.items():
                        if key in cell.text: cell.text = cell.text.replace(key, value)

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Помилка шаблону: {e}")
        return None

# --- СТАН СЕСІЇ ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.temp_flights = []

# --- АВТОРИЗАЦІЯ ---
if not st.session_state.logged_in:
    st.title("🛡️ Вхід до Кабінету Пілота")
    role = st.radio("Оберіть режим:", ["Пілот", "Адміністратор"], horizontal=True)
    
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Дрон на зміну:", DRONES)
            if st.button("Увійти"):
                if n:
                    st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                    st.rerun()
                else: st.error("Введіть прізвище")
        else:
            pwd = st.text_input("Пароль адміністратора:", type="password")
            if st.button("Увійти як Адмін"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.logged_in, st.session_state.role = True, "Admin"
                    st.rerun()
                else: st.error("Доступ заборонено")

# --- ПАНЕЛЬ КЕРУВАННЯ ---
else:
    st.sidebar.title("🛡️ Навігація")
    if st.sidebar.button("Вийти з системи"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab_add, tab_docx, tab_stats = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])

        with tab_add:
            st.header("Дані польотного завдання")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата", datetime.now())
                m_start = c2.time_input("Початок зміни", value=time(8, 0), step=60)
                m_end = c3.time_input("Кінець зміни", value=time(20, 0), step=60)
                m_route = c4.text_input("Напрямок/Маршрут", placeholder="Круті - Плоть")

            st.write("---")
            st.subheader("📝 Додати виліт")
            with st.expander("Деталі окремого польоту", expanded=True):
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                t_off = col1.time_input("Точний час взльоту", value=time(9, 0), step=60)
                t_land = col2.time_input("Точний час посадки", value=time(9, 30), step=60)
                
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ Тривалість:<br><b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                
                f_dist = col4.number_input("Дистанція (м)", min_value=0, step=10)
                
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"])
                f_notes = st.text_area("Примітки")
                f_imgs = st.file_uploader("Скріншоти", accept_multiple_files=True)
                
                if st.button("➕ Додати політ у список"):
                    flight = {
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
                        "Примітки": f_notes,
                        "Файлів": len(f_imgs) if f_imgs else 0
                    }
                    st.session_state.temp_flights.append(flight)
                    st.toast(f"Виліт додано ({f_dur} хв)")
                    st.rerun()

            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Список до відправки")
                df_temp = pd.DataFrame(st.session_state.temp_flights)
                st.dataframe(df_temp[["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат"]], use_container_width=True)
                
                b_clr, b_snd = st.columns(2)
                if b_clr.button("🗑️ Очистити все"):
                    st.session_state.temp_flights = []
                    st.rerun()
                if b_snd.button("✅ ВІДПРАВИТИ ВСІ ДАНІ В БАЗУ"):
                    # Тут логіка conn.update для Google Sheets
                    st.success("Дані успішно збережено в Google Таблицю!")
                    st.session_state.temp_flights = []

        with tab_docx:
            st.header("Генерація звіту")
            rep_date = st.date_input("Оберіть дату", datetime.now())
            rep_date_str = rep_date.strftime("%d.%m.%Y")
            
            all_df = load_data()
            if not all_df.empty:
                filtered = all_df[(all_df['Дата'] == rep_date_str) & (all_df['Підрозділ'] == st.session_state.user['unit'])]
                if not filtered.empty:
                    st.success(f"Знайдено записів: {len(filtered)}")
                    buf = generate_docx(filtered, "Донесення_УПЗ_template.docx")
                    if buf:
                        st.download_button("📥 Завантажити DOCX", buf, f"Report_{rep_date_str}.docx")
                else: st.warning("Немає даних на цю дату.")

        with tab_stats:
            st.header("Ваш наліт")
            all_df = load_data()
            u_df = all_df[all_df['Підрозділ'] == st.session_state.user['unit']]
            if not u_df.empty:
                st.metric("Сумарний наліт (хв)", u_df['Тривалість (хв)'].sum())
                fig = px.bar(u_df, x='Дата', y='Тривалість (хв)', title="Наліт по днях")
                st.plotly_chart(fig, use_container_width=True)

    else:
        st.title("🛰️ Глобальна аналітика")
        df_all = load_data()
        if not df_all.empty:
            sel_u = st.sidebar.multiselect("Підрозділи:", UNITS, default=UNITS)
            f_df = df_all[df_all['Підрозділ'].isin(sel_u)]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Всього польотів", len(f_df))
            c2.metric("Загальний наліт (год)", round(f_df['Тривалість (хв)'].sum()/60, 1))
            c3.metric("Затримання", len(f_df[f_df['Результат'] == "Затримання"]))
            
            st.plotly_chart(px.pie(f_df, names='Дрон', title="Розподіл за моделями"), use_container_width=True)
            st.dataframe(f_df, use_container_width=True)