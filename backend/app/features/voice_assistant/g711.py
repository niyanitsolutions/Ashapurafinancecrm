"""Bounded raw G.711 mu-law/PCM16 frame conversion. No container or resampling.

PCM output remains mono 8 kHz. A model requiring 16 kHz needs a separately tested
resampler; a WAV header or 16 kHz label must never be added to these raw frames.
"""

import struct


def decode_mulaw_frame(frame: bytes) -> bytes:
    if not isinstance(frame, bytes) or len(frame) != 160:
        raise ValueError("Expected one raw 20ms, 8kHz mono mu-law frame.")
    result = []
    for byte in frame:
        value = (~byte) & 255
        sample = (((value & 15) << 3) + 132) << ((value >> 4) & 7)
        result.append(132 - sample if value & 128 else sample - 132)
    return struct.pack("<160h", *result)


def encode_pcm16_frame(frame: bytes) -> bytes:
    if not isinstance(frame, bytes) or len(frame) != 320:
        raise ValueError("Expected one raw 20ms, 8kHz mono signed little-endian PCM16 frame.")
    result = bytearray()
    for sample in struct.unpack("<160h", frame):
        # G.711's 14-bit quantizer, including negative-sample rounding.
        sample >>= 2
        mask = 127 if sample < 0 else 255
        if sample < 0:
            sample = -sample
        sample = min(sample + 33, 8191)
        exponent = max(0, sample.bit_length() - 6)
        mantissa = (sample >> (exponent + 1)) & 15
        result.append(((exponent << 4) | mantissa) ^ mask)
    return bytes(result)
