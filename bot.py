import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TOKEN = "8721437251:AAHN0siD2ie8Raqc56tKHKKgiur7x199prg"

URL = "https://app.hama-univ.edu.sy/StdMark/Home/Result"

COLLEGES = {
    "صيدلة": 4,
    "تمريض": 5,
    "طب": 1,
    "أسنان": 3,
    "اقتصاد": 7,
    "آداب": 6,
    "تربية": 8
}

def get_marks(student_id, college_id):

    try:

        data = {
            "UniversityId": student_id,
            "CollegeId": college_id
        }

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        print("Sending request...")
        print("Student ID:", student_id)
        print("College:", college_id)

        response = requests.post(URL, data=data, headers=headers)

        print("STATUS CODE:", response.status_code)
        print("RESPONSE SAMPLE:")
        print(response.text[:500])

        if response.status_code != 200:
            return "⚠️ الموقع لم يستجب"

        soup = BeautifulSoup(response.text, "html.parser")

        text = soup.get_text()

        if len(text) < 50:
            return "❌ لم يتم العثور على نتائج"

        return text[:4000]

    except Exception as e:

        print("ERROR OCCURRED:")
        print(e)

        return "⚠️ حدث خطأ أثناء جلب البيانات"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        message = update.message.text.strip()
        lines = message.split("\n")

        if len(lines) != 2:
            return

        faculty = lines[0].strip()
        student_id = lines[1].strip()

        print("Received message")
        print("Faculty:", faculty)
        print("Student ID:", student_id)

        college_id = COLLEGES.get(faculty)

        if not college_id:
            await update.message.reply_text("❌ الكلية غير معروفة")
            return

        await update.message.reply_text("⏳ جاري جلب النتائج...")

        result = get_marks(student_id, college_id)

        await update.message.reply_text(result)

    except Exception as e:

        print("BOT ERROR:")
        print(e)

        await update.message.reply_text("⚠️ حدث خطأ")


def main():

    print("Bot started...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()