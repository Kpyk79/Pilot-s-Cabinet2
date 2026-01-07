import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import requests
from datetime import datetime, time

# --- КОНФІГУРАЦІЯ ТА СТИЛЬ ---
st.set_page_config(page_title="UAV Pilot Cabinet", layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    </style>
    """, unsafe_allow_html=True)

# Константи
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# Telegram Secrets
TG_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")

# --- СЕРВІСИ ---
def send_to_telegram(file_obj, caption):
    """Надсилає медіа в Telegram"""
    if not TG_TOKEN or not TG_CHAT_ID:
        return "❌ Помилка: Токен TG не налаштовано"
    
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        files = {'photo': file_obj.getvalue()}
        data = {'chat_id': TG_CHAT_ID, 'caption': caption}
        response = requests.post(url, files=files, data=data, timeout=15)
        if response.json().get("ok"):
            return f"✅ Фото: {file_obj.name}"
        return f"❌ Помилка TG: {response.json().get('description')}"
    except Exception as e:
        return f"❌ Помилка зв'язку: {str(e)}"

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

# --- ЛОГІКА СЕСІЇ ---
if 'temp_flights' not in st.session_state:
    st.session_state.temp_flights = []
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- ІНТЕРФЕЙС ВХОДУ ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА (TG-Sync)")
    auth_role = st.radio("Вхід:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if auth_role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("БпЛА на зміну:", DRONES)
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
    # --- ОСНОВНИЙ КАБІНЕТ ---
    st.sidebar.markdown(f"**Користувач:** {st.session_state.role}")
    if st.sidebar.button("Вихід"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Донесення", "📊 Аналітика"])

        with tab1:
            st.header("Внесення даних")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
                m_date = c1.date_input("Дата")
                m_start = c2.time_input("Початок зміни", value=time(8,0))
                m_end = c3.time_input("Кінець зміни", value=time(20,0))
                m_route = c4.text_input("Маршрут польотів")

            st.write("---")
            with st.expander("📝 Додати новий виліт", expanded=True):
                col1, col2, col3, col4 = st.columns([1,1,1,1])
                t_off = col1.time_input("Взльот", step=60)
                t_land = col2.time_input("Посадка", step=60)
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Дистанція (м)", min_value=0, step=10)
                
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"])
                f_note = st.text_area("Деталі вильоту")
                f_imgs = st.file_uploader("📸 Скріншоти (TG)", accept_multiple_files=True)

                if st.button("➕ Додати у список"):
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
                        "Примітки": f_note,
                        "files": f_imgs
                    })
                    st.toast("Виліт додано до черги!")
                    st.rerun()

            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Черга відправки")
                st.dataframe(pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Результат"]], use_container_width=True)
                
                if st.button("🚀 ВІДПРАВИТИ ВСЕ В ТАБЛИЦЮ ТА TELEGRAM"):
                    with st.spinner("Завантаження медіа та оновлення бази..."):
                        final_rows = []
                        for fl in st.session_state.temp_flights:
                            media_results = []
                            # Кожне фото — окремим повідомленням з підписом
                            for img in fl['files']:
                                caption = f"🛡️ {fl['Підрозділ']} | {fl['Оператор']}\n📅 {fl['Дата']} | ✈️ {fl['Взльот']}\n🎯 {fl['Результат']}"
                                status = send_to_telegram(img, caption)
                                media_results.append(status)
                            
                            row = fl.copy()
                            del row['files'] # видаляємо об'єкти файлів
                            row["Медіа (статус)"] = "\n".join(media_results) if media_results else "Немає"
                            final_rows.append(row)
                        
                        # Оновлення GSheets
                        old_df = load_data()
                        updated_df = pd.concat([old_df, pd.DataFrame(final_rows)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=updated_df)
                        
                        st.success(f"Готово! Польотів записано: {len(final_rows)}")
                        st.session_state.temp_flights = []
                        st.rerun()

        with tab2:
            st.header("Генерація донесення")
            # Код для DOCX залишається аналогічним
            
        with tab3:
            st.header("Ваша статистика")
            # Код для графіків Plotly