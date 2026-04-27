import os

import re

import io

import asyncio

import urllib3

import requests

from bs4 import BeautifulSoup

from pymongo import MongoClient

from google import genai

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, WebAppInfo

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- 1. الإعدادات والاتصال ---

ADMIN_ID = int(os.getenv("ADMINID"))

TOKEN = os.getenv('TOKEN')

MONGO_URI = f"mongodb+srv:/{os.getenv('MONGOURL')}"

CHANNEL_ID = -int(os.getenv("CHANNELID"))

GEMINI_API_KEY = os.getenv("GEMINITOKEN")

# نماذج Gemini (الأسرع أولاً)

GEMINI_MODELS = [

    "gemini-2.5-flash",

    "gemini-2.0-flash",

]

client_ai = None

if GEMINI_API_KEY:

    client_ai = genai.Client(api_key=GEMINI_API_KEY)

client = MongoClient(MONGO_URI)

db = client["AcademyBotDB"]

# مجموعات البيانات

files_col = db["files_structure"]

quiz_col = db["quiz_structure"]

users_col = db["users_data"]

def get_data(col_type):

    col = files_col if col_type == "library" else quiz_col

    doc = col.find_one({"_id": "tree_data"})

    return doc.get("content", {}) if doc else {}

def save_data(col_type, data):

    col = files_col if col_type == "library" else quiz_col

    col.update_one({"_id": "tree_data"}, {"$set": {"content": data}}, upsert=True)

# --- قوائم مساعدة ---

YEARS = [

    ("السنة الثانية", "السنة الثانية"),

    ("السنة الثالثة", "السنة الثالثة"),

    ("السنة الرابعة", "السنة الرابعة"),

    ("السنة الخامسة", "السنة الخامسة"),

]

SEMS = [

    ("الفصل الأول", "الفصل الأول"),

    ("الفصل الثاني", "الفصل الثاني"),

]

MODES = [

    ("نظري", "نظري"),

    ("عملي", "عملي"),

]

def main_menu_keyboard(user_id=None):

    kb = [

        [KeyboardButton("📊 بوابة العلامات")],

        [KeyboardButton("📝 الاختبارات (Quiz)")],

        [KeyboardButton("📚 مكتبة الملفات")],

        [KeyboardButton("🤖 المساعد الذكي")],

        [KeyboardButton("المختبر الافتراضي 🧪", web_app=WebAppInfo("https://abdullah12340808-blip.github.io/Virtual_Lab/"))],

    ]

    if user_id == ADMIN_ID:

        kb.append([KeyboardButton("أدمن 🛠")])

    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def nav_btns():

    return ["🔙 العودة للخلف", "🏠 القائمة الرئيسية"]

def admin_inline_menu():

    return InlineKeyboardMarkup([

        [InlineKeyboardButton("إعلان 📢", callback_data="admin:broadcast")],

        [InlineKeyboardButton("إحصائيات 📊", callback_data="admin:stats")],

        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")],

    ])

def admin_stats_menu():

    return InlineKeyboardMarkup([

        [InlineKeyboardButton("📄 استخراج قائمة المستخدمين", callback_data="admin:getusernames")],

        [InlineKeyboardButton("🔙 رجوع", callback_data="admin:back")],

        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")],

    ])

def section_nav_keyboard(section: str, back_target: str):

    return InlineKeyboardMarkup([

        [

            InlineKeyboardButton("🔙 رجوع", callback_data=f"nav:{section}:back:{back_target}"),

            InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"),

        ]

    ])

def year_keyboard(section: str):

    rows = [[InlineKeyboardButton(label, callback_data=f"nav:{section}:year:{code}")] for code, label in YEARS]

    rows.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")])

    return InlineKeyboardMarkup(rows)

def sem_keyboard(section: str):

    rows = [[InlineKeyboardButton(label, callback_data=f"nav:{section}:sem:{code}")] for code, label in SEMS]

    rows.append([

        InlineKeyboardButton("🔙 رجوع", callback_data=f"nav:{section}:back:year"),

        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"),

    ])

    return InlineKeyboardMarkup(rows)

def mode_keyboard(section: str):

    rows = [[InlineKeyboardButton(label, callback_data=f"nav:{section}:mode:{code}")] for code, label in MODES]

    rows.append([

        InlineKeyboardButton("🔙 رجوع", callback_data=f"nav:{section}:back:sem"),

        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"),

    ])

    return InlineKeyboardMarkup(rows)

def subject_keyboard(section: str, subjects):

    rows = []

    for idx, sub in enumerate(subjects):

        rows.append([InlineKeyboardButton(sub, callback_data=f"nav:{section}:subject:{idx}")])

    rows.append([

        InlineKeyboardButton("🔙 رجوع", callback_data=f"nav:{section}:back:mode"),

        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"),

    ])

    return InlineKeyboardMarkup(rows)

def lecture_keyboard(section: str, lectures):

    rows = []

    for idx, lec in enumerate(lectures):

        rows.append([InlineKeyboardButton(lec, callback_data=f"nav:{section}:lecture:{idx}")])

    rows.append([

        InlineKeyboardButton("🔙 رجوع", callback_data=f"nav:{section}:back:subject"),

        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"),

    ])

    return InlineKeyboardMarkup(rows)

def library_items_keyboard(items, is_admin: bool):

    rows = []

    for idx, item in enumerate(items):

        text = f"{item.get('name', 'بدون اسم')} ({len(item.get('ids', []))})"

        if is_admin:

            rows.append([

                InlineKeyboardButton(text, callback_data=f"lib:get:{idx}"),

                InlineKeyboardButton("🗑 حذف", callback_data=f"lib:del:{idx}"),

            ])

        else:

            rows.append([InlineKeyboardButton(text, callback_data=f"lib:get:{idx}")])

    rows.append([

        InlineKeyboardButton("🔙 رجوع", callback_data="nav:library:back:subject"),

        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"),

    ])

    return InlineKeyboardMarkup(rows)

def clear_section_state(ud):

    for key in [

        "section", "step", "year", "sem", "mode", "subject", "lecture",

        "subjects_cache", "lectures_cache", "items_cache"

    ]:

        ud.pop(key, None)

async def show_main_menu(chat_id, context: ContextTypes.DEFAULT_TYPE, user_id: int,

                         text="مرحباً بك في بوت فارما أكاديميا المطور ⚕️"):

    context.user_data.clear()

    await context.bot.send_message(

        chat_id=chat_id,

        text=text,

        reply_markup=main_menu_keyboard(user_id)

    )

async def send_or_edit_main_menu(query, context, user_id, text="مرحباً بك في بوت فارما أكاديميا المطور ⚕️"):

    clear_section_state(context.user_data)

    try:

        await query.edit_message_text("✅ تم الرجوع إلى القائمة الرئيسية.")

    except:

        pass

    await context.bot.send_message(

        chat_id=query.message.chat.id,

        text=text,

        reply_markup=main_menu_keyboard(user_id)

    )

def get_selected_label(code, pairs):

    for c, label in pairs:

        if c == code:

            return label

    return None

# --- 2. جلب العلامات ---

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_pharmacy_marks(std_id):

    try:

        session = requests.Session()

        base_url = "http://app.hama-univ.edu.sy/StdMark/Home/Result"

        headers = {

            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",

            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",

            "Referer": "http://app.hama-univ.edu.sy/StdMark/",

            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",

        }

        res_get = session.get(base_url, headers=headers, timeout=20, verify=False)

        soup_get = BeautifulSoup(res_get.text, "html.parser")

        token_input = soup_get.find("input", {"name": "__RequestVerificationToken"})

        if not token_input:

            res_get = session.get("http://app.hama-univ.edu.sy/StdMark/", headers=headers, timeout=20, verify=False)

            soup_get = BeautifulSoup(res_get.text, "html.parser")

            token_input = soup_get.find("input", {"name": "__RequestVerificationToken"})

        if not token_input:

            return "⚠️ عذراً، موقع الجامعة يرفض الجلسة حالياً. حاول لاحقاً."

        token = token_input["value"]

        payload = {"__RequestVerificationToken": token, "UniversityId": std_id, "CollegeId": "4"}

        res_post = session.post(base_url, data=payload, headers=headers, timeout=25, verify=False)

        res_post.encoding = "utf-8"

        soup = BeautifulSoup(res_post.text, "html.parser")

        if not soup.find("span", class_="bottom"):

            return "❌ لم يتم العثور على نتائج. تأكد من الرقم الجامعي."

        name = soup.find_all("span", class_="bottom")[0].text.strip()

        output = f"🎓 *الاسم:* *{name}*\n"

        for panel in soup.find_all("div", class_="panel-info"):

            header = panel.find("h3")

            if header:

                output += f"\n📅 *{header.text.strip()}*:\n"

            for row in panel.find_all("tr")[1:]:

                cols = row.find_all("td")

                if len(cols) >= 3:

                    sub_name = cols[0].text.strip()

                    grade = cols[2].text.strip()

                    status = cols[3].text.strip()

                    emoji = "✅" if "ناجح" in status else "❌" if "راسب" in status else "⛔️"

                    output += f"{emoji} {sub_name}: {grade}\n"

        return output

    except Exception as e:

        return f"⚠️ خطأ في الاتصال: {str(e)}"

# --- 3. المساعد الذكي ---

async def ask_gemini_with_retry(prompt_content: str) -> str:

    if not client_ai:

        raise RuntimeError("Gemini client is not configured.")

    last_error = None

    for model_name in GEMINI_MODELS:

        for attempt in range(4):

            try:

                response = client_ai.models.generate_content(

                    model=model_name,

                    contents=prompt_content

                )

                if response and getattr(response, "text", None):

                    return response.text

                raise RuntimeError("Gemini returned an empty response.")

            except Exception as e:

                last_error = e

                err_text = str(e)

                if "503" in err_text or "UNAVAILABLE" in err_text:

                    if attempt < 3:

                        await asyncio.sleep(2 ** attempt)

                        continue

                    break

                break

    raise last_error if last_error else RuntimeError("Failed to get a response from Gemini.")

# --- 4. منطق الرسائل ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user

    users_col.update_one(

        {"_id": user.id},

        {"$set": {"username": user.username, "first_name": user.first_name}},

        upsert=True

    )

    context.user_data.clear()

    await update.message.reply_text(

        "مرحباً بك في بوت فارما أكاديميا المطور ⚕️",

        reply_markup=main_menu_keyboard(user.id)

    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    ud = context.user_data

    # --- إضافة الاختبارات عبر التصويت المباشر ---

    if update.message.poll:

        if user_id == ADMIN_ID:

            if ud.get("step") == "in_lecture" and ud.get("type") == "quiz":

                poll = update.message.poll

                if poll.type != "quiz":

                    await update.message.reply_text("⚠️ الرجاء تفعيل خيار 'وضع الاختبار' (Quiz Mode) عند إنشاء التصويت.")

                    return

                new_quiz = {

                    "question": poll.question,

                    "options": [opt.text for opt in poll.options],

                    "correct_idx": poll.correct_option_id,

                    "media_id": None,

                }

                data = get_data("quiz")

                data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]][ud["lecture"]].append(new_quiz)

                save_data("quiz", data)

                await update.message.reply_text("✅ تم حفظ الاختبار المباشر للمحاضرة بنجاح.")

            else:

                await update.message.reply_text("⚠️ يجب أن تكون داخل المحاضرة أولاً لإضافة اختبار بهذه الطريقة.")

        return

    text = update.message.text

    # --- الإذاعة ---

    if ud.get("step") == "broadcast" and user_id == ADMIN_ID:

        if text and text in nav_btns():

            ud["step"] = "admin_menu"

            await update.message.reply_text("⚙️ لوحة تحكم الإدارة:", reply_markup=admin_inline_menu())

            return

        all_users = users_col.find({}, {"_id": 1})

        success, failed = 0, 0

        msg = await update.message.reply_text("⏳ جاري الإرسال...")

        for u in all_users:

            try:

                await context.bot.copy_message(

                    chat_id=u["_id"],

                    from_chat_id=user_id,

                    message_id=update.message.message_id

                )

                success += 1

            except:

                failed += 1

        await msg.edit_text(f"✅ تم الإرسال بنجاح لـ {success}\n❌ فشل الإرسال لـ {failed} (قاموا بحظر البوت)")

        ud["step"] = "admin_menu"

        await update.message.reply_text("⚙️ لوحة تحكم الإدارة:", reply_markup=admin_inline_menu())

        return

    if not text:

        return

    if text == "🏠 القائمة الرئيسية":

        await start(update, context)

        return

    if text == "🔙 العودة للخلف":

        step = ud.get("step")

        if step in ["year", "ai_assistant", "admin_menu", "broadcast"]:

            await start(update, context)

        elif step == "sem":

            ud["step"] = "year"

            section = ud.get("section")

            if section:

                await update.message.reply_text("اختر السنة:", reply_markup=year_keyboard(section))

            else:

                await start(update, context)

        elif step == "mode":

            ud["step"] = "sem"

            section = ud.get("section")

            if section:

                await update.message.reply_text("اختر الفصل:", reply_markup=sem_keyboard(section))

            else:

                await start(update, context)

        elif step in ["subject", "list", "lecture_list", "in_lecture", "marks"]:

            await start(update, context)

        return

    # --- المساعد الذكي ---

    if text == "🤖 المساعد الذكي":

        if not GEMINI_API_KEY:

            await update.message.reply_text("⚠️ المساعد الذكي غير مفعل. الرجاء إضافة مفتاح GeminiToken للإعدادات.")

            return

        ud["step"] = "ai_assistant"

        await update.message.reply_text(

            "أهلاً بك في المساعد الذكي المدعوم بـ Gemini! 🤖✨\n"

            "اطرح أي سؤال وسأحاول مساعدتك (شرح مواد، تلخيص، إجابة على استفسارات...).\n\n"

            "للخروج من المساعد، اضغط على (🔙 العودة للخلف).",

            reply_markup=ReplyKeyboardMarkup([nav_btns()], resize_keyboard=True)

        )

        return

    elif ud.get("step") == "ai_assistant" and text not in nav_btns():

        loading = await update.message.reply_text("⏳ جاري التفكير...")

        try:

            prompt_content = (

                "أنت مساعد ذكي ولطيف لمساعدة طلاب صيدلة جامعة حماة.\n\n"

                f"سؤال الطالب: {text}"

            )

            reply_text = await ask_gemini_with_retry(prompt_content)

            if len(reply_text) > 4000:

                reply_text = reply_text[:4000] + "\n\n..."

            await loading.edit_text(reply_text)

        except Exception:

            await loading.edit_text("⚠️ المساعد الذكي مشغول الآن أو الخدمة متعبة قليلًا.\nجرّب مرة أخرى بعد لحظات.")

        return

    # --- إدارة الأدمن بالنصوص ---

    if user_id == ADMIN_ID:

        if text == "أدمن 🛠":

            ud["step"] = "admin_menu"

            await update.message.reply_text("⚙️ لوحة تحكم الإدارة:", reply_markup=admin_inline_menu())

            return

        if text.startswith("إضافة مادة:"):

            if ud.get("step") != "subject":

                await update.message.reply_text("⚠️ يجب أن تكون داخل قسم (نظري أو عملي) أولاً.")

                return

            sub_name = text.replace("إضافة مادة:", "").strip()

            data = get_data(ud["type"])

            y, s, m = ud["year"], ud["sem"], ud["mode"]

            if y not in data:

                data[y] = {}

            if s not in data[y]:

                data[y][s] = {}

            if m not in data[y][s]:

                data[y][s][m] = {}

            data[y][s][m][sub_name] = {} if ud["type"] == "quiz" else []

            save_data(ud["type"], data)

            await update.message.reply_text(f"✅ تم إضافة مادة: {sub_name}")

            return

        if text.startswith("حذف مادة:"):

            if ud.get("step") != "subject":

                await update.message.reply_text("⚠️ ادخل إلى قسم (نظري أو عملي) أولاً لتتمكن من حذف مادة منه.")

                return

            sub_name = text.replace("حذف مادة:", "").strip()

            data = get_data(ud["type"])

            y, s, m = ud["year"], ud["sem"], ud["mode"]

            if sub_name in data.get(y, {}).get(s, {}).get(m, {}):

                del data[y][s][m][sub_name]

                save_data(ud["type"], data)

                await update.message.reply_text(f"✅ تم حذف مادة {sub_name} بنجاح.")

            else:

                await update.message.reply_text(f"⚠️ المادة '{sub_name}' غير موجودة.")

            return

        if text.startswith("إضافة محاضرة:"):

            if ud.get("step") != "lecture_list" or ud.get("type") != "quiz":

                await update.message.reply_text("⚠️ يجب أن تكون داخل المادة في قسم الاختبارات أولاً.")

                return

            lec_name = text.replace("إضافة محاضرة:", "").strip()

            data = get_data("quiz")

            subj_dict = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(ud["subject"], {})

            if isinstance(subj_dict, list):

                subj_dict = {}

                data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]] = subj_dict

            if lec_name not in subj_dict:

                subj_dict[lec_name] = []

                save_data("quiz", data)

                await update.message.reply_text(f"✅ تم إضافة المحاضرة: {lec_name}")

            else:

                await update.message.reply_text("⚠️ المحاضرة موجودة مسبقاً.")

            return

        if text.startswith("حذف محاضرة:"):

            if ud.get("step") != "lecture_list" or ud.get("type") != "quiz":

                await update.message.reply_text("⚠️ يجب أن تكون داخل المادة في قسم الاختبارات أولاً.")

                return

            lec_name = text.replace("حذف محاضرة:", "").strip()

            data = get_data("quiz")

            subj_dict = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(ud["subject"], {})

            if lec_name in subj_dict:

                del subj_dict[lec_name]

                save_data("quiz", data)

                await update.message.reply_text(f"✅ تم حذف المحاضرة {lec_name} بنجاح.")

            else:

                await update.message.reply_text("⚠️ المحاضرة غير موجودة.")

            return

        if text.startswith("إضافة اختبار:"):

            if ud.get("step") != "in_lecture" or ud.get("type") != "quiz":

                await update.message.reply_text("⚠️ يجب أن تكون داخل المحاضرة أولاً لإضافة اختبار.")

                return

            pattern = r"إضافة اختبار:\s*\((.*?)\)\s*\((.*?)\)\s*(\d+)(?:\s*\|\s*(\d+))?"

            match = re.search(pattern, text)

            if not match:

                await update.message.reply_text(

                    "⚠️ التنسيق خاطئ. الرجاء استخدام:\n"

                    "إضافة اختبار:(نص السؤال) (جواب1، جواب2) رقم_الصحيح | ID_مرفق\n"

                    "أو بدون مرفق:\n"

                    "إضافة اختبار:(نص السؤال) (جواب1، جواب2) رقم_الصحيح"

                )

                return

            question = match.group(1).strip()

            options_str = match.group(2).strip()

            options = [opt.strip() for opt in re.split(r"[,،]", options_str)]

            correct_idx = int(match.group(3).strip()) - 1

            media_id = int(match.group(4).strip()) if match.group(4) else None

            if not (0 <= correct_idx < len(options)):

                await update.message.reply_text("⚠️ رقم الجواب الصحيح غير متوافق مع عدد الخيارات.")

                return

            if len(options) < 2 or len(options) > 10:

                await update.message.reply_text("⚠️ يجب أن يكون عدد الخيارات بين 2 و 10.")

                return

            new_quiz = {

                "question": question,

                "options": options,

                "correct_idx": correct_idx,

                "media_id": media_id,

            }

            data = get_data("quiz")

            data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]][ud["lecture"]].append(new_quiz)

            save_data("quiz", data)

            await update.message.reply_text("✅ تم إضافة الاختبار للمحاضرة بنجاح.")

            return

        if text.startswith("إضافة ملف:"):

            if ud.get("step") != "list" or ud.get("type") != "library":

                await update.message.reply_text("⚠️ ادخل إلى المادة المطلوبة في المكتبة أولاً.")

                return

            try:

                parts = text.replace("إضافة ملف:", "").split("|")

                f_name, ids_part = parts[0].strip(), parts[1].strip().split()

                ids = [int(ids_part[0])] if len(ids_part) == 1 else list(range(int(ids_part[0]), int(ids_part[1]) + 1))

                data = get_data(ud["type"])

                data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]].append({"name": f_name, "ids": ids})

                save_data(ud["type"], data)

                await update.message.reply_text(f"✅ تم إضافة '{f_name}' بنجاح.")

                return

            except:

                await update.message.reply_text("⚠️ التنسيق: إضافة ملف: الاسم | 10 20")

    # --- التنقل للمتنفسات الرئيسية ---

    if text in ["📚 مكتبة الملفات", "📝 الاختبارات (Quiz)"]:

        section = "library" if "مكتبة" in text else "quiz"

        clear_section_state(ud)

        ud.update({"type": section, "section": section, "step": "year"})

        await update.message.reply_text(

            "اختر السنة:",

            reply_markup=year_keyboard(section)

        )

    elif ud.get("step") == "year" and "السنة" in text:

        ud.update({"step": "sem", "year": text})

        section = ud.get("section")

        if section in ["library", "quiz"]:

            await update.message.reply_text("اختر الفصل:", reply_markup=sem_keyboard(section))

        else:

            await update.message.reply_text("اختر الفصل:", reply_markup=ReplyKeyboardMarkup([["الفصل الأول"], ["الفصل الثاني"]] + [nav_btns()], resize_keyboard=True))

    elif ud.get("step") == "sem" and "الفصل" in text:

        ud.update({"step": "mode", "sem": text})

        section = ud.get("section")

        if section in ["library", "quiz"]:

            await update.message.reply_text("اختر النوع:", reply_markup=mode_keyboard(section))

        else:

            await update.message.reply_text("اختر النوع:", reply_markup=ReplyKeyboardMarkup([["نظري", "عملي"]] + [nav_btns()], resize_keyboard=True))

    elif ud.get("step") == "mode" and text in ["نظري", "عملي"]:

        ud.update({"step": "subject", "mode": text})

        data = get_data(ud["type"])

        subjects = list(data.get(ud["year"], {}).get(ud["sem"], {}).get(text, {}).keys())

        ud["subjects_cache"] = subjects

        msg = "اختر المادة:" if subjects else "📂 لا يوجد مواد."

        if ud.get("section") in ["library", "quiz"]:

            await update.message.reply_text(msg, reply_markup=subject_keyboard(ud["section"], subjects))

        else:

            btns = [[s] for s in subjects] + [nav_btns()]

            await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))

    elif ud.get("step") == "subject" and text not in nav_btns():

        data = get_data(ud["type"])

        if ud["type"] == "library":

            ud.update({"step": "list", "subject": text})

            items = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(text, [])

            ud["items_cache"] = items

            if not items:

                await update.message.reply_text(

                    f"📂 مادة {text} فارغة.",

                    reply_markup=section_nav_keyboard("library", "subject")

                )

            else:

                await update.message.reply_text(

                    f"📑 محتويات مادة {text}:",

                    reply_markup=library_items_keyboard(items, user_id == ADMIN_ID)

                )

        elif ud["type"] == "quiz":

            ud.update({"step": "lecture_list", "subject": text})

            subj_data = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(text, {})

            if isinstance(subj_data, list):

                subj_data = {}

                data[ud["year"]][ud["sem"]][ud["mode"]][text] = subj_data

                save_data("quiz", data)

            lectures = list(subj_data.keys())

            ud["lectures_cache"] = lectures

            msg = f"اختر المحاضرة في {text}:" if lectures else "📂 لا يوجد محاضرات هنا."

            await update.message.reply_text(msg, reply_markup=lecture_keyboard("quiz", lectures))

    elif ud.get("step") == "lecture_list" and ud.get("type") == "quiz" and text not in nav_btns():

        ud.update({"step": "in_lecture", "lecture": text})

        data = get_data("quiz")

        quizzes = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(ud["subject"], {}).get(text, [])

        if not quizzes:

            await update.message.reply_text(

                f"📭 المحاضرة '{text}' فارغة. بانتظار إضافة الاختبارات.",

                reply_markup=ReplyKeyboardMarkup([nav_btns()], resize_keyboard=True)

            )

            return

        await update.message.reply_text(

            f"📝 جاري إرسال اختبارات {text}...",

            reply_markup=ReplyKeyboardMarkup([nav_btns()], resize_keyboard=True)

        )

        for q in quizzes:

            if q.get("media_id"):

                try:

                    await context.bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=q["media_id"])

                except:

                    pass

            try:

                await context.bot.send_poll(

                    chat_id=user_id,

                    question=q["question"],

                    options=q["options"],

                    type="quiz",

                    correct_option_id=q["correct_idx"]

                )

            except Exception as e:

                await update.message.reply_text(f"⚠️ خطأ في الإرسال: {e}")

        if user_id == ADMIN_ID:

            kb = []

            for idx, q in enumerate(quizzes):

                q_text = q["question"][:30] + "..." if len(q["question"]) > 30 else q["question"]

                kb.append([

                    InlineKeyboardButton(f"🔁 {q_text}", callback_data=f"resendq_{idx}"),

                    InlineKeyboardButton("❌", callback_data=f"askdelq_{idx}")

                ])

            await update.message.reply_text("⚙️ إدارة اختبارات المحاضرة:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "📊 بوابة العلامات":

        ud["step"] = "marks"

        await update.message.reply_text("أرسل الرقم الجامعي:", reply_markup=ReplyKeyboardMarkup([nav_btns()], resize_keyboard=True))

    elif ud.get("step") == "marks" and text.isdigit():

        loading = await update.message.reply_text("⏳ جارٍ سحب النتيجة...")

        res = get_pharmacy_marks(text)

        await loading.edit_text(res, parse_mode="Markdown")

# --- 5. أزرار Callback ---

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    user_id = query.from_user.id

    ud = context.user_data

    raw_data = query.data

    parts = raw_data.split(":") if ":" in raw_data else raw_data.split("_")

    action = parts[0]

    await query.answer()

    # --- الرجوع إلى الرئيسية ---

    if action == "home":

        await send_or_edit_main_menu(query, context, user_id)

        return

    # --- الأدمن ---

    if action == "admin":

        sub = parts[1] if len(parts) > 1 else ""

        if sub == "broadcast" and user_id == ADMIN_ID:

            ud["step"] = "broadcast"

            await query.edit_message_text(

                "📢 أرسل الآن الرسالة التي تريد بثها للجميع.\n"

                "يمكن أن تكون نصاً أو صورة أو فيديو أو ملفاً.\n\n"

                "للرجوع اضغط الزر أدناه.",

                reply_markup=InlineKeyboardMarkup([

                    [InlineKeyboardButton("🔙 رجوع", callback_data="admin:back")],

                    [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")]

                ])

            )

            return

        if sub == "stats" and user_id == ADMIN_ID:

            total_users = users_col.count_documents({})

            await query.edit_message_text(

                f"📊 إجمالي المستخدمين المسجلين: {total_users}",

                reply_markup=admin_stats_menu()

            )

            return

        if sub == "getusernames" and user_id == ADMIN_ID:

            users = users_col.find({}).sort("_id", 1)

            content = "قائمة مستخدمي البوت:\n\n"

            for i, u in enumerate(users, 1):

                content += f"{i}- {u.get('first_name', 'بدون اسم')} (@{u.get('username', 'لا يوجد')}) [ID: {u.get('_id')}]\n"

            output = io.BytesIO(content.encode("utf-8"))

            output.name = "users_list.txt"

            await context.bot.send_document(

                chat_id=user_id,

                document=output,

                caption="📊 قائمة المستخدمين بالتفصيل"

            )

            return

        if sub == "back" and user_id == ADMIN_ID:

            ud["step"] = "admin_menu"

            await query.edit_message_text("⚙️ لوحة تحكم الإدارة:", reply_markup=admin_inline_menu())

            return

    # --- التنقل داخل المكتبة/الكويز ---

    if action == "nav":

        section = parts[1] if len(parts) > 1 else ""

        kind = parts[2] if len(parts) > 2 else ""

        value = parts[3] if len(parts) > 3 else ""

        if kind == "back":

            if value == "main":

                await send_or_edit_main_menu(query, context, user_id)

                return

            if section in ["library", "quiz"]:

                if value == "year":

                    ud["type"] = section

                    ud["section"] = section

                    ud["step"] = "year"

                    for k in ["year", "sem", "mode", "subject", "lecture", "subjects_cache", "lectures_cache", "items_cache"]:

                        ud.pop(k, None)

                    await query.edit_message_text("اختر السنة:", reply_markup=year_keyboard(section))

                    return

                if value == "sem":

                    ud["step"] = "sem"

                    ud.pop("sem", None)

                    for k in ["mode", "subject", "lecture", "subjects_cache", "lectures_cache", "items_cache"]:

                        ud.pop(k, None)

                    await query.edit_message_text("اختر الفصل:", reply_markup=sem_keyboard(section))

                    return

                if value == "mode":

                    ud["step"] = "mode"

                    ud.pop("mode", None)

                    for k in ["subject", "lecture", "subjects_cache", "lectures_cache", "items_cache"]:

                        ud.pop(k, None)

                    await query.edit_message_text("اختر النوع:", reply_markup=mode_keyboard(section))

                    return

                if value == "subject":

                    ud["step"] = "subject"

                    ud.pop("subject", None)

                    ud.pop("lecture", None)

                    for k in ["lectures_cache", "items_cache"]:

                        ud.pop(k, None)

                    data = get_data(section)

                    subjects = list(data.get(ud.get("year", ""), {}).get(ud.get("sem", ""), {}).get(ud.get("mode", ""), {}).keys())

                    ud["subjects_cache"] = subjects

                    await query.edit_message_text("اختر المادة:", reply_markup=subject_keyboard(section, subjects))

                    return

            return

        # اختيار السنة

        if kind == "year" and section in ["library", "quiz"]:

            year_label = get_selected_label(value, YEARS)

            if not year_label:

                await query.answer("⚠️ سنة غير صالحة", show_alert=True)

                return

            ud.update({

                "type": section,

                "section": section,

                "step": "sem",

                "year": year_label,

            })

            for k in ["sem", "mode", "subject", "lecture", "subjects_cache", "lectures_cache", "items_cache"]:

                ud.pop(k, None)

            await query.edit_message_text("اختر الفصل:", reply_markup=sem_keyboard(section))

            return

        # اختيار الفصل

        if kind == "sem" and section in ["library", "quiz"]:

            sem_label = get_selected_label(value, SEMS)

            if not sem_label:

                await query.answer("⚠️ فصل غير صالح", show_alert=True)

                return

            ud.update({

                "step": "mode",

                "sem": sem_label,

            })

            for k in ["mode", "subject", "lecture", "subjects_cache", "lectures_cache", "items_cache"]:

                ud.pop(k, None)

            await query.edit_message_text("اختر النوع:", reply_markup=mode_keyboard(section))

            return

        # اختيار النوع

        if kind == "mode" and section in ["library", "quiz"]:

            mode_label = get_selected_label(value, MODES)

            if not mode_label:

                await query.answer("⚠️ نوع غير صالح", show_alert=True)

                return

            ud.update({

                "step": "subject",

                "mode": mode_label,

            })

            for k in ["subject", "lecture", "subjects_cache", "lectures_cache", "items_cache"]:

                ud.pop(k, None)

            data = get_data(section)

            subjects = list(data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).keys())

            ud["subjects_cache"] = subjects

            await query.edit_message_text("اختر المادة:", reply_markup=subject_keyboard(section, subjects))

            return

        # اختيار المادة

        if kind == "subject" and section in ["library", "quiz"]:

            try:

                idx = int(value)

            except:

                await query.answer("⚠️ مادة غير صالحة", show_alert=True)

                return

            data = get_data(section)

            subjects = list(data.get(ud.get("year", ""), {}).get(ud.get("sem", ""), {}).get(ud.get("mode", ""), {}).keys())

            if not (0 <= idx < len(subjects)):

                await query.answer("⚠️ مادة غير موجودة", show_alert=True)

                return

            subject = subjects[idx]

            ud["subject"] = subject

            ud.pop("lecture", None)

            if section == "library":

                ud["step"] = "list"

                items = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(subject, [])

                ud["items_cache"] = items

                if not items:

                    await query.edit_message_text(

                        f"📂 مادة {subject} فارغة.",

                        reply_markup=section_nav_keyboard("library", "subject")

                    )

                else:

                    await query.edit_message_text(

                        f"📑 محتويات مادة {subject}:",

                        reply_markup=library_items_keyboard(items, user_id == ADMIN_ID)

                    )

                return

            if section == "quiz":

                ud["step"] = "lecture_list"

                subj_data = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(subject, {})

                if isinstance(subj_data, list):

                    subj_data = {}

                    data[ud["year"]][ud["sem"]][ud["mode"]][subject] = subj_data

                    save_data("quiz", data)

                lectures = list(subj_data.keys())

                ud["lectures_cache"] = lectures

                await query.edit_message_text(

                    f"اختر المحاضرة في {subject}:",

                    reply_markup=lecture_keyboard("quiz", lectures)

                )

                return

        # اختيار المحاضرة في الكويز

        if kind == "lecture" and section == "quiz":

            try:

                idx = int(value)

            except:

                await query.answer("⚠️ محاضرة غير صالحة", show_alert=True)

                return

            data = get_data("quiz")

            lectures = list(

                data.get(ud.get("year", ""), {})

                    .get(ud.get("sem", ""), {})

                    .get(ud.get("mode", ""), {})

                    .get(ud.get("subject", ""), {})

                    .keys()

            )

            if not (0 <= idx < len(lectures)):

                await query.answer("⚠️ محاضرة غير موجودة", show_alert=True)

                return

            lecture = lectures[idx]

            ud["lecture"] = lecture

            ud["step"] = "in_lecture"

            quizzes = data.get(ud["year"], {}).get(ud["sem"], {}).get(ud["mode"], {}).get(ud["subject"], {}).get(lecture, [])

            if not quizzes:

                await query.edit_message_text(

                    f"📭 المحاضرة '{lecture}' فارغة.",

                    reply_markup=section_nav_keyboard("quiz", "subject")

                )

                return

            await context.bot.send_message(

                chat_id=user_id,

                text=f"📝 جاري إرسال اختبارات {lecture}..."

            )

            for q in quizzes:

                if q.get("media_id"):

                    try:

                        await context.bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=q["media_id"])

                    except:

                        pass

                try:

                    await context.bot.send_poll(

                        chat_id=user_id,

                        question=q["question"],

                        options=q["options"],

                        type="quiz",

                        correct_option_id=q["correct_idx"]

                    )

                except Exception as e:

                    await context.bot.send_message(chat_id=user_id, text=f"⚠️ خطأ في الإرسال: {e}")

            if user_id == ADMIN_ID:

                kb = []

                for q_idx, q in enumerate(quizzes):

                    q_text = q["question"][:30] + "..." if len(q["question"]) > 30 else q["question"]

                    kb.append([

                        InlineKeyboardButton(f"🔁 {q_text}", callback_data=f"resendq_{q_idx}"),

                        InlineKeyboardButton("❌", callback_data=f"askdelq_{q_idx}")

                    ])

                await context.bot.send_message(

                    chat_id=user_id,

                    text="⚙️ إدارة اختبارات المحاضرة:",

                    reply_markup=InlineKeyboardMarkup(kb)

                )

            return

    # --- المكتبة: فتح / حذف ملف ---

    if action == "lib":

        sub = parts[1] if len(parts) > 1 else ""

        idx_part = parts[2] if len(parts) > 2 else ""

        data = get_data("library")

        current_list = data.get(ud.get("year", ""), {}).get(ud.get("sem", ""), {}).get(ud.get("mode", ""), {}).get(ud.get("subject", ""), [])

        if sub == "get":

            try:

                idx = int(idx_part)

            except:

                await query.answer("⚠️ عنصر غير صالح", show_alert=True)

                return

            if not (0 <= idx < len(current_list)):

                await query.answer("⚠️ الملف غير موجود", show_alert=True)

                return

            for f_id in current_list[idx].get("ids", []):

                try:

                    await context.bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=f_id)

                except:

                    pass

            return

        if sub == "del" and user_id == ADMIN_ID:

            try:

                idx = int(idx_part)

            except:

                await query.answer("⚠️ عنصر غير صالح", show_alert=True)

                return

            if not (0 <= idx < len(current_list)):

                await query.answer("⚠️ الملف غير موجود", show_alert=True)

                return

            current_list.pop(idx)

            data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]] = current_list

            save_data("library", data)

            if not current_list:

                await query.edit_message_text(

                    "✅ تم حذف الملف، والقائمة أصبحت فارغة.",

                    reply_markup=section_nav_keyboard("library", "subject")

                )

            else:

                await query.edit_message_text(

                    "✅ تم الحذف.",

                    reply_markup=library_items_keyboard(current_list, True)

                )

            return

    # --- أزرار الاختبارات القديمة (إعادة الإرسال / الحذف) ---

    if action == "resendq":

        try:

            idx = int(parts[1])

        except:

            await query.answer("⚠️ عنصر غير صالح", show_alert=True)

            return

        db_data = get_data("quiz")

        q = db_data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]][ud["lecture"]][idx]

        if q.get("media_id"):

            try:

                await context.bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=q["media_id"])

            except:

                pass

        await context.bot.send_poll(

            chat_id=user_id,

            question=q["question"],

            options=q["options"],

            type="quiz",

            correct_option_id=q["correct_idx"]

        )

        return

    elif action == "askdelq" and user_id == ADMIN_ID:

        try:

            idx = int(parts[1])

        except:

            await query.answer("⚠️ عنصر غير صالح", show_alert=True)

            return

        kb = query.message.reply_markup.inline_keyboard

        new_kb = []

        for row in kb:

            if row[-1].callback_data == f"askdelq_{idx}":

                new_kb.append([

                    InlineKeyboardButton("✅ تأكيد الحذف", callback_data=f"confdelq_{idx}"),

                    InlineKeyboardButton("🔙 تراجع", callback_data=f"cancdelq_{idx}")

                ])

            else:

                new_kb.append(row)

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))

        return

    elif action == "confdelq" and user_id == ADMIN_ID:

        try:

            idx = int(parts[1])

        except:

            await query.answer("⚠️ عنصر غير صالح", show_alert=True)

            return

        db_data = get_data("quiz")

        lecture_quizzes = db_data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]][ud["lecture"]]

        try:

            lecture_quizzes.pop(idx)

            save_data("quiz", db_data)

            new_kb = []

            for new_idx, q in enumerate(lecture_quizzes):

                q_text = q["question"][:30] + "..." if len(q["question"]) > 30 else q["question"]

                new_kb.append([

                    InlineKeyboardButton(f"🔁 {q_text}", callback_data=f"resendq_{new_idx}"),

                    InlineKeyboardButton("❌", callback_data=f"askdelq_{new_idx}")

                ])

            if new_kb:

                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))

            else:

                await query.edit_message_text("✅ تم حذف جميع اختبارات المحاضرة.")

        except:

            await query.answer("⚠️ حدث خطأ أثناء الحذف.", show_alert=True)

        return

    elif action == "cancdelq" and user_id == ADMIN_ID:

        db_data = get_data("quiz")

        lecture_quizzes = db_data[ud["year"]][ud["sem"]][ud["mode"]][ud["subject"]][ud["lecture"]]

        new_kb = []

        for new_idx, q in enumerate(lecture_quizzes):

            q_text = q["question"][:30] + "..." if len(q["question"]) > 30 else q["question"]

            new_kb.append([

                InlineKeyboardButton(f"🔁 {q_text}", callback_data=f"resendq_{new_idx}"),

                InlineKeyboardButton("❌", callback_data=f"askdelq_{new_idx}")

            ])

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))

        return

    elif action == "cancel":

        await query.edit_message_text("🔙 تم الإلغاء.")

        return

if __name__ == "__main__":

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    print("Bot is Polling...")

    application.run_polling()
