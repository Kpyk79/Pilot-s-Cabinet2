import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
from datetime import datetime, time

# --- НАЛАШТУВАННЯ СТОРІНКИ ---
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

# --- ПІДКЛЮЧЕННЯ ТА ЗАВАНТАЖЕННЯ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # Читаємо дані. Назва аркуша за замовчуванням "Sheet1"
        df = conn.read()
        df = df.dropna(how="all") # прибираємо порожні рядки
        return df
    except:
        return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Файлів"])

def calculate_duration(start, end):
    start_mins = start.hour * 60 + start.minute
    end_mins = end.hour * 60 + end.minute
    duration = end_mins - start_mins
    if duration < 0: duration += 1440
    return duration

# --- ГЕНЕРАЦІЯ ЗВІТУ DOCX ---
def generate_docx(df_filtered, template_path):
    try:
        doc = Document(template_path)
        flights_summary = ""
        for (pilot, drone), group in df_filtered.groupby(['Оператор', 'Дрон']):
            details = " , ".join([f"{r['Взльот']} - {r['Посадка']} - {r['Дистанція (м)']} м" for _, r in group.iterrows()])
            flights_summary += f"{pilot} - {len(group)} польотів, {drone}, {details}; \n"

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
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    except: return None

# --- СТАН СЕСІЇ ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.temp_flights = []

# --- ЛОГІКА ВХОДУ ---
if not st.session_state.logged_in:
    st.title("🛡️ Вхід до Кабінету Пілота")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
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
            pwd = st.text_input("Пароль:", type="password")
            if st.button("Вхід як Адмін"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.logged_in, st.session_state.role = True, "Admin"
                    st.rerun()

# --- ПІСЛЯ ВХОДУ ---
else:
    st.sidebar.title("Меню")
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab_add, tab_docx, tab_stats = st.tabs(["🚀 До польотів", "📜 Звітність", "📊 Аналітика"])

        with tab_add:
            st.header("Внесення польотних даних")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата", datetime.now())
                m_start = c2.time_input("Початок зміни", value=time(8, 0))
                m_end = c3.time_input("Кінець зміни", value=time(20, 0))
                m_route = c4.text_input("Напрямок/Маршрут")

            st.write("---")
            with st.expander("Додати окремий політ", expanded=True):
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                t_off = col1.time_input("Взльот", value=time(9, 0))
                t_land = col2.time_input("Посадка", value=time(9, 30))
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ Тривалість:<br><b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Дистанція (м)", min_value=0)
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання"])
                f_notes = st.text_area("Примітки")
                
                if st.button("➕ Додати у список"):
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
                        "Примітки": f_notes
                    }
                    st.session_state.temp_flights.append(flight)
                    st.rerun()

            if st.session_state.temp_flights:
                df_temp = pd.DataFrame(st.session_state.temp_flights)
                st.table(df_temp[["Взльот", "Посадка", "Дистанція (м)", "Результат"]])
                if st.button("✅ ВІДПРАВИТИ ВСІ ДАНІ В ТАБЛИЦЮ"):
                    # ЧИТАЄМО СТАРІ ДАНІ ТА ДОДАЄМО НОВІ
                    old_df = load_data()
                    updated_df = pd.concat([old_df, df_temp], ignore_index=True)
                    # ЗАПИС У ГУГЛ ТАБЛИЦЮ ( Worksheet має називатися Sheet1 )
                    conn.update(data=updated_df)
                    st.success("Дані збережено!")
                    st.session_state.temp_flights = []
                    st.rerun()

        with tab_docx:
            st.header("Генерація звіту")
            rep_date = st.date_input("Дата звіту", datetime.now())
            rep_str = rep_date.strftime("%d.%m.%Y")
            df_full = load_data()
            
            if not df_full.empty:
                # ВАЖЛИВО: Фільтруємо за датою ТА підрозділом пілота
                filtered = df_full[(df_full['Дата'] == rep_str) & (df_full['Підрозділ'] == st.session_state.user['unit'])]
                if not filtered.empty:
                    st.write(f"Знайдено польотів: {len(filtered)}")
                    buf = generate_docx(filtered, "Донесення_УПЗ.docx")
                    if buf:
                        st.download_button("📥 Скачати DOCX", buf, f"Report_{rep_str}.docx")
                    else: st.error("Помилка шаблону")
                else: st.warning("Немає даних на цю дату")

        with tab_stats:
            st.header("Аналітика")
            df_full = load_data()
            if not df_full.empty:
                # Фільтруємо дані підрозділу
                u_df = df_full[df_full['Підрозділ'] == st.session_state.user['unit']].copy()
                if not u_df.empty:
                    # Перетворюємо типи для графіків
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'])
                    u_df['Дистанція (м)'] = pd.to_numeric(u_df['Дистанція (м)'])
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Загальний наліт (хв)", int(u_df['Тривалість (хв)'].sum()))
                    c2.metric("Загальна дистанція (м)", int(u_df['Дистанція (м)'].sum()))
                    
                    fig = px.bar(u_df.groupby('Дата')['Тривалість (хв)'].sum().reset_index(), x='Дата', y='Тривалість (хв)', title="Наліт по днях")
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("Дані підрозділу відсутні")

    # --- ПАНЕЛЬ АДМІНА ---
    else:
        st.title("🛰️ Глобальна аналітика")
        df_all = load_data()
        if not df_all.empty:
            sel_u = st.sidebar.multiselect("Підрозділи:", UNITS, default=UNITS)
            admin_df = df_all[df_all['Підрозділ'].isin(sel_u)].copy()
            
            # Перетворення типів
            admin_df['Тривалість (хв)'] = pd.to_numeric(admin_df['Тривалість (хв)'], errors='coerce').fillna(0)
            
            k1, k2 = st.columns(2)
            k1.metric("Всього вильотів", len(admin_df))
            k2.metric("Наліт всіх підрозділів (год)", round(admin_df['Тривалість (хв)'].sum()/60, 1))
            
            st.dataframe(admin_df, use_container_width=True)