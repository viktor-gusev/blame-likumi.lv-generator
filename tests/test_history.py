import json
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from blame_likumi_lv.git_history import build_history, law_filename
from blame_likumi_lv.models import Law, Revision


HTML_TEMPLATE = """<div class='doc-body'><div class='TV207'>{title}</div><div class='TV213'><div>{body}</div></div></div>"""
METADATA = {
    "id": "1",
    "title": "Pārbaudes likums",
    "type": "likums",
    "source": "https://likumi.lv/ta/id/1-test",
    "status": "spēkā esošs",
    "adopted": "2020-01-01",
    "published": "2020-01-02",
    "effective": "2020-01-03",
    "issuer": "Saeima",
    "language": "LV",
}


class HistoryTests(unittest.TestCase):
    def test_history_is_deterministic_and_uses_historical_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            (cache / "metadata").mkdir(parents=True)
            (cache / "revisions" / "1").mkdir(parents=True)
            (cache / "metadata" / "1.json").write_text(json.dumps(METADATA), encoding="utf-8")
            revisions = [
                Revision("1", date(2020, 1, 3), "https://likumi.lv/ta/id/1-test/redakcijas-datums/2020/01/03"),
                Revision("1", date(2020, 2, 1), "https://likumi.lv/ta/id/1-test/redakcijas-datums/2020/02/01"),
            ]
            for revision, body in zip(revisions, ("Pirmais teksts.", "Otrais teksts.")):
                (cache / "revisions" / "1" / f"{revision.effective.isoformat()}.html").write_text(
                    HTML_TEMPLATE.format(title="Pārbaudes likums", body=body), encoding="utf-8"
                )
            law = Law("1", "Pārbaudes likums", "parbaudes-likums", "likums", METADATA["source"])
            output = root / "latvian-laws"
            build_history([law], {"1": revisions}, cache, output)
            self.assertTrue((output / "README.md").exists())
            log = subprocess.check_output(["git", "-C", str(output), "log", "--format=%ad|%s", "--date=short"], text=True, encoding="utf-8")
            self.assertIn("2020-02-01|Update Pārbaudes likums", log)
            self.assertIn("2020-01-03|Add Pārbaudes likums", log)
            self.assertEqual((output / "likumi" / law_filename(law)).read_text(encoding="utf-8"), "Pārbaudes likums\n\nOtrais teksts.\n")
            status = subprocess.check_output(["git", "-C", str(output), "status", "--porcelain"], text=True, encoding="utf-8")
            self.assertEqual(status, "")

            second_output = root / "latvian-laws-second"
            build_history([law], {"1": revisions}, cache, second_output)
            first_head = subprocess.check_output(["git", "-C", str(output), "rev-parse", "HEAD"], text=True, encoding="utf-8").strip()
            second_head = subprocess.check_output(["git", "-C", str(second_output), "rev-parse", "HEAD"], text=True, encoding="utf-8").strip()
            self.assertEqual(first_head, second_head)


if __name__ == "__main__":
    unittest.main()
