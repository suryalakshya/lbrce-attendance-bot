from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import os
import time
import requests
import json
from datetime import datetime
from github import Github

# ================== ENV VARIABLES ==================
USERNAME = os.getenv("ERP_USERNAME")
PASSWORD = os.getenv("ERP_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")

STORED_ATTENDANCE_FILE = "stored_attendance.json"

# ================== SELENIUM SETUP ==================
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)

# ================== PARSE ATTENDANCE ==================
def parse_attendance_table(html):
    soup = BeautifulSoup(html, "html.parser")
    attendance = []
    overall = "0%"

    label = soup.find(string="Overall(%) :")
    if label:
        overall = label.find_next().get_text(strip=True)

    table = soup.find("table")
    if not table:
        return attendance, overall

    rows = table.find_all("tr")[1:]
    for r in rows:
        cols = r.find_all("td")
        if len(cols) < 5:
            continue

        subject = cols[1].get_text(strip=True)
        if not subject or subject.lower() == "month":
            continue

        held = int(cols[2].get_text(strip=True) or 0)
        present = int(cols[3].get_text(strip=True) or 0)
        percent = cols[4].get_text(strip=True)

        attendance.append({
            "subject": subject,
            "held": held,
            "present": present,
            "percentage": percent
        })

    return attendance, overall

# ================== ICON ==================
def icon(p):
    try:
        p = float(p.replace("%", ""))
        if p >= 90: return "🟢"
        if p >= 75: return "🟡"
        return "🔴"
    except:
        return "⚪"

# ================== GITHUB STORAGE ==================
def save_to_github(subjects, overall):
    data = {
        "subjects": subjects,
        "overall_percentage": overall,
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        try:
            content = repo.get_contents(STORED_ATTENDANCE_FILE)
            repo.update_file(
                content.path,
                f"Update attendance {datetime.now()}",
                json.dumps(data, indent=2),
                content.sha
            )
        except:
            repo.create_file(
                STORED_ATTENDANCE_FILE,
                "Initial attendance",
                json.dumps(data, indent=2)
            )
    except:
        with open(STORED_ATTENDANCE_FILE, "w") as f:
            json.dump(data, f, indent=2)

def load_from_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        content = repo.get_contents(STORED_ATTENDANCE_FILE)
        return json.loads(content.decoded_content.decode()).get("subjects", [])
    except:
        return None

# ================== COMPARISON (NEW LOGIC) ==================
def compare_attendance(current, stored):
    updates = []
    if not stored:
        return updates

    for curr in current:
        subject = curr["subject"]
        old = next((s for s in stored if s["subject"] == subject), None)
        if not old:
            continue

        old_held, old_pres = old["held"], old["present"]
        new_held, new_pres = curr["held"], curr["present"]

        # New class added
        if new_held > old_held:
            added = new_held - old_held
            attended = new_pres - old_pres

            if attended > 0:
                updates.append({
                    "type": "present",
                    "subject": subject,
                    "added": added,
                    "attended": attended
                })
            else:
                updates.append({
                    "type": "absent",
                    "subject": subject,
                    "added": added
                })

        # ERP correction
        elif new_pres < old_pres:
            updates.append({
                "type": "corrected",
                "subject": subject,
                "before": f"{old_pres}/{old_held}",
                "now": f"{new_pres}/{new_held}"
            })

    return updates

# ================== MAIN ==================
def main():
    driver = setup_driver()
    try:
        driver.get("https://erp.lbrce.ac.in/Login/")
        time.sleep(3)

        driver.find_element(By.NAME, "txtusername").send_keys(USERNAME)
        driver.find_element(By.NAME, "txtpassword").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[onclick*='login']").click()
        time.sleep(6)

        driver.get("https://erp.lbrce.ac.in/Discipline/StudentHistory.aspx")
        time.sleep(4)
        driver.find_element(By.NAME, "ctl00$ContentPlaceHolder1$btnAtt").click()
        time.sleep(5)

        current, overall = parse_attendance_table(driver.page_source)
        stored = load_from_github()

        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg = f"📊 *ATTENDANCE UPDATE*\n🕒 {now}\n📈 Overall: *{overall}*\n\n"

        for s in current:
            msg += f"{icon(s['percentage'])} *{s['subject']}* `{s['present']}/{s['held']}` {s['percentage']}\n"

        msg += "\n====================\n\n"

        if stored:
            updates = compare_attendance(current, stored)
            if updates:
                msg += "🆕 *TODAY'S CLASS UPDATES*\n\n"
                for u in updates:
                    if u["type"] == "present":
                        msg += f"🟢 *{u['subject']}*\n➕ New: {u['added']} | ✅ Attended\n\n"
                    elif u["type"] == "absent":
                        msg += f"🔴 *{u['subject']}*\n➕ New: {u['added']} | ❌ Absent\n\n"
                    else:
                        msg += f"⚠️ *{u['subject']}*\nERP correction\n{u['before']} → {u['now']}\n\n"
            else:
                msg += "➖ No new classes\n"
        else:
            msg += "ℹ️ First run — baseline saved\n"

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        )

        save_to_github(current, overall)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
