import requests
import json
import os
from datetime import datetime
import pytz
import hashlib

# Environment variables
ERP_USERNAME = os.getenv('ERP_USERNAME')
ERP_PASSWORD = os.getenv('ERP_PASSWORD')
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

IST = pytz.timezone('Asia/Kolkata')
ATTENDANCE_FILE = 'attendance_data.json'

class AttendanceTracker:
    def __init__(self):
        self.session = requests.Session()
        self.attendance_data = self.load_attendance_data()
    
    def load_attendance_data(self):
        """Load previous attendance data from file"""
        if os.path.exists(ATTENDANCE_FILE):
            with open(ATTENDANCE_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def save_attendance_data(self):
        """Save current attendance data to file"""
        with open(ATTENDANCE_FILE, 'w') as f:
            json.dump(self.attendance_data, f, indent=2)
    
    def login(self):
        """Login to ERP system"""
        try:
            login_url = 'https://erp.lbrce.ac.in/login'
            response = self.session.post(login_url, data={
                'username': ERP_USERNAME,
                'password': ERP_PASSWORD
            })
            return response.status_code == 200
        except Exception as e:
            print(f"Login failed: {e}")
            return False
    
    def fetch_attendance(self):
        """Fetch attendance from ERP"""
        try:
            attendance_url = 'https://erp.lbrce.ac.in/student/attendance'
            response = self.session.get(attendance_url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Failed to fetch attendance: {e}")
            return None
    
    def analyze_changes(self, current_data):
        """Analyze changes in attendance"""
        changes = {'new_absences': [], 'percentage_changes': []}
        
        if not self.attendance_data:
            # First run
            self.attendance_data = current_data
            return changes
        
        # Compare with previous data
        for subject, subject_data in current_data.items():
            if subject not in self.attendance_data:
                changes['new_absences'].append({
                    'subject': subject,
                    'status': 'New subject detected',
                    'current': subject_data
                })
            else:
                prev_data = self.attendance_data[subject]
                curr_percentage = subject_data.get('percentage', 0)
                prev_percentage = prev_data.get('percentage', 0)
                
                if curr_percentage < prev_percentage:
                    changes['percentage_changes'].append({
                        'subject': subject,
                        'prev': prev_percentage,
                        'current': curr_percentage,
                        'absent': subject_data.get('absent', 0)
                    })
        
        return changes
    
    def get_color_code(self, percentage):
        """Return color code based on attendance percentage"""
        if percentage >= 85:
            return '🟢'  # Green
        elif percentage >= 75:
            return '🟡'  # Yellow
        else:
            return '🔴'  # Red
    
    def send_telegram_notification(self, message):
        """Send notification via Telegram"""
        try:
            telegram_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
            payload = {
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(telegram_url, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Telegram notification: {e}")
            return False
    
    def run(self):
        """Main execution function"""
        print(f"[{datetime.now(IST)}] Starting attendance check...")
        
        if not self.login():
            self.send_telegram_notification("❌ ERP Login failed!")
            return
        
        current_data = self.fetch_attendance()
        if not current_data:
            self.send_telegram_notification("❌ Failed to fetch attendance data!")
            return
        
        changes = self.analyze_changes(current_data)
        self.attendance_data = current_data
        self.save_attendance_data()
        
        # Build notification message
        message = f"📊 <b>Attendance Update</b>\n"
        message += f"Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
        
        # Add color-coded attendance
        message += "<b>Current Attendance:</b>\n"
        for subject, data in current_data.items():
            color = self.get_color_code(data.get('percentage', 0))
            message += f"{color} {subject}: {data.get('percentage', 0)}% ({data.get('absent', 0)} absent)\n"
        
        # Add changes if any
        if changes['percentage_changes']:
            message += "\n<b>⚠️ Attendance Decreased:</b>\n"
            for change in changes['percentage_changes']:
                message += f"• {change['subject']}: {change['prev']}% → {change['current']}%\n"
        
        if changes['new_absences']:
            message += "\n<b>📌 New Absences Detected:</b>\n"
            for absence in changes['new_absences']:
                message += f"• {absence['subject']}\n"
        
        self.send_telegram_notification(message)
        print(f"[{datetime.now(IST)}] Attendance check completed!")

if __name__ == "__main__":
    tracker = AttendanceTracker()
    tracker.run()
