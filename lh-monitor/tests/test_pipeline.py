import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitor
import pipeline
from diff import compare
from parser import classify, parse_detail


def post(ident="a", **fields):
    return {"panId": ident, "title": "수원 청년 매입임대 모집", "category": "rental",
            "region": "경기도", "directSuwon": True, "broadCandidate": True,
            "detailUrl": "https://apply.lh.or.kr/official", "applicationStart": "2026-10-16",
            "applicationEnd": "2026-10-20", "status": "공고중", "attachments": [],
            "detailTextHash": "stable", "hashVersion": 2, "sourceNames": ["rental"], **fields}


class PipelineTests(unittest.TestCase):
    def test_calendar_existing_notice_and_rolling_window_do_not_duplicate(self):
        old = post(calendarSchedules=[{"start": "2026-10-16", "end": "2026-10-20"}])
        merged = pipeline.merge_sources([post()], [post(sourceNames=["calendar"], calendarSchedules=old["calendarSchedules"])], [old])
        self.assertEqual(len(merged), 1)
        self.assertEqual(compare([old], merged), [])
        archived = pipeline.merge_sources([], [], [old])
        self.assertEqual(len(archived), 1)
        self.assertEqual(compare([old], archived), [])

    def test_first_source_baseline_and_hash_migration_do_not_backfill(self):
        old = post(hashVersion=1, detailTextHash="legacy")
        extra = post("b", sourceNames=["notice"], category="notice")
        before = pipeline.comparison_baseline([old], [post(), extra], {})
        self.assertEqual(compare(before, [post(), extra]), [])
        initialized = pipeline.comparison_baseline([post()], [post(), extra], {"notice": True})
        self.assertEqual(compare(initialized, [post(), extra])[0]["panId"], "b")

    def test_reception_scheduled_and_status_paths_emit_exactly_once(self):
        old = post(applicationStart="2026-10-16T10:00:00+09:00")
        current = post(applicationStart=old["applicationStart"], status="接수중".replace("接", "접"))
        events, seen = pipeline.reception_events(compare([old], [current]), [old], [current], {},
             "2026-10-16T09:00:00+09:00", "2026-10-16T10:01:00+09:00", True)
        self.assertEqual(len(events), 1)
        self.assertIn("receptionStarted", events[0]["kinds"])
        repeated, seen2 = pipeline.reception_events(compare([old], [current]), [old], [current], seen,
             "2026-10-16T10:01:00+09:00", "2026-10-16T11:00:00+09:00", True)
        self.assertEqual(repeated, [])
        self.assertEqual(seen, seen2)

    def test_schedule_fires_when_status_is_late_and_date_only_is_not_precise(self):
        item = post()
        events, seen = pipeline.reception_events([], [item], [item], {},
             "2026-10-15T23:30:00+09:00", "2026-10-16T07:00:00+09:00", True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["receptionEvidence"], "officialStartDate")
        self.assertTrue(events[0]["requiresEligibilityReview"])
        status = {**item, "status": "접수중"}
        events, _ = pipeline.reception_events(compare([item], [status]), [item], [status], seen,
             "2026-10-16T07:00:00+09:00", "2026-10-16T08:00:00+09:00", True)
        self.assertEqual(events, [])

    def test_baseline_reception_does_not_retroactively_alert(self):
        events, seen = pipeline.reception_events([], [], [post()], {}, "", "2026-10-17T10:00:00+09:00", False)
        self.assertEqual(events, [])
        self.assertTrue(seen)

    def test_precise_time_supersedes_same_day_calendar_date(self):
        item = post(calendarSchedules=[{"start": "2026-10-16", "end": "2026-10-16"}],
                    applicationSchedules=[{"start": "2026-10-16T10:00:00+09:00", "end": "2026-10-16T17:00:00+09:00", "label": "일반공급"}])
        self.assertEqual(pipeline.starts(item), ["2026-10-16T10:00:00+09:00"])
        midnight, seen = pipeline.reception_events([], [item], [item], {}, "2026-10-15T23:00:00+09:00", "2026-10-16T07:00:00+09:00", True)
        self.assertEqual(midnight, [])
        morning, _ = pipeline.reception_events([], [item], [item], seen, "2026-10-16T07:00:00+09:00", "2026-10-16T10:01:00+09:00", True)
        self.assertEqual(len(morning), 1)

    def test_reopened_notice_is_a_new_reception_cycle(self):
        item = post(status="접수중")
        _, seen = pipeline.reception_events([], [], [item], {}, "", "2026-10-17T10:00:00+09:00", False)
        closed = {**item, "status": "접수마감"}
        events, _ = pipeline.reception_events(compare([closed], [item]), [closed], [item], seen, "2026-10-18T09:00:00+09:00", "2026-10-18T10:00:00+09:00", True)
        self.assertEqual(len(events), 1)
        self.assertIn("receptionStarted", events[0]["kinds"])

    def test_non_application_schedule_rows_never_start_reception(self):
        html = '<div id="sub_container"><div class="bbs_ViewA"><h3>수원 공고</h3></div><table><caption>공급일정</caption><tbody><tr><td>일반공급</td><td>2026.10.16 10:00 ~ 2026.10.16 17:00</td></tr><tr><td>당첨자발표</td><td>2026.10.21 10:00</td></tr><tr><td>서류제출</td><td>2026.10.22 10:00</td></tr><tr><td>계약체결</td><td>2026.10.23 10:00</td></tr></tbody></table></div>'
        parsed = parse_detail(html, post(title="수원 공고"))
        self.assertEqual(len(parsed["applicationSchedules"]), 1)

    def test_first_come_disappearance_and_reappearance_are_changes_not_new(self):
        item = post(category="firstComeRental", sourceNames=["firstComeRental"], currentlyListed=True)
        absent = pipeline.merge_sources([], [], [item])
        events = compare([item], absent)
        self.assertEqual(len(events), 1)
        self.assertIn("inventoryUnavailable", events[0]["kinds"])
        present = pipeline.merge_sources([], [item], absent)
        events = compare(absent, present)
        self.assertEqual(events[0]["kind"], "changed")
        self.assertIn("inventoryAvailable", events[0]["kinds"])

    def test_partial_calendar_window_rollover_keeps_past_schedules(self):
        a = {"start": "2026-10-16", "end": "2026-10-20"}
        b = {"start": "2026-11-10", "end": "2026-11-12"}
        old = post(calendarSchedules=[a, b])
        current = post(sourceNames=["calendar"], calendarSchedules=[b], calendarWindowStart="2026-11-01", calendarWindowEnd="2026-12-31")
        merged = pipeline.merge_sources([post()], [current], [old])
        self.assertEqual(compare([old], merged), [])

    def test_schedule_and_attachment_order_does_not_change_event(self):
        a = {"start": "2026-10-16", "end": "2026-10-20"}
        b = {"start": "2026-11-10", "end": "2026-11-12"}
        item = post(calendarSchedules=[a, b], attachments=[{"fileId": "1"}, {"fileId": "2"}])
        reordered = {**item, "calendarSchedules": [b, a], "attachments": list(reversed(item["attachments"]))}
        self.assertEqual(compare([item], [reordered]), [])

    def test_contact_address_does_not_prove_suwon_supply(self):
        unrelated = classify({"title": "부산 청년주택 모집", "region": "부산광역시", "category": "rental"}, "문의처: 경기도 수원시 LH 상담센터")
        self.assertFalse(unrelated["directSuwon"])
        self.assertFalse(unrelated["broadCandidate"])
        actual = classify({"title": "청년 주택 안내", "region": "", "category": "notice"}, "공급지역: 수원시 영통구")
        self.assertTrue(actual["directSuwon"])

    def test_all_categories_and_additional_regions_are_inclusive(self):
        for category in ("rental", "sale", "land", "commercial", "notice", "documents", "supplyRental"):
            for title in ("수원 안내", "경기남부 청년 모집", "경기도 일반 공급", "전국 공고"):
                p = classify({"title": title, "region": "", "category": category})
                self.assertTrue(p["directSuwon"] or p["broadCandidate"], (category, title))
        for city in ("화성", "오산"):
            self.assertIn(city, classify({"title": city + " 행복주택", "region": "", "category": "rental"})["confirmedRegions"])

    def test_detail_view_counts_are_not_content_changes(self):
        html = '<div id="sub_container"><div class="bbs_ViewA"><h3>수원 공고</h3><ul class="bbsV_data"><li><strong>조회수</strong>1</li></ul><div class="bbsV_cont">공급지역 수원, 접수기간 2026.10.16</div></div></div>'
        a = parse_detail(html, post(title="수원 공고"))
        b = parse_detail(html.replace('</strong>1', '</strong>200'), post(title="수원 공고"))
        self.assertEqual(a["detailTextHash"], b["detailTextHash"])

    def test_failure_report_keeps_history_and_last_success_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            history = [{"alertId": "keep-byte-for-byte", "panId": "old"}]
            state = json.dumps({"alertHistory": history, "posts": [post()]})
            (data / "lh-state.json").write_text(state, encoding="utf-8")
            with patch.object(monitor, "DATA", data): monitor.mark_failure("simulated timeout")
            report = json.loads((data / "lh-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["alertHistory"], history)
            self.assertEqual((data / "lh-state.json").read_text(encoding="utf-8"), state)


if __name__ == "__main__": unittest.main()
