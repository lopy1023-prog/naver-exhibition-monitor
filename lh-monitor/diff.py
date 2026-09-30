"""Compare only against the last successful LH snapshot."""

from __future__ import annotations

import re

from parser import identity


def family_key(post: dict) -> str:
    title = post.get("title", "")
    title = re.sub(r"[\[\(（]?\s*(정정공고|수정공고|변경공고|추가안내|정정|수정|변경)\s*[\]\)）]?", "", title)
    title = re.sub(r"\s+", "", title)
    return title


def compare(old_posts: list[dict], new_posts: list[dict]) -> list[dict]:
    old_by_id = {identity(post): post for post in old_posts}
    old_by_family: dict[str, list[dict]] = {}
    for post in old_posts:
        old_by_family.setdefault(family_key(post), []).append(post)
    events = []
    for post in new_posts:
        key = identity(post)
        old = old_by_id.get(key)
        if old is None:
            related = old_by_family.get(family_key(post), [])
            if post.get("correction") and related:
                post["correctionOf"] = related[0].get("panId", "")
            kind = "correction" if post.get("correction") else "new"
            events.append({"kind": kind, "panId": post.get("panId"), "title": post.get("title"), "detailUrl": post.get("detailUrl"), "relatedPanId": post.get("correctionOf", "")})
            continue
        changes = []
        for field in ("title", "type", "region", "postedAt", "applicationStart", "applicationEnd", "status", "detailTextHash", "attachments", "directSuwon"):
            if old.get(field) != post.get(field):
                changes.append(field)
        if not changes:
            continue
        kinds = ["changed"]
        if "status" in changes:
            kinds.append("statusChanged")
            if old.get("status") == "접수마감" and post.get("status") in ("공고중", "접수중"):
                kinds.append("reopened")
        if "applicationStart" in changes or "applicationEnd" in changes:
            kinds.append("deadlineChanged")
        if "attachments" in changes:
            kinds.append("attachmentChanged")
        if "추가모집" in post.get("title", "") or "추가입주자" in post.get("title", ""):
            kinds.append("additionalRecruitment")
        events.append({"kind": "changed", "kinds": kinds, "panId": post.get("panId"), "title": post.get("title"), "detailUrl": post.get("detailUrl"), "fields": changes})
    return events
