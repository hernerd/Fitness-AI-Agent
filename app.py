import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
import google.genai as genai
import markdown
from bs4 import BeautifulSoup
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='reportlab')  # Suppress ReportLab warnings about missing fonts, etc.

# ---------- Setup ----------
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing. Put it in .env as GEMINI_API_KEY=...")

client = genai.Client(api_key=API_KEY)

# Choose a fast, capable model. You can switch to "gemini-1.5-pro" later.
MODEL_NAME = "gemini-3-flash-preview"

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)


# ---------- Helpers ----------
def build_system_preamble(profile: Dict[str, Any]) -> str:
    """Build a brief profile context block for personalization."""
    if not profile:
        return (
            "You are a friendly, factual fitness & diet assistant. "
            "Answer clearly and helpfully for general questions."
        )

    # Normalize expected keys; tolerate missing fields
    age = profile.get("age", "")
    gender = profile.get("gender", "")
    height = profile.get("height", "")
    weight = profile.get("weight", "")
    goal = profile.get("goal", "")
    diet = profile.get("diet", "")
    cuisine = profile.get("cuisine", "")
    activity = profile.get("activity", "")
    allergies = profile.get("allergies", "")

    # NEW: Grab health concerns from the profile
    health_concerns = profile.get("health_concerns", "")

    

    return (
        "You are a friendly, factual fitness & diet assistant. "
        "Personalize suggestions using this user profile when relevant.\n\n"
        f"User Profile:\n"
        f"- Age: {age}\n"
        f"- Gender: {gender}\n"
        f"- Height: {height} inches\n"
        f"- Weight: {weight} lbs\n"
        f"- Goal: {goal}\n"
        f"- Diet Preference: {diet}\n"
        f"- Cuisine: {cuisine or 'none'}\n"
        f"- Activity Level: {activity}\n"
        f"- Allergies: {allergies or 'none'}\n"

        # NEW
        f"- Health Concerns: {health_concerns or 'none'}\n\n"
        "MEDICAL SAFETY RULES:\n"
        "1. If 'Diabetes' is mentioned, prioritize low-glycemic index foods and strictly limit added sugars.\n"
        "2. If 'High Cholesterol' is mentioned, limit saturated fats and emphasize fiber and heart-healthy fats.\n"
        "3. Always cross-reference recommendations against the user's listed Allergies.\n"
    )


def build_prompt(history: List[Dict[str, str]], user_message: str, system_preamble: str, intent_hint: str = "") -> str:
    lines = [system_preamble, "\nConversation so far:"]

    for turn in history[-12:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        lines.append(f"{role.capitalize()}: {content}")

    lines.append(f"User: {user_message}")

    message_lower = user_message.lower()

    if (
        "ingredients" in message_lower or
        "fridge" in message_lower or
        "what can i make" in message_lower or
        "what can i cook" in message_lower
    ):
        lines.append(
            "\nInstruction: The user listed ingredients they have. "
            "Suggest 3–5 simple meals using those ingredients. "
            "Use bullet points. Include short steps for each meal. "
            "You may include minimal extra pantry items if needed."
        )

    if intent_hint == "variation":
        lines.append(
            "\nInstruction: Provide a different variation from the last plan or suggestion. "
            "Keep it consistent with the user's profile & preferences."
        )

    lines.append(
        "\nAssistant: Respond concisely. Use bullet points for plans/steps. "
        "If giving a day plan, include approximate calories/macros when helpful."
    )

    return "\n".join(lines)

def format_diet_plan(md_text):
    # 1. Convert to HTML
    html = markdown.markdown(md_text)
    soup = BeautifulSoup(html, "html.parser")
    
    formatted_output = []

    # 2. Iterate through elements and add custom spacing/styling
    for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
        text = element.get_text().strip()
        
        if element.name in ['h1', 'h2', 'h3']:
            # Headers: Add extra space above and use UPPERCASE
            formatted_output.append(f"\n\n{text.upper()}\n" + "-" * len(text))
        
        elif element.name == 'p':
            # Paragraphs: Normal spacing
            formatted_output.append(f"\n{text}")
            
        elif element.name == 'li':
            # Bullet points: Clean indent and a single bullet
            formatted_output.append(f" • {text}")

    # Join with newlines and clean up any triple-spacing
    return "\n".join(formatted_output).strip().replace("\n\n\n", "\n\n")


def generate_pdf_bytes(text):
    """Generate PDF from formatted text and return as BytesIO buffer."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    story = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check if it's a header (all caps with dashes)
        if line.isupper() and len(line) > 0:
            p = Paragraph(line, styles['Heading1'])
        elif line.startswith('•'):
            p = Paragraph(line, styles['Normal'])
        else:
            p = Paragraph(line, styles['Normal'])
        story.append(p)
        story.append(Spacer(1, 0.1 * inch))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ---------- Routes ----------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Expected JSON body:
    {
      "message": "string",
      "history": [{"role":"user"|"assistant", "content":"..."}],
      "profile": {...},
      "intentHint": "variation" | ""    # optional
    }
    """
    data = request.get_json(force=True) or {}
    message: str = data.get("message", "").strip()
    history: List[Dict[str, str]] = data.get("history", [])
    profile: Dict[str, Any] = data.get("profile", {})
    intent_hint: str = data.get("intentHint", "")
    is_fridge = data.get("isFridge", False)  # optional

    # Detect /fridge command directly
    if message.lower().startswith("/fridge"):
        is_fridge = True

    if not message:
        return jsonify({"reply": "Please type a message.", "error": None})

    system_preamble = build_system_preamble(profile)
    prompt = build_prompt(history, message, system_preamble, intent_hint)

    try:
        resp = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        text = (resp.text or "").strip() if resp else ""
        formatted_text = format_diet_plan(text)  # Apply Markdown formatting for cleaner display in frontend
        if not formatted_text:
            formatted_text = "Sorry, I couldn’t generate a response."
        return jsonify({"reply": formatted_text})
    except Exception as e:
        print(f"Model error: {e}")  # Print error to console for debugging
        return jsonify({"reply": "Something went wrong calling the model.", "error": str(e)}), 500


@app.route("/api/pdf", methods=["POST"])
def api_pdf():
    """
    Convert already-rendered text to a PDF download.
    Expected JSON body: { "text": "string" }
    """
    data = request.get_json(force=True) or {}
    text: str = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided."}), 400

    try:
        pdf_buffer = generate_pdf_bytes(text)
        return send_file(pdf_buffer, as_attachment=True, download_name='fitness_plan.pdf', mimetype='application/pdf')
    except Exception as e:
        print(f"PDF error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Flask dev server
    app.run(host="127.0.0.1", port=5000, debug=True)