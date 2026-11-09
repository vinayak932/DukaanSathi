import os
from pathlib import Path
from dotenv import load_dotenv
from gnani.stt import GnaniSTTClient
import subprocess
import tempfile

# Load environment variables
load_dotenv()

def transcribe_audio(audio_path, language_code="hi-IN"):
    audio_path = Path(audio_path)

    if not audio_path.is_file():
        raise FileNotFoundError("Audio file not found.")

    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise ValueError("GNANI_API_KEY is missing.")

    # Convert audio to WAV: PCM 16-bit, 16 kHz, mono
    with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False
    ) as wav_file:
        wav_path = Path(wav_file.name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(audio_path),
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
                str(wav_path)
            ],
            check=True,
            capture_output=True,
            text=True
        )

        client = GnaniSTTClient(api_key)

        result = client.transcribe(
            str(wav_path),
            language_code=language_code
        )

        if not result.get("success"):
            raise RuntimeError("Gnani transcription failed.")

        return {
            "success": True,
            "transcript": result.get("transcript", ""),
            "model": result.get("model"),
            "processing_time": result.get("processing_time"),
            "end_to_end_latency": result.get("end_to_end_latency")
        }

    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"FFmpeg conversion failed: {error.stderr[-1000:]}"
        ) from error

    finally:
        if wav_path.exists():
            wav_path.unlink()
