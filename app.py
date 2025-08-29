from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, re, logging
import PyPDF2
import google.generativeai as genai

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ---------- API KEY ----------
API_KEY = os.getenv("GEMINI_API_KEY") or "AIzaSyA-YOqqY7OyWJfqNO6suCM3LtAjlnIADOk"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ---------- helpers ----------
def extract_text_from_pdf(file_storage):
    try:
        reader = PyPDF2.PdfReader(file_storage)
        chunks = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                chunks.append(t)
        return "\n".join(chunks).strip()
    except Exception as e:
        app.logger.exception("PDF read error")
        return ""

def parse_json_strict(raw):
    if not raw:
        return None
    s = raw.strip()

    # remove ```json or ``` fences
    s = re.sub(r"^```json\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"```$", "", s, flags=re.IGNORECASE)

    # try direct JSON
    try:
        return json.loads(s)
    except Exception:
        pass

    # try to locate first JSON object block {...}
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None

def parse_fallback(raw_text):
    """
    Flexible parser: finds MCQs where options are labeled A/B/C/D (with ., ) or no punctuation),
    and True/False pairs with 'Answer: True/False'.
    Returns dict {mcqs: [...], true_false: [...]}
    """
    mcqs = []
    tf = []
    text = (raw_text or "").replace("\r\n", "\n")

    # Normalize repeated spaces and unify bullets
    # We'll search for MCQ blocks using a tolerant regex
    mcq_pattern = re.compile(
        r'(?:Q\s*\d+[:\).\s]*)?'                         # optional Q1:
        r'(?P<q>.+?)\n'                                  # question (non-greedy)
        r'\s*(?:A|a)[\.\)]?\s*(?P<A>.*?)\n'             # A.
        r'\s*(?:B|b)[\.\)]?\s*(?P<B>.*?)\n'             # B.
        r'\s*(?:C|c)[\.\)]?\s*(?P<C>.*?)\n'             # C.
        r'\s*(?:D|d)[\.\)]?\s*(?P<D>.*?)\n'             # D.
        r'\s*(?:Answer|answer)[:\s]*([A-Da-d])',         # Answer: B
        flags=re.DOTALL | re.IGNORECASE
    )

    for m in mcq_pattern.finditer(text):
        question = m.group("q").strip()
        a = m.group("A").strip()
        b = m.group("B").strip()
        c = m.group("C").strip()
        d = m.group("D").strip()
        ans = m.group(5).strip().upper()
        mcqs.append({
            "question": question,
            "options": [a, b, c, d],
            "answer": ans
        })

    # True/False: find lines with 'Answer: True' or 'Answer: False'
    tf_pattern = re.compile(
        r'(?:T(?:RUE\/FALSE)?\s*\d*[:\.\)]*\s*)?'    # optional TRUE/FALSE header or numbering
        r'(?P<stmt>.+?)\n\s*(?:Answer|answer)[:\s]*(?P<ans>True|False)',
        flags=re.IGNORECASE | re.DOTALL
    )

    # Another approach for TF: find segments after a header 'TRUE/FALSE' too
    matches = tf_pattern.finditer(text)
    for m in matches:
        stmt = m.group("stmt").strip()
        ans = m.group("ans").strip().capitalize()
        # discard if looks like an MCQ captured above
        if stmt and not any(stmt in q['question'] for q in mcqs):
            tf.append({"question": stmt, "answer": ans})

    return {"mcqs": mcqs, "true_false": tf}

# ---------- routes ----------
@app.route("/")
def home():
    return "Quiz Question Creator Backend is Running 🚀"

@app.route("/generate-questions", methods=["POST"])
def generate_questions():
    try:
        if "pdf" not in request.files:
            return jsonify({"error": "No PDF uploaded"}), 400

        pdf_file = request.files["pdf"]
        text = extract_text_from_pdf(pdf_file)
        if not text:
            return jsonify({"error": "No text found in PDF (maybe scanned image-only PDF)."}), 400

        # prompt asking strict JSON
        prompt = f"""
You are an expert quiz generator. From the text below, produce EXACTLY valid JSON and NOTHING else.
Return JSON matching this schema:

{{
  "mcqs": [
    {{
      "question": "string",
      "options": ["string","string","string","string"],
      "answer": "A|B|C|D"
    }},
    {{ "question":"string","options":["...","...","...","..."],"answer":"A|B|C|D" }},
    {{ "question":"string","options":["...","...","...","..."],"answer":"A|B|C|D" }}
  ],
  "true_false": [
    {{ "question": "string", "answer": "True|False" }},
    {{ "question": "string", "answer": "True|False" }}
  ]
}}

Text:
{text[:4000]}
"""

        resp = model.generate_content(prompt)
        raw = getattr(resp, "text", "") or ""
        app.logger.info("Raw model output (first 2000 chars):\n%s", raw[:2000])

        # Try strict JSON parse first
        data = parse_json_strict(raw)
        if not isinstance(data, dict):
            app.logger.info("Strict JSON parse failed. Falling back to tolerant parser.")
            data = parse_fallback(raw)

        # If still empty, try a last attempt: check for pure text 'questions' style
        if not isinstance(data, dict):
            return jsonify({"error": "Unable to parse model output", "raw": raw}), 500

        data.setdefault("mcqs", [])
        data.setdefault("true_false", [])

        # If parsed arrays are empty, return raw so frontend can show it for debugging
        if len(data["mcqs"]) == 0 and len(data["true_false"]) == 0:
            return jsonify({"mcqs": [], "true_false": [], "raw": raw})

        return jsonify(data)

    except Exception as e:
        app.logger.exception("Unhandled backend error")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    if not API_KEY or API_KEY == "REPLACE_WITH_YOUR_KEY":
        app.logger.warning("GEMINI API KEY not set or still placeholder. Set GEMINI_API_KEY env var.")
    app.run(debug=True, port=5000)