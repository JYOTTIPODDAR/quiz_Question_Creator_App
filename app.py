from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, json, re, logging
import PyPDF2
import google.generativeai as genai

# ----------------- App Setup -----------------
app = Flask(__name__, static_folder='.')  # frontend files in same folder
CORS(app)
logging.basicConfig(level=logging.INFO)

# ----------------- API Key -----------------
API_KEY = os.getenv("AIzaSyA-YOqqY7OyWJfqNO6suCM3LtAjlnIADOk")
if not API_KEY:
    app.logger.error("GEMINI_API_KEY not set")
    raise ValueError("GEMINI_API_KEY environment variable not set")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ----------------- Helper Functions -----------------
def extract_text_from_pdf(file_storage):
    try:
        reader = PyPDF2.PdfReader(file_storage)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        app.logger.exception("PDF read error")
        return ""

def parse_json_strict(raw):
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```json\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"```$", "", s, flags=re.IGNORECASE)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None

def parse_fallback(raw_text):
    # simple fallback parser
    mcqs = []
    tf = []
    text = (raw_text or "").replace("\r\n", "\n")
    mcq_pattern = re.compile(
        r'(?:Q\s*\d+[:\).\s]*)?(?P<q>.+?)\n\s*(?:A|a)[\.\)]?\s*(?P<A>.*?)\n\s*(?:B|b)[\.\)]?\s*(?P<B>.*?)\n\s*(?:C|c)[\.\)]?\s*(?P<C>.*?)\n\s*(?:D|d)[\.\)]?\s*(?P<D>.*?)\n\s*(?:Answer|answer)[:\s]*([A-Da-d])',
        flags=re.DOTALL | re.IGNORECASE
    )
    for m in mcq_pattern.finditer(text):
        question = m.group("q").strip()
        a = m.group("A").strip()
        b = m.group("B").strip()
        c = m.group("C").strip()
        d = m.group("D").strip()
        ans = m.group(5).strip().upper()
        mcqs.append({"question": question, "options": [a, b, c, d], "answer": ans})

    tf_pattern = re.compile(
        r'(?:T(?:RUE\/FALSE)?\s*\d*[:\.\)]*\s*)?(?P<stmt>.+?)\n\s*(?:Answer|answer)[:\s]*(?P<ans>True|False)',
        flags=re.IGNORECASE | re.DOTALL
    )
    for m in tf_pattern.finditer(text):
        stmt = m.group("stmt").strip()
        ans = m.group("ans").strip().capitalize()
        if stmt and not any(stmt in q['question'] for q in mcqs):
            tf.append({"question": stmt, "answer": ans})

    return {"mcqs": mcqs, "true_false": tf}

# ----------------- Serve Frontend -----------------
@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# ----------------- API Route -----------------
@app.route("/generate-questions", methods=["POST"])
def generate_questions():
    try:
        if "pdf" not in request.files:
            return jsonify({"error": "No PDF uploaded"}), 400

        pdf_file = request.files["pdf"]
        text = extract_text_from_pdf(pdf_file)
        if not text:
            return jsonify({"error": "No text found in PDF"}), 400

        prompt = f"""
You are an expert quiz generator. From the text below, produce EXACTLY valid JSON and NOTHING else.
Return JSON matching this schema:

{{
  "mcqs": [
    {{
      "question": "string",
      "options": ["string","string","string","string"],
      "answer": "A|B|C|D"
    }}
  ],
  "true_false": [
    {{ "question": "string", "answer": "True|False" }}
  ]
}}

Text:
{text[:4000]}
"""
        resp = model.generate_content(prompt)
        raw = getattr(resp, "text", "") or ""
        app.logger.info("Raw model output (first 2000 chars):\n%s", raw[:2000])

        data = parse_json_strict(raw)
        if not isinstance(data, dict):
            app.logger.info("Strict JSON parse failed. Falling back to tolerant parser.")
            data = parse_fallback(raw)
        if not isinstance(data, dict):
            return jsonify({"error": "Unable to parse model output", "raw": raw}), 500

        data.setdefault("mcqs", [])
        data.setdefault("true_false", [])

        return jsonify(data)
    except Exception as e:
        app.logger.exception("Unhandled backend error")
        return jsonify({"error": str(e)}), 500

# ----------------- Run App -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
