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

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(
    page_title="Кабінет пілота БПЛА v7.2",
    layout="wide",
    page_icon="🛡️"
)

def get_secret(key):
    try:
        return st.secrets.get(key) or \
               st.secrets.get("connections", {}).get("gsheets", {}).get(key)
    except Exception:
        return None

TG_TOKEN = get_secret("ТОКЕН_БОТА_ТЕЛЕГРАМ")
TG_CHAT_ID = get_secret("ІДЕНТИФІКАТОР_ТЕЛЕГРАМ_ЧАТУ")

UNITS = [
    "впс Кодима","віпс Шершенці","віпс Загнітків","впс Станіславка",
    "віпс Тимкове","віпс Чорна","впс Окни","віпс Ткаченкове",
    "віпс Гулянка","віпс Новосеменівка","впс Великокомарівка",
    "віпс Павлівка","віпс Велика Михайлівка","віпс Слов'яносербка",
    "віпс Гребеники","впс Степанівка","впс Кучурган",
    "впс Лиманське","впс Лучинське","УПЗ"
]

ADMIN_PASSWORD = "admin_secret"

UKR_MONTHS = {
    1:"січень",2:"лютий",3:"березень",4:"квітень",
    5:"травень",6:"червень",7:"липень",8:"серпень",
    9:"вересень",10:"жовтень",11:"листопад",12:"грудень"
}

# ==================================================
# HELPERS
# ==================================================
def smart_time_parse(val):
    if not val:
        return None
    s = "".join(filter(str.isdigit, str(val)))
    try:
        if len(s) <= 2:
            h, m = int(s), 0
        elif len(s) == 3:
            h, m = int(s[0]), int(s[1:])
        elif len(s) == 4:
            h, m = int(s[:2]), int(s[2:])
        else:
            return None
        if 0 <= h < 24 and 0 <= m < 60:
            return d_time(h, m)
    except Exception:
        pass
    return None

def minutes_from_time(t):
    return t.hour * 60 + t.minute

def calculate_duration(start, end):
    """Коректно рахує тривалість з переходом через 00:00"""
    s = minutes_from_time(start)
    e = minutes_from_time(end)
    return e - s if e >= s else e - s + 1440

def format_to_time_str(mins):
    return f"{mins//60:02d}:{mins%60:02d}"

def validate_flight(p_off, p_land, dist, akb, cyc):
    errors = []
    if not p_off or not p_land:
        errors.append("Некоректний час зльоту або посадки")
    else:
        dur = calculate_duration(p_off, p_land)
        if dur <= 0 or dur > 720:
            errors.append("Підозріла тривалість польоту")
    if dist < 0:
        errors.append("Відстань не може бути відʼємною")
    if akb and len(akb) > 20:
        errors.append("Номер АКБ занадто довгий")
    if cyc < 0 or cyc > 2000:
        errors.append("Некоректна кількість циклів АКБ")
    return errors

# ==================================================
# GSHEETS
# ==================================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(ws="Sheet1"):
    try:
        df = conn.read(worksheet=ws, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def write_df(ws, df):
    conn.update(worksheet=ws, data=df)

# ==================================================
# STATE
# ==================================================
defaults = {
    "logged_in": False,
    "role": None,
    "user": {},
    "temp_flights": []
}
for k,v in defaults.items():
    st.session_state.setdefault(k,v)

# ==================================================
# LOGIN
# ==================================================
if not st.session_state.logged_in:
    st.title("🛡️ Вхід у систему")
    role = st.radio("Режим", ["Пілот","Адміністратор"], horizontal=True)

    if role == "Пілот":
        unit = st.selectbox("Підрозділ", UNITS)
        name = st.text_input("Звання та Прізвище")
        if st.button("УВІЙТИ") and name:
            st.session_state.logged_in = True
            st.session_state.role = "Pilot"
            st.session_state.user = {"unit":unit,"name":name}
            st.rerun()
    else:
        pwd = st.text_input("Пароль", type="password")
        if st.button("ВХІД") and pwd == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.role = "Адміністратор"
            st.session_state.user = {"name":"Адмін","unit":""}
            st.rerun()
    st.stop()

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.write(f"👤 {st.session_state.user.get('name','')}")
if st.sidebar.button("Вихід"):
    st.session_state.clear()
    st.rerun()

tabs = st.tabs([
    "🚀 Польоти","📋 Заявка","📡 ЦУС",
    "📜 Архів","📊 Аналітика","ℹ️ Довідка"
])

# ==================================================
# TAB: ПОЛЬОТИ
# ==================================================
with tabs[0]:
    st.header("Внесення вильоту")

    c1,c2,c3 = st.columns(3)
    t_off = c1.text_input("Зліт (0930)")
    t_land = c2.text_input("Посадка (1010)")
    dist = c3.number_input("Дистанція (м)", min_value=0)

    c4,c5 = st.columns(2)
    akb = c4.text_input("Номер АКБ")
    cyc = c5.number_input("Цикли АКБ", min_value=0)

    p_off = smart_time_parse(t_off)
    p_land = smart_time_parse(t_land)

    if p_off and p_land:
        dur = calculate_duration(p_off,p_land)
        st.info(f"⏱ Тривалість: {dur} хв")

    if st.button("➕ ДОДАТИ"):
        errs = validate_flight(p_off,p_land,dist,akb,cyc)
        if errs:
            for e in errs:
                st.error(e)
        else:
            st.session_state.temp_flights.append({
                "Дата": datetime.now().strftime("%d.%m.%Y"),
                "Підрозділ": st.session_state.user["unit"],
                "Оператор": st.session_state.user["name"],
                "Взльот": p_off.strftime("%H:%M"),
                "Посадка": p_land.strftime("%H:%M"),
                "Тривалість (хв)": dur,
                "Дистанція (м)": dist,
                "Номер АКБ": akb,
                "Цикли АКБ": cyc
            })
            st.success("Додано")
            st.rerun()

    if st.session_state.temp_flights:
        st.dataframe(pd.DataFrame(st.session_state.temp_flights), use_container_width=True)
        if st.button("🚀 ВІДПРАВИТИ ВСЕ"):
            write_df("Sheet1", pd.DataFrame(st.session_state.temp_flights))
            st.session_state.temp_flights = []
            st.success("Надіслано")
            st.rerun()

# ==================================================
# TAB: ЗАЯВКА
# ==================================================
with tabs[1]:
    st.header("Формування заявки")
    st.warning("Цей розділ не відправляє заявку автоматично")

# ==================================================
# TAB: ЦУС (EDGE-CASE)
# ==================================================
with tabs[2]:
    st.header("Дані для ЦУС")
    before, after = [], []
    for f in st.session_state.temp_flights:
        fs = datetime.strptime(f["Взльот"],"%H:%M").time()
        fe = datetime.strptime(f["Посадка"],"%H:%M").time()
        if fe < fs:
            before.append(f)
            after.append(f)
        else:
            before.append(f)
    st.subheader("До 00:00")
    st.code("\n".join([f"{f['Взльот']} - {f['Посадка']}" for f in before]))
    st.subheader("Після 00:00")
    st.code("\n".join([f"{f['Взльот']} - {f['Посадка']}" for f in after]))

# ==================================================
# TAB: АРХІВ
# ==================================================
with tabs[3]:
    df = load_data("Sheet1")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Архів порожній")

# ==================================================
# TAB: АНАЛІТИКА
# ==================================================
with tabs[4]:
    df = load_data("Sheet1")
    if not df.empty and "Дата" in df.columns:
        df["Дата_dt"] = pd.to_datetime(df["Дата"], format="%d.%m.%Y", errors="coerce")
        df = df.dropna(subset=["Дата_dt"])
        df["M"] = df["Дата_dt"].dt.month
        df["Y"] = df["Дата_dt"].dt.year
        rs = df.groupby(["Y","M"]).agg(
            Польоти=("Дата","count"),
            Хв=("Тривалість (хв)","sum")
        ).reset_index()
        rs["Місяць"] = rs.apply(lambda x: f"{UKR_MONTHS[x.M]} {x.Y}", axis=1)
        rs["Наліт"] = rs["Хв"].apply(format_to_time_str)
        st.table(rs[["Місяць","Польоти","Наліт"]])
    else:
        st.info("Недостатньо даних")

# ==================================================
# TAB: ДОВІДКА
# ==================================================
with tabs[5]:
    st.markdown("### Слава Україні 🇺🇦")
