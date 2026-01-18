from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import time
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)
CORS(app)

BASE_URL = "https://beu-bih.ac.in"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Cache store
CACHE = {
    "exams": {"data": None, "expiry": 0},
    "results": {}
}

EXAMS_CACHE_TTL = 60 * 30   # 30 minutes
RESULT_CACHE_TTL = 60 * 10  # 10 minutes

@app.route("/")
def home():
    return {"status": "BEU Universal Result Backend Running"}

# -----------------------------
# 1️⃣ ALL EXAMS LIST API
# -----------------------------
@app.route("/api/exams", methods=["GET"])
def exams_list():
    now = time.time()

    # Cache hit
    if CACHE["exams"]["data"] and CACHE["exams"]["expiry"] > now:
        return {
            "success": True,
            "cached": True,
            "exams": CACHE["exams"]["data"]
        }

    # Cache miss
    res = requests.get(BASE_URL + "/result", headers=HEADERS, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")

    exams = []
    for row in soup.find_all("tr"):
        a = row.find("a")
        if not a or not a.get("href"):
            continue

        title = a.get_text(strip=True)
        if "Examination" not in title:
            continue

        exams.append({
            "title": title,
            "course": title.split()[0],
            "link": a["href"]
        })

    # Save to cache
    CACHE["exams"] = {"data": exams, "expiry": now + EXAMS_CACHE_TTL}

    return {
        "success": True,
        "cached": False,
        "exams": exams
    }

# -----------------------------
# 2️⃣ RESULT FETCH API
# -----------------------------
@app.route("/api/result", methods=["POST"])
def fetch_result():
    data = request.get_json()
    reg_no = str(data.get("reg_no", "")).strip()
    link = data.get("link", "")

    if not reg_no or not link:
        return {"success": False, "error": "reg_no and link required"}, 400

    cache_key = f"{reg_no}_{link}"
    now = time.time()

    # Cache hit
    if cache_key in CACHE["results"]:
        cached = CACHE["results"][cache_key]
        if cached["expiry"] > now:
            return {
                "success": True,
                "cached": True,
                "result": cached["data"]
            }

    # Cache miss
    result_url = BASE_URL + link
    payload = {"reg_no": reg_no}

    res = requests.post(result_url, data=payload, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table")

    if not table:
        return {"success": False, "error": "Result not found / invalid reg_no"}

    rows = table.find_all("tr")
    headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]

    data_rows = []
    for r in rows[1:]:
        cols = [td.get_text(strip=True) for td in r.find_all("td")]
        if cols:
            data_rows.append(dict(zip(headers, cols)))

    # Save to cache
    CACHE["results"][cache_key] = {
        "data": data_rows,
        "expiry": now + RESULT_CACHE_TTL
    }

    return {
        "success": True,
        "cached": False,
        "result": data_rows
    }

# -----------------------------
# 3️⃣ PDF DOWNLOAD API
# -----------------------------
@app.route("/api/download-pdf", methods=["POST"])
def download_pdf():
    data = request.get_json()
    reg_no = data.get("reg_no", "")
    exam_title = data.get("exam_title", "")
    result = data.get("result", [])

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height - 40, "BEU Result")
    c.setFont("Helvetica", 12)
    c.drawString(40, height - 60, f"Reg No: {reg_no}")
    c.drawString(40, height - 80, f"Exam: {exam_title}")

    y = height - 120

    if result:
        headers = list(result[0].keys())
        c.setFont("Helvetica-Bold", 10)
        x = 40
        for h in headers:
            c.drawString(x, y, h)
            x += 120

        y -= 20
        c.setFont("Helvetica", 10)

        for row in result:
            x = 40
            for h in headers:
                c.drawString(x, y, str(row[h]))
                x += 120
            y -= 20

            if y < 40:
                c.showPage()
                y = height - 40

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"BEU_Result_{reg_no}.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
