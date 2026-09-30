import unittest

from blame_likumi_lv.errors import UnknownStructureError
from blame_likumi_lv.html_parser import discover_revisions, extract_official_text, parse_metadata


FIXTURE = """<!doctype html>
<div class='redakcija-container r-container'>
  <ul>
    <li><div class='element-data'>{&quot;value&quot;:&quot;01.01.2020&quot;,&quot;iso_value&quot;:&quot;2020/01/01&quot;}</div></li>
    <li><div class='element-data'>{&quot;value&quot;:&quot;01.02.2020&quot;,&quot;iso_value&quot;:&quot;2020/02/01&quot;}</div></li>
  </ul>
</div>
<div class='doc-body'>
  <div class='TV207'>Likums</div>
  <div class='TV213'><div>1.pants.</div><div>Ābols&nbsp;— bērzs.</div></div>
</div>
<div class='pase-container'><div class='wrapper body'>
  <span><font>Nosaukums: </font>Likums</span>
  <span><font>Izdevējs: </font>Saeima</span>
  <span><font>Veids: </font><a>likums</a></span>
  <span><font>Pieņemts: </font>01.01.2020.</span>
  <span><font>Stājas spēkā: </font>01.01.2020.</span>
  <span><font>Publicēts: </font>Latvijas Vēstnesis, 1, 01.01.2020.</span>
</div></div>"""


class ParserTests(unittest.TestCase):
    def test_extracts_only_doc_body(self):
        text = extract_official_text(FIXTURE)
        self.assertIn("Likums", text)
        self.assertIn("Ābols — bērzs.", text)
        self.assertNotIn("Tiesību akta pase", text)

    def test_discovers_revision_urls(self):
        revisions = discover_revisions(FIXTURE, "1", "https://likumi.lv/ta/id/1-law")
        self.assertEqual([item.effective.isoformat() for item in revisions], ["2020-01-01", "2020-02-01"])
        self.assertTrue(revisions[0].url.endswith("/redakcijas-datums/2020/01/01"))

    def test_parses_metadata(self):
        metadata = parse_metadata(FIXTURE, "https://likumi.lv/ta/id/1-law", "1", "Fallback", "likums")
        self.assertEqual(metadata.title, "Likums")
        self.assertEqual(metadata.issuer, "Saeima")
        self.assertEqual(metadata.effective.isoformat(), "2020-01-01")

    def test_parses_noteikumi_metadata(self):
        noteikumi = FIXTURE.replace("<a>likums</a>", "<a>noteikumi</a>")
        metadata = parse_metadata(noteikumi, "https://likumi.lv/ta/id/1-noteikumi", "1", "Fallback", "noteikumi")
        self.assertEqual(metadata.type, "noteikumi")

    def test_discovers_single_current_version_without_selector(self):
        single = FIXTURE.replace(
            "<div class='redakcija-container r-container'>\n  <ul>\n    <li><div class='element-data'>{&quot;value&quot;:&quot;01.01.2020&quot;,&quot;iso_value&quot;:&quot;2020/01/01&quot;}</div></li>\n    <li><div class='element-data'>{&quot;value&quot;:&quot;01.02.2020&quot;,&quot;iso_value&quot;:&quot;2020/02/01&quot;}</div></li>\n  </ul>\n</div>",
            "<div id='version_date' data-version_date='01.02.2020'></div>",
        )
        revisions = discover_revisions(single, "1", "https://likumi.lv/ta/id/1-law")
        self.assertEqual([item.effective.isoformat() for item in revisions], ["2020-02-01"])

    def test_missing_body_fails_closed(self):
        with self.assertRaises(UnknownStructureError):
            extract_official_text("<div class='pase-container'></div>")


if __name__ == "__main__":
    unittest.main()
