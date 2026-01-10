#!/usr/bin/env python3
"""
main.py

Приклад надійного оновлення аркуша Google Sheets з повним логуванням gspread APIError.

Налаштування (один із варіантів):
- Змінна середовища SERVICE_ACCOUNT_FILE -> шлях до service account JSON файлу
  або
- Змінна середовища SERVICE_ACCOUNT_INFO -> JSON string з вмістом service account (для Streamlit secrets)
- Змінна середовища SPREADSHEET_URL -> URL або ID таблиці Google Sheets

"""

import os
import json
import sys
import traceback
from typing import Optional

import pandas as pd
import requests
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# Обов'язкові scope'и для багатьох операцій (включно з доступом через Drive)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Шляхи / параметри (налаштуйте середовищні змінні перед запуском)
SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE")  # шлях до json-файлу
SERVICE_ACCOUNT_INFO = os.environ.get("SERVICE_ACCOUNT_INFO")  # json string (наприклад, з Streamlit secrets)
SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")  # повний URL або ID таблиці
OUTPUT_ERROR_PATH = os.environ.get("GSPREAD_ERROR_PATH", "/tmp/gspread_api_error.json")


def load_credentials() -> Credentials:
    """
    Завантажує credentials з файлу або з JSON-строки.
    Повертає google.oauth2.service_account.Credentials з потрібними scope'ами.
    """
    if SERVICE_ACCOUNT_INFO:
        try:
            info = json.loads(SERVICE_ACCOUNT_INFO)
        except Exception as e:
            raise RuntimeError("SERVICE_ACCOUNT_INFO встановлено, але це не валідний JSON") from e
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return creds

    if SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return creds

    # Спробуємо GOOGLE_APPLICATION_CREDENTIALS як запасний варіант
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and os.path.exists(gac):
        creds = Credentials.from_service_account_file(gac, scopes=SCOPES)
        return creds

    raise RuntimeError(
        "Не знайдено service account credentials. Встановіть SERVICE_ACCOUNT_FILE або SERVICE_ACCOUNT_INFO "
        "або GOOGLE_APPLICATION_CREDENTIALS."
    )


def create_gspread_client(creds: Credentials) -> gspread.Client:
    """
    Повертає ініціалізований gspread.Client з сесією requests.
    """
    client = gspread.Client(auth=creds)
    # Забезпечимо наявність session, іноді бібліотека очікує requests.Session()
    client.session = requests.Session()
    client.auth = creds
    return client


def ensure_worksheet(spreadsheet: gspread.Spreadsheet, title: str, rows: int = 1000, cols: int = 26):
    """
    Перевіряє наявність аркуша з назвою title. Якщо немає — створює.
    """
    try:
        ws = spreadsheet.worksheet(title)
        return ws
    except gspread.WorksheetNotFound:
        print(f"Worksheet '{title}' not found — створюю новий.")
        ws = spreadsheet.add_worksheet(title=title, rows=str(rows), cols=str(cols))
        return ws


def save_api_error(e: APIError, path: str):
    """
    Зберігає повну інформацію з e.response у файл path. Використовується для діагностики, коли UI редагує повідомлення.
    """
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
        # Більш безпечне fallback
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
        print(f"Повна відповідь API збережена в: {path}")
    except Exception as write_err:
        print(f"Не вдалося записати файл помилки: {write_err}")
        print("Повна відповідь (скорочено):")
        print(text[:2000] if text else "<no text>")


def update_drafts_dataframe(spreadsheet_arg: str, df: pd.DataFrame, worksheet_name: str = "Drafts"):
    """
    Основна функція: відкриває spreadsheet за URL/ID і оновлює аркуш worksheet_name даними df.
    Огорнута в безпечний try/except, що записує повний body відповіді у випадку APIError.
    """
    creds = load_credentials()
    client = create_gspread_client(creds)

    if not spreadsheet_arg:
        raise RuntimeError("SPREADSHEET_URL не встановлено. Встановіть SPREADSHEET_URL як змінну середовища.")

    # Відкриваємо по URL або по ID
    try:
        if spreadsheet_arg.startswith("http"):
            ss = client.open_by_url(spreadsheet_arg)
        else:
            # можливо передали сам ID
            ss = client.open_by_key(spreadsheet_arg)
    except Exception as e:
        print("Не вдалося відкрити spreadsheet. Перевірте SPREADSHEET_URL та доступи.")
        traceback.print_exc()
        raise

    # Переконаємось що аркуш існує
    try:
        ws = ensure_worksheet(ss, worksheet_name)
    except Exception as e:
        print("Помилка при перевірці/створенні worksheet:")
        traceback.print_exc()
        raise

    # Записуємо DataFrame у аркуш
    try:
        # Видаляємо існуючі дані (опціонально) та записуємо з заголовками
        ws.clear()
        set_with_dataframe(ws, df, include_index=False, include_column_header=True)
        print(f"Успішно оновлено аркуш '{worksheet_name}'.")
    except APIError as e:
        # Зберігаємо повний API response у файл для діагностики
        print("Caught gspread.exceptions.APIError — зберігаю повну відповідь у файл для діагностики.")
        save_api_error(e, OUTPUT_ERROR_PATH)
        # Друкуємо короткий snippet у stdout (UI може редагувати, але файл міститиме повний dump)
        try:
            snippet = e.response.text[:1000] if getattr(e, "response", None) is not None else repr(e)
        except Exception:
            snippet = repr(e)
        print("Короткий snippet відповіді:", snippet)
        traceback.print_exc()
        # Ререйзимо, якщо потрібно, або повертаємо помилку
        raise
    except Exception as e:
        print("Інша помилка при записі у аркуш:")
        traceback.print_exc()
        raise


def example_dataframe() -> pd.DataFrame:
    """Генерує приклад DataFrame — замініть на свій реальний df."""
    return pd.DataFrame(
        [
            {"flight_id": "AB123", "pilot": "Ivan", "status": "draft"},
            {"flight_id": "CD456", "pilot": "Olena", "status": "draft"},
        ]
    )


if __name__ == "__main__":
    # Приклад запуску: зчитаємо змінні середовища і виконаємо оновлення
    try:
        spreadsheet_arg = SPREADSHEET_URL or (len(sys.argv) > 1 and sys.argv[1]) or None
        if not spreadsheet_arg:
            raise RuntimeError(
                "SPREADSHEET_URL не задано (через змінну середовища або як аргумент командного рядка)."
            )

        df_to_write = example_dataframe()  # замініть на свій df або зчитайте зі свого коду
        update_drafts_dataframe(spreadsheet_arg, df_to_write, worksheet_name="Drafts")
    except Exception as e:
        print("Критична помилка в main:")
        traceback.print_exc()
        sys.exit(1)
