"""Snapshot migration, canonical source merging and one-time reception alerts."""
from __future__ import annotations

import copy
from datetime import datetime, time, timedelta, timezone

from parser import classify, digest, identity

KST = timezone(timedelta(hours=9))


def merge_sources(primary, supplemental, old_posts):
    merged = {}
    old_by_id = {identity(p): p for p in old_posts}
    for item in [*primary, *supplemental]:
        ident = identity(item)
        if ident not in merged:
            merged[ident] = copy.deepcopy(item)
            if ident in old_by_id:
                merged[ident]["firstSeenAt"] = old_by_id[ident].get("firstSeenAt", item.get("firstSeenAt", ""))
            continue
        target = merged[ident]
        target["sourceNames"] = sorted(set(target.get("sourceNames", [target.get("category")]) + item.get("sourceNames", [item.get("category")])))
        if item.get("calendarSchedules"):
            target["calendarSchedules"] = copy.deepcopy(item["calendarSchedules"])
            target["calendarWindowStart"] = item.get("calendarWindowStart", "")
            target["calendarWindowEnd"] = item.get("calendarWindowEnd", "")
            for field in ("applicationStart", "applicationEnd"):
                if not target.get(field): target[field] = item.get(field, "")
        if item.get("tracked"): target["tracked"] = item["tracked"]
    # Retention is essential: disappearing calendar days or expired source rows
    # must never turn the same panId into a new notice on reappearance.
    for ident, old in old_by_id.items():
        if ident not in merged:
            merged[ident] = {**copy.deepcopy(old), "currentlyListed": False}
        else:
            merged[ident]["currentlyListed"] = True
            if "calendarSchedules" not in merged[ident] and old.get("calendarSchedules"):
                merged[ident]["calendarSchedules"] = copy.deepcopy(old["calendarSchedules"])
            elif old.get("calendarSchedules") and merged[ident].get("calendarWindowStart"):
                target = merged[ident]
                outside = [s for s in old["calendarSchedules"]
                           if (s.get("end") or s.get("start") or s.get("resultAt") or "9999")[:10] < target["calendarWindowStart"]
                           or (s.get("start") or s.get("resultAt") or "0000")[:10] > target["calendarWindowEnd"]]
                combined = {digest(s): s for s in outside + target["calendarSchedules"]}
                target["calendarSchedules"] = sorted(combined.values(), key=digest)
    return list(merged.values())


def comparison_baseline(old_posts, current, source_baselines):
    baseline = {identity(p): copy.deepcopy(p) for p in old_posts}
    for item in current:
        ident = identity(item)
        old = baseline.get(ident)
        if old is None:
            sources = item.get("sourceNames", [item.get("category", "")])
            supplemental = all(s not in ("rental", "sale", "land", "commercial", "presale") for s in sources)
            if supplemental and any(not source_baselines.get(s) for s in sources):
                baseline[ident] = copy.deepcopy(item)
            continue
        if old.get("hashVersion") != item.get("hashVersion"):
            # The legacy text included view counters. Establish the semantic
            # hash without rewriting any previously emitted alert IDs.
            old["detailTextHash"] = item.get("detailTextHash")
            old["directSuwon"] = item.get("directSuwon")
        if "calendarSchedules" not in old and "calendarSchedules" in item:
            old["calendarSchedules"] = copy.deepcopy(item["calendarSchedules"])
            for field in ("applicationStart", "applicationEnd"):
                if not source_baselines.get("calendar") or not old.get(field): old[field] = item.get(field)
        if "applicationSchedules" not in old and "applicationSchedules" in item:
            old["applicationSchedules"] = copy.deepcopy(item["applicationSchedules"])
    return list(baseline.values())


def is_target(post):
    return bool(post.get("directSuwon") or post.get("broadCandidate") or post.get("confirmedRegions") or post.get("tracked"))


def starts(post):
    values = {s.get("start", "") for s in post.get("calendarSchedules", [])}
    values.update(s.get("start", "") for s in post.get("applicationSchedules", []))
    if not any(values): values.add(post.get("applicationStart", ""))
    precise_days = {v[:10] for v in values if "T" in v}
    return sorted(v for v in values if v and ("T" in v or v[:10] not in precise_days))


def reception_events(events, old_posts, posts, previous_seen, previous_at, checked_at, initialized):
    seen = dict(previous_seen)
    output = copy.deepcopy(events)
    old = {identity(p): p for p in old_posts}
    current_time = datetime.fromisoformat(checked_at).astimezone(KST)
    prior_time = datetime.fromisoformat(previous_at).astimezone(KST) if previous_at else current_time
    for post in posts:
        if not is_target(post) or post.get("informationOnly") or post.get("currentlyListed") is False: continue
        ident = identity(post)
        before = old.get(ident)
        transition = bool(before and before.get("status") != "접수중" and post.get("status") == "접수중")
        due = []
        for start in starts(post):
            when = datetime.fromisoformat(start) if "T" in start else datetime.combine(datetime.fromisoformat(start).date(), time.min, KST)
            if when.tzinfo is None: when = when.replace(tzinfo=KST)
            token = digest([ident, start])
            if not initialized:
                if when <= current_time: seen[token] = checked_at
                continue
            if prior_time < when <= current_time and token not in seen: due.append((start, token))
        if transition:
            # The same schedule observed via time and via a delayed LH status
            # transition is one reception event, even across separate runs.
            values = starts(post)
            start = next((s for s in reversed(values) if s[:10] <= checked_at[:10]), values[0] if values else "")
            token = digest([ident, start])
            reopening = before.get("status") in ("접수마감", "마감", "접수종료")
            if reopening:
                token = digest([ident, start, "reopened", previous_at])
            if start and token in seen:
                output = [e for e in output if not (e.get("panId") == ident and e.get("kind") == "changed" and set(e.get("fields", [])) <= {"status"})]
                transition = False
            elif token not in seen:
                due.append((start, token))
        if not initialized or not due: continue
        matches = [e for e in output if e.get("panId") == ident]
        event = matches[0] if matches else {"kind": "receptionStart", "kinds": [], "panId": ident,
                                           "title": post["title"], "detailUrl": post["detailUrl"]}
        event["kinds"] = sorted(set(event.get("kinds", []) + ["receptionStarted"]))
        event["receptionEvidence"] = "officialStatus" if transition else "officialStartTime" if "T" in due[0][0] else "officialStartDate"
        event["officialStarts"] = sorted({s for s, _ in due})
        event["requiresEligibilityReview"] = True
        if not matches: output.append(event)
        for _, token in due: seen[token] = checked_at
    return output, seen


def annotate(post):
    post["roomCount"] = None
    post["roomCountStatus"] = "확인 필요"
    post["eligibilityStatus"] = "개별 공고의 자격·순위·대상자별 접수 일정 확인 필요"
    title = post.get("title", "")
    post["recruitmentKind"] = next((label for text, label in (("예비", "예비입주자"), ("잔여", "잔여모집"), ("추가", "추가모집")) if text in title), "공고 내용 확인 필요")
    return post
