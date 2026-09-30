"""Parse LH's server-rendered official announcement pages."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from bs4 import BeautifulSoup

BASE = "https://apply.lh.or.kr"
LIST_PATH = "/lhapply/apply/wt/wrtanc/selectWrtancList.do"
DETAIL_PATH = "/lhapply/apply/wt/wrtanc/selectWrtancInfo.do"
DIRECT = ("수원", "수원시", "수원당수", "장안구", "권선구", "팔달구", "영통구")
BROAD_SCOPE = re.compile(r"경기\s*남부(?:지역본부)?|경기도|경기지역|수도권|전국|(?<![가-힣])경기(?![가-힣])")
OTHER_SCOPE = re.compile(r"경기\s*북부|부산|대구|광주|충북|충청북도|충남|충청남도|경북|경상북도|경남|경상남도|전북|전라북도|전남|전라남도|대전|울산|인천|강원|제주|세종")
DETAIL_SCOPE = re.compile(r"(?:공급|모집|대상|입주|사업)\s*(?:지역|주택|대상|지구|소재지)\s*[:：]?\s*.{0,40}?(?:" + BROAD_SCOPE.pattern + r")")
CORRECTIONS = ("정정공고", "수정공고", "변경공고", "추가안내", "첨부파일 교체", "공급주택 목록 교체")


class ParseError(ValueError):
    pass


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def classify(post: dict, detail_text: str = "") -> dict:
    title, region = post.get("title", ""), post.get("region", "")
    text = " ".join((title, region, detail_text))
    post["directSuwon"] = any(word in text for word in DIRECT)
    headline_scope = bool(BROAD_SCOPE.search(title))
    region_scope = bool(BROAD_SCOPE.search(region))
    detail_scope = bool(DETAIL_SCOPE.search(detail_text))
    # A named non-Suwon jurisdiction takes precedence over a generic list region
    # or an unrelated address in the common detail-page text.
    named_elsewhere = bool(OTHER_SCOPE.search(title) or OTHER_SCOPE.search(region))
    post["broadCandidate"] = (post.get("category") in ("rental", "sale", "presale")
                              and (headline_scope or detail_scope or (region_scope and not named_elsewhere)))
    return post


def identity(post: dict) -> str:
    return post.get("panId") or post.get("detailUrl") or digest([post.get("title"), post.get("postedAt"), post.get("type")])


def detail_url(pan_id: str, ccr: str, upper: str, subtype: str, mi: str) -> str:
    return BASE + DETAIL_PATH + "?" + urlencode({"panId": pan_id, "ccrCnntSysDsCd": ccr, "uppAisTpCd": upper, "aisTpCd": subtype, "mi": mi})


def parse_list(html: str, category: str, mi: str, checked_at: str) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    total = soup.select_one(".bbs_total")
    if not total:
        raise ParseError("LH 목록 건수 표시를 찾지 못함: 응답 구조 변경 또는 오류 화면")
    match = re.search(r"전체\s*([\d,]+)\s*건\s*([\d,]+)\s*/\s*([\d,]+)\s*페이지", clean(total.get_text(" ", strip=True)))
    if not match:
        raise ParseError("LH 목록 건수/페이지 표시를 해석하지 못함")
    count, current_page, total_pages = (int(v.replace(",", "")) for v in match.groups())
    expected_pages = math.ceil(count / 100) if count else 0
    if total_pages != expected_pages:
        raise ParseError(f"페이지 수 불일치: LH={total_pages}, 계산={expected_pages}, 건수={count}")
    posts = []
    for row in soup.select(".bbs_ListA tbody tr"):
        link = row.select_one("a.slpaInfoBtn" if category == "presale" else "a.wrtancInfoBtn")
        if not link:
            continue
        cells = row.find_all("td", recursive=False)
        if len(cells) < 8:
            raise ParseError("LH 공고 행 열 수 변경")
        pan_id = link.get("data-id1", "").strip()
        ccr = link.get("data-id2", "").strip()
        upper = link.get("data-id3", "").strip()
        subtype = link.get("data-id4", "").strip()
        if not all((pan_id, ccr, upper) if category == "presale" else (pan_id, ccr, upper, subtype)):
            raise ParseError("LH 공고 행 식별자 누락")
        title_node = link.select_one("span") or link
        day = title_node.select_one("em")
        if day:
            day.decompose()
        title = clean(title_node.get_text(" ", strip=True))
        offset = -1 if category == "presale" else 0
        posted = clean(cells[5 + offset].get_text(" ", strip=True)).replace(".", "-")
        deadline = clean(cells[6 + offset].get_text(" ", strip=True)).replace(".", "-")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", posted) or not title:
            raise ParseError(f"LH 공고 {pan_id} 제목 또는 게시일 누락")
        post = {
            "panId": pan_id, "title": title, "category": category,
            "type": clean(cells[1].get_text(" ", strip=True)),
            "region": "" if category == "presale" else clean(cells[3].get_text(" ", strip=True)),
            "postedAt": posted, "applicationStart": "", "applicationEnd": deadline,
            "status": clean(cells[7 + offset].get_text(" ", strip=True)),
            "detailUrl": (BASE + "/lhapply/apply/bfh/slpa/slpaInfo.do?" + urlencode({"mi": mi, "panId": pan_id, "aisTpCd": ccr, "otxtPanId": upper})) if category == "presale" else detail_url(pan_id, ccr, upper, subtype, mi),
            "attachments": [], "correction": any(v in title for v in CORRECTIONS),
            "correctionOf": "", "firstSeenAt": checked_at, "lastSeenAt": checked_at,
            "needsReview": False, "reviewReason": [],
        }
        classify(post)
        post["contentHash"] = content_hash(post)
        posts.append(post)
    expected_rows = min(100, max(0, count - (current_page - 1) * 100)) if count else 0
    if len(posts) != expected_rows:
        raise ParseError(f"페이지 {current_page} 행 수 불일치: {len(posts)} / {count}")
    return {"totalCount": count, "totalPages": total_pages, "currentPage": current_page}, posts


def content_hash(post: dict) -> str:
    fields = ("title", "category", "type", "region", "postedAt", "applicationStart", "applicationEnd", "status", "detailTextHash", "attachments", "correction", "correctionOf")
    return digest({key: post.get(key) for key in fields})


def parse_detail(html: str, post: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    view = soup.select_one(".bbs_ViewA")
    if not view or not view.select_one("h3"):
        raise ParseError(f"LH 상세 구조 변경: {post['panId']}")
    title = clean(view.select_one("h3").get_text(" ", strip=True))
    if title != post["title"]:
        # A live correction may change the displayed title between list/detail requests.
        post["title"] = title
    post["correction"] = any(value in title for value in CORRECTIONS)
    for item in view.select(".bbsV_data li"):
        label = item.select_one("strong")
        if not label:
            continue
        key = clean(label.get_text(" ", strip=True))
        value = clean(item.get_text(" ", strip=True).replace(key, "", 1))
        if key == "공고상태": post["status"] = value
        elif key == "유형": post["type"] = value
        elif key == "마감일":
            match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", value)
            if match:
                year, month, day = map(int, match.groups())
                post["applicationEnd"] = f"{year:04}-{month:02}-{day:02}"
    # LH closes .bbs_ViewA before some supply/schedule sections; #sub_container owns the full detail.
    main = soup.select_one("#sub_container") or view
    text = clean(main.get_text(" ", strip=True))
    if not text:
        raise ParseError(f"LH 상세 본문 누락: {post['panId']}")
    post["detailTextHash"] = hashlib.sha256(text.encode()).hexdigest()
    post["detailExcerpt"] = text[:500]
    post["_detailText"] = text
    date_pattern = r"\d{4}[.\-]\d{2}[.\-]\d{2}"
    schedule = next((table for table in main.select("table") if table.select_one("caption") and "공급일정" in table.select_one("caption").get_text()), None)
    if schedule:
        dates = re.findall(date_pattern, schedule.get_text(" ", strip=True))
        if dates:
            post["applicationStart"] = dates[0].replace(".", "-")
    if not post["applicationStart"]:
        match = re.search(r"(?:접수기간|신청일시|신청기간)\s*[:：]?\s*(" + date_pattern + r")", text)
        if match:
            post["applicationStart"] = match.group(1).replace(".", "-")
    attachments = []
    for link in view.select(".bbsV_atchmnfl a[href]"):
        match = re.search(r"(?:fileDownLoad\(['\"]?|[?&]fileid=)(\d+)", link.get("href", ""))
        if match:
            name = clean(link.get_text(" ", strip=True))
            attachments.append({"fileId": match.group(1), "name": name, "url": BASE + "/lhapply/lhFile.do?fileid=" + match.group(1)})
    post["attachments"] = attachments
    classify(post, text)
    post["contentHash"] = content_hash(post)
    return post
