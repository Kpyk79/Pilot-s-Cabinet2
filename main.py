import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import requests
from datetime import datetime, time

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v3.2", layout="wide", page_icon="🛡️")

# Функція для отримання секретів (стабільна версія)
def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try:
        return st.secrets["connections"]["gsheets"].get(key)
    except:
        return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. СЕРВІСИ ТЕЛЕГРАМ ---
def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return "❌ Помилка: Ключі не знайдені в Secrets"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': text, 'parse_mode': 'Markdown'}, timeout=15)
        res = response.json()
        return "✅ Успішно" if res.get("ok") else f"❌ TG Error: {res.get('description')}"
    except Exception as e:
        return f"❌ Помилка зв'язку: {str(e)}"

def send_telegram_photo(file_obj, caption):
    if not TG_TOKEN or not TG_CHAT_ID:
        return "❌ Помилка: Ключі не знайдені в Secrets"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        files = {'photo': (file_obj.name, file_obj.getvalue(), file_obj.type)}
        data = {'chat_id': str(TG_CHAT_ID), 'caption': caption, 'parse_mode': 'Markdown'}
        response = requests.post(url, files=files, data=data, timeout=20)
        res = response.json()
        return "✅ Фото надіслано" if res.get("ok") else f"❌ TG Error: {res.get('description')}"
    except Exception as e:
        return f"❌ Помилка зв'язку: {str(e)}"

# --- 3. ПІДКЛЮЧЕННЯ ДО ТАБЛИЦЬ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read()
        return df.dropna(how="all")
    except:
        return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Медіа (статус)"])

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

# --- 4. СТАН СЕСІЇ ТА ВХІД ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🛡️ Вхід у систему БпЛА")
    role_choice = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role_choice == "Пілот":
            u_select = st.selectbox("Підрозділ:", UNITS)
            n_input = st.text_input("Звання та прізвище:")
            d_select = st.selectbox("Дрон на зміну:", DRONES)
            if st.button("Увійти"):
                if n_input:
                    st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u_select, "name": n_input, "drone": d_select}
                    st.rerun()
        else:
            p_input = st.text_input("Пароль:", type="password")
            if st.button("Вхід"):
                if p_input == ADMIN_PASSWORD:
                    st.session_state.logged_in, st.session_state.role = True, "Admin"
                    st.rerun()
else:
    # --- ОСНОВНИЙ ІНТЕРФЕЙС ---
    st.sidebar.markdown(f"**👤 {st.session_state.role}**")
    
    # ТЕСТОВА КНОПКА ДЛЯ ТЕЛЕГРАМ
    if st.sidebar.button("🧪 Тест зв'язку з Telegram"):
        res = send_telegram_text("🔔 Тестове повідомлення: Зв'язок встановлено!")
        st.sidebar.info(res)

    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Донесення", "📊 Аналітика"])

        with tab1:
            st.header("Внесення польотних даних")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата", datetime.now())
                m_start = c2.time_input("Початок зміни", value=time(8,0))
                m_end = c3.time_input("Кінець зміни", value=time(20,0))
                m_route = c4.text_input("Напрямок/Маршрут")

            st.write("---")
            with st.expander("📝 Додати новий виліт", expanded=True):
                col1, col2, col3, col4 = st.columns([1,1,1,1])
                t_off = col1.time_input("Взльот", value=time(9,0), step=60)
                t_land = col2.time_input("Посадка", value=time(9,30), step=60)
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Дистанція (м)", min_value=0, step=10)
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"])
                f_note = st.text_area("Примітки")
                f_imgs = st.file_uploader("📸 Скріншоти вильоту", accept_multiple_files=True)

                if st.button("➕ Додати у список"):
                    st.session_state.temp_flights.append({
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
                        "Примітки": f_note,
                        "files": f_imgs
                    })
                    st.rerun()

            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Вильоти у черзі")
                temp_df_display = pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)"]]
                temp_df_display.columns = ["Зліт", "Посадка", "Тривалість", "Дистанція"]
                st.dataframe(temp_df_display, use_container_width=True)
                
                if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                    with st.spinner("Відправка звіту..."):
                        all_fl = st.session_state.temp_flights
                        first = all_fl[0]
                        
                        # Агрегація тексту
                        flights_list = ""
                        total_min = 0
                        for i, f in enumerate(all_fl, 1):
                            flights_list += f"{i}. {f['Взльот']} - {f['Посадка']} ({f['Тривалість (хв)']} хв)\n"
                            total_min += f['Тривалість (хв)']

                        report_text = (
                            f"🚁 **Донесення: {first['Підрозділ']}**\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"👤 **Пілот:** {first['Оператор']}\n"
                            f"📅 **Дата:** {first['Дата']}\n"
                            f"⏱ **Час завд.:** {first['Час завдання']}\n"
                            f"📍 **Маршрут:** {first['Маршрут']}\n"
                            f"🛡 **БпЛА:** {first['Дрон']}\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🚀 **Вильоти:**\n{flights_list}"
                            f"⏱ **Загальний наліт:** {total_min} хв\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🎯 **Результат:** {first['Результат']}\n"
                            f"📝 **Примітки:** {first['Примітки']}"
                        )

                        media_sent = False
                        final_rows = []
                        
                        for fl in all_fl:
                            status_log = []
                            if fl['files']:
                                for img in fl['files']:
                                    res = send_telegram_photo(img, report_text)
                                    status_log.append(res)
                                media_sent = True
                            
                            row = fl.copy(); del row['files']
                            row["Медіа (статус)"] = "Надіслано з фото" if fl['files'] else "Текстовий звіт"
                            final_rows.append(row)

                        if not media_sent:
                            res = send_telegram_text(report_text)
                            st.info(f"Статус Telegram: {res}")
                        
                        # Sheets
                        old_df = load_data()
                        new_df = pd.concat([old_df, pd.DataFrame(final_rows)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=new_df)
                        
                        st.success("Дані успішно відправлені!")
                        st.session_state.temp_flights = []
                        st.rerun()

        with tab2:
            st.header("Генерація донесення")
            r_date = st.date_input("Оберіть дату")
            df_full = load_data()
            if not df_full.empty:
                filt = df_full[(df_full['Дата'] == r_date.strftime("%d.%m.%Y")) & (df_full['Підрозділ'] == st.session_state.user['unit'])]
                if not filt.empty:
                    buf = generate_docx(filt, "Донесення_УПЗ.docx")
                    if buf: st.download_button("📥 DOCX", buf, f"Report_{r_date}.docx")
                else: st.warning("Немає записів.")

        with tab3:
            st.header("📊 Аналітика")
            df_full = load_data()
            if not df_full.empty:
                u_df = df_full[df_full['Підрозділ'] == st.session_state.user['unit']].copy()
                if not u_df.empty:
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'], errors='coerce')
                    st.plotly_chart(px.bar(u_df, x='Дата', y='Тривалість (хв)', color='Результат'), use_container_width=True)