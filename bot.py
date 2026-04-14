import os
import threading
import urllib3
import requests
from flask import Flask
from bs4 import BeautifulSoup
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- 1. الإعدادات والاتصال ---
ADMIN_ID = int(os.getenv("ADMINID")) 
TOKEN = os.getenv('Token')
MONGO_URI = f"mongodb+srv://{os.getenv('Mongourl')}"
CHANNEL_ID = -int(os.getenv("ChannelID")) 

client = MongoClient(MONGO_URI)
db = client['AcademyBotDB']

# مجموعات البيانات
files_col = db['files_structure']
quiz_col = db['quiz_structure']

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Active! 🚀"

def get_data(col_type):
    col = files_col if col_type == 'library' else quiz_col
    doc = col.find_one({"_id": "tree_data"})
    return doc.get("content", {}) if doc else {}

def save_data(col_type, data):
    col = files_col if col_type == 'library' else quiz_col
    col.update_one({"_id": "tree_data"}, {"$set": {"content": data}}, upsert=True)

# --- 2. جلب العلامات (نظام الجلسة المتقدم) ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
def get_pharmacy_marks(std_id):
    try:
        session = requests.Session()
        base_url = "http://app.hama-univ.edu.sy/StdMark/Home/Result"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Referer': 'http://app.hama-univ.edu.sy/StdMark/',
            'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8'
        }
        
        # محاولة جلب التوكن
        res_get = session.get(base_url, headers=headers, timeout=20, verify=False)
        soup_get = BeautifulSoup(res_get.text, 'html.parser')
        token_input = soup_get.find('input', {'name': '__RequestVerificationToken'})
        
        if not token_input:
            res_get = session.get("http://app.hama-univ.edu.sy/StdMark/", headers=headers, timeout=20, verify=False)
            soup_get = BeautifulSoup(res_get.text, 'html.parser')
            token_input = soup_get.find('input', {'name': '__RequestVerificationToken'})

        if not token_input: return "⚠️ عذراً، موقع الجامعة يرفض الجلسة حالياً. حاول لاحقاً."
            
        token = token_input['value']
        payload = {'__RequestVerificationToken': token, 'UniversityId': std_id, 'CollegeId': "4"}
        
        # طلب النتيجة
        res_post = session.post(base_url, data=payload, headers=headers, timeout=25, verify=False)
        res_post.encoding = 'utf-8'
        soup = BeautifulSoup(res_post.text, 'html.parser')
        
        if not soup.find('span', class_='bottom'): return '❌ لم يتم العثور على نتائج. تأكد من الرقم الجامعي.'
            
        name = soup.find_all('span', class_='bottom')[0].text.strip()
        output = f"🎓 *الاسم:* *{name}*\n"
        for panel in soup.find_all('div', class_='panel-info'):
            header = panel.find('h3')
            if header: output += f"\n📅 *{header.text.strip()}*:\n"
            for row in panel.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    # --- Formatting Logic ---
                    sub_name = cols[0].text.strip()
                    grade = cols[2].text.strip()
                    status = cols[3].text.strip()
                    
                    emoji = "✅" if "ناجح" in status else "❌" if "راسب" in status else "⛔️"
                    # Format: {Emoji} {subject name:} {grade}
                    output += f"{emoji} {sub_name}: {grade}\n"
        return output
    except Exception as e: return f"⚠️ خطأ في الاتصال: {str(e)}"

# --- 3. الأزرار ---
def main_menu_keyboard():
    return ReplyKeyboardMarkup([['📊 بوابة العلامات'], ['📝 الاختبارات (Quiz)'], ['📚 مكتبة الملفات'], ['🤖 المساعد الذكي']], resize_keyboard=True)

def nav_btns(): return ["🔙 العودة للخلف", "🏠 القائمة الرئيسية"]

# --- 4. منطق الرسائل ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("مرحباً بك في بوت فارما أكاديميا المطور ⚕️", reply_markup=main_menu_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    ud = context.user_data
    
    if text == "🏠 القائمة الرئيسية":
        await start(update, context); return

    if text == "🔙 العودة للخلف":
        step = ud.get('step')
        if step == 'year': await start(update, context)
        elif step == 'sem': 
            ud['step'] = 'year'
            btns = [[y] for y in ["السنة الثانية", "السنة الثالثة", "السنة الرابعة", "السنة الخامسة"]] + [nav_btns()]
            await update.message.reply_text("اختر السنة:", reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
        elif step == 'mode':
            ud['step'] = 'sem'
            await update.message.reply_text("اختر الفصل:", reply_markup=ReplyKeyboardMarkup([["الفصل الأول"], ["الفصل الثاني"]] + [nav_btns()], resize_keyboard=True))
        elif step == 'subject':
            ud['step'] = 'mode'
            await update.message.reply_text("اختر النوع:", reply_markup=ReplyKeyboardMarkup([["نظري", "عملي"]] + [nav_btns()], resize_keyboard=True))
        elif step == 'list':
            ud['step'] = 'subject'
            data = get_data(ud['type'])
            subjects = list(data.get(ud['year'], {}).get(ud['sem'], {}).get(ud['mode'], {}).keys())
            btns = [[s] for s in subjects] + [nav_btns()]
            await update.message.reply_text("🔙 اختر المادة:", reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
        elif step == 'marks': await start(update, context)
        return

    # --- إدارة الأدمن ---
    if user_id == ADMIN_ID:
        if text.startswith("إضافة مادة:"):
            if ud.get('step') != 'subject':
                await update.message.reply_text("⚠️ يجب أن تكون داخل قسم (نظري أو عملي) أولاً.")
                return
            sub_name = text.replace("إضافة مادة:", "").strip()
            data = get_data(ud['type'])
            y, s, m = ud['year'], ud['sem'], ud['mode']
            if y not in data: data[y] = {}
            if s not in data[y]: data[y][s] = {}
            if m not in data[y][s]: data[y][s][m] = {}
            data[y][s][m][sub_name] = []
            save_data(ud['type'], data)
            await update.message.reply_text(f"✅ تم إضافة مادة: {sub_name}")
            return

        if text.startswith("حذف مادة:"):
            if ud.get('step') != 'subject':
                await update.message.reply_text("⚠️ ادخل إلى قسم (نظري أو عملي) أولاً لتتمكن من حذف مادة منه.")
                return
            sub_name = text.replace("حذف مادة:", "").strip()
            data = get_data(ud['type'])
            y, s, m = ud['year'], ud['sem'], ud['mode']
            if sub_name in data.get(y, {}).get(s, {}).get(m, {}):
                del data[y][s][m][sub_name]
                save_data(ud['type'], data)
                await update.message.reply_text(f"✅ تم حذف مادة {sub_name} بنجاح.")
            else:
                await update.message.reply_text(f"⚠️ المادة '{sub_name}' غير موجودة.")
            return

        if text.startswith("إضافة ملف:"):
            if ud.get('step') != 'list':
                await update.message.reply_text("⚠️ ادخل إلى المادة المطلوبة أولاً.")
                return
            try:
                parts = text.replace("إضافة ملف:", "").split("|")
                f_name, ids_part = parts[0].strip(), parts[1].strip().split()
                ids = [int(ids_part[0])] if len(ids_part) == 1 else list(range(int(ids_part[0]), int(ids_part[1]) + 1))
                data = get_data(ud['type'])
                data[ud['year']][ud['sem']][ud['mode']][ud['subject']].append({"name": f_name, "ids": ids})
                save_data(ud['type'], data)
                await update.message.reply_text(f"✅ تم إضافة '{f_name}' بنجاح.")
                return
            except: await update.message.reply_text("⚠️ التنسيق: إضافة ملف: الاسم | 10 20")

    # --- التنقل ---
    if text in ['📚 مكتبة الملفات', '📝 الاختبارات (Quiz)']:
        ud.update({'type': 'library' if 'مكتبة' in text else 'quiz', 'step': 'year'})
        years = ["السنة الثانية", "السنة الثالثة", "السنة الرابعة", "السنة الخامسة"]
        await update.message.reply_text("اختر السنة:", reply_markup=ReplyKeyboardMarkup([[y] for y in years] + [nav_btns()], resize_keyboard=True))

    elif ud.get('step') == 'year' and "السنة" in text:
        ud.update({'step': 'sem', 'year': text})
        await update.message.reply_text(f"📁 {text}:", reply_markup=ReplyKeyboardMarkup([["الفصل الأول"], ["الفصل الثاني"]] + [nav_btns()], resize_keyboard=True))

    elif ud.get('step') == 'sem' and "الفصل" in text:
        ud.update({'step': 'mode', 'sem': text})
        await update.message.reply_text("اختر النوع:", reply_markup=ReplyKeyboardMarkup([["نظري", "عملي"]] + [nav_btns()], resize_keyboard=True))

    elif ud.get('step') == 'mode' and text in ["نظري", "عملي"]:
        ud.update({'step': 'subject', 'mode': text})
        data = get_data(ud['type'])
        subjects = list(data.get(ud['year'], {}).get(ud['sem'], {}).get(text, {}).keys())
        btns = [[s] for s in subjects] + [nav_btns()]
        msg = "اختر المادة:" if subjects else "📂 لا يوجد مواد."
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))

    elif ud.get('step') == 'subject' and text not in nav_btns():
        ud.update({'step': 'list', 'subject': text})
        data = get_data(ud['type'])
        items = data.get(ud['year'], {}).get(ud['sem'], {}).get(ud['mode'], {}).get(text, [])
        if not items:
            await update.message.reply_text(f"📂 مادة {text} فارغة.", reply_markup=ReplyKeyboardMarkup([nav_btns()], resize_keyboard=True))
        else:
            kb = []
            for idx, item in enumerate(items):
                row = [InlineKeyboardButton(f"{item['name']} ({len(item['ids'])})", callback_data=f"get_{idx}")]
                if user_id == ADMIN_ID: row.append(InlineKeyboardButton("❌", callback_data=f"ask_{idx}"))
                kb.append(row)
            await update.message.reply_text(f"📑 محتويات {text}:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == '📊 بوابة العلامات':
        ud['step'] = 'marks'
        await update.message.reply_text("أرسل الرقم الجامعي:", reply_markup=ReplyKeyboardMarkup([nav_btns()], resize_keyboard=True))
    
    elif ud.get('step') == 'marks' and text.isdigit():
        loading = await update.message.reply_text("⏳ جارٍ سحب النتيجة...")
        res = get_pharmacy_marks(text)
        await loading.edit_text(res, parse_mode='Markdown')

# --- 5. أزرار Callback ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    ud = context.user_data
    data_parts = query.data.split('_')
    action, idx = data_parts[0], int(data_parts[1])
    await query.answer()

    db_data = get_data(ud.get('type'))
    current_list = db_data[ud['year']][ud['sem']][ud['mode']][ud['subject']]
    
    if action == "get":
        for f_id in current_list[idx]['ids']:
            try:
                if ud.get('type') == 'quiz':
                    await context.bot.forward_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=f_id)
                else:
                    await context.bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=f_id)
            except: pass
    elif action == "ask" and user_id == ADMIN_ID:
        kb = [[InlineKeyboardButton("🗑 حذف الدفعة", callback_data=f"delall_{idx}")]]
        if len(current_list[idx]['ids']) > 1:
            for f_id in current_list[idx]['ids']:
                kb.append([InlineKeyboardButton(f"❌ حذف ID: {f_id}", callback_data=f"onespec_{idx}_{f_id}")])
        kb.append([InlineKeyboardButton("🔙 تراجع", callback_data="cancel_0")])
        await query.edit_message_text("خيارات الحذف:", reply_markup=InlineKeyboardMarkup(kb))
    elif action == "delall":
        current_list.pop(idx)
        save_data(ud['type'], db_data)
        await query.edit_message_text("✅ تم الحذف.")
    elif action == "onespec":
        f_id_to_del = int(data_parts[2])
        current_list[idx]['ids'] = [f for f in current_list[idx]['ids'] if f != f_id_to_del]
        if not current_list[idx]['ids']: current_list.pop(idx)
        save_data(ud['type'], db_data)
        await query.edit_message_text(f"✅ تم حذف الملف {f_id_to_del}.")
    elif action == "cancel": await query.edit_message_text("🔙 تم الإلغاء.")

if __name__ == '__main__':
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=7860), daemon=True).start()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is Polling...")
    application.run_polling()