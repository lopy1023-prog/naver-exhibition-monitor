"""Hourly LH Suwon monitor. Exit nonzero unless all official lists validate."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from diff import compare, family_key
from lh_client import CATEGORIES, LHClient
from parser import ParseError, classify, content_hash, identity, parse_detail

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "lh"
TRACKED = Path(__file__).with_name("tracked.json")
KST = timezone(timedelta(hours=9))
TRACK_PATTERNS = {
    "잔여주택 공개": r"잔여\s*(?:주택|세대)",
    "수원 잔여물량": r"수원.{0,70}잔여|잔여.{0,70}수원",
    "열람기간": r"열람\s*기간|열람\s*일",
    "정정공고": r"정정\s*공고|수정\s*공고",
    "물량변경": r"물량\s*변경|공급\s*(?:주택|세대|호수)\s*변경",
    "결과 발표": r"결과\s*발표|당첨자\s*발표",
}


def now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def mark_failure(reason: str) -> None:
    """Publish a failed run without advancing the last successful snapshot."""
    feed = read_json(DATA / "lh-feed.json", {})
    if feed.get("sourceStatus") != "error":
        feed = {"schemaVersion": 1, "baselineStart": feed.get("baselineStart"),
                "categories": {}, "postCount": 0, "posts": [], "errors": []}
    feed["sourceStatus"] = "error"
    feed["syncedAt"] = now()
    feed["errors"] = list(dict.fromkeys([*feed.get("errors", []), reason]))
    report = {"schemaVersion": 1, "sourceStatus": "error", "syncedAt": feed["syncedAt"],
              "new": None, "changed": None, "alerts": None, "directSuwon": None, "broadCandidates": None,
              "needsReview": None, "tracked": None, "errors": feed["errors"]}
    write_json(DATA / "lh-feed.json", feed)
    write_json(DATA / "lh-report.json", report)


def enrich(client: LHClient, post: dict):
    # Check every detail: a generic list title may hide Suwon only in the supply location.
    try:
        post = parse_detail(client.get(post["detailUrl"]), post)
    except Exception as exc:
        post["needsReview"] = True
        post["reviewReason"].append(f"상세페이지 확인 실패: {type(exc).__name__}: {exc}")
        return post
    detail_text = post.pop("_detailText", "")
    classify(post, detail_text)
    if post.get("tracked"):
        searchable = " ".join((post["title"], detail_text))
        post["trackedSignals"] = {}
        for label, pattern in TRACK_PATTERNS.items():
            match = re.search(pattern, searchable)
            post["trackedSignals"][label] = searchable[max(0, match.start() - 60):match.end() + 100] if match else None
        post["trackedSignals"]["신청 시작"] = post.get("applicationStart") or None
        post["trackedSignals"]["신청 종료"] = post.get("applicationEnd") or None
        if not post.get("applicationStart"):
            post["needsReview"] = True
            post["reviewReason"].append("추적 공고 신청 시작일 자동 확인 불가")
    post["contentHash"] = content_hash(post)
    return post


def validate(feed: dict) -> list[str]:
    errors = []
    required = tuple(CATEGORIES) + ("presale",)
    for category in required:
        info = feed.get("categories", {}).get(category)
        if not info or not info.get("complete"):
            errors.append(f"{category}: 수집 미완료")
            continue
        if info.get("totalPages") != info.get("checkedPages") or info.get("totalCount") != info.get("parsedCount"):
            errors.append(f"{category}: 페이지 또는 공고 건수 불일치")
    if len(feed.get("posts", [])) != feed.get("postCount"):
        errors.append("전체 공고 건수 불일치")
    if feed.get("sourceStatus") != "ok":
        errors.extend(feed.get("errors", []))
    return list(dict.fromkeys(errors))


def summary(post: dict) -> dict:
    keys = ("panId", "title", "category", "type", "region", "postedAt", "applicationStart",
            "applicationEnd", "status", "detailUrl", "directSuwon", "broadCandidate", "needsReview",
            "reviewReason", "correction", "correctionOf", "noticeFamily", "tracked", "trackedSignals")
    return {key: post[key] for key in keys if key in post}


def link_families(posts: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for post in posts:
        post["noticeFamily"] = family_key(post)
        groups.setdefault(post["noticeFamily"], []).append(post)
    for group in groups.values():
        originals = [post for post in group if not post.get("correction")]
        originals.sort(key=lambda post: post.get("postedAt", ""))
        if not originals:
            continue
        for post in group:
            if post.get("correction"):
                post["correctionOf"] = originals[0]["panId"]
                post["contentHash"] = content_hash(post)


def run() -> int:
    checked_at = now()
    last = read_json(DATA / "lh-state.json", {})
    baseline_start = last.get("baselineStart")
    today = datetime.now(KST).date()
    start = date.fromisoformat(baseline_start) if baseline_start else today - timedelta(days=45)
    client = LHClient()
    feed = {"schemaVersion": 1, "sourceStatus": "error", "syncedAt": checked_at,
            "baselineStart": start.isoformat(), "categories": {}, "postCount": 0, "posts": [], "errors": []}
    old_by_id = {identity(post): post for post in last.get("posts", [])}
    posts = []
    for category in CATEGORIES:
        try:
            info, found = client.collect_category(category, start, today, checked_at)
            feed["categories"][category] = info
            posts.extend(found)
            print(f"{category}: {info['parsedCount']} posts, {info['checkedPages']}/{info['totalPages']} pages", flush=True)
        except Exception as exc:
            reason = f"{category}: {type(exc).__name__}: {exc}"
            feed["categories"][category] = {"totalCount": getattr(exc, "total_count", None),
                                            "parsedCount": getattr(exc, "parsed_count", 0),
                                            "totalPages": getattr(exc, "total_pages", None),
                                            "checkedPages": getattr(exc, "checked_pages", 0), "complete": False,
                                            "sourceUrl": f"https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi={CATEGORIES[category][0]}",
                                            "checkedAt": checked_at, "error": reason}
            feed["errors"].append(reason)
    try:
        info, found = client.collect_presale(checked_at, start, today)
        feed["categories"]["presale"] = info
        posts.extend(found)
    except Exception as exc:
        reason = f"presale: {type(exc).__name__}: {exc}"
        feed["categories"]["presale"] = {"totalCount": None, "parsedCount": 0, "totalPages": None,
                                           "checkedPages": 0, "complete": False,
                                           "sourceUrl": "https://apply.lh.or.kr/lhapply/apply/bfh/slpa/list.do?mi=1349",
                                           "checkedAt": checked_at, "error": reason}
        feed["errors"].append(reason)
    if feed["errors"]:
        feed["posts"] = posts
        feed["postCount"] = len(posts)
        report = {"schemaVersion": 1, "sourceStatus": "error", "syncedAt": checked_at,
                  "new": None, "changed": None, "alerts": None, "directSuwon": None, "broadCandidates": None,
                  "needsReview": None, "tracked": None, "errors": feed["errors"]}
        write_json(DATA / "lh-feed.json", feed)
        write_json(DATA / "lh-report.json", report)
        print("LH source error: " + "; ".join(feed["errors"]), file=sys.stderr)
        return 1

    # The tracked notice is searched separately over all of 2026 even when it falls outside the baseline range.
    tracked_config = read_json(TRACKED, {"notices": []})
    tracked_posts = []
    for config in tracked_config.get("notices", []):
        try:
            _, matches = client.collect_category("rental", date(2026, 1, 1), today, checked_at, config["search"])
            matches = [item for item in matches if all(term in item["title"] for term in config["containsAll"])]
            if not matches:
                raise ParseError(f"추적 공고 검색 결과 없음: {config['search']}")
            for item in matches:
                item["tracked"] = config["id"]
            tracked_posts.extend(matches)
        except Exception as exc:
            feed["errors"].append(f"tracked {config['id']}: {type(exc).__name__}: {exc}")
    if feed["errors"]:
        write_json(DATA / "lh-feed.json", feed)
        write_json(DATA / "lh-report.json", {"schemaVersion": 1, "sourceStatus": "error", "syncedAt": checked_at,
                                                 "new": None, "changed": None, "alerts": None, "directSuwon": None,
                                                 "broadCandidates": None, "needsReview": None, "tracked": None,
                                                 "errors": feed["errors"]})
        return 1

    by_id = {identity(post): post for post in posts}
    for post in tracked_posts:
        by_id.setdefault(identity(post), post)["tracked"] = post["tracked"]
    posts = list(by_id.values())
    worker_local = threading.local()
    for post in posts:
        previous = old_by_id.get(identity(post))
        if previous:
            post["firstSeenAt"] = previous.get("firstSeenAt", checked_at)
    def enrich_one(post: dict) -> dict:
        if not hasattr(worker_local, "client"):
            worker_local.client = LHClient()
        return enrich(worker_local.client, post)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(enrich_one, post) for post in posts]
        for index, future in enumerate(as_completed(futures), start=1):
            future.result()
            if index % 50 == 0:
                print(f"details: {index}/{len(posts)}", flush=True)
    link_families(posts)
    detail_failures = sum(any(reason.startswith("상세페이지 확인 실패") for reason in post["reviewReason"]) for post in posts)
    if len(posts) >= 10 and detail_failures * 5 >= len(posts):
        feed["errors"].append(f"광범위한 상세페이지 확인 실패: {detail_failures}/{len(posts)}")
    known = next((post for post in posts if post.get("panId") == "0000061181"), None)
    if not known or not known.get("directSuwon"):
        from bs4 import BeautifulSoup
        known_url = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=0000061181&ccrCnntSysDsCd=02&uppAisTpCd=39&aisTpCd=39&mi=1027"
        try:
            heading = BeautifulSoup(client.get(known_url), "html.parser").select_one(".bbs_ViewA h3")
            if not heading:
                feed["errors"].append("panId=0000061181 공식 상세 제목 확인 실패")
            elif "수원" in heading.get_text():
                feed["errors"].append("공식 상세에 존재하는 panId=0000061181 수원 공고가 목록/분류에서 누락")
            elif not known:
                feed["errors"].append("panId=0000061181 공식 상세는 존재하지만 목록에서 누락")
        except Exception as exc:
            feed["errors"].append(f"panId=0000061181 확인 실패: {type(exc).__name__}: {exc}")
    feed["posts"] = sorted(posts, key=lambda p: (p.get("postedAt", ""), p.get("panId", "")), reverse=True)
    feed["postCount"] = len(feed["posts"])
    feed["sourceStatus"] = "error" if feed["errors"] else "ok"
    errors = validate(feed)
    if errors:
        feed["sourceStatus"] = "error"
        feed["errors"] = errors
        report = {"schemaVersion": 1, "sourceStatus": "error", "syncedAt": checked_at,
                  "new": None, "changed": None, "alerts": None, "directSuwon": None, "broadCandidates": None,
                  "needsReview": None, "tracked": None, "errors": errors}
        write_json(DATA / "lh-feed.json", feed)
        write_json(DATA / "lh-report.json", report)
        print("LH validation error: " + "; ".join(errors), file=sys.stderr)
        return 1
    events = compare(last.get("posts", []), feed["posts"])
    current_by_id = {identity(post): post for post in feed["posts"]}
    alerts = [event for event in events if current_by_id.get(event.get("panId"), {}).get("directSuwon")]
    report = {"schemaVersion": 1, "sourceStatus": "ok", "syncedAt": checked_at,
              "new": [e for e in events if e["kind"] in ("new", "correction")],
              "changed": [e for e in events if e["kind"] == "changed"],
              "alerts": alerts if last.get("posts") else [],
              "directSuwon": [summary(p) for p in feed["posts"] if p["directSuwon"]],
              "broadCandidates": [summary(p) for p in feed["posts"] if p["broadCandidate"]],
              "needsReview": [summary(p) for p in feed["posts"] if p["needsReview"]],
              "tracked": [summary(p) for p in feed["posts"] if p.get("tracked")], "errors": []}
    tracked_state = {"schemaVersion": 1, "syncedAt": checked_at, "posts": report["tracked"]}
    state = {"schemaVersion": 1, "syncedAt": checked_at, "baselineStart": start.isoformat(), "posts": feed["posts"]}
    write_json(DATA / "lh-feed.json", feed)
    write_json(DATA / "lh-report.json", report)
    write_json(DATA / "lh-tracked-state.json", tracked_state)
    # The normal snapshot is the commit marker and is written only after all other files.
    write_json(DATA / "lh-state.json", state)
    print(json.dumps({"sourceStatus": "ok", "postCount": feed["postCount"],
                      "categories": {k: f"{v['checkedPages']}/{v['totalPages']}" for k, v in feed["categories"].items()},
                      "directSuwon": len(report["directSuwon"]), "broadCandidates": len(report["broadCandidates"]),
                      "needsReview": len(report["needsReview"]),
                      "targetPanId": any(p["panId"] == "0000061181" and p["directSuwon"] for p in feed["posts"])}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--mark-failure", metavar="REASON")
    args = parser.parse_args()
    if args.mark_failure:
        mark_failure(args.mark_failure)
        return 0
    if args.validate:
        feed = read_json(DATA / "lh-feed.json", {})
        errors = validate(feed)
        if errors:
            print("; ".join(errors), file=sys.stderr)
            return 1
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
