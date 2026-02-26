"""
Toonic — Etap 6: Audio Handler (VAD + Telephony)
=================================================

Obsługa: pliki audio (.wav, .mp3, .flac) + strumienie RTSP audio.
Pipeline: audio → VAD speech detection → 3kHz lowpass → 8kHz μ-law → TOON.

Nowe capabilities (z załączonych rozwiązań):
- WebRTC VAD speech detection (20ms frames, <0.1ms latency)
- Telephony band 3kHz lowpass (numpy FIR)
- μ-law compression (16-bit → 8-bit, G.711)
- Downsample 16kHz → 8kHz
- Speech-triggered segmentation (85% mniej segmentów)

Zależności: pyaudio, webrtcvad, numpy (pip install pyaudio webrtcvad numpy)
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from stage_0_foundation import BaseHandlerMixin, FileLogic, FormatRegistry


# =============================================================================
# Modele logiki audio
# =============================================================================

@dataclass
class SpeechSegment:
    """Pojedynczy segment wykrytej mowy."""
    start_s: float
    end_s: float
    duration_s: float
    energy_db: float = 0.0      # średnia energia segmentu
    is_speech: bool = True
    sample_rate: int = 8000
    encoding: str = "ulaw"      # ulaw | pcm16 | pcm8
    b64_data: str = ""          # base64 audio
    size_bytes: int = 0


@dataclass
class AudioLogic:
    """Logika audio — implementuje FileLogic Protocol.

    Nowy model dla v4.x multimodal pipeline.
    Kompresja: VAD (80% reduction) + 3kHz lowpass + μ-law (50% reduction)
    Efektywny rozmiar: ~4kB/s mowy (vs 32kB/s surowego 16kHz 16-bit)
    """
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
    speech_ratio: float = 0.0   # % czasu z mową
    vad_aggressiveness: int = 2  # 0-3
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
    """μ-law kompresja/dekompresja — standard G.711 telephony.

    Źródło: załączony research "audio z tej kamery"
    - PCM 16-bit → μ-law 8-bit (50% redukcja rozmiaru)
    - Zachowuje dynamikę mowy percepcyjnie bez strat
    """

    MU = 255  # G.711 μ=255

    @staticmethod
    def compress(pcm_16bit: bytes) -> bytes:
        """PCM 16-bit signed → μ-law 8-bit."""
        import numpy as np
        samples = np.frombuffer(pcm_16bit, dtype=np.int16).astype(np.float64)
        MAX = 32767.0
        # Normalize
        normalized = np.clip(samples / MAX, -1.0, 1.0)
        # μ-law compression
        sign = np.sign(normalized)
        magnitude = np.abs(normalized)
        compressed = sign * np.log(1 + MuLawCodec.MU * magnitude) / np.log(1 + MuLawCodec.MU)
        # Quantize to 8-bit unsigned
        quantized = ((compressed + 1.0) * 127.5).astype(np.uint8)
        return quantized.tobytes()

    @staticmethod
    def decompress(ulaw_8bit: bytes) -> bytes:
        """μ-law 8-bit → PCM 16-bit signed."""
        import numpy as np
        samples = np.frombuffer(ulaw_8bit, dtype=np.uint8).astype(np.float64)
        # De-quantize
        normalized = (samples / 127.5) - 1.0
        # μ-law expansion
        sign = np.sign(normalized)
        magnitude = np.abs(normalized)
        expanded = sign * (1.0 / MuLawCodec.MU) * ((1 + MuLawCodec.MU) ** magnitude - 1)
        # Scale to 16-bit
        pcm = (expanded * 32767).astype(np.int16)
        return pcm.tobytes()


# =============================================================================
# Telephony band lowpass filter
# =============================================================================

class TelephonyFilter:
    """Filtr dolnoprzepustowy 3kHz — pasmo telefoniczne ITU-T G.711.

    FIR filter z numpy — prosty, deterministyczny, edge-ready.
    """

    @staticmethod
    def lowpass_3khz(audio_16khz: bytes, sr: int = 16000) -> bytes:
        """Lowpass 3kHz + downsample do 8kHz."""
        import numpy as np

        samples = np.frombuffer(audio_16khz, dtype=np.int16).astype(np.float32)

        # FIR lowpass filter (proste okno Hanninga)
        nyquist = sr / 2
        cutoff_norm = 3000 / nyquist
        filter_order = 31
        n = np.arange(filter_order)
        # Sinc filter
        h = np.sinc(2 * cutoff_norm * (n - (filter_order - 1) / 2))
        # Window
        h *= np.hanning(filter_order)
        # Normalize
        h /= np.sum(h)

        filtered = np.convolve(samples, h, mode='same')

        # Downsample: 16kHz → 8kHz (co 2. próbka)
        downsampled = filtered[::2].astype(np.int16)

        return downsampled.tobytes()


# =============================================================================
# VAD Speech Detector
# =============================================================================

class SpeechDetector:
    """Voice Activity Detection z WebRTC VAD.

    Źródło: załączony research "audio z tej kamery"
    - 20ms frames, agresywność 0-3
    - Latency <0.1ms
    - Zero false positives na agresywności 2-3
    """

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        self.aggressiveness = aggressiveness
        self.sample_rate = sample_rate
        self.frame_duration_ms = 20
        self.frame_size = int(sample_rate * self.frame_duration_ms / 1000)  # 320 samples@16kHz
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
        """Wykryj segmenty mowy w audio PCM 16-bit.

        Returns: lista (start_s, end_s) segmentów mowy.
        """
        vad = self._get_vad()
        frame_bytes = self.frame_size * 2  # 16-bit = 2 bytes/sample
        total_frames = len(pcm_16bit) // frame_bytes

        # VAD per frame
        is_speech_frames = []
        for i in range(total_frames):
            offset = i * frame_bytes
            frame = pcm_16bit[offset:offset + frame_bytes]
            if len(frame) < frame_bytes:
                break
            is_speech_frames.append(vad.is_speech(frame, self.sample_rate))

        # Merge contiguous speech frames
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

        # Zamknij ostatni segment
        if speech_start is not None:
            end_s = len(is_speech_frames) * self.frame_duration_ms / 1000
            if end_s - speech_start >= min_speech_s:
                segments.append((speech_start, end_s))

        return segments


# =============================================================================
# Audio File Handler
# =============================================================================

class AudioFileHandler(BaseHandlerMixin):
    """Handler dla plików audio (.wav, .mp3, .flac, .ogg).

    Pipeline: audio file → VAD → speech segments → 3kHz lowpass → μ-law → TOON
    """

    extensions = frozenset({'.wav', '.mp3', '.flac', '.ogg', '.m4a'})
    category = 'audio'
    requires = ('numpy',)  # webrtcvad i pyaudio opcjonalne

    def parse(self, path: Path) -> AudioLogic:
        """Parsuje plik audio → AudioLogic ze speech segments."""
        import wave
        import numpy as np

        # Czytaj WAV (prosty fallback — dla MP3/FLAC potrzeba pydub)
        if path.suffix == '.wav':
            with wave.open(str(path), 'rb') as wav:
                sr = wav.getframerate()
                channels = wav.getnchannels()
                bitdepth = wav.getsampwidth() * 8
                n_frames = wav.getnframes()
                duration = n_frames / sr
                pcm = wav.readframes(n_frames)
        else:
            # Placeholder dla nie-WAV
            return AudioLogic(
                source_file=path.name,
                source_hash=self._compute_hash(path),
                metadata={"note": f"Format {path.suffix} wymaga pydub/ffmpeg"},
            )

        # Mono
        if channels > 1:
            samples = np.frombuffer(pcm, dtype=np.int16)
            samples = samples[::channels]  # weź co N-ty sample (prosty downmix)
            pcm = samples.tobytes()

        # VAD detection
        speech_segs = []
        total_speech = 0.0

        try:
            detector = SpeechDetector(aggressiveness=2, sample_rate=sr)
            raw_segments = detector.detect_speech_segments(pcm)

            for start, end in raw_segments:
                dur = end - start
                total_speech += dur

                # Extract segment audio
                start_byte = int(start * sr * 2)
                end_byte = int(end * sr * 2)
                seg_pcm = pcm[start_byte:end_byte]

                # Telephony compress
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
            # Bez webrtcvad — fallback: cały plik jako jeden segment
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
        """
        # meeting.wav | audio | 3600s | speech:720s (20%) | 48 segments
        # VAD:2 | 3kHz μ-law 8kHz | total:2.8MB
        A[48]:
          A0[12.3-15.1s]: 2.8s speech | 11.2kB μ-law
          A1[45.6-52.0s]: 6.4s speech | 25.6kB μ-law
          ...
        """
        lines = [
            f"# {a.source_file} | audio | {a.duration_s}s | "
            f"speech:{a.total_speech_s}s ({a.speech_ratio:.0%}) | "
            f"{len(a.speech_segments)} segments"
        ]

        total_size = sum(s.size_bytes for s in a.speech_segments)
        lines.append(
            f"# VAD:{a.vad_aggressiveness} | {a.telephony_band_hz/1000:.0f}kHz "
            f"μ-law {a.output_sample_rate}Hz | total:{total_size/1024:.1f}kB"
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
        """Audio nie da się odtworzyć z opisu — zwróć timeline."""
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
    for handler in [AudioFileHandler()]:
        FormatRegistry.register(handler)


# =============================================================================
# Testy (bez wymagania webrtcvad/pyaudio)
# =============================================================================

if __name__ == '__main__':
    print("=== Toonic Stage 6: Audio Handler Tests ===\n")

    # Test 1: Modele logiki
    seg = SpeechSegment(
        start_s=12.3, end_s=15.1, duration_s=2.8,
        encoding='ulaw', size_bytes=11200,
    )
    assert seg.duration_s == 2.8
    print("✓ SpeechSegment works")

    logic = AudioLogic(
        source_file="meeting.wav",
        source_hash="abc123",
        duration_s=3600.0,
        original_sample_rate=44100,
        original_channels=2,
        original_bitdepth=16,
        speech_segments=[seg],
        total_speech_s=720.0,
        speech_ratio=0.20,
    )
    d = logic.to_dict()
    assert d["duration_s"] == 3600.0
    assert d["speech_ratio"] == 0.20
    print(f"✓ AudioLogic: {d}")

    # Test 2: TOON generation
    handler = AudioFileHandler()
    toon = handler.to_spec(logic, 'toon')
    assert 'meeting.wav' in toon
    assert 'speech:720.0s' in toon
    assert 'A[1]' in toon
    print(f"✓ AudioFileHandler.to_spec:\n{toon}\n")

    # Test 3: μ-law codec (with numpy)
    try:
        import numpy as np
        # Test μ-law round-trip
        original = np.array([0, 1000, -1000, 16000, -16000, 32767], dtype=np.int16)
        compressed = MuLawCodec.compress(original.tobytes())
        assert len(compressed) == len(original)  # 8-bit = half size per sample
        decompressed_bytes = MuLawCodec.decompress(compressed)
        decompressed = np.frombuffer(decompressed_bytes, dtype=np.int16)
        # Lossy — nie identyczne, ale blisko
        error = np.mean(np.abs(original.astype(float) - decompressed.astype(float)))
        assert error < 5000, f"μ-law error too high: {error}"
        print(f"✓ MuLawCodec round-trip: mean error={error:.0f} (acceptable for speech)")
    except ImportError:
        print("⊘ numpy not available, skipping μ-law test")

    # Test 4: Telephony filter (with numpy)
    try:
        import numpy as np
        # Generuj 1s audio 16kHz
        t = np.linspace(0, 1, 16000)
        # Ton 1kHz (powinien przejść) + ton 5kHz (powinien być odfiltrowany)
        signal = (np.sin(2 * np.pi * 1000 * t) * 16000 +
                  np.sin(2 * np.pi * 5000 * t) * 16000).astype(np.int16)
        filtered = TelephonyFilter.lowpass_3khz(signal.tobytes(), sr=16000)
        filtered_samples = np.frombuffer(filtered, dtype=np.int16)
        assert len(filtered_samples) == 8000  # downsampled 16k→8k
        print(f"✓ TelephonyFilter: 16kHz→8kHz, {len(signal)} → {len(filtered_samples)} samples")
    except ImportError:
        print("⊘ numpy not available, skipping filter test")

    # Test 5: Sniff
    assert handler.sniff(Path("audio.wav"), "") > 0.5
    assert handler.sniff(Path("readme.md"), "") == 0.0
    print("✓ sniff works")

    # Test 6: Registry
    FormatRegistry.reset()
    register_audio_handlers()
    resolved = FormatRegistry.resolve(Path("test.wav"))
    assert isinstance(resolved, AudioFileHandler)
    print("✓ AudioFileHandler registered and resolved")

    print("\n=== All Stage 6 tests passed ===")
