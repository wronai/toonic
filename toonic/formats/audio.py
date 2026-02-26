"""
Audio handlers — VAD speech detection, telephony filter, μ-law compression
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toonic.core.base import BaseHandlerMixin
from toonic.core.registry import FormatRegistry


# =============================================================================
# Modele logiki audio
# =============================================================================

@dataclass
class SpeechSegment:
    """Pojedynczy segment wykrytej mowy."""
    start_s: float
    end_s: float
    duration_s: float
    energy_db: float = 0.0
    is_speech: bool = True
    sample_rate: int = 8000
    encoding: str = "ulaw"
    b64_data: str = ""
    size_bytes: int = 0


@dataclass
class AudioLogic:
    """Logika audio — implementuje FileLogic Protocol."""
    source_file: str
    source_hash: str
    file_category: str = "audio"

    duration_s: float = 0.0
    original_sample_rate: int = 0
    original_channels: int = 0
    original_bitdepth: int = 0
    codec: str = ""

    speech_segments: List[SpeechSegment] = field(default_factory=list)
    total_speech_s: float = 0.0
    speech_ratio: float = 0.0
    vad_aggressiveness: int = 2
    telephony_band_hz: int = 3000
    output_sample_rate: int = 8000

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "duration_s": self.duration_s,
            "original_sr": self.original_sample_rate,
            "speech_segments": len(self.speech_segments),
            "total_speech_s": round(self.total_speech_s, 2),
            "speech_ratio": round(self.speech_ratio, 2),
            "telephony_band_hz": self.telephony_band_hz,
            "output_sr": self.output_sample_rate,
        }

    def complexity(self) -> int:
        return len(self.speech_segments) * 2 + int(self.duration_s / 10)


# =============================================================================
# μ-law kompresja (G.711)
# =============================================================================

class MuLawCodec:
    """μ-law kompresja/dekompresja — standard G.711 telephony."""

    MU = 255

    @staticmethod
    def compress(pcm_16bit: bytes) -> bytes:
        import numpy as np
        samples = np.frombuffer(pcm_16bit, dtype=np.int16).astype(np.float64)
        MAX = 32767.0
        normalized = np.clip(samples / MAX, -1.0, 1.0)
        sign = np.sign(normalized)
        magnitude = np.abs(normalized)
        compressed = sign * np.log(1 + MuLawCodec.MU * magnitude) / np.log(1 + MuLawCodec.MU)
        quantized = ((compressed + 1.0) * 127.5).astype(np.uint8)
        return quantized.tobytes()

    @staticmethod
    def decompress(ulaw_8bit: bytes) -> bytes:
        import numpy as np
        samples = np.frombuffer(ulaw_8bit, dtype=np.uint8).astype(np.float64)
        normalized = (samples / 127.5) - 1.0
        sign = np.sign(normalized)
        magnitude = np.abs(normalized)
        expanded = sign * (1.0 / MuLawCodec.MU) * ((1 + MuLawCodec.MU) ** magnitude - 1)
        pcm = (expanded * 32767).astype(np.int16)
        return pcm.tobytes()


# =============================================================================
# Telephony band lowpass filter
# =============================================================================

class TelephonyFilter:
    """Filtr dolnoprzepustowy 3kHz — pasmo telefoniczne ITU-T G.711."""

    @staticmethod
    def lowpass_3khz(audio_16khz: bytes, sr: int = 16000) -> bytes:
        import numpy as np

        samples = np.frombuffer(audio_16khz, dtype=np.int16).astype(np.float32)

        nyquist = sr / 2
        cutoff_norm = 3000 / nyquist
        filter_order = 31
        n = np.arange(filter_order)
        h = np.sinc(2 * cutoff_norm * (n - (filter_order - 1) / 2))
        h *= np.hanning(filter_order)
        h /= np.sum(h)

        filtered = np.convolve(samples, h, mode='same')

        downsampled = filtered[::2].astype(np.int16)

        return downsampled.tobytes()


# =============================================================================
# VAD Speech Detector
# =============================================================================

class SpeechDetector:
    """Voice Activity Detection z WebRTC VAD."""

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        self.aggressiveness = aggressiveness
        self.sample_rate = sample_rate
        self.frame_duration_ms = 20
        self.frame_size = int(sample_rate * self.frame_duration_ms / 1000)
        self._vad = None

    def _get_vad(self):
        if self._vad is None:
            import webrtcvad
            self._vad = webrtcvad.Vad(self.aggressiveness)
        return self._vad

    def detect_speech_segments(
        self,
        pcm_16bit: bytes,
        min_speech_s: float = 0.3,
        min_silence_s: float = 0.5,
    ) -> List[Tuple[float, float]]:
        vad = self._get_vad()
        frame_bytes = self.frame_size * 2
        total_frames = len(pcm_16bit) // frame_bytes

        is_speech_frames = []
        for i in range(total_frames):
            offset = i * frame_bytes
            frame = pcm_16bit[offset:offset + frame_bytes]
            if len(frame) < frame_bytes:
                break
            is_speech_frames.append(vad.is_speech(frame, self.sample_rate))

        segments = []
        speech_start = None
        silence_count = 0
        min_silence_frames = int(min_silence_s * 1000 / self.frame_duration_ms)
        min_speech_frames = int(min_speech_s * 1000 / self.frame_duration_ms)

        for i, is_speech in enumerate(is_speech_frames):
            time_s = i * self.frame_duration_ms / 1000

            if is_speech:
                if speech_start is None:
                    speech_start = time_s
                silence_count = 0
            else:
                silence_count += 1
                if speech_start is not None and silence_count >= min_silence_frames:
                    end_s = time_s - silence_count * self.frame_duration_ms / 1000
                    duration = end_s - speech_start
                    if duration >= min_speech_s:
                        segments.append((speech_start, end_s))
                    speech_start = None

        if speech_start is not None:
            end_s = len(is_speech_frames) * self.frame_duration_ms / 1000
            if end_s - speech_start >= min_speech_s:
                segments.append((speech_start, end_s))

        return segments


# =============================================================================
# Audio File Handler
# =============================================================================

class AudioFileHandler(BaseHandlerMixin):
    """Handler dla plików audio (.wav, .mp3, .flac, .ogg)."""

    extensions = frozenset({'.wav', '.mp3', '.flac', '.ogg', '.m4a'})
    category = 'audio'
    requires = ('numpy',)

    def parse(self, path: Path) -> AudioLogic:
        import wave
        import numpy as np

        if path.suffix == '.wav':
            with wave.open(str(path), 'rb') as wav:
                sr = wav.getframerate()
                channels = wav.getnchannels()
                bitdepth = wav.getsampwidth() * 8
                n_frames = wav.getnframes()
                duration = n_frames / sr
                pcm = wav.readframes(n_frames)
        else:
            return AudioLogic(
                source_file=path.name,
                source_hash=self._compute_hash(path),
                metadata={"note": f"Format {path.suffix} wymaga pydub/ffmpeg"},
            )

        if channels > 1:
            samples = np.frombuffer(pcm, dtype=np.int16)
            samples = samples[::channels]
            pcm = samples.tobytes()

        speech_segs = []
        total_speech = 0.0

        try:
            detector = SpeechDetector(aggressiveness=2, sample_rate=sr)
            raw_segments = detector.detect_speech_segments(pcm)

            for start, end in raw_segments:
                dur = end - start
                total_speech += dur

                start_byte = int(start * sr * 2)
                end_byte = int(end * sr * 2)
                seg_pcm = pcm[start_byte:end_byte]

                if sr >= 16000:
                    telephony = TelephonyFilter.lowpass_3khz(seg_pcm, sr)
                else:
                    telephony = seg_pcm

                ulaw = MuLawCodec.compress(telephony) if len(telephony) > 0 else b''

                speech_segs.append(SpeechSegment(
                    start_s=round(start, 2),
                    end_s=round(end, 2),
                    duration_s=round(dur, 2),
                    sample_rate=8000,
                    encoding='ulaw',
                    b64_data=base64.b64encode(ulaw).decode(),
                    size_bytes=len(ulaw),
                ))

        except ImportError:
            speech_segs.append(SpeechSegment(
                start_s=0, end_s=duration, duration_s=duration,
                sample_rate=sr, encoding='pcm16',
            ))
            total_speech = duration

        return AudioLogic(
            source_file=path.name,
            source_hash=self._compute_hash(path),
            duration_s=round(duration, 2),
            original_sample_rate=sr,
            original_channels=channels,
            original_bitdepth=bitdepth,
            speech_segments=speech_segs,
            total_speech_s=round(total_speech, 2),
            speech_ratio=round(total_speech / max(duration, 0.01), 2),
        )

    def to_spec(self, logic: AudioLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            return self._to_toon(logic)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def _to_toon(self, a: AudioLogic) -> str:
        lines = [
            f"# {a.source_file} | audio | {a.duration_s}s | "
            f"speech:{a.total_speech_s}s ({a.speech_ratio:.0%}) | "
            f"{len(a.speech_segments)} segments"
        ]

        total_size = sum(s.size_bytes for s in a.speech_segments)
        lines.append(
            f"# VAD:{a.vad_aggressiveness} | {a.telephony_band_hz/1000:.0f}kHz "
            f"u-law {a.output_sample_rate}Hz | total:{total_size/1024:.1f}kB"
        )

        if a.speech_segments:
            lines.append(f"A[{len(a.speech_segments)}]:")
            for i, seg in enumerate(a.speech_segments):
                lines.append(
                    f"  A{i}[{seg.start_s:.1f}-{seg.end_s:.1f}s]: "
                    f"{seg.duration_s:.1f}s {seg.encoding} | "
                    f"{seg.size_bytes/1024:.1f}kB"
                )

        return '\n'.join(lines)

    def reproduce(self, logic: AudioLogic, client: Any = None, target_fmt: str | None = None) -> str:
        lines = [f"# Audio timeline: {logic.source_file}"]
        for seg in logic.speech_segments:
            lines.append(f"[{seg.start_s:.1f}s-{seg.end_s:.1f}s] speech ({seg.encoding})")
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        return 0.8 if path.suffix.lower() in self.extensions else 0.0


# =============================================================================
# Rejestracja
# =============================================================================

def register_audio_handlers() -> None:
    FormatRegistry.register(AudioFileHandler())
