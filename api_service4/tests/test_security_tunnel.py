import json
import unittest
from datetime import datetime

from cryptography.exceptions import InvalidTag

from api_service4.app.services.payment_crypto import generate_sm2_keypair, sm2_encrypt
from api_service4.app.services.security_tunnel import (
    ALGORITHM_NAME,
    PROTOCOL_VERSION,
    open_request_envelope,
    request_aad,
    sm4_gcm_encrypt,
)


class SecurityTunnelTests(unittest.TestCase):
    def setUp(self):
        self.keypair = generate_sm2_keypair()
        self.key = bytes.fromhex("0123456789abcdeffedcba9876543210")
        self.method = "POST"
        self.path = "/api/v1/users/register"
        self.timestamp = 1_700_000_000_000
        self.nonce = "nonce-001"
        self.request_id = "request-001"
        aad = request_aad(self.method, self.path, self.timestamp, self.nonce, self.request_id)
        encrypted = sm4_gcm_encrypt(json.dumps({"username": "test"}).encode("utf-8"), self.key, aad=aad)
        self.envelope = {
            "version": PROTOCOL_VERSION,
            "algorithm": ALGORITHM_NAME,
            "encrypted_key": sm2_encrypt(self.keypair["public_key"], self.key),
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            **encrypted,
        }

    def test_decrypts_and_rejects_replay(self):
        consumed = set()
        expirations = []

        def consume_nonce(nonce, request_id, expires_at):
            expirations.append(expires_at)
            marker = (nonce, request_id)
            if marker in consumed:
                return False
            consumed.add(marker)
            return True

        payload, key, request_id = open_request_envelope(
            self.envelope,
            method=self.method,
            path=self.path,
            private_key=self.keypair["private_key"],
            consume_nonce=consume_nonce,
            now_ms=self.timestamp,
        )
        self.assertEqual(payload, {"username": "test"})
        self.assertEqual(key, self.key)
        self.assertEqual(request_id, self.request_id)
        self.assertGreater(expirations[0], datetime.now())

        with self.assertRaises(FileExistsError):
            open_request_envelope(
                self.envelope,
                method=self.method,
                path=self.path,
                private_key=self.keypair["private_key"],
                consume_nonce=consume_nonce,
                now_ms=self.timestamp,
            )

    def test_rejects_expired_and_tampered_envelopes(self):
        with self.assertRaises(TimeoutError):
            open_request_envelope(
                self.envelope,
                method=self.method,
                path=self.path,
                private_key=self.keypair["private_key"],
                now_ms=self.timestamp + 121_000,
            )

        tampered = dict(self.envelope)
        tampered["ciphertext"] = f"{tampered['ciphertext'][:-1]}{'0' if tampered['ciphertext'][-1] != '0' else '1'}"
        with self.assertRaises(InvalidTag):
            open_request_envelope(
                tampered,
                method=self.method,
                path=self.path,
                private_key=self.keypair["private_key"],
                now_ms=self.timestamp,
            )


if __name__ == "__main__":
    unittest.main()
