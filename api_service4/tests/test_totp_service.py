import unittest

from api_service4.app.services.totp_service import generate_totp_secret, totp_code, verify_totp


class TotpServiceTests(unittest.TestCase):
    def test_accepts_configured_clock_drift_and_rejects_wrong_code(self):
        secret = generate_totp_secret()
        timestamp = 1_700_000_000
        current = verify_totp(secret, totp_code(secret, timestamp // 30), at_time=timestamp)
        previous = verify_totp(
            secret,
            totp_code(secret, timestamp // 30 - 1),
            at_time=timestamp,
        )
        following = verify_totp(
            secret,
            totp_code(secret, timestamp // 30 + 1),
            at_time=timestamp,
        )
        self.assertEqual(current, timestamp // 30)
        self.assertEqual(previous, timestamp // 30 - 1)
        self.assertEqual(following, timestamp // 30 + 1)
        wrong_code = str((int(totp_code(secret, timestamp // 30)) + 1) % 1_000_000).zfill(6)
        self.assertIsNone(verify_totp(secret, wrong_code, at_time=timestamp))


if __name__ == "__main__":
    unittest.main()
