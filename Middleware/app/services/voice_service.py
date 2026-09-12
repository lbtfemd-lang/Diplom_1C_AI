import os
import sys
import base64
import logging
import re
import io
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class VoiceService:
    def __init__(self):
        self._record_process = None
        self._temp_wav_path = os.path.join(os.environ.get("TEMP", "."), "1c_ai_voice_input.wav")

    @property
    def gemini_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def groq_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    @property
    def openai_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    def start_recording(self) -> Dict[str, Any]:
        """Start recording from Windows default microphone using dedicated subprocess"""
        import subprocess
        try:
            if self._record_process and self._record_process.poll() is None:
                try:
                    self._record_process.kill()
                except Exception as exc:
                    logger.warning("Recorder cleanup failed (%s)", type(exc).__name__)

            if os.path.exists(self._temp_wav_path):
                try:
                    os.remove(self._temp_wav_path)
                except Exception as exc:
                    logger.warning("Temporary audio cleanup failed (%s)", type(exc).__name__)

            recorder_path = os.path.join(os.path.dirname(__file__), "audio_recorder.py")
            self._record_process = subprocess.Popen(
                [sys.executable, recorder_path, self._temp_wav_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logger.info("Voice recording subprocess started (PID: %s)", self._record_process.pid)
            return {"status": "recording"}
        except Exception as e:
            logger.error("Error starting voice recording process: %s", e)
            return {"status": "error", "detail": str(e)}

    async def stop_recording_and_transcribe(self, language: str = "ru") -> Dict[str, Any]:
        """Stop recording subprocess, wait for file save, and transcribe accurately"""
        try:
            if self._record_process and self._record_process.poll() is None:
                try:
                    self._record_process.communicate(input=b"stop\n", timeout=3.0)
                except Exception as e:
                    logger.warning("Error communicating stop to recorder: %s", e)
                    self._record_process.kill()
                self._record_process = None

            logger.info("Voice recording stopped. Checking %s", self._temp_wav_path)
            
            import asyncio
            for _ in range(5):
                if os.path.exists(self._temp_wav_path) and os.path.getsize(self._temp_wav_path) > 1000:
                    break
                await asyncio.sleep(0.1)

            if os.path.exists(self._temp_wav_path) and os.path.getsize(self._temp_wav_path) > 1000:
                with open(self._temp_wav_path, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode("ascii")
                return await self.transcribe_audio(audio_b64, audio_format="wav", language=language)
            else:
                logger.warning("Recorded audio file is empty or too short.")
                return {"text": "", "confidence": 0.0, "detected_language": language}
        except Exception as e:
            logger.error("Error stopping voice recording: %s", e)
            return {"text": "", "error": str(e)}

    async def transcribe_audio(self, audio_base64: str, audio_format: str = "wav", language: str = "ru") -> Dict[str, Any]:
        """
        Fast multi-tier speech recognition:
        1. SpeechRecognition (Google Web Speech) - fast, free, accurate Russian speech-to-text;
        2. Groq Whisper API (if configured);
        3. Gemini Multimodal (if available).
        """
        if not audio_base64 or len(audio_base64.strip()) == 0:
            return {"text": "", "confidence": 0.0, "detected_language": language}

        audio_bytes = base64.b64decode(audio_base64)

        # 0. Convert any format (OGG OPUS from Telegram, MP3, FLAC) to PCM WAV in memory
        try:
            import soundfile as sf
            data, samplerate = sf.read(io.BytesIO(audio_bytes))
            wav_io = io.BytesIO()
            sf.write(wav_io, data, samplerate, format='WAV', subtype='PCM_16')
            audio_bytes = wav_io.getvalue()
            logger.info("Decoded audio (%s) to WAV PCM (%d Hz, %d samples)", audio_format, samplerate, len(data))
        except Exception as e:
            logger.info("Direct soundfile conversion skipped or raw: %s", e)

        # 0.5. Try Domestic Yandex SpeechKit (Отечественный стек)
        yandex_stt_key = os.getenv("YANDEX_SPEECHKIT_API_KEY") or os.getenv("YANDEX_API_KEY")
        if yandex_stt_key and not yandex_stt_key.startswith("your_"):
            try:
                yandex_text = await self._transcribe_yandex(audio_bytes, language=language)
                if yandex_text:
                    yandex_text = self._normalize_1c_business_text(yandex_text)
                    logger.info("Transcribed via Yandex SpeechKit [Отечественный стек]: '%s'", yandex_text)
                    return {"text": yandex_text, "confidence": 0.99, "detected_language": language}
            except Exception as e:
                logger.warning("Yandex SpeechKit transcription failed: %s", e)

        # 1. Try Fast SpeechRecognition (Google Web Speech API)
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            audio_io = io.BytesIO(audio_bytes)
            with sr.AudioFile(audio_io) as source:
                audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ru-RU")
            if text:
                text = self._normalize_1c_business_text(text)
                logger.info("Transcribed via SpeechRecognition: '%s'", text)
                return {"text": text, "confidence": 0.98, "detected_language": language}
        except Exception as e:
            logger.warning("SpeechRecognition attempt failed: %s", e)

        # 2. Try Gemini Multimodal Speech Transcription (high accuracy, domain-aware)
        if self.gemini_key and not self.gemini_key.startswith("your_"):
            try:
                wav_b64 = base64.b64encode(audio_bytes).decode("ascii")
                gemini_text = await self._transcribe_gemini(wav_b64, mime_type="audio/wav")
                if gemini_text:
                    gemini_text = self._normalize_1c_business_text(gemini_text)
                    logger.info("Transcribed via Gemini Multimodal: '%s'", gemini_text)
                    return {"text": gemini_text, "confidence": 0.99, "detected_language": language}
            except Exception as e:
                logger.warning("Gemini voice transcription failed: %s", e)

        # 3. Try Groq Whisper if key is present
        if self.groq_key and not self.groq_key.startswith("your_"):
            try:
                text = await self._transcribe_groq(audio_base64, audio_format, language)
                if text:
                    text = self._normalize_1c_business_text(text)
                    return {"text": text, "confidence": 0.99, "detected_language": language}
            except Exception as e:
                logger.warning("Groq whisper transcription failed: %s", e)

        # Return empty if nothing spoken (no dummy fallback text!)
        return {
            "text": "",
            "confidence": 0.0,
            "detected_language": language
        }

    async def _transcribe_gemini(self, audio_base64: str, mime_type: str = "audio/wav") -> Optional[str]:
        """Transcribes speech using Google Gemini Flash Multimodal Audio understanding"""
        if not self.gemini_key or self.gemini_key.startswith("your_"):
            return None
        try:
            import httpx
            if "NO_PROXY" in os.environ and "::" in os.environ["NO_PROXY"]:
                os.environ["NO_PROXY"] = ",".join([p for p in os.environ["NO_PROXY"].split(",") if "::" not in p])

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": audio_base64}},
                        {"text": "Точно расшифруй русскую речь из этой аудиозаписи для системы 1С:Предприятие. Верни ТОЛЬКО расшифрованный текст, без кавычек, пояснений и временных меток. Если в записи только тишина, верни пустоту."}
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 200
                }
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        if raw_text and not re.match(r'^\d+:\d+$', raw_text):
                            return raw_text
        except Exception as e:
            logger.warning("Gemini voice transcription error: %s", e)
        return None

    async def _transcribe_yandex(self, audio_bytes: bytes, language: str = "ru") -> Optional[str]:
        """Transcribes speech using domestic Yandex SpeechKit API (Российский стек)"""
        import httpx
        api_key = os.getenv("YANDEX_SPEECHKIT_API_KEY") or os.getenv("YANDEX_API_KEY")
        if not api_key:
            return None
        folder_id = os.getenv("YANDEX_FOLDER_ID", "")
        params = {"topic": "general", "lang": "ru-RU", "format": "lpcm", "sampleRateHertz": 16000}
        if folder_id:
            params["folderId"] = folder_id
        headers = {"Authorization": f"Api-Key {api_key}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://stt.api.cloud.yandex.net/speech/v1/stt:recognize", params=params, headers=headers, content=audio_bytes)
            if resp.status_code == 200:
                return resp.json().get("result", "").strip()
        return None

    async def _transcribe_groq(self, audio_base64: str, audio_format: str, language: str) -> Optional[str]:
        import httpx
        audio_bytes = base64.b64decode(audio_base64)
        files = {'file': (f'audio.{audio_format}', audio_bytes, f'audio/{audio_format}')}
        headers = {"Authorization": f"Bearer {self.groq_key}"}
        data = {"model": "whisper-large-v3-turbo", "language": language}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
        return None

    def _normalize_1c_business_text(self, text: str) -> str:
        """
        Normalize numbers, quantities, and common 1C terms in spoken text.
        """
        if not text:
            return ""
        
        cleaned = text.strip()
        cleaned = cleaned.replace("«", "").replace("»", "").replace('"', "")
        
        replacements = [
            (r'\bодин\b', '1'), (r'\bдва\b', '2'), (r'\bтри\b', '3'), (r'\bчетыре\b', '4'),
            (r'\bпять\b', '5'), (r'\bшесть\b', '6'), (r'\bсемь\b', '7'), (r'\bвосемь\b', '8'),
            (r'\bдевять\b', '9'), (r'\bдесять\b', '10'),
            (r'\bштук\b', 'шт'), (r'\bштуки\b', 'шт'), (r'\bштука\b', 'шт'),
            (r'\bрублей\b', 'руб'), (r'\bрубля\b', 'руб'), (r'\bрубль\b', 'руб'),
            (r'\bметров\b', 'м'), (r'\bметра\b', 'м'), (r'\bметр\b', 'м'),
            (r'\bальфа\s+март\b', 'АльфаМарт', re.IGNORECASE),
            (r'\bлаверна\b', 'Лаверна ООО', re.IGNORECASE),
        ]
        
        for pat, repl, *flags in replacements:
            flag = flags[0] if flags else 0
            cleaned = re.sub(pat, repl, cleaned, flags=flag)
            
        return cleaned

voice_service = VoiceService()
