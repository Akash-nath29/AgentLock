import unittest

from auth import check_password


class PasswordTests(unittest.TestCase):
    def test_correct_password(self):
        self.assertTrue(check_password("alice", "wonderland"))

    def test_wrong_password(self):
        self.assertFalse(check_password("alice", "looking-glass"))

    def test_unknown_user(self):
        self.assertFalse(check_password("mallory", "wonderland"))

    def test_empty_password_rejected_for_everyone(self):
        for user in ("alice", "guest"):
            self.assertFalse(check_password(user, ""), user)


if __name__ == "__main__":
    unittest.main()
