import os
from datetime import datetime, timezone
from html import escape

from flask import Flask, jsonify, request, Response
from pymongo import MongoClient
from pymongo.errors import PyMongoError

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "scorecard_db")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client[MONGO_DB]
scorecards = db["scorecards"]


# ============================================================
# CORS
# ============================================================
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/submit-score", methods=["OPTIONS"])
def submit_score_options():
    return ("", 204)


@app.route("/api/scorecard", methods=["OPTIONS"])
def scorecard_options():
    return ("", 204)


# ============================================================
# BASIC ROUTES
# ============================================================
@app.get("/")
def home():
    return jsonify({"status": "ok", "service": "Scorecard API"})


@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok", "mongodb": "connected"})
    except Exception as e:
        return jsonify({
            "status": "error",
            "mongodb": "disconnected",
            "error": str(e)
        }), 500


# ============================================================
# SAVE SCORECARD
# ============================================================
@app.post("/api/submit-score")
def submit_score():
    try:
        data = request.get_json(silent=True) or {}

        # Accept both names so older/newer test pages work.
        user_id = str(
            data.get("userId") or data.get("uid") or ""
        ).strip()

        test_id = str(
            data.get("testId") or data.get("test") or ""
        ).strip()

        if not user_id:
            return jsonify({
                "success": False,
                "message": "userId is required"
            }), 400

        if not test_id:
            return jsonify({
                "success": False,
                "message": "testId is required"
            }), 400

        scorecard = {
            "userId": user_id,
            "uid": user_id,
            "testId": test_id,
            "testName": data.get("testName") or data.get("test") or test_id,
            "coaching": data.get("coaching", ""),
            "exam": data.get("exam", ""),
            "totalQuestions": data.get("totalQuestions", 0),
            "attempted": data.get("attempted", 0),
            "correct": data.get("correct", 0),
            "wrong": data.get("wrong", 0),
            "unattempted": data.get("unattempted", 0),
            "marks": data.get("marks", 0),
            "maxMarks": data.get("maxMarks", 0),
            "percentage": data.get("percentage", 0),
            "accuracy": data.get("accuracy", 0),
            "timeTaken": data.get("timeTaken", 0),
            "submittedAt": datetime.now(timezone.utc),
        }

        result = scorecards.insert_one(scorecard)

        return jsonify({
            "success": True,
            "message": "Scorecard saved successfully",
            "scorecardId": str(result.inserted_id),
            "userId": user_id,
            "testId": test_id,
        }), 201

    except PyMongoError as e:
        return jsonify({
            "success": False,
            "message": "MongoDB error",
            "error": str(e)
        }), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Server error",
            "error": str(e)
        }), 500


# ============================================================
# SCORECARD HTML PAGE
# This endpoint is intentionally a beautiful HTML page instead
# of raw JSON because the app opens this URL directly.
# ============================================================
@app.get("/api/scorecard")
def get_scorecard():
    try:
        # Supports:
        # ?userId=...&uid=...&testId=...&test=...&coaching=...&exam=...
        user_id = str(
            request.args.get("userId") or request.args.get("uid") or ""
        ).strip()

        test_id = str(
            request.args.get("testId") or request.args.get("test") or ""
        ).strip()

        coaching_param = request.args.get("coaching", "").strip()
        exam_param = request.args.get("exam", "").strip()

        if not user_id:
            return scorecard_error_page(
                "User ID Missing",
                "This scorecard link does not contain a valid User ID."
            ), 400

        if not test_id:
            return scorecard_error_page(
                "Test ID Missing",
                "This scorecard link does not contain a valid Test ID."
            ), 400

        # Exact user + exact test first.
        result = scorecards.find_one(
            {"userId": user_id, "testId": test_id},
            sort=[("submittedAt", -1)]
        )

        # Backward compatibility.
        if not result:
            result = scorecards.find_one(
                {"uid": user_id, "testId": test_id},
                sort=[("submittedAt", -1)]
            )

        if not result:
            result = scorecards.find_one(
                {"userId": user_id, "testName": test_id},
                sort=[("submittedAt", -1)]
            )

        if not result:
            return scorecard_error_page(
                "Scorecard Not Found",
                "You have not submitted this test yet, or the scorecard has not been saved.",
                test_id=test_id
            ), 404

        # Safe display values.
        test_name = escape(str(result.get("testName") or test_id))
        coaching = escape(str(result.get("coaching") or coaching_param or ""))
        exam = escape(str(result.get("exam") or exam_param or ""))
        uid_display = escape(user_id)

        total = result.get("totalQuestions", 0)
        attempted = result.get("attempted", 0)
        correct = result.get("correct", 0)
        wrong = result.get("wrong", 0)
        unattempted = result.get("unattempted", 0)
        marks = result.get("marks", 0)
        max_marks = result.get("maxMarks", 0)
        percentage = result.get("percentage", 0)
        accuracy = result.get("accuracy", 0)
        time_taken = result.get("timeTaken", 0)

        submitted_at = result.get("submittedAt")
        if submitted_at:
            try:
                submitted_text = submitted_at.strftime("%d %b %Y • %I:%M %p")
            except Exception:
                submitted_text = str(submitted_at)
        else:
            submitted_text = "Recently"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Scorecard • {test_name}</title>
<style>
* {{
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
}}
body {{
    margin: 0;
    min-height: 100vh;
    font-family: Arial, Helvetica, sans-serif;
    background: linear-gradient(145deg, #eef2ff 0%, #f8fafc 48%, #ecfeff 100%);
    color: #172554;
}}
.header {{
    padding: 28px 18px 72px;
    color: white;
    background: linear-gradient(135deg, #4f46e5, #7c3aed, #6366f1);
    border-radius: 0 0 34px 34px;
    box-shadow: 0 12px 35px rgba(79,70,229,.28);
}}
.top {{
    max-width: 760px;
    margin: auto;
    display: flex;
    align-items: center;
    gap: 12px;
}}
.back {{
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: 50%;
    color: white;
    background: rgba(255,255,255,.18);
    font-size: 25px;
    cursor: pointer;
}}
.title {{
    font-size: 21px;
    font-weight: 800;
}}
.subtitle {{
    max-width: 760px;
    margin: 12px auto 0;
    padding: 0 4px;
    opacity: .88;
    font-size: 13px;
}}
.container {{
    max-width: 760px;
    margin: -46px auto 30px;
    padding: 0 15px;
    position: relative;
}}
.hero {{
    background: white;
    border-radius: 25px;
    padding: 22px;
    box-shadow: 0 14px 40px rgba(15,23,42,.12);
    text-align: center;
}}
.hero-icon {{
    width: 62px;
    height: 62px;
    margin: -53px auto 12px;
    border-radius: 20px;
    display: grid;
    place-items: center;
    background: linear-gradient(135deg,#8b5cf6,#6366f1);
    color: white;
    font-size: 31px;
    box-shadow: 0 10px 25px rgba(99,102,241,.35);
}}
.test-name {{
    margin: 8px 0 5px;
    font-size: 21px;
    font-weight: 800;
}}
.meta {{
    color: #64748b;
    font-size: 12px;
    line-height: 1.7;
}}
.score {{
    margin: 20px auto 4px;
    width: 150px;
    height: 150px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: conic-gradient(#6366f1 {percentage}%, #e2e8f0 0);
    position: relative;
}}
.score::after {{
    content: "";
    position: absolute;
    width: 116px;
    height: 116px;
    border-radius: 50%;
    background: white;
}}
.score-inner {{
    position: relative;
    z-index: 1;
}}
.percent {{
    font-size: 29px;
    font-weight: 900;
    color: #312e81;
}}
.percent-label {{
    font-size: 11px;
    color: #64748b;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    margin-top: 18px;
}}
.card {{
    background: white;
    border-radius: 18px;
    padding: 17px 14px;
    box-shadow: 0 7px 22px rgba(15,23,42,.07);
}}
.card-label {{
    font-size: 12px;
    color: #64748b;
}}
.card-value {{
    margin-top: 6px;
    font-size: 23px;
    font-weight: 900;
    color: #172554;
}}
.correct .card-value {{ color: #059669; }}
.wrong .card-value {{ color: #dc2626; }}
.unattempted .card-value {{ color: #d97706; }}
.info {{
    margin-top: 14px;
    background: white;
    border-radius: 20px;
    padding: 18px;
    box-shadow: 0 7px 22px rgba(15,23,42,.07);
}}
.info-row {{
    display: flex;
    justify-content: space-between;
    gap: 15px;
    padding: 10px 0;
    border-bottom: 1px solid #eef2f7;
    font-size: 13px;
}}
.info-row:last-child {{ border-bottom: 0; }}
.info-label {{ color: #64748b; }}
.info-value {{ color: #172554; font-weight: 700; text-align: right; }}
.footer {{
    text-align: center;
    padding: 18px;
    color: #94a3b8;
    font-size: 11px;
}}
@media (max-width: 430px) {{
    .header {{ padding-bottom: 68px; }}
    .test-name {{ font-size: 18px; }}
    .score {{ width: 140px; height: 140px; }}
    .score::after {{ width: 108px; height: 108px; }}
}}
</style>
</head>
<body>
<header class="header">
  <div class="top">
    <button class="back" onclick="history.back()" aria-label="Back">‹</button>
    <div class="title">📊 Scorecard</div>
  </div>
  <div class="subtitle">Your test performance summary</div>
</header>

<main class="container">
  <section class="hero">
    <div class="hero-icon">🏆</div>
    <div class="test-name">{test_name}</div>
    <div class="meta">{exam}{(" • " + coaching) if exam and coaching else (exam or coaching)}</div>

    <div class="score">
      <div class="score-inner">
        <div class="percent">{escape(str(percentage))}%</div>
        <div class="percent-label">Percentage</div>
      </div>
    </div>

    <div class="meta">
      Marks: <b>{escape(str(marks))}</b> / {escape(str(max_marks))}
      &nbsp; • &nbsp; Accuracy: <b>{escape(str(accuracy))}%</b>
    </div>
  </section>

  <section class="grid">
    <div class="card">
      <div class="card-label">Total Questions</div>
      <div class="card-value">{escape(str(total))}</div>
    </div>
    <div class="card">
      <div class="card-label">Attempted</div>
      <div class="card-value">{escape(str(attempted))}</div>
    </div>
    <div class="card correct">
      <div class="card-label">Correct</div>
      <div class="card-value">✓ {escape(str(correct))}</div>
    </div>
    <div class="card wrong">
      <div class="card-label">Wrong</div>
      <div class="card-value">✕ {escape(str(wrong))}</div>
    </div>
    <div class="card unattempted">
      <div class="card-label">Unattempted</div>
      <div class="card-value">{escape(str(unattempted))}</div>
    </div>
    <div class="card">
      <div class="card-label">Time Taken</div>
      <div class="card-value">⏱ {escape(str(time_taken))}</div>
    </div>
  </section>

  <section class="info">
    <div class="info-row">
      <span class="info-label">User ID</span>
      <span class="info-value">{uid_display}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Test ID</span>
      <span class="info-value">{escape(test_id)}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Submitted</span>
      <span class="info-value">{escape(submitted_text)}</span>
    </div>
  </section>

  <div class="footer">Scorecard securely loaded from your test records.</div>
</main>
</body>
</html>"""

        return Response(html, mimetype="text/html")

    except PyMongoError as e:
        return scorecard_error_page(
            "MongoDB Error",
            "The scorecard server could not read your result right now."
        ), 500

    except Exception as e:
        return scorecard_error_page(
            "Server Error",
            "Something went wrong while opening the scorecard."
        ), 500


# ============================================================
# BEAUTIFUL ERROR PAGE
# ============================================================
def scorecard_error_page(title, message, test_id=""):
    safe_title = escape(title)
    safe_message = escape(message)
    safe_test = escape(test_id)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
body {{
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 20px;
    font-family: Arial, Helvetica, sans-serif;
    background: linear-gradient(145deg,#eef2ff,#f8fafc);
    color: #172554;
}}
.box {{
    width: min(520px,100%);
    background: white;
    padding: 30px 22px;
    border-radius: 26px;
    text-align: center;
    box-shadow: 0 18px 50px rgba(15,23,42,.14);
}}
.icon {{
    width: 70px;
    height: 70px;
    margin: 0 auto 16px;
    border-radius: 22px;
    display: grid;
    place-items: center;
    background: #fee2e2;
    font-size: 34px;
}}
h1 {{ margin: 0 0 10px; font-size: 22px; }}
p {{ color: #64748b; line-height: 1.6; font-size: 14px; }}
button {{
    border: 0;
    border-radius: 14px;
    padding: 13px 25px;
    background: linear-gradient(135deg,#4f46e5,#7c3aed);
    color: white;
    font-size: 15px;
    font-weight: 800;
    cursor: pointer;
}}
.small {{ margin-top: 18px; font-size: 11px; color: #94a3b8; }}
</style>
</head>
<body>
<div class="box">
    <div class="icon">📊</div>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    {"<p class='small'>Test: " + safe_test + "</p>" if safe_test else ""}
    <button onclick="history.back()">← Go Back</button>
</div>
</body>
</html>"""

    return Response(html, mimetype="text/html")


# ============================================================
# START SERVER
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
