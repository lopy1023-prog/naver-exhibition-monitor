"""Failure and timing boundaries, exercised without live notifications."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitor
from diff import compare
from parser import classify, parse_detail
from pipeline import reception_events, comparison_baseline


def post(**changes):
    return {"panId": "isolated-audit", "title": "수원 청년 임대 모집", "category": "rental", "region": "경기도",
            "directSuwon": True, "broadCandidate": True, "status": "공고중", "detailUrl": "https://apply.lh.or.kr/",
            "applicationStart": "2026-10-16T10:00:00+09:00", "applicationEnd": "2026-10-16", "attachments": [], **changes}


def slot(hour, end_hour, label):
    return {"start": f"2026-10-16T{hour:02}:00:00+09:00", "end": f"2026-10-16T{end_hour:02}:00:00+09:00", "label": label}


def notice_html(status="공고중", body="공급지역 수원시 안내문 원본"):
    return ('<div id="sub_container"><div class="bbs_ViewA"><h3>수원 청년 임대 모집</h3>'
            f'<ul class="bbsV_data"><li><strong>공고상태</strong>{status}</li></ul>'
            f'<div class="bbsV_cont">{body}</div></div><table><caption>공급일정</caption><tbody>'
            '<tr><td>일반공급</td><td>2026.10.16 10:00 ~ 2026.10.16 17:00</td></tr></tbody></table></div>')


class BoundaryTests(unittest.TestCase):
    def test_same_day_status_transition_does_not_consume_next_round(self):
        rounds = [slot(10, 12, "1순위"), slot(14, 17, "2순위")]
        before = post(applicationSchedules=rounds)
        opened = {**before, "status": "접수중"}
        events, seen = reception_events(compare([before], [opened]), [before], [opened], {},
                     "2026-10-16T09:00:00+09:00", "2026-10-16T10:01:00+09:00", True)
        self.assertEqual(events[0]["officialStarts"], [rounds[0]["start"]])
        later, seen = reception_events([], [opened], [opened], seen,
                     "2026-10-16T10:01:00+09:00", "2026-10-16T14:01:00+09:00", True)
        self.assertEqual(len(later), 1)
        self.assertEqual(later[0]["officialStarts"], [rounds[1]["start"]])
        repeated, _ = reception_events([], [opened], [opened], seen,
                     "2026-10-16T14:01:00+09:00", "2026-10-16T15:00:00+09:00", True)
        self.assertEqual(repeated, [])

    def test_status_before_known_future_round_does_not_consume_it(self):
        future = slot(14, 17, "대상자별 접수")
        before = post(applicationStart=future["start"], applicationSchedules=[future])
        opened = {**before, "status": "접수중"}
        events, seen = reception_events(compare([before], [opened]), [before], [opened], {},
                     "2026-10-16T09:00:00+09:00", "2026-10-16T10:00:00+09:00", True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["receptionEvidence"], "officialStatus")
        self.assertEqual(events[0]["officialStarts"], [])
        later, _ = reception_events([], [opened], [opened], seen,
                     "2026-10-16T10:00:00+09:00", "2026-10-16T14:01:00+09:00", True)
        self.assertEqual(len(later), 1)
        self.assertEqual(later[0]["officialStarts"], [future["start"]])

    def test_status_delayed_beyond_end_still_links_to_announced_start(self):
        before = post(applicationSchedules=[slot(10, 17, "일반공급")])
        _, seen = reception_events([], [before], [before], {},
                     "2026-10-16T09:00:00+09:00", "2026-10-16T10:01:00+09:00", True)
        opened = {**before, "status": "접수중"}
        events, _ = reception_events(compare([before], [opened]), [before], [opened], seen,
                     "2026-10-16T10:01:00+09:00", "2026-10-16T18:00:00+09:00", True)
        self.assertEqual(events, [])

    def test_real_html_late_status_alone_is_quiet_but_body_correction_alerts(self):
        before = parse_detail(notice_html(), post())
        _, seen = reception_events([], [before], [before], {},
                     "2026-10-16T09:00:00+09:00", "2026-10-16T10:01:00+09:00", True)
        opened = parse_detail(notice_html("접수중"), post())
        events, _ = reception_events(compare([before], [opened]), [before], [opened], seen,
                     "2026-10-16T10:01:00+09:00", "2026-10-16T11:00:00+09:00", True)
        alerts, _ = monitor.build_alerts(events, [before], [opened], [], "2026-10-16T11:00:00+09:00", True)
        self.assertEqual(alerts, [])
        corrected = parse_detail(notice_html("접수중", "공급지역 수원시 안내문 정정"), post())
        events, _ = reception_events(compare([before], [corrected]), [before], [corrected], seen,
                     "2026-10-16T10:01:00+09:00", "2026-10-16T11:00:00+09:00", True)
        alerts, _ = monitor.build_alerts(events, [before], [corrected], [], "2026-10-16T11:00:00+09:00", True)
        self.assertEqual(len(alerts), 1)
        self.assertIn("detailTextHash", alerts[0]["fields"])

    def test_status_hash_migration_preserves_simultaneous_real_body_change(self):
        # Frozen v2 hash from the same official-shaped HTML before the policy
        # change; it included the status metadata.
        old = parse_detail(notice_html(), post())
        old.update(hashVersion=2, detailTextHash="bdb6480c2e84a55b9251e52bbb81887b36ce82ba48ebffce843b0781f85d8b36")
        current = parse_detail(notice_html("접수중"), post(_previousStatus="공고중"))
        changes = compare(comparison_baseline([old], [current], {}), [current])
        self.assertEqual(changes[0]["fields"], ["status"])
        corrected = parse_detail(notice_html("접수중", "공급지역 수원시 안내문 정정"), post(_previousStatus="공고중"))
        changes = compare(comparison_baseline([old], [corrected], {}), [corrected])
        self.assertIn("detailTextHash", changes[0]["fields"])

    def test_terminal_status_does_not_emit_scheduled_start(self):
        for status in ("접수마감", "접수종료", "공고취소", "취소", "접수중단"):
            with self.subTest(status=status):
                item = post(status=status)
                events, _ = reception_events([], [item], [item], {},
                      "2026-10-16T09:00:00+09:00", "2026-10-16T10:01:00+09:00", True)
                self.assertEqual(events, [])

    def test_expired_precise_window_is_not_announced_as_start(self):
        item = post(applicationSchedules=[slot(10, 17, "일반공급")])
        events, _ = reception_events([], [item], [item], {},
                      "2026-10-16T09:00:00+09:00", "2026-10-16T18:00:00+09:00", True)
        self.assertEqual(events, [])
        reopened = {**item, "status": "접수중"}
        events, _ = reception_events(compare([item], [reopened]), [item], [reopened], {},
                      "2026-10-16T09:00:00+09:00", "2026-10-16T18:00:00+09:00", True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["receptionEvidence"], "officialStatus")

    def test_contact_label_ends_inline_supply_geography(self):
        for label in ("문의처", "접수처", "연락처", "전화번호", "상담센터"):
            with self.subTest(label=label):
                actual = classify({"title": "부산 청년주택 모집", "region": "부산광역시", "category": "rental"},
                                  f"공급지역 : 부산광역시 {label} : 경기도 수원시 상담센터")
                self.assertFalse(actual["directSuwon"])
                actual = classify({"title": "지역 통합 모집", "region": "", "category": "rental"},
                                  f"공급지역 : 수원시 {label} : 부산광역시 상담센터")
                self.assertTrue(actual["directSuwon"])

    def test_repeated_supply_fields_after_contact_are_not_swallowed(self):
        actual = classify({"title": "부산 통합 모집", "region": "부산광역시", "category": "notice"},
                          "공급지역 : 부산광역시 문의처 : 부산 공급지역 : 수원시")
        self.assertTrue(actual["directSuwon"])

    def test_bad_optional_span_retains_notice_and_broad_candidate(self):
        for attr, value in (("colspan", ""), ("colspan", "unknown"), ("colspan", "0"), ("rowspan", ""), ("rowspan", "unknown")):
            with self.subTest(attr=attr, value=value):
                html = ('<div id="sub_container"><div class="bbs_ViewA"><h3>경기남부 통합 모집</h3></div>'
                        '<table><caption>공급정보 : 지역</caption><thead><tr><th>지역</th></tr></thead>'
                        f'<tbody><tr><td {attr}="{value}">경기도</td></tr></tbody></table></div>')
                try:
                    actual = parse_detail(html, post(title="경기남부 통합 모집", directSuwon=False))
                except (ValueError, TypeError) as exc:
                    self.fail(f"Optional supply layout aborted the notice: {exc}")
                self.assertTrue(actual["broadCandidate"])

    def test_rounds_with_varied_poll_gaps_and_delayed_status(self):
        rounds = [slot(9, 18, "1순위"), slot(11, 18, "2순위"), slot(15, 18, "3순위")]
        beginning = datetime.fromisoformat("2026-10-16T08:00:00+09:00")
        ending = datetime.fromisoformat("2026-10-16T18:00:00+09:00")
        for interval in (15, 30, 90, 180):
            for status_hour in range(8, 17):
                with self.subTest(pollMinutes=interval, statusHour=status_hour):
                    previous = post(applicationStart=rounds[0]["start"], applicationSchedules=rounds)
                    previous_at = beginning - timedelta(minutes=1)
                    seen, observed = {}, set()
                    check = beginning
                    while check <= ending:
                        current = {**previous, "status": "접수중" if check.hour >= status_hour else "공고중",
                                   "applicationSchedules": list(reversed(rounds))}
                        # Independent oracle: only the starts crossed by this
                        # successful check can be recorded as scheduled starts.
                        expected = {s["start"] for s in rounds
                                    if previous_at < datetime.fromisoformat(s["start"]) <= check}
                        events, seen = reception_events(compare([previous], [current]), [previous], [current], seen,
                                                       previous_at.isoformat(), check.isoformat(), True)
                        actual = {start for e in events for start in e.get("officialStarts", [])}
                        self.assertEqual(actual, expected)
                        self.assertFalse(actual & observed)
                        observed.update(actual)
                        previous, previous_at = current, check
                        check += timedelta(minutes=interval)
                    self.assertEqual(observed, {s["start"] for s in rounds})

    def test_one_supplemental_failure_preserves_state_and_unknown_events(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            history = [{"alertId": "preserve-original-event", "panId": "original"}]
            state = json.dumps({"baselineStart": "2026-08-16", "posts": [], "alertHistory": history})
            for name in ("lh-state.json", "lh-tracked-state.json"):
                (data / name).write_text(state, encoding="utf-8")
            info = {"totalCount": 0, "parsedCount": 0, "totalPages": 0, "checkedPages": 0, "complete": True}
            client = MagicMock()
            client.collect_category.return_value = (info, [])
            client.collect_presale.return_value = (info, [])
            def collect(client, source, *args):
                if source == "calendar":
                    raise TimeoutError("injected calendar outage")
                return info, []
            with patch.object(monitor, "DATA", data), patch.object(monitor, "TRACKED", data / "no-tracked.json"), \
                 patch.object(monitor, "LHClient", return_value=client), patch.object(monitor, "collect_source", side_effect=collect):
                self.assertEqual(monitor.run(), 1)
            self.assertEqual((data / "lh-state.json").read_text(encoding="utf-8"), state)
            self.assertEqual((data / "lh-tracked-state.json").read_text(encoding="utf-8"), state)
            result = json.loads((data / "lh-report.json").read_text(encoding="utf-8"))
            self.assertEqual(result["sourceStatus"], "error")
            self.assertEqual(result["alertHistory"], history)
            self.assertIsNone(result["alerts"])
            self.assertIsNone(result["new"])


if __name__ == "__main__":
    unittest.main()
