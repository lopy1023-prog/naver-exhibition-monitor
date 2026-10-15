"""Replay snapshots and synthetic receptions without production writes."""
import argparse
import copy
import json
import random
from pathlib import Path
from diff import compare
from monitor import build_alerts
from pipeline import comparison_baseline, reception_events


def simulate(baseline, current):
    result = {}
    original = baseline.get("alertHistory", [])
    history = current.get("alertHistory", [])
    assert history[:len(original)] == original, "Original history changed"
    result["historyPrefixPreserved"] = len(original)
    posts = copy.deepcopy(current["posts"])
    for iteration in (2, 3):
        reordered = copy.deepcopy(posts)
        random.Random(iteration).shuffle(reordered)
        for p in reordered:
            p["lastSeenAt"] = f"simulation-{iteration}"
            p["calendarSchedules"] = list(reversed(p.get("calendarSchedules", [])))
        alerts, next_history = build_alerts(compare(posts, reordered), posts, reordered, history, "2026-10-16T08:00:00+09:00", True)
        assert alerts == [] and next_history == history
        result[f"unchangedReplay{iteration}Alerts"] = len(alerts)
    before = comparison_baseline(baseline["posts"], posts, {})
    supplemental_new = [e for e in compare(before, posts) if e["kind"] == "new" and any(p["panId"] == e["panId"] and p.get("category") not in ("rental", "sale", "land", "commercial", "presale") for p in posts)]
    assert supplemental_new == []
    result["supplementalBackfillAlerts"] = len(supplemental_new)
    sample = next(copy.deepcopy(p) for p in posts if p.get("directSuwon") and p.get("category") == "rental")
    sample.update({"panId": "simulation-only", "applicationStart": "2026-10-16T10:00:00+09:00", "applicationEnd": "2026-10-17", "status": "공고중", "currentlyListed": True,
                   "calendarSchedules": [{"start": "2026-10-16", "end": "2026-10-17"}],
                   "applicationSchedules": [{"start": "2026-10-16T10:00:00+09:00", "end": "2026-10-17"}]})
    events, seen = reception_events([], [sample], [sample], {}, "2026-10-16T09:59:00+09:00", "2026-10-16T10:01:00+09:00", True)
    assert len(events) == 1 and events[0]["receptionEvidence"] == "officialStartTime"
    result["scheduledReceptionAlerts"] = len(events)
    late = {**sample, "status": "접수중"}
    events, _ = reception_events(compare([sample], [late]), [sample], [late], seen, "2026-10-16T10:01:00+09:00", "2026-10-16T11:00:00+09:00", True)
    assert events == []
    result["lateStatusDuplicateAlerts"] = len(events)
    for city in ("수원", "화성", "오산"):
        new = {**sample, "panId": "simulation-" + city, "title": city + " 행복주택 신규 모집", "confirmedRegions": [city]}
        alerts, _ = build_alerts(compare([], [new]), [], [new], [], "2026-10-16T10:00:00+09:00", True)
        assert len(alerts) == 1
        result[city + "NewNoticeAlerts"] = len(alerts)
    result["productionWrites"] = 0
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = simulate(json.loads(args.baseline.read_text(encoding="utf-8")), json.loads(args.current.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False))
