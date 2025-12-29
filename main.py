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

USERNAME = os.getenv("ERP_USERNAME")
PASSWORD = os.getenv("ERP_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")

STORED_ATTENDANCE_FILE = "stored_attendance.json"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--remote-debugging-port=9222")
    
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)

def parse_attendance_table(html):
    soup = BeautifulSoup(html, 'html.parser')
    attendance_data = []
    overall_percentage = "0%"
    
    overall_label = soup.find(string="Overall(%) :")
    if overall_label:
        overall_elem = overall_label.find_next()
        if overall_elem:
            overall_percentage = overall_elem.get_text(strip=True)
    
    tables = soup.find_all('table')
    if tables:
        table = tables[0]
        rows = table.find_all('tr')
        
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 5:
                try:
                    sno = cols[0].get_text(strip=True)
                    subject = cols[1].get_text(strip=True)
                    held_text = cols[2].get_text(strip=True)
                    present_text = cols[3].get_text(strip=True)
                    percentage = cols[4].get_text(strip=True)
                    
                    if not subject or subject.lower() == 'month':
                        continue
                    
                    held = int(held_text) if held_text.isdigit() else 0
                    present = int(present_text) if present_text.isdigit() else 0
                    
                    attendance_data.append({
                        'sno': sno,
                        'subject': subject,
                        'held': held,
                        'present': present,
                        'percentage': percentage
                    })
                except:
                    continue
    
    return attendance_data, overall_percentage

def get_attendance_icon(percentage_str):
    try:
        num = float(percentage_str.replace('%', '').strip())
        if num >= 90: return "🟢"
        elif num >= 75: return "🟡"
        else: return "🔴"
    except:
        return "⚪"

def save_to_github(attendance_list, overall_percent):
    data = {
        'subjects': attendance_list,
        'overall_percentage': overall_percent,
        'timestamp': datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        
        try:
            content = repo.get_contents(STORED_ATTENDANCE_FILE)
            repo.update_file(
                path=content.path,
                message=f"Update attendance {datetime.now().isoformat()}",
                content=json.dumps(data, indent=2),
                sha=content.sha
            )
        except:
            repo.create_file(
                path=STORED_ATTENDANCE_FILE,
                message=f"Initial attendance {datetime.now().isoformat()}",
                content=json.dumps(data, indent=2)
            )
        print("✅ Saved to GitHub")
        return True
    except Exception as e:
        print(f"❌ GitHub save failed: {e}")
        with open(STORED_ATTENDANCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return False

def load_from_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        content = repo.get_contents(STORED_ATTENDANCE_FILE)
        data = json.loads(content.decoded_content.decode())
        return data.get('subjects', [])
    except:
        print("ℹ️ No previous attendance found")
        return None

def compare_attendance(current, stored):
    absences = []
    if not stored: return absences
    
    for curr_subject in current:
        subject_name = curr_subject['subject']
        stored_subject = next((s for s in stored if s.get('subject') == subject_name), None)
        
        if stored_subject:
            stored_held = stored_subject.get('held', 0)
            stored_present = stored_subject.get('present', 0)
            curr_held = curr_subject['held']
            curr_present = curr_subject['present']
            
            if curr_present < stored_present:
                absences.append({
                    'subject': subject_name,
                    'before_held': stored_held, 'before_present': stored_present,
                    'now_held': curr_held, 'now_present': curr_present,
                    'classes_missed': stored_present - curr_present,
                    'type': 'corrected_absent'
                })
            elif curr_held > stored_held and curr_present == stored_present:
                absences.append({
                    'subject': subject_name,
                    'before_held': stored_held, 'before_present': stored_present,
                    'now_held': curr_held, 'now_present': curr_present,
                    'classes_missed': curr_held - stored_held,
                    'type': 'missed_class'
                })
    return absences

def main():
    print("🚀 LBRCE ATTENDANCE BOT STARTED")
    driver = setup_driver()
    
    try:
        print("🔐 Logging in...")
        driver.get("https://erp.lbrce.ac.in/Login/")
        time.sleep(3)
        
        driver.find_element(By.NAME, "txtusername").send_keys(USERNAME)
        driver.find_element(By.NAME, "txtpassword").send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, 'button.btn.blue.pull-right[onclick*="login()"]').click()
        time.sleep(6)
        
        print("📂 Fetching attendance...")
        driver.get("https://erp.lbrce.ac.in/Discipline/StudentHistory.aspx")
        time.sleep(5)
        driver.find_element(By.NAME, "ctl00$ContentPlaceHolder1$btnAtt").click()
        time.sleep(6)
        
        html = driver.page_source
        current_attendance, overall_percentage = parse_attendance_table(html)
        print(f"✅ Found {len(current_attendance)} subjects | Overall: {overall_percentage}")
        
        stored_attendance = load_from_github()
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        message = f"📊 *ATTENDANCE REPORT*\n🕐 {now}\n👤 Roll: `{USERNAME}`\n📈 Overall: *{overall_percentage}*\n{'='*50}\n\n"
        message += "📋 *SUBJECT-WISE:*\n\n"
        
        for subject in current_attendance:
            icon = get_attendance_icon(subject['percentage'])
            message += f"{icon} *{subject['subject']}*\n  `{subject['present']}/{subject['held']}` | {subject['percentage']}\n\n"
        
        message += f"{'='*50}\n"
        
        if stored_attendance:
            absences = compare_attendance(current_attendance, stored_attendance)
            if absences:
                message += "🚨 *ABSENCES DETECTED:*\n\n"
                for absence in absences:
                    emoji = "🔴" if absence['type'] == 'corrected_absent' else "⚠️"
                    message += f"{emoji} *{absence['subject']}*\n"
                    message += f"   Before: `{absence['before_present']}/{absence['before_held']}`\n"
                    message += f"   Now: `{absence['now_present']}/{absence['now_held']}`\n"
                    message += f"   *MISSED: {absence['classes_missed']} class(es)*\n\n"
            else:
                message += "✅ *NO NEW ABSENCES* - All good!\n"
        else:
            message += "ℹ️ *FIRST RUN* - Baseline saved ✅\n"
        
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
            'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'
        }).raise_for_status()
        print("📱 Telegram sent!")
        
        save_to_github(current_attendance, overall_percentage)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        error_msg = f"❌ *Bot Error*\n`{str(e)[:1000]}`"
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
                'chat_id': CHAT_ID, 'text': error_msg, 'parse_mode': 'Markdown'
            })
        except:
            pass
    finally:
        driver.quit()
        print("🎉 COMPLETED!")

if __name__ == "__main__":
    main()
