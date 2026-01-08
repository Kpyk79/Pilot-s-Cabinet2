import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from docx import Document
import io
import requests
import os
from datetime import datetime, time

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v4.3", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try:
        return st.secrets["connections"]["gsheets"].get(key)
    except:
        return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. СЕРВІСИ ТЕЛЕГРАМ ---
def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return "❌ Помилка налаштувань"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': text, 'parse_mode': 'Markdown'}, timeout=30)
        return "✅ Успішно" if r.json().get("ok") else f"❌ {r.json().get('description')}"
    except: return "❌ Помилка зв'язку"

def send_telegram_photo(file_obj, caption):
    if not TG_TOKEN or not TG_CHAT_ID: return "❌ Помилка налаштувань"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        files = {'photo': (file_obj.name, file_obj.getvalue(), file_obj.type)}
        r = requests.post(url, files=files, data={'chat_id': str(TG_CHAT_ID), 'caption': caption, 'parse_mode': 'Markdown'}, timeout=60)
        return "✅ Фото надіслано" if r.json().get("ok") else f"❌ {r.json().get('description')}"
    except: return "❌ Помилка зв'язку"

# --- 4. РОБОТА З ДАНИМИ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read()
        return df.dropna(how="all")
    except:
        return pd.DataFrame(columns=["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Номер АКБ", "Цикли АКБ", "Результат", "Примітки", "Медіа (статус)"])

def generate_docx(df_filtered, template_path):
    if not os.path.exists(template_path):
        return "ERROR_FILE_MISSING"
    try:
        doc = Document(template_path)
        flights_summary = ""
        for (pilot, drone), group in df_filtered.groupby(['Оператор', 'Дрон']):
            details = ", ".join([f"{r['Взльот']}-{r['Посадка']} ({r['Дистанція (м)']}м)" for _, r in group.iterrows()])
            flights_summary += f"{pilot} — {len(group)} польотів, {drone} ({details});\n"

        replacements = {
            "{{DATE}}": str(df_filtered['Дата'].iloc[0]),
            "{{UNIT}}": str(df_filtered['Підрозділ'].iloc[0]),
            "{{FLIGHTS_LIST}}": flights_summary,
            "{{ROUTE}}": str(df_filtered['Маршрут'].iloc[0]),
            "{{RESULTS}}": f"{df_filtered['Результат'].iloc[0]}. {df_filtered['Примітки'].iloc[0]}"
        }
        for paragraph in doc.paragraphs:
            for key, value in replacements.items():
                if key in paragraph.text:
                    paragraph.text = paragraph.text.replace(key, value)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for key, value in replacements.items():
                        if key in cell.text:
                            cell.text = cell.text.replace(key, value)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except Exception: return None

def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

# --- 5. СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

# --- 6. ІНТЕРФЕЙС ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS)
            n = st.text_input("Звання та прізвище:")
            d = st.selectbox("Дрон на зміну:", DRONES)
            if st.button("Увійти") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("Вхід") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"
                st.rerun()
else:
    st.sidebar.markdown(f"**👤 {st.session_state.role}**")
    if st.sidebar.button("🧪 Тест зв'язку з TG"):
        st.sidebar.info(send_telegram_text("🔔 Тест зв'язку: ОК"))
    if st.sidebar.button("Вийти"):
        st.session_state.logged_in = False
        st.session_state.temp_flights = []
        st.rerun()

    if st.session_state.role == "Pilot":
        tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Донесення", "📊 Аналітика"])

        with tab1:
            st.header("Внесення даних зміні")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                m_date = c1.date_input("Дата завдання", datetime.now())
                m_start = c2.time_input("Зміна з", value=time(8,0), step=60)
                m_end = c3.time_input("Зміна до", value=time(20,0), step=60)
                m_route = c4.text_input("Маршрут")

            with st.expander("📝 Додати політ", expanded=True):
                col1, col2, col3, col4 = st.columns(4)
                # Використовуємо ключі для віджетів
                t_off = col1.time_input("Взльот", value=time(9,0), step=60, key="t_off")
                t_land = col2.time_input("Посадка", value=time(9,30), step=60, key="t_land")
                f_dur = calculate_duration(t_off, t_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{f_dur} хв</b></div>", unsafe_allow_html=True)
                f_dist = col4.number_input("Відстань (м)", min_value=0, step=10, key="f_dist")
                
                # Поля АКБ
                cb1, cb2 = st.columns(2)
                f_akb = cb1.text_input("Номер АКБ", placeholder="АКБ-05", key="f_akb")
                f_cyc = cb2.number_input("Кількість циклів", min_value=0, step=1, key="f_cyc")
                
                f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
                f_note = st.text_area("Примітки", key="f_note")
                
                # Завантажувач файлів зі змінним ключем для скидання
                f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")

                if st.button("➕ Додати у список"):
                    # Зберігаємо дані в список
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
                        "Номер АКБ": f_akb,
                        "Цикли АКБ": f_cyc,
                        "Результат": f_res,
                        "Примітки": f_note,
                        "files": f_imgs
                    })
                    
                    # СКИДАННЯ ПОЛІВ:
                    st.session_state.f_dist = 0
                    st.session_state.f_akb = ""
                    st.session_state.f_cyc = 0
                    st.session_state.f_note = ""
                    # Зміна ключа завантажувача для його очищення
                    st.session_state.uploader_key += 1
                    
                    st.rerun()

            if st.session_state.temp_flights:
                st.write("---")
                st.subheader("📋 Вильоти у черзі")
                raw_df = pd.DataFrame(st.session_state.temp_flights)
                cols_to_show = ["Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Номер АКБ", "Цикли АКБ"]
                existing_cols = [c for c in cols_to_show if c in raw_df.columns]
                df_view = raw_df[existing_cols]
                display_names = {"Взльот": "Зліт", "Посадка": "Посадка", "Тривалість (хв)": "Тривалість", "Дистанція (м)": "Дистанція", "Номер АКБ": "№ АКБ", "Цикли АКБ": "Цикли"}
                df_view.columns = [display_names.get(c, c) for c in df_view.columns]
                st.dataframe(df_view, use_container_width=True)
                
                if st.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                    with st.spinner("Відправка звіту..."):
                        all_fl = st.session_state.temp_flights
                        first = all_fl[0]
                        flights_txt = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв, АКБ: {f['Номер АКБ']})" for i, f in enumerate(all_fl)])
                        total_min = sum([f['Тривалість (хв)'] for f in all_fl])

                        report = (
                            f"🚁 **Донесення: {first['Підрозділ']}**\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"👤 **Пілот:** {first['Оператор']}\n"
                            f"📅 **Дата:** {first['Дата']}\n"
                            f"⏱ **Час завд.:** {first['Час завдання']}\n"
                            f"📍 **Маршрут:** {first['Маршрут']}\n"
                            f"🛡 **БпЛА:** {first['Дрон']}\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🚀 **Вильоти:**\n{flights_txt}\n"
                            f"⏱ **Загальний наліт:** {total_min} хв\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🎯 **Результат:** {first['Результат']}"
                        )

                        media_sent = False
                        final_rows = []
                        for fl in all_fl:
                            if fl['files']:
                                for img in fl['files']: send_telegram_photo(img, report)
                                media_sent = True
                            row = fl.copy(); del row['files']
                            row["Медіа (статус)"] = "З фото" if fl['files'] else "Текст"
                            final_rows.append(row)

                        if not media_sent: send_telegram_text(report)
                        
                        conn.update(worksheet="Sheet1", data=pd.concat([load_data(), pd.DataFrame(final_rows)], ignore_index=True))
                        st.success("Дані успішно відправлені!")
                        st.session_state.temp_flights = []
                        st.rerun()

        with tab2:
            st.header("📜 Донесення")
            r_date = st.date_input("Оберіть дату для звіту", datetime.now())
            df_full = load_data()
            if not df_full.empty:
                target_date = r_date.strftime("%d.%m.%Y")
                filt = df_full[(df_full['Дата'] == target_date) & (df_full['Підрозділ'] == st.session_state.user['unit'])]
                if not filt.empty:
                    st.success(f"✅ Знайдено польотів: {len(filt)}")
                    buf = generate_docx(filt, "Донесення_УПЗ.docx")
                    if buf == "ERROR_FILE_MISSING": st.error("❌ Файл шаблону не знайдено.")
                    elif buf: st.download_button("📥 Завантажити DOCX", buf, f"Report_{target_date}.docx")
                else: st.warning(f"Даних за {target_date} не знайдено.")

        with tab3:
            st.header("📊 Аналітика")
            df_full = load_data()
            if not df_full.empty:
                u_df = df_full[df_full['Підрозділ'] == st.session_state.user['unit']].copy()
                if not u_df.empty:
                    u_df['Тривалість (хв)'] = pd.to_numeric(u_df['Тривалість (хв)'], errors='coerce')
                    st.plotly_chart(px.bar(u_df, x='Дата', y='Тривалість (хв)', color='Результат'), use_container_width=True)