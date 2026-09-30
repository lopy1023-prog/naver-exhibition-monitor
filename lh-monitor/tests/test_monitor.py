import io
import json
import sys
import unittest
from unittest.mock import MagicMock, patch
import zipfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from attachment_parser import extract_text
from diff import compare
from monitor import link_families, validate
from parser import classify, parse_detail, parse_list
from lh_client import LHClient
import requests
import monitor


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
        client.session.get.return_value.__exit__.assert_called_once()

    def test_failed_collection_preserves_last_success_and_null_events(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for filename in ("lh-state.json", "lh-tracked-state.json"):
                (data / filename).write_text('{"marker":"last-success"}', encoding="utf-8")
            client = MagicMock()
            client.collect_category.side_effect = requests.Timeout("official list unavailable")
            client.collect_presale.side_effect = requests.Timeout("official list unavailable")
            with patch.object(monitor, "DATA", data), patch.object(monitor, "LHClient", return_value=client):
                self.assertEqual(monitor.run(), 1)
            for filename in ("lh-state.json", "lh-tracked-state.json"):
                self.assertEqual(json.loads((data / filename).read_text())["marker"], "last-success")
            report = json.loads((data / "lh-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["sourceStatus"], "error")
            self.assertIsNone(report["new"])
            self.assertTrue(report["errors"])
            with patch.object(monitor, "DATA", data):
                monitor.mark_failure("Actions 수집 시간 초과")
            report = json.loads((data / "lh-report.json").read_text(encoding="utf-8"))
            self.assertIn("Actions 수집 시간 초과", report["errors"])
            self.assertIsNone(report["new"])
            self.assertEqual(json.loads((data / "lh-state.json").read_text())["marker"], "last-success")

    def test_presale_identifiers_columns_and_direct_attachment(self):
        html = ('<p class="bbs_total">전체 1건 1/1페이지</p><div class="bbs_ListA"><table><tbody><tr>'
                '<td>1</td><td>공공임대</td><td><a class="slpaInfoBtn" data-id1="61" data-id2="50" data-id3="61">'
                '<span>수원 사전청약</span></a></td><td>첨부</td><td>2024.01.04</td><td>2024.01.25</td>'
                '<td>접수마감</td><td>100</td></tr></tbody></table></div>')
        _, posts = parse_list(html, "presale", "1349", "now")
        post = posts[0]
        self.assertIn("slpaInfo.do?", post["detailUrl"])
        self.assertEqual(post["postedAt"], "2024-01-04")
        detail = ('<div class="bbs_ViewA"><h3>수원 사전청약</h3><ul class="bbsV_data">'
                  '<li><strong>마감일</strong>2024년 01월 25일</li></ul>'
                  '<div class="bbsV_atchmnfl"><a href="/lhapply/lhFile.do?fileid=123">공고.pdf</a></div></div>')
        parse_detail(detail, post)
        self.assertEqual(post["applicationEnd"], "2024-01-25")
        self.assertEqual(post["attachments"][0]["fileId"], "123")

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

    def test_new_additional_recruitment_keeps_new_event(self):
        event = compare([], [{"panId": "0000061181", "title": "수원당수 추가입주자 모집"}])[0]
        self.assertEqual(event["kind"], "new")
        self.assertIn("additionalRecruitment", event["kinds"])

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
