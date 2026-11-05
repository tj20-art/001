import unittest

from api_service4.app.services.refresh_token_service import generate_refresh_token, hash_refresh_token


class RefreshTokenServiceTests(unittest.TestCase):
    def test_generates_high_entropy_unique_opaque_tokens(self):
        first = generate_refresh_token()
        second = generate_refresh_token()

        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 64)
        self.assertNotIn(".", first)

    def test_hash_is_deterministic_and_does_not_expose_token(self):
        token = generate_refresh_token()
        token_hash = hash_refresh_token(token)

        self.assertEqual(token_hash, hash_refresh_token(token))
        self.assertEqual(len(token_hash), 64)
        self.assertNotEqual(token, token_hash)

    def test_rejects_empty_tokens(self):
        with self.assertRaises(ValueError):
            hash_refresh_token("")


if __name__ == "__main__":
    unittest.main()
