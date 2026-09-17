import json
import os
import secrets
from typing import Any, Dict, Tuple

from gmssl import sm2, func
from gmssl.sm4 import CryptSM4, SM4_ENCRYPT, SM4_DECRYPT

SIGN_RAW_TEMPLATE = "{order_no}|{amount_cents}|{merchant_id}|{timestamp}|{nonce}"


def _normalize_hex(value: str, *, public_key: bool = False) -> str:
    cleaned = "".join(str(value or "").strip().split()).lower()
    if public_key and cleaned.startswith("04") and len(cleaned) == 130:
        cleaned = cleaned[2:]
    if not cleaned:
        raise ValueError("hex key is empty")
    int(cleaned, 16)
    return cleaned


def generate_sm2_keypair() -> Dict[str, str]:
    private_key = func.random_hex(len(sm2.default_ecc_table["n"]))
    crypt_sm2 = sm2.CryptSM2(public_key="", private_key=private_key)
    public_key = crypt_sm2._kg(int(private_key, 16), sm2.default_ecc_table["g"])
    return {"private_key": private_key, "public_key": public_key}


def build_sign_raw(order_no: str, amount_cents: int, merchant_id: str, timestamp: str, nonce: str) -> str:
    return SIGN_RAW_TEMPLATE.format(
        order_no=str(order_no),
        amount_cents=int(amount_cents),
        merchant_id=str(merchant_id),
        timestamp=str(timestamp),
        nonce=str(nonce),
    )


def sm2_verify(public_key_hex: str, raw_text: str, signature_hex: str) -> bool:
    try:
        public_key = _normalize_hex(public_key_hex, public_key=True)
        signature = _normalize_hex(signature_hex)
        crypt_sm2 = sm2.CryptSM2(public_key=public_key, private_key="")
        return bool(crypt_sm2.verify_with_sm3(signature, str(raw_text).encode("utf-8")))
    except Exception:
        return False


def sm2_encrypt(public_key_hex: str, plaintext: bytes) -> str:
    public_key = _normalize_hex(public_key_hex, public_key=True)
    crypt_sm2 = sm2.CryptSM2(public_key=public_key, private_key="")
    ciphertext = crypt_sm2.encrypt(plaintext)
    if isinstance(ciphertext, str):
        return ciphertext
    return ciphertext.hex()


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def sm4_encrypt_json(payload: Dict[str, Any], key: bytes = None, iv: bytes = None) -> Tuple[bytes, str, str]:
    key = key or secrets.token_bytes(16)
    iv = iv or secrets.token_bytes(16)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    crypt_sm4 = CryptSM4()
    crypt_sm4.set_key(key, SM4_ENCRYPT)
    ciphertext = crypt_sm4.crypt_cbc(iv, pkcs7_pad(plaintext))
    return key, iv.hex(), ciphertext.hex()


def make_digital_envelope(payload: Dict[str, Any], receiver_public_key_hex: str) -> Dict[str, str]:
    sm4_key, iv_hex, data_hex = sm4_encrypt_json(payload)
    encrypted_key_hex = sm2_encrypt(receiver_public_key_hex, sm4_key)
    return {"encrypted_key": encrypted_key_hex, "iv": iv_hex, "data": data_hex}


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return file.read().strip()


def get_payment_key(env_name: str, default_filename: str) -> str:
    value = os.getenv(env_name)
    if value:
        return value.strip()
    keys_dir = os.path.abspath(os.getenv("PAYMENT_KEYS_DIR", "./payment_keys"))
    path = os.path.join(keys_dir, default_filename)
    if os.path.exists(path):
        return _read_text_file(path)
    raise RuntimeError(f"缺少支付密钥：请设置 {env_name} 或创建 {path}")
