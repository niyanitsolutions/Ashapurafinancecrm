# Airtel VoiceBOT protocol implementation

Authoritative reference: supplied guide v1.0.0, May 2026, pp14–20. Implemented in
`backend/app/features/voice_assistant/airtel_media.py`; **offline codec only**.
The registered live WebSocket is intentionally blocked. This is not an installed
speech runtime or a claim of provider-tested interoperability.

| Direction / event | Validated envelope / behavior |
|---|---|
| In: connected | `event`, `protocol: Call`, `version: 1.0.0`; exactly once, before start |
| In: start | Top-level `streamSid`, nested start stream/account/call identities, caller/called numbers and mediaFormat |
| In: media | `media.payload`: validated Base64, exactly 160 raw μ-law bytes |
| In: dtmf | `dtmf.digit`: one of 0–9, `*`, `#` |
| In: callState | `call.state`: `hold` or `unhold`; blocks generated audio while held |
| In: mark | `mark.name`: must reference an issued mark; duplicates classified explicitly |
| In: stop | `stop.accountSid`, `callSid`, optional nested `streamSid`, all checked against this session |
| Out: media | Top-level event/streamSid, nested Base64 raw μ-law audio |
| Out: mark | Unique bounded per-stream generated `mark.name` |
| Out: clear | Only event/streamSid; invalidates outstanding playback assumptions |
| Out: terminate | Reason code 1 hangup, 2 agent fallback, 3 particular DID; code3 requires E.164 fallbackNumber |

There is **no sequenceNumber** requirement in this guide. This codec does not inherit
Smartflo's sequence contract. `start.mediaFormat` accepts both documented variants
`ulaw` and `audio/x-mulaw`, mono 8kHz. String `"8000"`/`"1"` and matching integers
are accepted; booleans and other formats are rejected. The table's `customParameters`
and example's `customParams` are supported as bounded JSON strings; conflicting
dual values are rejected. Metadata never establishes a verified CRM customer.

Messages are bounded UTF-8 JSON text; binary audio frames are not the guide's
transport. Audio is raw, without RIFF/WAV/AU headers. 160 bytes is 20ms at 8kHz
mono μ-law; outbound 20ms frames fall within the recommended 20–40ms. The codec
rejects changed account/call/stream identities, unknown envelopes, oversized or
malformed payloads, output after stop and repeated termination. Unacknowledged
marks are capped at 256; overload fails explicitly rather than growing forever.

**Clear can generate mark echoes for flushed audio.** Issued marks transition
`sent → played` on normal echo; clear transitions outstanding marks to `cleared`,
and subsequent echoes to `clear_acknowledged`, never `played`. Duplicate echoes
are labelled duplicate. Echoes still do not prove the customer heard audio.

`g711.py` implements bounded raw μ-law ↔ little-endian PCM16 frame conversion with
no runtime `audioop` dependency. PCM remains 8kHz; resampling to a model's input
rate, WAV decoding and TTS rate conversion remain host-adapter work. Exhaustive
tests compare all PCM16 values and all μ-law codewords with Python3.12's independent
`audioop` oracle (test-only). No unverified resampler or WAV-to-stream adapter is
claimed.

The existing `DynamicAudioConversation` accepts this codec without changing its
financial safety policy. Fake-service tests exercise overlapping sessions, separate
histories, source scopes, media identities and cleanup. Real ingress authorization,
VAD/STT, streaming LLM/TTS, output pacing, distributed admission, authentication,
TLS/proxy and provider interoperability are **not implemented by this codec**.

Guide requirements for eventual host: WSS/TLS1.2+, CA-trusted certificate,
recommended port443, one connection per active call; failed handshakes are not
retried by Airtel. Bearer/mTLS/signed parameters are bilateral choices, not an
agreed authentication scheme. Do not expose secrets in URL query strings. Obtain
provider IP ranges; trust forwarded addresses only from explicitly trusted proxies.
Do not accept live streams until these controls and approved runtime services exist.
