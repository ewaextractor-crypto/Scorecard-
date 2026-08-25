import os
from datetime import datetime, timezone
from flask import Flask, jsonify, request
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

# Allow the GitHub-hosted test/app to call this API.
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

@app.get("/")
def home():
    return jsonify({"status": "ok", "service": "Scorecard API"})

@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok", "mongodb": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "mongodb": "disconnected", "error": str(e)}), 500

@app.post("/api/submit-score")
def submit_score():
    try:
        data = request.get_json(silent=True) or {}

        # Accept both names so older/newer test pages work.
        user_id = str(data.get("userId") or data.get("uid") or "").strip()
        test_id = str(data.get("testId") or data.get("test") or "").strip()

        if not user_id:
            return jsonify({"success": False, "message": "userId is required"}), 400
        if not test_id:
            return jsonify({"success": False, "message": "testId is required"}), 400

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
        return jsonify({"success": False, "message": "MongoDB error", "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "message": "Server error", "error": str(e)}), 500

@app.get("/api/scorecard")
def get_scorecard():
    try:
        # Supports the exact URL format the app is currently generating:
        # ?userId=...&uid=...&testId=...&test=...&coaching=...&exam=...
        user_id = str(request.args.get("userId") or request.args.get("uid") or "").strip()
        test_id = str(request.args.get("testId") or request.args.get("test") or "").strip()

        if not user_id:
            return jsonify({"success": False, "message": "userId is required"}), 400
        if not test_id:
            return jsonify({"success": False, "message": "testId is required"}), 400

        # First try the exact user + test pair. This is what guarantees that
        # one user's scorecard cannot be confused with another test's result.
        query = {"userId": user_id, "testId": test_id}
        result = scorecards.find_one(query, sort=[("submittedAt", -1)])

        # Backward compatibility for records created with uid/test aliases.
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
            return jsonify({
                "success": False,
                "message": "Scorecard not found",
                "userId": user_id,
                "testId": test_id,
            }), 404

        result["_id"] = str(result["_id"])
        return jsonify({"success": True, "scorecard": result})

    except PyMongoError as e:
        return jsonify({"success": False, "message": "MongoDB error", "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "message": "Server error", "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
