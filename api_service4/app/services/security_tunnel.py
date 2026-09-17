"""SM2 + SM4-GCM application-layer envelope for sensitive JSON requests."""

import json
import os
import secrets
import time
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from flask import g, request

from api_service4.app.services.payment_crypto import generate_sm2_keypair, sm2_decrypt


PROTOCOL_VERSION = "1"
ALGORITHM_NAME = "SM2+SM4-GCM"
DEFAULT_TIME_WINDOW_SECONDS = 120


def _key_dir():
    package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.abspath(os.getenv("TUNNEL_KEYS_DIR", os.path.join(package_root, "security_keys")))


def _key_paths():
    directory = _key_dir()
    return (
        os.path.join(directory, "tunnel_private.key"),
        os.path.join(directory, "tunnel_public.key"),
    )


def load_or_create_tunnel_keypair():
    private_path, public_path = _key_paths()
    if os.path.exists(private_path) and os.path.exists(public_path):
        with open(private_path, "r", encoding="ascii") as private_file:
            private_key = private_file.read().strip()
        with open(public_path, "r", encoding="ascii") as public_file:
            public_key = public_file.read().strip()
        return {"private_key": private_key, "public_key": public_key}

    os.makedirs(os.path.dirname(private_path), exist_ok=True)
    pair = generate_sm2_keypair()
    with open(private_path, "w", encoding="ascii") as private_file:
        private_file.write(pair["private_key"])
    with open(public_path, "w", encoding="ascii") as public_file:
        public_file.write(pair["public_key"])
    return pair


def request_aad(method, path, timestamp, nonce, request_id):
    return f"{str(method).upper()}\n{path}\n{int(timestamp)}\n{nonce}\n{request_id}".encode("utf-8")


def response_aad(request_id):
    return f"RESPONSE\n{request_id}".encode("utf-8")


def sm4_gcm_encrypt(plaintext, key, *, aad=b""):
    if len(key) != 16:
        raise ValueError("SM4 会话密钥必须为16字节")
    iv = secrets.token_bytes(12)
    encryptor = Cipher(algorithms.SM4(key), modes.GCM(iv)).encryptor()
    encryptor.authenticate_additional_data(aad)
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    return {"iv": iv.hex(), "ciphertext": ciphertext.hex(), "tag": encryptor.tag.hex()}


def sm4_gcm_decrypt(*, ciphertext_hex, key, iv_hex, tag_hex, aad=b""):
    if len(key) != 16:
        raise ValueError("SM4 会话密钥必须为16字节")
    iv = bytes.fromhex(str(iv_hex))
    tag = bytes.fromhex(str(tag_hex))
    ciphertext = bytes.fromhex(str(ciphertext_hex))
    if len(iv) != 12 or len(tag) != 16:
        raise ValueError("SM4-GCM IV 或认证标签长度错误")
    decryptor = Cipher(algorithms.SM4(key), modes.GCM(iv, tag)).decryptor()
    decryptor.authenticate_additional_data(aad)
    return decryptor.update(ciphertext) + decryptor.finalize()


def _unwrap_session_key(encrypted_key, private_key):
    decrypted = sm2_decrypt(private_key, str(encrypted_key))
    if len(decrypted) == 16:
        return decrypted
    try:
        key = bytes.fromhex(decrypted.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("SM2 解封后的会话密钥格式错误") from exc
    if len(key) != 16:
        raise ValueError("SM2 解封后的会话密钥长度错误")
    return key


def open_request_envelope(envelope, *, method, path, private_key, consume_nonce=None, now_ms=None):
    required = {
        "version",
        "algorithm",
        "encrypted_key",
        "iv",
        "ciphertext",
        "tag",
        "nonce",
        "timestamp",
        "request_id",
    }
    missing = sorted(required.difference(envelope or {}))
    if missing:
        raise ValueError(f"安全信封缺少字段: {', '.join(missing)}")
    if str(envelope["version"]) != PROTOCOL_VERSION or envelope["algorithm"] != ALGORITHM_NAME:
        raise ValueError("不支持的安全信封版本或算法")

    timestamp = int(envelope["timestamp"])
    current_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    window_seconds = int(os.getenv("TUNNEL_TIME_WINDOW_SECONDS", DEFAULT_TIME_WINDOW_SECONDS))
    if abs(current_ms - timestamp) > window_seconds * 1000:
        raise TimeoutError("请求时间戳已过期或超出允许时间窗")

    nonce = str(envelope["nonce"])
    request_id = str(envelope["request_id"])
    if not nonce or len(nonce) > 96 or not request_id or len(request_id) > 96:
        raise ValueError("Nonce 或 request_id 格式错误")

    key = _unwrap_session_key(envelope["encrypted_key"], private_key)
    aad = request_aad(method, path, timestamp, nonce, request_id)
    plaintext = sm4_gcm_decrypt(
        ciphertext_hex=envelope["ciphertext"],
        key=key,
        iv_hex=envelope["iv"],
        tag_hex=envelope["tag"],
        aad=aad,
    )
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("安全信封正文不是有效 JSON") from exc
    if not isinstance(payload, (dict, list)):
        raise ValueError("安全信封正文必须是 JSON 对象或数组")

    if consume_nonce:
        # MySQL TIMESTAMP/CURRENT_TIMESTAMP uses the active DB session timezone.
        # Store a matching local naive datetime so a UTC/local offset cannot
        # make a freshly consumed nonce appear expired immediately.
        expires_at = datetime.now() + timedelta(seconds=window_seconds * 2)
        if not consume_nonce(nonce, request_id, expires_at):
            raise FileExistsError("检测到重复 Nonce，请求已按重放攻击拒绝")

    return payload, key, request_id


def encrypt_response_payload(payload, *, key, request_id):
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encrypted = sm4_gcm_encrypt(plaintext, key, aad=response_aad(request_id))
    return {
        "version": PROTOCOL_VERSION,
        "algorithm": "SM4-GCM",
        "request_id": request_id,
        **encrypted,
    }


def decrypt_flask_request(security_control):
    if request.headers.get("X-Secure-Envelope") != PROTOCOL_VERSION:
        return None
    if not request.is_json:
        raise ValueError("安全信封仅支持 application/json")

    envelope = request.get_json(silent=True)
    if not isinstance(envelope, dict):
        raise ValueError("安全信封格式错误")
    keypair = load_or_create_tunnel_keypair()
    payload, key, request_id = open_request_envelope(
        envelope,
        method=request.method,
        path=request.path,
        private_key=keypair["private_key"],
        consume_nonce=security_control.consume_nonce,
    )
    request._cached_json = (payload, payload)
    request._cached_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    g.secure_tunnel = {"key": key, "request_id": request_id}
    return payload


def encrypt_flask_response(response):
    tunnel = getattr(g, "secure_tunnel", None)
    if not tunnel or not response.is_json:
        return response
    payload = response.get_json(silent=True)
    if payload is None:
        return response
    envelope = encrypt_response_payload(payload, key=tunnel["key"], request_id=tunnel["request_id"])
    response.set_data(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["X-Secure-Response"] = PROTOCOL_VERSION
    response.headers["Cache-Control"] = "no-store"
    return response


__all__ = [
    "ALGORITHM_NAME",
    "InvalidTag",
    "PROTOCOL_VERSION",
    "decrypt_flask_request",
    "encrypt_flask_response",
    "encrypt_response_payload",
    "load_or_create_tunnel_keypair",
    "open_request_envelope",
    "request_aad",
    "response_aad",
    "sm4_gcm_decrypt",
    "sm4_gcm_encrypt",
]
