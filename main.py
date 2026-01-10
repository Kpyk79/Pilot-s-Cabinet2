#!/usr/bin/env python3
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time
from datetime import datetime, time as d_time, timedelta

import json
import traceback
import os
from gspread.exceptions import APIError

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="UAV Pilot Cabinet v7.2", layout="wide", page_icon="🛡️")

def get_secret(key):
    val = None
    try:
        val = st.secrets.get(key)
    except Exception:
        pass
    if val:
        return val
    try:
        return st.secrets["connections"]["gsheets"].get(key)
    except Exception:
        return None

TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# Path to save full API error dump (can be overridden by env GSPREAD_ERROR_PATH)
OUTPUT_ERROR_PATH = os.environ.get("GSPREAD_ERROR_PATH", "/tmp/gspread_api_error.json")

# --- 2. КОНСТАНТИ ТА СЛОВНИКИ ---
UNITS = [
    "впс Кодима", "віпс Шершенці", "віпс Загнітків", "впс Станіславка", 
    "віпс Тимкове", "віпс Чорна", "впс Окни", "віпс Ткаченкове", 
    "віпс Гулянка", "віпс Новосеменівка", "впс Великокомарівка", 
    "віпс Павлівка", "впс Велика Михайлівка", "віпс Слов'яносербка", 
    "віпс Гребеники", "впс Степанівка", "впс Кучурган", 
    "віпс Лиманське", "віпс Лучинське", "УПЗ"
]
ADMIN_PASSWORD = "admin_secret"

UKR_MONTHS = {1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"}

# --- 3. ДОПОМІЖНІ ФУНКЦІЇ ---
def smart_time_parse(val):
    if not val: return None
    val = "".join(filter(str.isdigit, str(val)))
    if not val: return None
    try:
        if len(val) <= 2: h, m = int(val), 0
        elif len(val) == 3: h, m = int(val[0]), int(val[1:])
        elif len(val) == 4: h, m = int(val[:2]), int(val[2:])
        else: return None
        if 0 <= h < 24 and 0 <= m < 60: return d_time(h, m)
    except: pass
    return None

def calculate_duration(start, end):
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    d = e - s
    return d if d >= 0 else d + 1440

def format_to_time_str(total_minutes):
    try:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{int(hours):02d}:{int(minutes):02d}"
    except: return "00:00"

def save_api_error(e: APIError, path: str = OUTPUT_ERROR_PATH):
    try:
        resp = getattr(e, "response", None)
        status = getattr(resp, "status_code", None)
        headers = getattr(resp, "headers", None)
        text = None
        try:
            text = resp.text if resp is not None else None
        except Exception:
            text = "<could not read response.text>"
    except Exception as inner:
        status = None
        headers = None
        text = f"<error while extracting response: {inner}>"

    payload = {
        "status_code": status,
        "headers": dict(headers) if headers else None,
        "text": text,
        "repr": repr(e),
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"gspread APIError saved to: {path}")
    except Exception as write_err:
        print(f"Failed to write API error file: {write_err}")
        print((text or "")[:2000])

# normalize dataframe columns (strip whitespace and BOM)
def normalize_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    cols = [str(c).strip().replace('\ufeff', '') for c in df.columns]
    df = df.copy()
    df.columns = cols
    return df

# safe conn update wrapper
def safe_conn_update(conn, **kwargs):
    try:
        return conn.update(**kwargs)
    except APIError as e:
        save_api_error(e)
        st.error("Помилка при збереженні у Google Sheets. Деталі збережені в " + OUTPUT_ERROR_PATH)
        raise
    except Exception:
        traceback.print_exc()
        st.error("Несподівана помилка при зверненні до Google Sheets. Перевірте логи.")
        raise

# helper to load data and normalize columns + strip text fields
def load_data(ws="Sheet1"):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame()
        df = normalize_df_columns(df)
        # ensure string columns are stripped
        for c in df.select_dtypes(include=[object]).columns:
            df[c] = df[c].astype(str).str.strip()
        return df.dropna(how="all")
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

# write dataframe to sheet, optionally remove existing rows for a given operator
def write_df_to_sheet(worksheet_name: str, new_df: pd.DataFrame, remove_operator: str | None = None) -> None:
    new_df = normalize_df_columns(new_df)
    try:
        existing = load_data(worksheet_name)
    except Exception:
        existing = pd.DataFrame()

    if remove_operator and not new_df.empty and 'Оператор' in new_df.columns:
        op = remove_operator.strip().lower()
        if not existing.empty and 'Оператор' in existing.columns:
            existing = existing[~(existing['Оператор'].astype(str).str.strip().str.lower() == op)]

    if existing.empty:
        out = new_df.reset_index(drop=True)
    else:
        # ensure same columns: take union
        out = pd.concat([existing, new_df], ignore_index=True, sort=False).reset_index(drop=True)

    # Safe update
    safe_conn_update(conn, worksheet=worksheet_name, data=out)

# remember user in Settings sheet for persistence between sessions
def save_remembered_user(name: str, unit: str):
    try:
        df = pd.DataFrame([{"key": "last_user", "Оператор": name.strip(), "Підрозділ": unit.strip()}])
        safe_conn_update(conn, worksheet="Settings", data=df)
    except Exception:
        traceback.print_exc()

def load_remembered_user():
    try:
        df = load_data("Settings")
        if not df.empty:
            # try to find row with key last_user
            if 'key' in df.columns:
                row = df[df['key'] == 'last_user']
                if not row.empty:
                    return row.iloc[0].get('Оператор', ''), row.iloc[0].get('Підрозділ', UNITS[0])
            # else take first row
            row = df.iloc[0]
            return row.get('Оператор', ''), row.get('Підрозділ', UNITS[0])
    except Exception:
        traceback.print_exc()
    return '', UNITS[0]

# robust drone lookup: accept different column names
def get_drones_for_unit(unit):
    try:
        df = load_data("DronesDB")
        if df.empty: return []
        # possible name variants
        unit_col = None
        for c in df.columns:
            if c.lower().strip() in ['підрозділ', 'pidrozdil', 'unit', 'підрозділ:']:
                unit_col = c
                break
        if unit_col is None and 'Підрозділ' in df.columns:
            unit_col = 'Підрозділ'
        if unit_col is None:
            # try first column
            unit_col = df.columns[0]

        unit_drones = df[df[unit_col].astype(str).str.strip() == unit]
        if unit_drones.empty: return []

        # possible model and sn columns
        model_col = None
        sn_col = None
        for c in df.columns:
            cl = c.lower()
            if 'модел' in cl or 'модель' in cl or 'model' in cl:
                model_col = c
            if 's/n' in cl or cl == 'sn' or 's_n' in cl or 'serial' in cl:
                sn_col = c
        # fallback names
        if model_col is None:
            for alt in ['Модель БпЛА', 'Модель']:
                if alt in df.columns:
                    model_col = alt
                    break
        if sn_col is None:
            for alt in ['S/N', 's/n', 'SN', 's_n', 'S N']:
                if alt in df.columns:
                    sn_col = alt
                    break

        drones_list = []
        for _, row in unit_drones.iterrows():
            model = row.get(model_col, '') if model_col else ''
            sn = row.get(sn_col, '') if sn_col else ''
            if pd.isna(model): model = ''
            if pd.isna(sn): sn = ''
            model = str(model).strip()
            sn = str(sn).strip()
            if model:
                display = f"{model} (S/N: {sn})" if sn else model
                drones_list.append(display)
        return drones_list
    except Exception:
        traceback.print_exc()
        return []

# --- 4. РОБОТА З БАЗОЮ ТА TG ---
conn = st.connection("gsheets", type=GSheetsConnection)

def send_telegram_msg(all_fl):
    if not TG_TOKEN or not TG_CHAT_ID: return
    first = all_fl[0]
    flights_details = []
    for i, f in enumerate(all_fl):
        flight_text = f"{i+1}. {f['Взльот']}-{f['Посадка']} ({f['Тривалість (хв)']} хв)\n   Результат: {f['Результат']}"
        if f.get('Примітки'):
            flight_text += f"\n   Примітки: {f['Примітки']}"
        flights_details.append(flight_text)
    flights_txt = "\n".join(flights_details)
    report = f"🚁 **Донесення: {first['Підрозділ']}**\n👤 **Пілот:** {first['Оператор']}\n📅 **Дата:** {first['Дата']}\n⏰ **Час завдання:** {first['Час завдання']}\n🛡 **БпЛА:** {first['Дрон']}\n━━━━━━━━━━━━━━━\n🚀 **Вильоти:**\n{flights_txt}"
    all_photos = []
    for fl in all_fl:
        if fl.get('files'):
            for img in fl['files']:
                all_photos.append(img)
    if all_photos:
        media_group = []
        for idx, img in enumerate(all_photos):
            photo_data = {'type': 'photo', 'media': f'attach://photo{idx}'}
            if idx == 0:
                photo_data['caption'] = report
                photo_data['parse_mode'] = 'Markdown'
            media_group.append(photo_data)
        files = {f'photo{idx}': (getattr(img, 'name', f'photo{idx}.jpg'), img.getvalue(), getattr(img, 'type', 'image/jpeg')) for idx, img in enumerate(all_photos)}
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup",
            data={'chat_id': str(TG_CHAT_ID), 'media': json.dumps(media_group)},
            files=files
        )
    else:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={'chat_id': str(TG_CHAT_ID), 'text': report, 'parse_mode': 'Markdown'}
        )

# --- 5. ІНІЦІАЛІЗАЦІЯ СТАНУ ---
if 'temp_flights' not in st.session_state: st.session_state.temp_flights = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'splash_done' not in st.session_state: st.session_state.splash_done = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
if 'last_unit' not in st.session_state: st.session_state.last_unit = UNITS[0]
if 'last_name' not in st.session_state: st.session_state.last_name = ""
if 'remember_credentials' not in st.session_state: st.session_state.remember_credentials = True
if 'app_contact' not in st.session_state: st.session_state.app_contact = ""
if 'app_phone' not in st.session_state: st.session_state.app_phone = ""

# Load remembered user from Settings sheet (persisted across app restarts)
try:
    remembered_name, remembered_unit = load_remembered_user()
    if remembered_name:
        st.session_state.last_name = remembered_name
    if remembered_unit:
        st.session_state.last_unit = remembered_unit
except Exception:
    pass

# --- 6. СТИЛІ ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; background-color: #2E7D32; color: white; height: 3.5em; font-weight: bold; border: none; }
    .stButton>button:hover { background-color: #1B5E20; color: white; }
    .duration-box { background-color: #f1f3f5; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; color: #1b5e20; font-size: 1.2em; }
    .splash-container { text-align: center; margin-top: 15%; }
    .slogan-box { color: #2E7D32; font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.5em; border-top: 2px solid #2E7D32; border-bottom: 2px solid #2E7D32; padding: 20px 0; margin: 20px 0; letter-spacing: 2px; }
    .contact-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32; margin-bottom: 15px; color: black !important; }
    .contact-title { font-size: 1.1em; font-weight: bold; color: black !important; margin-bottom: 5px; }
    .contact-desc { font-size: 0.9em; color: black !important; font-style: italic; margin-bottom: 10px; line-height: 1.3; }
    .stAlert p { color: black !important; }
    .login-hint { font-size: 0.85em; color: #666; font-style: italic; margin-top: -10px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 7. SPLASH SCREEN ---
if not st.session_state.splash_done:
    container = st.empty()
    with container.container():
        st.markdown("<div class='splash-container'><h1 style='font-size: 4em;'>🛡️</h1><h1>UAV PILOT CABINET</h1><div class='slogan-box'>СТАЛЕВИЙ ОБЛІК ДЛЯ СТАЛЕВОГО КОРДОНУ</div></div>", unsafe_allow_html=True)
        my_bar = st.progress(0, text="Ініціалізація...")
        for p in range(100): time.sleep(0.01); my_bar.progress(p + 1)
        st.session_state.splash_done = True; st.rerun()

# --- 8. ІНТЕРФЕЙС ВХОДУ ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🛡️ ВХІД У СИСТЕМУ</h2>", unsafe_allow_html=True)
    role = st.radio("Режим:", ["Пілот", "Адміністратор"], horizontal=True)
    with st.container(border=True):
        if role == "Пілот":
            unit_index = UNITS.index(st.session_state.last_unit) if st.session_state.last_unit in UNITS else 0
            u = st.selectbox("Підрозділ:", UNITS, index=unit_index)
            n = st.text_input("Звання та Прізвище:", value=st.session_state.last_name, placeholder="наприклад: ст.с-т Іваненко")
            if st.session_state.last_name:
                st.markdown("<p class='login-hint'>💡 Дані автоматично збережено з попереднього входу</p>", unsafe_allow_html=True)
            remember = st.checkbox("Запам'ятати мої дані", value=st.session_state.remember_credentials)
            if st.button("УВІЙТИ") and n:
                if remember:
                    st.session_state.last_unit = u
                    st.session_state.last_name = n
                    st.session_state.remember_credentials = True
                    # persist to Settings sheet
                    try:
                        save_remembered_user(n, u)
                    except Exception:
                        pass
                else:
                    st.session_state.last_unit = UNITS[0]
                    st.session_state.last_name = ""
                    st.session_state.remember_credentials = False
                st.session_state.logged_in = True
                st.session_state.role = "Pilot"
                st.session_state.user = {"unit": u, "name": n}
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    my_d = df_d[df_d['Оператор'].astype(str).str.strip().str.lower() == n.strip().lower()]
                    if not my_d.empty:
                        st.session_state.temp_flights.extend(my_d.to_dict('records'))
                st.rerun()
        else:
            p = st.text_input("Пароль:", type="password")
            if st.button("ВХІД") and p == ADMIN_PASSWORD:
                st.session_state.logged_in, st.session_state.role = True, "Admin"
                st.rerun()

# --- 9. ОСНОВНИЙ ІНТЕРФЕЙС ---
else:
    st.sidebar.markdown(f"👤 **{st.session_state.user['name'] if st.session_state.role=='Pilot' else 'Адмін'}**")
    if st.sidebar.button("Вийти"): 
        st.session_state.logged_in = False
        st.session_state.splash_done = False
        st.rerun()

    tab_f, tab_app, tab_cus, tab_hist, tab_stat, tab_info = st.tabs(["🚀 Польоти", "📋 Заявка", "📡 ЦУС", "📜 Архів", "📊 Аналітика", "ℹ️ Довідка"])

    # --- ВКЛАДКА ПОЛЬОТИ ---
    with tab_f:
        st.header("Внесення польотів")
        
        # Отримуємо дрони для поточного підрозділу
        available_drones = get_drones_for_unit(st.session_state.user['unit'])
        if not available_drones:
            st.warning(f"⚠️ У базі даних немає дронів для підрозділу '{st.session_state.user['unit']}'. Зверніться до адміністратора.")
            available_drones = ["Дрон не вказано"]
        
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            m_date = c1.date_input("Дата завдання", datetime.now(), key="m_date_val")
            m_start = c2.time_input("Зміна з", d_time(8,0), key="m_start_val")
            m_end = c3.time_input("Зміна до", d_time(20,0), key="m_end_val")
            m_route = c4.text_input("Маршрут", key="m_route_val", placeholder="Введіть маршрут")
            st.selectbox("🛡️ БпЛА НА ЗМІНУ:", available_drones, key="sel_drone_val")
        
        with st.expander("➕ ДОДАТИ НОВИЙ ВИЛІТ", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            t_off_str = col1.text_input("Взльот", value="", placeholder="09:00 або 0930", help="Можна 930 або 0930", key="t_off_input")
            t_land_str = col2.text_input("Посадка", value="", placeholder="09:30", key="t_land_input")
            p_off, p_land = smart_time_parse(t_off_str), smart_time_parse(t_land_str)
            if p_off and p_land:
                dur = calculate_duration(p_off, p_land)
                col3.markdown(f"<div class='duration-box'>⏳ <b>{dur} хв</b></div>", unsafe_allow_html=True)
            else:
                col3.info("⏳ Час?")
            f_dist = col4.number_input("Відстань (м)", min_value=0, value=0, key="f_dist", help="Відстань польоту в метрах")
            cb1, cb2 = st.columns(2)
            f_akb = cb1.text_input("Номер АКБ", value="", placeholder="Введіть номер", key="f_akb")
            f_cyc = cb2.number_input("Цикли АКБ", min_value=0, value=0, key="f_cyc")
            f_res = st.selectbox("Результат", ["Без ознак порушення", "Затримання", "Виявлення цілі"], key="f_res")
            f_note = st.text_area("Примітки", value="", placeholder="Додаткова інформація (необов'язково)", key="f_note")
            f_imgs = st.file_uploader("📸 Скріншоти", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            
            if st.button("✅ ДОДАТИ У СПИСОК"):
                if p_off and p_land:
                    st.session_state.temp_flights.append({
                        "Дата": st.session_state.m_date_val.strftime("%d.%m.%Y"),
                        "Час завдання": f"{st.session_state.m_start_val.strftime('%H:%M')} - {st.session_state.m_end_val.strftime('%H:%M')}",
                        "Підрозділ": st.session_state.user['unit'],
                        "Оператор": st.session_state.user['name'],
                        "Дрон": st.session_state.sel_drone_val,
                        "Маршрут": st.session_state.m_route_val,
                        "Взльот": p_off.strftime("%H:%M"),
                        "Посадка": p_land.strftime("%H:%M"),
                        "Тривалість (хв)": calculate_duration(p_off, p_land),
                        "Дистанція (м)": st.session_state.f_dist,
                        "Номер АКБ": st.session_state.f_akb,
                        "Цикли АКБ": st.session_state.f_cyc,
                        "Результат": f_res,
                        "Примітки": f_note,
                        "files": f_imgs
                    })
                    st.session_state.uploader_key += 1
                    st.rerun()
                else:
                    st.error("⚠️ Будь ласка, введіть коректний час взльоту та посадки")

        if st.session_state.temp_flights:
            df_t = pd.DataFrame(st.session_state.temp_flights)
            df_v = df_t[[c for c in ["Взльот", "Посадка", "Дистанція (м)", "Тривалість (хв)", "Номер АКБ", "Цикли АКБ"] if c in df_t.columns]]
            df_v.columns = ["Зліт", "Посадка", "Відстань", "Хв", "№ АКБ", "Цикли"][:len(df_v.columns)]
            st.dataframe(df_v, use_container_width=True)
            cb1, cb2, cb3 = st.columns(3)
            if cb1.button("🗑️ Видалити останній"):
                st.session_state.temp_flights.pop()
                st.rerun()
            if cb2.button("💾 Зберегти в Хмару"):
                df_d = load_data("Drafts")
                # remove previous drafts for this operator
                try:
                    new_df = pd.DataFrame(st.session_state.temp_flights).drop(columns=['files'], errors='ignore')
                    write_df_to_sheet("Drafts", new_df, remove_operator=st.session_state.user['name'])
                    st.success("💾 Збережено у чернетки (Drafts)!")
                except Exception:
                    st.error("Не вдалося зберегти. Подивіться лог /tmp/gspread_api_error.json для детал��й.")
            if cb3.button("🚀 ВІДПРАВИТИ ВСІ ДАНІ"):
                all_fl = st.session_state.temp_flights
                send_telegram_msg(all_fl)
                final_to_db = []
                for f in all_fl:
                    row = f.copy()
                    row.pop('files', None)
                    row["Медіа (статус)"] = "З фото" if f.get('files') else "Текст"
                    final_to_db.append(row)
                try:
                    write_df_to_sheet("Sheet1", pd.DataFrame(final_to_db))
                except Exception:
                    st.error("Не вдалося записати у основну базу. Подивіться лог /tmp/gspread_api_error.json.")
                    raise

                # Очищуємо Drafts після успішної відправки
                df_d = load_data("Drafts")
                if not df_d.empty and "Оператор" in df_d.columns:
                    try:
                        # remove this operator's drafts
                        remaining = df_d[~(df_d['Оператор'].astype(str).str.strip().str.lower() == st.session_state.user['name'].strip().lower())]
                        if not remaining.empty:
                            safe_conn_update(conn, worksheet="Drafts", data=remaining)
                        else:
                            # If no remaining drafts, clear the sheet
                            safe_conn_update(conn, worksheet="Drafts", data=pd.DataFrame())
                    except Exception:
                        st.error("Не вдалося оновити Drafts після відправки. Перевірте лог.")
                        raise

                st.success("✅ Надіслано!")
                st.session_state.temp_flights = []
                st.rerun()

    # --- ВКЛАДКА ЗАЯВКА ---
    with tab_app:
        st.header("📝 Формування заявки")
        
        st.warning("⚠️ **УВАГА:** Даний розділ НЕ відправляє заявки автоматично на ЦУС! Він лише допомагає швидко сформувати текст заявки. Після формування скопіюйте текст та відправте його самостійно через месенджери.")
        
        available_drones = get_drones_for_unit(st.session_state.user['unit'])
        if not available_drones:
            st.warning(f"⚠️ У базі даних немає дронів для підрозділу '{st.session_state.user['unit']}'.")
            available_drones = ["Дрон не вказано"]
        
        with st.container(border=True):
            app_unit = st.selectbox("1. Заявник:", UNITS, index=UNITS.index(st.session_state.user['unit']) if st.session_state.user['unit'] in UNITS else 0)
            app_drones = st.multiselect("2. Тип БпЛА:", available_drones, default=None)
            app_dates = st.date_input("3. Дата здійснення польоту:", value=(datetime.now(), datetime.now() + timedelta(days=1)))
            c_t1, c_t2 = st.columns(2)
            a_t1 = c_t1.time_input("4. Час роботи з:", d_time(8,0))
            a_t2 = c_t2.time_input("до:", d_time(20,0))
            app_route = st.text_area("5. Населений пункт (маршрут):")
            c_h1, c_h2 = st.columns(2)
            a_h = c_h1.text_input("6. Висота (м):", "до 500 м")
            a_r = c_h2.text_input("7. Радіус (км):", "до 5 км")
            app_purp = st.selectbox("8. Мета:", ["патрулювання ділянки відповідальності", "за оперативною необхідністю", "навчально-тренувальні польоти"])
            
            c_cont, c_phone = st.columns(2)
            app_cont = c_cont.text_input("9. Контактна особа:", value=st.session_state.app_contact if st.session_state.app_contact else st.session_state.user['name'], placeholder="Прізвище Ім'я")
            app_phone = c_phone.text_input("10. Номер телефону:", value=st.session_state.app_phone, placeholder="+380...")
            
        if st.button("✨ СФОРМУВАТИ ТЕКСТ ЗАЯВКИ"):
            st.session_state.app_contact = app_cont
            st.session_state.app_phone = app_phone
            d_str = ", ".join(app_drones) if app_drones else "не вказано"
            dt_r = f"з {app_dates[0].strftime('%d.%m.%Y')} по {app_dates[1].strftime('%d.%m.%Y')}" if isinstance(app_dates, tuple) and len(app_dates) == 2 else app_dates[0].strftime('%d.%m.%Y')
            contact_info = f"{app_cont}, тел: {app_phone}" if app_phone else app_cont
            f_txt = f"ЗАЯВКА НА ПОЛІТ\n1. Заявник: в/ч 2196 ({app_unit})\n2. Тип БпЛА: {d_str}\n3. Дата здійснення польоту: {dt_r}\n4. Час роботи: з {a_t1.strftime('%H:%M')} по {a_t2.strftime('%H:%M')}\n5. Населений пункт (маршрут): {app_route}\n6. Висота роботи (м): {a_h}\n7. Радіус роботи (км): {a_r}\n8. Мета польоту: {app_purp}\n9. Контактна особа: {contact_info}"
            st.code(f_txt, language="text")

    # --- ВКЛАДКА ЦУС ---
    with tab_cus:
        st.header("📡 Дані для ЦУС")
        if not st.session_state.temp_flights:
            st.info("Додайте польоти.")
        else:
            all_f = st.session_state.temp_flights
            s_start = st.session_state.m_start_val
            b_m, a_m, cr = [], [], False
            for f in all_f:
                fs = datetime.strptime(f['Взльот'], "%H:%M").time()
                fe = datetime.strptime(f['Посадка'], "%H:%M").time()
                if cr or fe < fs or fs < s_start:
                    cr = True
                    a_m.append(f)
                else:
                    b_m.append(f)
            def fc(fls):
                return "\n".join([f"{f['Взльот']} - {f['Посадка']} - {f.get('Дистанція (м)', 0)} м ({f['Тривалість (хв)']} хв)" for f in fls])
            st.subheader("🌙 До 00:00")
            st.code(fc(b_m), language="text")
            st.subheader("☀️ Після 00:00")
            st.code(fc(a_m), language="text")

    # --- ВКЛАДКА АРХІВ ---
    with tab_hist:
        st.header("📜 Мій журнал")
        df_h = load_data("Sheet1")
        if not df_h.empty and "Оператор" in df_h.columns:
            if st.session_state.role == "Pilot":
                # case-insensitive match
                mask = df_h['Оператор'].astype(str).str.strip().str.lower() == st.session_state.user['name'].strip().lower()
                p_df = df_h[mask]
            else:
                p_df = df_h
            if not p_df.empty:
                # ensure date parsing for sorting
                p_df['Дата_dt'] = pd.to_datetime(p_df['Дата'], format='%d.%m.%Y', errors='coerce')
                cols = ["Дата", "Час завдання", "Підрозділ", "Оператор", "Дрон", "Маршрут", "Взльот", "Посадка", "Тривалість (хв)", "Дистанція (м)", "Результат", "Примітки", "Медіа (статус)", "Номер АКБ", "Цикли АКБ"]
                available_cols = [c for c in cols if c in p_df.columns]
                st.dataframe(p_df[available_cols].sort_values(by='Дата_dt', ascending=False).drop(columns=['Дата_dt'], errors='ignore'), use_container_width=True)
            else:
                st.info("Архів порожній для цього оператора.")
        else:
            st.info("База даних ще не містить записів.")

    # --- ВКЛАДКА АНАЛІТИКА ---
    with tab_stat:
        st.header("📊 Аналітика")
        df_s = load_data("Sheet1")
        if not df_s.empty and "Оператор" in df_s.columns and "Дата" in df_s.columns:
            if st.session_state.role == "Pilot":
                df_s = df_s[df_s['Оператор'].astype(str).str.strip().str.lower() == st.session_state.user['name'].strip().lower()]
            if not df_s.empty:
                df_s['Дата_dt'] = pd.to_datetime(df_s['Дата'], format='%d.%m.%Y', errors='coerce')
                df_s = df_s.dropna(subset=['Дата_dt'])
                if not df_s.empty:
                    df_s['M_num'] = df_s['Дата_dt'].dt.month
                    df_s['Y_num'] = df_s['Дата_dt'].dt.year
                    # make sure duration is numeric
                    if 'Тривалість (хв)' in df_s.columns:
                        df_s['Тривалість (хв)'] = pd.to_numeric(df_s['Тривалість (хв)'], errors='coerce').fillna(0)
                    else:
                        df_s['Тривалість (хв)'] = 0
                    rs = df_s.groupby(['Y_num', 'M_num']).agg(
                        Польоти=('Дата', 'count'),
                        Затримання=('Результат', lambda x: (x == "Затримання").sum()),
                        Хв=('Тривалість (хв)', 'sum')
                    ).reset_index()
                    if not rs.empty:
                        rs['Місяць'] = rs.apply(lambda x: f"{UKR_MONTHS.get(int(x['M_num']), '???')} {int(x['Y_num'])}", axis=1)
                        rs['Наліт'] = rs['Хв'].apply(format_to_time_str)
                        st.table(rs.sort_values(by=['Y_num', 'M_num'], ascending=False)[['Місяць', 'Польоти', 'Затримання', 'Наліт']])
            else:
                st.info("Немає польотів.")

    # --- ВКЛАДКА ДОВІДКА ---
    with tab_info:
        st.header("ℹ️ Довідка")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("<div class='contact-card'><div class='contact-title'>🎓 Інструктор</div><div class='contact-desc'>Питання тактики застосування, налаштування системи та спеціалізованого ПЗ БпАС.</div><b>Олександр</b><br>+380502310609</div>", unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='contact-card'><div class='contact-title'>🔧 Технік-майстер</div><div class='contact-desc'>Механічні пошкодження майна, ремонт, збої апаратної частини.</div><b>Сергій</b><br>+380997517054</div>", unsafe_allow_html=True)
        with c3:
            st.markdown("<div class='contact-card'><div class='contact-title'>📦 Начальник складу</div><div class='contact-desc'>Облік майна, оформлення актів переміщення та передача обладнання.</div><b>Ірина</b><br>+380667869701</div>", unsafe_allow_html=True)
        st.write("---")
        st.subheader("📖 Повна документація")
        with st.expander("🛡️ ІНСТРУКЦІЯ КОРИСТУВАЧА", expanded=False):
            st.markdown("""**1. 🔑 Вхід у систему**
* Оберіть Підрозділ, введіть Звання та Прізвище.
* При повторному вході дані автоматично підставляться.
* Натисніть «Увійти».

**2. 🚀 Вкладка «Польоти»**
* **Крок А (Завдання):** Встановіть Дату, Час зміни та оберіть БпЛА на зміну.
* **Крок Б (Виліт):** Вкажіть час Взльоту/Посадки, Відстань, Номер АКБ та Цикли.
* **Крок В (Управління):** Тисніть «➕ Додати у список». В кінці зміни — «🚀 ВІДПРАВИТИ ВСІ ДАНІ».

**3. 📋 Вкладка «Заявка»**
* УВАГА: Розділ НЕ відправляє заявки автоматично!
* Оберіть параметри польоту та натисніть «Сформувати текст заявки».
* Скопіюйте текст та відправте самостійно через месенджери.

**4. 📡 Вкладка «ЦУС»**
* Система сама розбиває польоти на вікна «До 00:00» та «Після 00:00».

**💡 Поради:**
* При слабкому інтернеті тисніть «Зберегти в Хмару».
* Для нічної зміни вказуйте дату, якою зміна почалася.
* Система автоматично запам'ятовує ваші контактні дані.""")
        with st.expander("📲 ЯК ВСТАНОВИТИ НА СМАРТФОН", expanded=False):
            st.markdown("""**Android (Chrome):** Три крапки (⋮) -> «Додати на головний екран».
**iPhone (Safari):** Поділитися -> «Додати на початковий екран».""")
        st.write("---")
        st.markdown("<div style='text-align: center; color: black;'>Слава Україні! 🇺🇦</div>", unsafe_allow_html=True)