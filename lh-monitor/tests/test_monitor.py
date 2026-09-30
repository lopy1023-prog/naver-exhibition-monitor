import json
import sys
import unittest
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diff import compare
from monitor import link_families, validate
from parser import classify, parse_detail, parse_list
import requests
import monitor


class MonitorTests(unittest.TestCase):
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

    def test_other_region_and_generic_scope_words_are_not_broad(self):
        for title, region in (
            ("[부산지역본부] 통합모집", "부산광역시"),
            ("[대구지역본부] 일괄모집", "대구광역시"),
            ("[광주전남지역본부] 여러 지역 모집", "광주광역시"),
            ("[충북지역본부] 권역별 모집", "충청북도"),
            ("[경기북부지역본부] 모집", "경기도"),
            ("경기장 인근 공급", ""),
        ):
            with self.subTest(title=title):
                post = classify({"title": title, "region": region, "category": "rental"},
                                "LH 본사 주소 경기도, 전국 지역본부 공통 안내")
                self.assertFalse(post["broadCandidate"])

    def test_real_suwon_scope_remains_broad(self):
        for title in ("경기남부지역본부 모집", "경기도 모집", "경기지역 모집", "수도권 모집", "전국 모집", "경기 모집"):
            with self.subTest(title=title):
                post = classify({"title": title, "region": "", "category": "rental"})
                self.assertTrue(post["broadCandidate"])
        post = classify({"title": "청년 임대주택 모집", "region": "", "category": "rental"},
                        "공급지역: 경기남부, 신청기간 2026.10.01")
        self.assertTrue(post["broadCandidate"])

    def test_new_broad_and_tracked_events_reach_history_without_baseline_backfill(self):
        posts = [
            classify({"panId": "broad", "title": "경기남부지역본부 모집", "region": "", "category": "rental"}),
            {"panId": "tracked", "title": "추적 중인 모집", "tracked": "family-a"},
            {"panId": "other", "title": "부산지역본부 모집", "directSuwon": False, "broadCandidate": False},
        ]
        events = compare([], posts)
        alerts, history = monitor.build_alerts(events, [], posts, [], "2026-09-30T10:00:00+09:00", False)
        self.assertEqual((alerts, history), ([], []))
        alerts, history = monitor.build_alerts(events, [], posts, [], "2026-09-30T10:00:00+09:00", True)
        self.assertEqual({item["panId"] for item in alerts}, {"broad", "tracked"})
        self.assertEqual(len(history), 2)

    def test_same_event_id_is_stable_and_history_is_deduplicated(self):
        post = classify({"panId": "0000061181", "title": "수원당수 A-3 추가입주자 모집", "region": "경기도", "category": "sale"})
        events = compare([], [post])
        first, history = monitor.build_alerts(events, [], [post], [], "2026-09-30T10:00:00+09:00", True)
        repeated, repeated_history = monitor.build_alerts(events, [], [post], history,
                                                          "2026-09-30T11:00:00+09:00", True)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["alertId"], monitor.build_alerts(events, [], [post], [],
                         "2026-09-30T12:00:00+09:00", True)[0][0]["alertId"])
        self.assertEqual(repeated, [])
        self.assertEqual(repeated_history, history)

    def test_new_values_and_correction_get_new_ids_for_same_notice(self):
        old = {"panId": "same", "title": "수원 공고", "status": "공고중", "applicationEnd": "2026-10-01", "directSuwon": True}
        middle = {**old, "status": "접수중", "applicationEnd": "2026-10-02"}
        latest = {**middle, "status": "접수마감", "applicationEnd": "2026-10-03"}
        first = monitor.build_alerts(compare([old], [middle]), [old], [middle], [], "first", True)[0][0]
        second = monitor.build_alerts(compare([middle], [latest]), [middle], [latest], [], "second", True)[0][0]
        correction = {**latest, "title": "[정정공고] 수원 공고", "correction": True}
        third = monitor.build_alerts(compare([latest], [correction]), [latest], [correction], [], "third", True)[0][0]
        self.assertEqual(len({first["alertId"], second["alertId"], third["alertId"]}), 3)
        self.assertIn("deadlineChanged", first["kinds"])
        self.assertIn("statusChanged", second["kinds"])

    def test_repeated_status_cycle_is_a_new_event(self):
        closed = {"panId": "same", "title": "수원 모집", "status": "접수마감", "directSuwon": True}
        open_post = {**closed, "status": "접수중"}
        first, history = monitor.build_alerts(compare([closed], [open_post]), [closed], [open_post], [], "first", True)
        _, history = monitor.build_alerts(compare([open_post], [closed]), [open_post], [closed], history, "second", True)
        repeated, history = monitor.build_alerts(compare([closed], [open_post]), [closed], [open_post], history, "third", True)
        self.assertEqual(len(repeated), 1)
        self.assertNotEqual(first[0]["alertId"], repeated[0]["alertId"])
        self.assertEqual(len(history), 3)

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
        old = {"panId": "same", "title": "공고", "applicationEnd": "2026-10-01", "attachments": [{"fileId": "1"}]}
        new = {"panId": "same", "title": "공고", "applicationEnd": "2026-10-02", "attachments": [{"fileId": "2"}]}
        event = compare([old], [new])[0]
        self.assertIn("deadlineChanged", event["kinds"])
        self.assertIn("attachmentChanged", event["kinds"])

    def test_previous_attachment_text_hash_is_not_a_new_alert(self):
        old = {"panId": "same", "title": "수원 공고", "attachments": [{"fileId": "1", "name": "공고.pdf", "url": "official", "sha256": "old"}]}
        new = {"panId": "same", "title": "수원 공고", "attachments": [{"fileId": "1", "name": "공고.pdf", "url": "official"}]}
        self.assertEqual(compare([old], [new]), [])

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
