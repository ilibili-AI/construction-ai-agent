import base64
import io
from typing import Optional
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, DEEPGRAM_API_KEY, ENABLE_TTS


def elevenlabs_ready() -> bool:
    return bool(ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)


def deepgram_ready() -> bool:
    return bool(DEEPGRAM_API_KEY)


def make_elevenlabs_audio_base64(text: str) -> str:
    if not elevenlabs_ready():
        return ""
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.generate(
            text=text[:900],
            voice=ELEVENLABS_VOICE_ID,
            model="eleven_multilingual_v2",
        )
        data = b"".join(audio)
        return base64.b64encode(data).decode("utf-8")
    except Exception as e:
        print(f"[Voice] ElevenLabs error: {e}")
        return ""


def make_gtts_audio_base64(text: str) -> str:
    try:
        from gtts import gTTS
        buffer = io.BytesIO()
        tts = gTTS(text=text[:900], lang="en")
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")
    except Exception as e:
        print(f"[Voice] gTTS error: {e}")
        return ""


def make_audio_base64(text: str) -> str:
    if not ENABLE_TTS:
        return ""
    if elevenlabs_ready():
        result = make_elevenlabs_audio_base64(text)
        if result:
            return result
    return make_gtts_audio_base64(text)


def speech_to_text(audio_data: bytes) -> str:
    if not deepgram_ready():
        print("[Voice] Deepgram not configured")
        return ""
    try:
        from deepgram import DeepgramClient, PrerecordedOptions
        client = DeepgramClient(DEEPGRAM_API_KEY)
        payload = {"buffer": audio_data}
        options = PrerecordedOptions(model="nova-2", language="en-US")
        response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
        return response.results.channels[0].alternatives[0].transcript
    except Exception as e:
        print(f"[Voice] Deepgram error: {e}")
        return ""


def text_to_speech(text: str) -> bytes:
    if elevenlabs_ready():
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            audio = client.generate(
                text=text[:900],
                voice=ELEVENLABS_VOICE_ID,
                model="eleven_multilingual_v2",
            )
            return b"".join(audio)
        except Exception as e:
            print(f"[Voice] ElevenLabs TTS error: {e}")
    try:
        from gtts import gTTS
        buffer = io.BytesIO()
        tts = gTTS(text=text[:900], lang="en")
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        print(f"[Voice] gTTS fallback error: {e}")
        return b""