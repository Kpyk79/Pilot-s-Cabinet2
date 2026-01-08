import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from docx import Document
import io
import requests
import os
from datetime import datetime, time

# --- 1. КОНФІГУРАЦІЯ ТА СЕКРЕТИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v4.9", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = st.secrets.get(key)
    if val: return val
    try: return st.secrets["connections"]["gsheets"].get(key)
    except: return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# --- 2. КОНСТАНТИ ---
UNITS = ["впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", "віпс Гандрабури", "віпс Новосеменівка", "впс Великокомарівка", "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", "віпс Гребеники", "впс Степанівка", "віпс Кучурган", "віпс Лиманське", "віпс Лучинське", "УПЗ"]
DRONES = ["DJI Mavic 3 Pro", "DJI Mavic 3E", "DJI Mavic 3T", "DJI Matrice 30T", "DJI Matrice 300", "Autel Evo Max 4T", "Skydio X2D", "Puma LE"]
ADMIN_PASSWORD = "admin_secret"

# --- 3. ДОПОМІЖНІ ФУНКЦІЇ ---
def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def add_flight_callback():
    dur = calculate_duration(st.session_state.t_off, st.session_state.t_land)
    st.session_state.temp_flights.append({
        "Дата": st.session_state.m_date_val.strftime("%d.%m.%Y"),
        "Час завдання": f"{st.session_state.m_start_val.strftime('%H:%M')} - {st.session_state.m_end_val.strftime('%H:%M')}",
        "Підрозділ": st.session_state.user['unit'],
        "Оператор": st.session_state.user['name'],
        "Дрон": st.session_state.user['drone'],
        "Маршрут": st.session_state.m_route_val,
        "Взльот": st.session_state.t_off.strftime("%H:%M"),
        "Посадка": st.session_state.t_land.strftime("%H:%M"),
        "Тривалість (хв)": dur,
        "Дистанція (м)": st.session_state.f_dist,
        "Номер АКБ": st.session_state.f_akb,
        "Цикли АКБ": st.session_state.f_cyc,
        "Результат": st.session_state.f_res,
        "Примітки": st.session_state.f_note,
        "files": st.session_state[f"uploader_{st.session_state.uploader_key}"]
    })
    st.session_state.f_dist = 0; st.session_state.f_akb = ""; st.session_state.f_cyc = 0; st.session_state.f_note = ""
    st.session_state.uploader_key += 1

# --- 4. РОБОТА З ТАБЛИЦЯМИ ТА ТЕЛЕГРАМ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try: return conn.read(worksheet=ws).dropna(how="all")
    except: return pd.DataFrame()

def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, data={'chat_id': str(TG_CHAT_ID), 'text': text, 'parse_mode': 'Markdown'}, timeout=20)

def send_telegram_photo(file_obj, caption):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {'photo': (file_obj.name, file_obj.getvalue(), file_obj.type)}
    requests.post(url, files=files, data={'chat_id': str(TG_CHAT_ID), 'caption': caption, 'parse_mode': 'Markdown'}, timeout=60)

def generate_docx(df_filtered, template_path="Донесення_УПЗ.docx"):
    if not os.path.exists(template_path): return "ERROR_MISSING"
    try:
        doc = Document(template_path)
        flights_summary = ""
        for i, r in df_filtered.iterrows():
            flights_summary += f"{r['Взльот']}-{r['Посадка']} ({r['Дрон']}, АКБ: {r['Номер АКБ']}); "
        
        replacements = {
            "{{DATE}}": str(df_filtered['Дата'].iloc[0]),
            "{{UNIT}}": str(df_filtered['Підрозділ'].iloc[0]),
            "{{PILOT}}": str(df_filtered['Оператор'].iloc[0]),
            "{{FLIGHTS}}": flights_summary,
            "{{ROUTE}}": str(df_filtered['Маршрут'].iloc[0]),
            "{{RESULTS}}": str(df_filtered['Результат'].iloc[0])
        }
        for p in doc.paragraphs:
            for k, v in replacements.items():
                if k in p.text: p.text = p.text.replace(k, v)
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

# --- 5. СТАН СЕСІЇ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

st.markdown("<style>.stButton>button { width: 100%; border-radius: 8px; background-color: #2b4231; color: white; height: 3.5em; font-weight: bold; } .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #2b4231; font-size: 1.2em; }</style>", unsafe_allow_html=True)

# --- 6. ЛОГІКА ІНТЕРФЕЙСУ ---
if not st.session_state.logged_in:
    st.title("🛡️ Кабінет пілота БпЛА")
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            u = st.selectbox("Підрозділ:", UNITS); n = st.text_input("Звання та прізвище:"); d = st.selectbox("Дрон:", DRONES)
            if st.button("Увійти") and n:
                st.session_state.logged_in, st.session_state.role, st.session_state.user = True, "Pilot", {"unit": u, "name": n, "drone": d}
                df_d = load_data("Drafts")
                if not df_d.empty: st.session_state.temp_flights.extend(df_d[df_d['Оператор'] == n].to_dict('records'))
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("Вхід") and p == ADMIN_PASSWORD: st.session_state.logged_in, st.session_state.role = True, "Admin"; st.rerun()
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name'] if st.session_state.role=='Pilot' else 'Адмін'}**")
    if st.sidebar.button("Вийти"): st.session_state.logged_in = False; st.rerun()

    tab1, tab2, tab3 = st.tabs(["🚀 Польоти", "📜 Архів та Звіти", "📊 Аналітика"])

    with tab1:
        st.header("Внесення польотів")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", value=time(8,0), step=60, key="m_start_val")
            m_end = c3.time_input("Зміна до", value=time(20,0), step=60, key="m_end_val")
            m_route = c4.text_input("Маршрут", key="m_route_val")

        with st.expander("📝 Додати політ", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            t_o = col1.time_input("Зліт", value=time(9,0), step=60, key="t_off")
            t_l = col2.time_input("Посадка", value=time(9,30), step=60, key="t_land")
            dur = calculate_duration(t_o, t_l)
            col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            f_dist = col4.number_input("Відстань (м)", min_value=0, key="f_dist")
            cb1, cb2 = st.columns(2); f_akb = cb1.text_input("Номер АКБ", key="f_akb"); f_cyc = cb2.number_input("Цикли", min_value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
            f_note = st.text_area("Примітки", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            st.button("➕ Додати у список", on_click=add_flight_callback)

        if st.session_state.temp_flights:
            st.subheader("📋 Список польотів")
            df_v = pd.DataFrame(st.session_state.temp_flights)[["Взльот", "Посадка", "Тривалість (хв)", "Номер АКБ"]]
            st.dataframe(df_v, use_container_width=True)
            
            c_b1, c_b2, c_b3 = st.columns(3)
            if c_b1.button("🗑️ Видалити останній"): st.session_state.temp_flights.pop(); st.rerun()
            if c_b2.button("💾 Зберегти чернетку"):
                df_d = load_data("Drafts")
                df_d = df_d[df_d['Оператор'] != st.session_state.user['name']]
                conn.update(worksheet="Drafts", data=pd.concat([df_d, pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')], ignore_index=True))
                st.success("💾 Збережено!")

            if c_b3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                with st.spinner("Відправка..."):
                    all_fl = st.session_state.temp_flights
                    # 1. Telegram
                    flights_txt = "\n".join([f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)" for i, f in enumerate(all_fl)])
                    report = f"🚁 **Донесення: {all_fl[0]['Підрозділ']}**\n👤 **Пілот:** {all_fl[0]['Оператор']}\n🚀 **Вильоти:**\n{flights_txt}"
                    for fl in all_fl:
                        if fl.get('files'):
                            for img in fl['files']: send_telegram_photo(img, report)
                    if not any(f.get('files') for f in all_fl): send_telegram_text(report)
                    
                    # 2. Google Sheets (БАКЕТНЕ ОНОВЛЕННЯ)
                    final_to_save = []
                    for fl in all_fl:
                        row = fl.copy(); row.pop('files', None); row["Медіа (статус)"] = "З фото" if fl.get('files') else "Текст"
                        final_to_save.append(row)
                    
                    current_db = load_data("Sheet1")
                    updated_db = pd.concat([current_db, pd.DataFrame(final_to_save)], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=updated_db)
                    
                    # 3. Очищення чернеток
                    df_d = load_data("Drafts")
                    conn.update(worksheet="Drafts", data=df_d[df_d['Оператор'] != st.session_state.user['name']])
                    st.success("✅ Дані збережено!"); st.session_state.temp_flights = []; st.rerun()

    with tab2:
        st.header("📜 Архів польотів")
        full_archive = load_data("Sheet1")
        if not full_archive.empty:
            # Фільтри для Архіва
            c_f1, c_f2 = st.columns(2)
            if st.session_state.role == "Admin":
                sel_unit = c_f1.selectbox("Фільтр за підрозділом", ["Всі"] + UNITS)
                pilots_list = ["Всі"] + sorted(full_archive['Оператор'].unique().tolist())
                sel_pilot = c_f2.selectbox("Фільтр за пілотом", pilots_list)
            else:
                sel_unit = st.session_state.user['unit']
                sel_pilot = st.session_state.user['name']
                st.info(f"Відображення даних для: {sel_pilot} ({sel_unit})")

            # Застосування фільтрів
            display_df = full_archive.copy()
            if sel_unit != "Всі": display_df = display_df[display_df['Підрозділ'] == sel_unit]
            if sel_pilot != "Всі": display_df = display_df[display_df['Оператор'] == sel_pilot]
            
            st.dataframe(display_df.sort_values(by="Дата", ascending=False), use_container_width=True)
            
            # Генератор звіту на основі відфільтрованих даних
            if st.button("📄 Сформувати DOCX звіт (за фільтром)"):
                if not display_df.empty:
                    buf = generate_docx(display_df)
                    if buf == "ERROR_MISSING": st.error("❌ Шаблон DOCX не знайдено!")
                    elif buf: st.download_button("📥 Скачати звіт", buf, f"Report_{datetime.now().strftime('%d_%m')}.docx")
                else: st.warning("Немає даних для звіту")
        else: st.info("Архів порожній")

    with tab3:
        st.header("📊 Статистика")
        # (Ваш код аналітики з v4.8)