"""Local transcription with faster-whisper (CPU, int8, no API key). Slow fallback."""

from __future__ import annotations

import tempfile
import time
import wave
from pathlib import Path

from .media import extract_audio
from .transcript import DEFAULT_PROMPT, count_words, scribe_words, write_transcript


def load_model(name: str, threads: int):
    from faster_whisper import WhisperModel

    model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)
    print(f"  whisper model {name} on cpu/int8 ({threads} threads)", flush=True)
    return model


def transcribe_to(model, video: Path, out: Path, language: str | None, audio_track: int = 0,
                  prompt: str | None = DEFAULT_PROMPT) -> str:
    import numpy as np

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        extract_audio(video, wav, audio_track)
        # Decode ourselves: faster-whisper's own decoder breaks on newer PyAV releases.
        with wave.open(str(wav), "rb") as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
        segments, info = model.transcribe(
            audio,
            language=language,
            word_timestamps=True,
            vad_filter=False,                  # keep real silences; we cut them ourselves
            condition_on_previous_text=False,  # fewer hallucinated repeats on long takes
            initial_prompt=prompt,
        )
        words = scribe_words(
            {"text": w.word, "start": w.start, "end": w.end, "logprob": round(w.probability, 3)}
            for seg in segments for w in (seg.words or [])
        )
    write_transcript(out, "faster-whisper", info.language, words)
    return f"saved ({count_words(words)} words, local whisper) in {time.time() - t0:.0f}s"
