import os
import telebot
import requests
from bs4 import BeautifulSoup
import urllib3

# Disable SSL warnings for the university site
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
# Northflank will provide this via Environment Variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Error: BOT_TOKEN environment variable not set!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

COLLEGE_MAP = {
    "أسنان": "3", "طب بشري": "1", "صيدلة": "4", "تمريض": "5",
    "مدنية": "11", "عمارة": "10", "ميكانيك": "21", "كهرباء": "21",
    "حاسوب": "18", "اقتصاد": "7", "آداب": "6", "علوم": "13",
    "تربية": "8", "زراعة": "12", "بيطري": "2"
}

BASE_URL = 'http://app.hama-univ.edu.sy/StdMark/'
POST_URL = 'http://app.hama-univ.edu.sy/StdMark/Home/Result'

def get_student_results(college_id, university_id):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        # Step A: Get Token
        response = session.get(BASE_URL, verify=False, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        token_tag = soup.find('input', {'name': '__RequestVerificationToken'})
        
        if not token_tag:
            return "❌ تعذر الاتصال بموقع الجامعة (Token Error)."
            
        token = token_tag['value']
        
        # Step B: Post Data
        payload = {
            '__RequestVerificationToken': token,
            'UniversityId': university_id,
            'CollegeId': college_id
        }
        res_page = session.post(POST_URL, data=payload, verify=False, timeout=30)
        res_soup = BeautifulSoup(res_page.text, 'html.parser')

        # 1. Extract Student Info
        name_span = res_soup.find('span', string="الاسم")
        if name_span:
            full_name = name_span.find_next('span', class_='bottom').text.strip()
            college_name = res_soup.find('span', string="الكلية").find_next('span', class_='bottom').text.strip()
            final_report = f"👤 **الطالب:** {full_name}\n🏛 **الكلية:** {college_name}\n"
            final_report += "—" * 15 + "\n"
        else:
            return "❌ لم يتم العثور على بيانات. تأكد من الرقم الجامعي والكلية."

        # 2. Extract Year Panels
        panels = res_soup.find_all('div', class_='panel-info')
        if not panels:
            return final_report + "\nلا توجد علامات مسجلة حالياً."

        for panel in panels:
            year_title = panel.find('h3', class_='panel-title').get_text(strip=True)
            final_report += f"\n📌 **{year_title}**\n"
            
            rows = panel.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    subject = cols[0].get_text(strip=True)
                    grade = cols[2].get_text(strip=True).replace('.00', '')
                    status = cols[3].get_text(strip=True)
                    
                    icon = "✅" if "ناجح" in status else "❌"
                    final_report += f"{icon} {subject}: **{grade}**\n"
            
        return final_report

    except Exception as e:
        return f"⚠️ حدث خطأ أثناء جلب البيانات: {str(e)}"

# --- Bot Handlers ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(m):
    bot.reply_to(m, "أهلاً بك في بوت نتائج جامعة حماة 🎓\n\nأرسل الكلية ثم الرقم الجامعي في سطرين.\nمثال:\nأسنان\n922091981")

@bot.message_handler(func=lambda m: True)
def handle_msg(m):
    lines = m.text.strip().split('\n')
    if len(lines) < 2:
        bot.reply_to(m, "⚠️ يرجى إرسال الكلية في السطر الأول والرقم الجامعي في السطر الثاني.")
        return
    
    college_input = lines[0].strip()
    student_id = lines[1].strip()
    
    cid = next((v for k, v in COLLEGE_MAP.items() if k in college_input), None)
    if not cid:
        bot.reply_to(m, "❌ الكلية غير مدعومة حالياً. تأكد من كتابة اسم الكلية بشكل صحيح (مثلاً: أسنان، اقتصاد).")
        return

    # Let user know we are working on it
    bot.send_chat_action(m.chat.id, 'typing')
    wait_msg = bot.reply_to(m, "⏳ جاري الاتصال بموقع الجامعة... يرجى الانتظار.")
    
    report = get_student_results(cid, student_id)
    
    # Clean up the wait message and send results
    bot.delete_message(m.chat.id, wait_msg.message_id)
    
    if len(report) > 4000:
        for x in range(0, len(report), 4000):
            bot.send_message(m.chat.id, report[x:x+4000], parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, report, parse_mode="Markdown")

print("Bot is starting...")
bot.infinity_polling()
