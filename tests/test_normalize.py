import unittest

from blame_likumi_lv.normalize import normalize_text


class NormalizeTests(unittest.TestCase):
    def test_unicode_spaces_and_line_endings_are_deterministic(self):
        self.assertEqual(
            normalize_text("\ufeffĀ\u00a0B  \r\n\r\n"),
            "Ā B\n",
        )

    def test_empty_text_stays_empty(self):
        self.assertEqual(normalize_text(" \r\n\t"), "")


if __name__ == "__main__":
    unittest.main()

