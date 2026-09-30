import tempfile
import unittest
from datetime import date
from pathlib import Path

from blame_likumi_lv.errors import VerificationError
from blame_likumi_lv.html_parser import extract_official_text
from blame_likumi_lv.models import Law
from blame_likumi_lv.verification import verify_law

from test_parser import FIXTURE


class FakeFetcher:
    def law_page(self, law):
        return FIXTURE, b"", True

    def revision_page(self, revision):
        return FIXTURE, b"", True


class VerificationTests(unittest.TestCase):
    def test_one_changed_character_fails(self):
        law = Law("1", "Likums", "likums", "likums", "https://likumi.lv/ta/id/1-law")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            (output / "likumi").mkdir(parents=True)
            path = output / "likumi" / "1-likums.txt"
            path.write_text(extract_official_text(FIXTURE).replace("bērzs", "bērzis"), encoding="utf-8")
            with self.assertRaises(VerificationError) as raised:
                verify_law(law, output, FakeFetcher(), today=date(2020, 2, 1))
            self.assertIn("normalized text mismatch", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

