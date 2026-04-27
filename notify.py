import os
import json
import re
import html as html_lib
from datetime import datetime, timedelta
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
    return datetime.now(ZoneInfo("Asia/Bangkok"))


def thai_now_text():
    return thai_now().strftime("%Y-%m-%d %H:%M:%S")


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


def parse_datetime(value):
    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value[:19], fmt)
            return dt.replace(tzinfo=ZoneInfo("Asia/Bangkok"))
        except:
            pass

    return None


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
เวลาไทย: {thai_now_text()}

18K: {find_price("18K")}
14K: {find_price("14K")}
9K: {find_price("9K")}
"""

    except Exception as e:
        return f"ดึงราคาทองไม่สำเร็จ: {e}"


def check_tasks():
    ws = get_sheet().worksheet("Tasks")
    rows = ws.get_all_records()

    now = thai_now()
    alerts = []

    for row in rows:
        task_name = (
            row.get("Task")
            or row.get("งาน")
            or row.get("TaskName")
            or row.get("รายละเอียด")
            or ""
        )

        due_raw = (
            row.get("DueDateTime")
            or row.get("Due Date Time")
            or row.get("Due")
            or row.get("เวลา")
            or ""
        )

        status = str(
            row.get("Status")
            or row.get("สถานะ")
            or ""
        ).lower()

        if not task_name or not due_raw:
            continue

        if status == "done":
            continue

        due_time = parse_datetime(due_raw)

        if not due_time:
            continue

        diff_min = (due_time - now).total_seconds() / 60

        # แจ้งล่วงหน้า 10 นาที
        if 5 < diff_min <= 10:
            alerts.append(f"⏰ อีกประมาณ 10 นาที: {task_name} | {due_raw}")

        # แจ้งตรงเวลา ภายในช่วง 0-5 นาทีหลังถึงเวลา
        elif -5 <= diff_min <= 0:
            alerts.append(f"🚨 ถึงเวลา: {task_name} | {due_raw}")

    return alerts


def check_followups():
    ws = get_sheet().worksheet("Customers")
    rows = ws.get_all_records()

    now = thai_now()
    alerts = []

    for row in rows:
        name = row.get("Name") or row.get("ชื่อ") or ""
        interest = row.get("Interest") or row.get("สนใจ") or ""
        budget = row.get("Budget") or row.get("งบ") or "-"
        follow_raw = (
            row.get("FollowUpDateTime")
            or row.get("Follow Up Date Time")
            or row.get("FollowUp")
            or row.get("เวลา")
            or ""
        )

        status = str(
            row.get("Status")
            or row.get("สถานะ")
            or ""
        ).lower()

        if not follow_raw:
            continue

        if status == "done":
            continue

        follow_time = parse_datetime(follow_raw)

        if not follow_time:
            continue

        diff_min = (follow_time - now).total_seconds() / 60

        label = name if name else "ไม่ระบุชื่อ"

        if 5 < diff_min <= 10:
            alerts.append(
                f"⏰ อีกประมาณ 10 นาที: {label} | {interest} | งบ {budget} | {follow_raw}"
            )

        elif -5 <= diff_min <= 0:
            alerts.append(
                f"🚨 ถึงเวลา follow-up: {label} | {interest} | งบ {budget} | {follow_raw}"
            )

    return alerts


if __name__ == "__main__":
    task_alerts = check_tasks()
    follow_alerts = check_followups()

    # ไม่มีอะไรต้องเตือน = ไม่ส่ง LINE
    if not task_alerts and not follow_alerts:
        print("No alerts at this time")
        raise SystemExit

    message = f"🔔 แจ้งเตือน VIVIAN\nเวลาไทย: {thai_now_text()}\n\n"

    if task_alerts:
        message += "📅 งาน:\n"
        message += "\n".join(task_alerts)
        message += "\n\n"

    if follow_alerts:
        message += "👤 Follow-up ลูกค้า:\n"
        message += "\n".join(follow_alerts)
        message += "\n"

    push_line(message)
