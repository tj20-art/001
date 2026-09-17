"""TOTP and one-time recovery-code helpers used by privileged accounts."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from api_service4.app.services.gm_crypto import sm3_hex


TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def generate_totp_secret(byte_length=20):
    return base64.b32encode(secrets.token_bytes(byte_length)).decode("ascii").rstrip("=")


def _decode_secret(secret):
    normalized = str(secret).strip().replace(" ", "").upper()
    padded = normalized + "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(padded, casefold=True)


def totp_code(secret, counter):
    digest = hmac.new(
        _decode_secret(secret),
        struct.pack(">Q", int(counter)),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp(secret, code, *, at_time=None, valid_window=1):
    candidate = str(code or "").strip()
    if len(candidate) != TOTP_DIGITS or not candidate.isdigit():
        return None

    current_counter = int((at_time if at_time is not None else time.time()) // TOTP_PERIOD_SECONDS)
    for offset in range(-int(valid_window), int(valid_window) + 1):
        counter = current_counter + offset
        if counter >= 0 and hmac.compare_digest(totp_code(secret, counter), candidate):
            return counter
    return None


def build_otpauth_uri(secret, username, issuer="FreeSpace Mall"):
    label = quote(f"{issuer}:{username}")
    return (
        f"otpauth://totp/{label}?secret={quote(secret)}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"
    )


def generate_recovery_codes(count=8):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(12))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return codes


def normalize_recovery_code(code):
    return str(code or "").replace("-", "").replace(" ", "").upper()


def hash_recovery_code(user_id, code):
    normalized = normalize_recovery_code(code)
    return sm3_hex(f"{int(user_id)}:{normalized}".encode("utf-8"))
