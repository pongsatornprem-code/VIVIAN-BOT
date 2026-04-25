import os
import json
import re
import html as html_lib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import gspread

from google.oauth2.service_account import Credentials

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)


LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")


def thai_now():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")


def thai_today():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d")


def thai_now_minute():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M")


def get_sheet():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID)


def push_line(text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

    if not LINE_USER_ID:
        raise RuntimeError("Missing LINE_USER_ID")

    config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

    with ApiClient(config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.push_message(
            PushMessageRequest(
                to=LINE_USER_ID,
                messages=[TextMessage(text=text)]
            )
        )


def get_gold_text():
    url = "https://www.talupa.com/gold/Thailand"

    try:
        res = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        res.raise_for_status()

        raw = html_lib.unescape(res.text)
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text)

        def find_price(k):
            pattern = rf"ราคาทองต่อกรัม\s*{k}\s*฿\s*([\d,]+\.\d+)"
            match = re.search(pattern, text, re.IGNORECASE)
            return f"฿ {match.group(1)}" if match else "ไม่พบ"

        return f"""📊 ราคาทองวันนี้
เวลาไทย: {thai_now()}

18K: {find_price("18K")}
14K: {find_price("14K")}
9K: {find_price("9K")}
"""

    except Exception as e:
        return f"ดึงราคาทองไม่สำเร็จ: {e}"


def check_tasks_now():
    ws = get_sheet().worksheet("Tasks")
    rows = ws.get_all_records()
    now = thai_now_minute()

    alerts = []

    for row in rows:
        due = str(row.get("DueDateTime", ""))[:16]
        status = str(row.get("Status", "")).lower()

        if due == now and status != "done":
            alerts.append(row.get("Task"))

    return alerts


def check_followups_now():
    ws = get_sheet().worksheet("Customers")
    rows = ws.get_all_records()
    now = thai_now_minute()

    alerts = []

    for row in rows:
        follow_time = str(row.get("FollowUpDateTime", ""))[:16]

        if follow_time == now:
            alerts.append(
                f"{row.get('Name')} | {row.get('Interest')} | งบ {row.get('Budget')}"
            )

    return alerts


def today_tasks_text():
    ws = get_sheet().worksheet("Tasks")
    rows = ws.get_all_records()
    today = thai_today()

    tasks = [
        row for row in rows
        if str(row.get("DueDateTime", "")).startswith(today)
        and str(row.get("Status", "")).lower() != "done"
    ]

    if not tasks:
        return "✅ วันนี้ยังไม่มีงานค้าง"

    text = f"✅ งานวันนี้ ({today})\n"
    for i, row in enumerate(tasks, 1):
        text += f"{i}. {row.get('Task')} | {row.get('DueDateTime')}\n"

    return text


def follow_today_text():
    ws = get_sheet().worksheet("Customers")
    rows = ws.get_all_records()
    today = thai_today()

    followups = [
        row for row in rows
        if str(row.get("FollowUpDateTime", "")).startswith(today)
    ]

    if not followups:
        return "🔔 วันนี้ยังไม่มี follow-up ลูกค้า"

    text = f"🔔 Follow-up วันนี้ ({today})\n"
    for row in followups:
        text += f"- {row.get('Name')} | {row.get('Interest')} | งบ {row.get('Budget')} | {row.get('FollowUpDateTime')}\n"

    return text


if __name__ == "__main__":
    task_alerts = check_tasks_now()
    follow_alerts = check_followups_now()

    if task_alerts or follow_alerts:
        message = "🔔 แจ้งเตือนตามเวลา\n\n"

        if task_alerts:
            message += "งานที่ถึงเวลา:\n"
            for task in task_alerts:
                message += f"- {task}\n"

        if follow_alerts:
            message += "\nFollow-up ที่ถึงเวลา:\n"
            for follow in follow_alerts:
                message += f"- {follow}\n"

        push_line(message)

    else:
        # ถ้าอยากให้ส่งสรุปทุกครั้งที่ Cron รัน ให้ใช้ message นี้
        # แต่ถ้า Cron ตั้งทุก 5 นาที ไม่แนะนำให้ส่งทุกครั้ง
        print("No alerts at this minute")
