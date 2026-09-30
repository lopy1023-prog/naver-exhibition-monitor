import io
import json
import sys
import unittest
from unittest.mock import MagicMock, patch
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from attachment_parser import extract_text
from diff import compare
from monitor import link_families, validate
from parser import classify, parse_detail, parse_list
from lh_client import LHClient
import requests


class MonitorTests(unittest.TestCase):
    def test_slow_continuous_download_has_total_deadline(self):
        client = LHClient()
        response = MagicMock()
        response.headers = {}
        response.iter_content.return_value = iter([b"first", b"second"])
        client.session.get = MagicMock()
        client.session.get.return_value.__enter__.return_value = response
        with patch("lh_client.time.monotonic", side_effect=[0, 1, 91]):
            with self.assertRaises(requests.Timeout):
                client.content("https://apply.lh.or.kr/example")
        response.__exit__.assert_not_called()

    def test_a_direct_suwon(self):
        post = {"title": "수원당수 A-3블록 신혼희망타운", "region": "경기도", "category": "sale"}
        self.assertTrue(classify(post)["directSuwon"])

    def test_b_broad_gyeonggi_south_requires_detail(self):
        post = {"title": "경기남부 2026년 일반 매입임대주택", "region": "", "category": "rental"}
        self.assertFalse(classify(post)["directSuwon"])
        self.assertTrue(post["broadCandidate"])

    def test_c_missing_page_fails_validation(self):
        category = {"totalCount": 2, "parsedCount": 2, "totalPages": 2, "checkedPages": 1, "complete": True}
        feed = {"sourceStatus": "ok", "categories": {name: category for name in ("rental", "sale", "land", "commercial", "presale")}, "postCount": 0, "posts": []}
        self.assertTrue(validate(feed))

    def test_d_new_pan_id(self):
        self.assertEqual(compare([], [{"panId": "new", "title": "새 공고"}])[0]["kind"], "new")

    def test_e_same_pan_id_date_and_attachment_change(self):
        old = {"panId": "same", "title": "공고", "applicationEnd": "2026-10-01", "attachments": [{"fileId": "1", "sha256": "a"}]}
        new = {"panId": "same", "title": "공고", "applicationEnd": "2026-10-02", "attachments": [{"fileId": "1", "sha256": "b"}]}
        event = compare([old], [new])[0]
        self.assertIn("deadlineChanged", event["kinds"])
        self.assertIn("attachmentChanged", event["kinds"])

    def test_unreadable_attachment_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            extract_text("houses.pdf", b"not a PDF")

    def test_hwpx_xml_extracts_suwon(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("Contents/section0.xml", "<root><p>수원시 공급주택 목록</p></root>")
        self.assertIn("수원시", extract_text("notice.hwpx", output.getvalue()))

    def test_page_count_detects_partial_table(self):
        html = '<p class="bbs_total">전체 <strong>2</strong>건 <strong>1</strong>/1페이지</p><div class="bbs_ListA"><table><tbody></tbody></table></div>'
        with self.assertRaises(ValueError):
            parse_list(html, "rental", "1026", "now")

    def test_detail_schedule_after_view_is_read(self):
        html = ('<div id="sub_container"><div class="bbs_ViewA"><h3>수원당수 공고</h3>'
                '<div class="bbsV_atchmnfl"></div></div><section><table>'
                '<caption>공급일정 : 신청일시</caption><tr><td>2026.10.12 10:00</td></tr>'
                '</table></section></div>')
        post = {"panId": "0000061181", "title": "수원당수 공고", "region": "경기도", "category": "sale",
                "applicationStart": "", "applicationEnd": "", "attachments": []}
        self.assertEqual(parse_detail(html, post)["applicationStart"], "2026-10-12")

    def test_correction_links_to_original_family(self):
        posts = [
            {"panId": "1", "title": "경기남부 일반 매입임대주택", "postedAt": "2026-01-01", "correction": False},
            {"panId": "2", "title": "[정정공고] 경기남부 일반 매입임대주택", "postedAt": "2026-01-02", "correction": True},
        ]
        link_families(posts)
        self.assertEqual(posts[1]["correctionOf"], "1")
        self.assertEqual(posts[0]["noticeFamily"], posts[1]["noticeFamily"])


if __name__ == "__main__":
    unittest.main()
