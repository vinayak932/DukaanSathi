import os
import tempfile
from pathlib import Path
from flask import Blueprint, request, jsonify
from flask_login import login_required
from services.gnani_service import transcribe_audio
from flask import current_app as app
from services.intent_parser import detect_intent

voice = Blueprint("voice", __name__)

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".aac"
}


@voice.route("/voice/transcribe", methods=["POST"])
@login_required
def transcribe():
    audio = request.files.get("audio")

    if not audio or not audio.filename:
        return jsonify({
            "success": False,
            "error": "No audio file received."
        }), 400

    extension = Path(audio.filename).suffix.lower()

    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported audio file format."
        }), 400

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
                suffix=extension,
                delete=False
        ) as temp_file:
            temp_path = temp_file.name
            audio.save(temp_path)

        # Limit uploaded audio to 16 MB.
        if os.path.getsize(temp_path) > 16 * 1024 * 1024:
            return jsonify({
                "success": False,
                "error": "Audio file is too large. Maximum size is 16 MB."
            }), 413

        result = transcribe_audio(
            temp_path,
            language_code="hi-IN"
        )

        # Extract transcript
        transcript = result.get("transcript", "").strip()

        # Detect user intent
        intent = detect_intent(transcript)

        # Add intent to response
        result["intent"] = intent

        return jsonify(result), 200

    except Exception as error:
        print("GNANI TRANSCRIPTION ERROR:", repr(error))
        app.logger.exception("Voice transcription failed")

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
