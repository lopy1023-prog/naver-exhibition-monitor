"""Validated official calendar, bulletin, plan and first-come adapters.

Only public HTML/JSON is fetched. Attachment bodies are never requested.
"""
from __future__ import annotations

import calendar
import copy
import json
import math
import re
from datetime import date, timedelta
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit, parse_qsl

from bs4 import BeautifulSoup

from parser import BASE, CORRECTIONS, ParseError, classify, clean, content_hash, detail_url, digest

CALENDAR = BASE + "/lhapply/apply/sc/list.do?mi=1312"
BOARD_PATH = "/lhapply/apply/noti/an/"
BOARDS = {"notice": ("03", "1079"), "moveIn": ("05", "1330"), "documents": ("02", "1080")}
PLANS = {"movePlan": ("/lhapply/apply/noti/mp/list.do", {"mi": "1331"}, "move"),
         "supplyRental": ("/lhapply/apply/noti/sp/list.do", {"sUppAisTpCd": "06", "mi": "1042"}, "supply"),
         "supplySale": ("/lhapply/apply/noti/sp/list.do", {"sUppAisTpCd": "05", "mi": "201523"}, "supply"),
         "supplyLand": ("/lhapply/apply/noti/sp/list.do", {"sUppAisTpCd": "01", "hyCd": "99", "mi": "201524"}, "supply"),
         "supplyCommercial": ("/lhapply/apply/noti/sp/list.do", {"sUppAisTpCd": "22", "mi": "201525"}, "supply")}
FIRST_COME = {"firstComeLand": (0, "201527"), "firstComeSale": (1, "201526"),
              "firstComeConversion": (2, "201529"), "firstComeCommercial": (3, "201528"),
              "firstComeRentalCommercial": (4, "31381"), "firstComeRental": (5, "1201802")}
SOURCE_NAMES = ("calendar", *BOARDS, *PLANS, *FIRST_COME)


def blank_post(ident, title, source, url, region="", subtype="", posted=""):
    post = {"panId": ident, "title": clean(title), "category": source, "sourceNames": [source],
            "type": clean(subtype), "region": clean(region), "postedAt": posted,
            "applicationStart": "", "applicationEnd": "", "status": "",
            "detailUrl": url, "attachments": [], "correction": any(x in title for x in CORRECTIONS),
            "correctionOf": "", "needsReview": False, "reviewReason": []}
    classify(post)
    post["contentHash"] = content_hash(post)
    return post


def counts(soup):
    total = soup.select_one(".bbs_total")
    match = re.search(r"전체\s*([\d,]+)\s*건\s*([\d,]+)\s*/\s*([\d,]+)\s*페이지",
                      clean(total.get_text(" ", strip=True)) if total else "")
    if not match:
        raise ParseError("공식 목록의 전체 건수/페이지 표시 누락")
    count, current, pages = (int(x.replace(",", "")) for x in match.groups())
    if (count == 0 and pages != 0) or (count > 0 and not 1 <= current <= pages):
        raise ParseError("목록 페이지 범위 불일치")
    return {"totalCount": count, "currentPage": current, "totalPages": pages}


def check_rows(meta, posts, list_size, allow_duplicates=False):
    if meta["totalPages"] != math.ceil(meta["totalCount"] / list_size):
        raise ParseError("목록 전체 페이지 수 불일치")
    expected = min(list_size, max(0, meta["totalCount"] - (meta["currentPage"] - 1) * list_size)) if meta["totalCount"] else 0
    if len(posts) != expected or (not allow_duplicates and len({p["panId"] for p in posts}) != len(posts)):
        raise ParseError(f"목록 행 수/고유 식별자 불일치: {len(posts)}/{expected}")


def normalize_date(value):
    match = re.search(r"(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})(?:\s+(\d{2}):(\d{2}))?", str(value or ""))
    if not match:
        return ""
    year, month, day = map(int, match.groups()[:3])
    day_text = date(year, month, day).isoformat()
    return day_text + ("T" + match[4] + ":" + match[5] + ":00+09:00" if match[4] else "")


def parse_calendar_month(html, year, month):
    soup = BeautifulSoup(html, "html.parser")
    form = soup.select_one("#calForm")
    if not form:
        raise ParseError("청약캘린더 조회 양식 누락")
    y = form.select_one('[name="selectYear"] option[selected]')
    m = form.select_one('[name="selectMonth"]')
    if not y or int(y.get("value") or y.get_text()) != year or not m or int(m.get("value", 0)) != month:
        raise ParseError("요청한 캘린더 월과 응답 월이 다름")
    result = {}
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        key = f"{year:04}{month:02}{day:02}"
        cell = soup.find("td", id=key)
        if not cell:
            raise ParseError(f"캘린더 날짜 누락: {key}")
        more = cell.select_one(".btn_more_mob span")
        result[key] = int(re.sub(r"\D", "", more.get_text()) or "0") if more else len(cell.select("ul li a"))
    return result


def parse_calendar_day(payload, day, expected):
    if not isinstance(payload, dict) or payload.get("resultAt") == "N" or not isinstance(payload.get("panList"), list):
        raise ParseError("캘린더 전체보기 응답 실패")
    if payload.get("panDt") and payload["panDt"] != day:
        raise ParseError("캘린더 전체보기 날짜 불일치")
    if len(payload["panList"]) != expected:
        raise ParseError(f"캘린더 숨김 항목 건수 불일치: {day} {len(payload['panList'])}/{expected}")
    posts = []
    for row in payload["panList"]:
        if not all(row.get(k) for k in ("panId", "panNm", "ccrCnntSysDsCd", "uppAisTpCd", "aisTpCd", "mi")):
            raise ParseError("캘린더 공고 식별자 누락")
        category = {"1026": "rental", "1027": "sale", "1062": "land", "1069": "commercial"}.get(str(row["mi"]), "presale")
        region = "경기도" if "41" in str(row.get("cnpCdListCts", "")).split("|") else ""
        post = blank_post(row["panId"], row["panNm"], category,
                          detail_url(row["panId"], row["ccrCnntSysDsCd"], row["uppAisTpCd"], row["aisTpCd"], row["mi"]),
                          region, row.get("aisTpCdNm", ""), normalize_date(row.get("panDtNm") or row.get("panDt")))
        post["sourceNames"] = ["calendar"]
        schedule = {"start": normalize_date(row.get("acpStDttm")), "end": normalize_date(row.get("acpEdDttm")),
                    "resultAt": normalize_date(row.get("pzwrAncDtPttrn") or row.get("pzwrAncDt")),
                    "label": clean(row.get("panSs", ""))}
        post["calendarSchedules"] = [schedule]
        post["applicationStart"], post["applicationEnd"] = schedule["start"], schedule["end"]
        # Calendar labels describe the selected day, not the notice's current status.
        posts.append(post)
    return posts


def merge_calendar_records(posts):
    merged = {}
    for post in posts:
        target = merged.setdefault(post["panId"], copy.deepcopy(post))
        schedules = {digest(s): s for s in target["calendarSchedules"] + post["calendarSchedules"]}
        target["calendarSchedules"] = sorted(schedules.values(), key=lambda s: digest(s))
    for post in merged.values():
        starts = [s["start"] for s in post["calendarSchedules"] if s.get("start")]
        ends = [s["end"] for s in post["calendarSchedules"] if s.get("end")]
        post["applicationStart"] = min(starts, default="")
        post["applicationEnd"] = max(ends, default="")
    return list(merged.values())


def parse_bulletin_list(html, source, mi, list_size=100):
    soup = BeautifulSoup(html, "html.parser")
    meta = counts(soup)
    posts = []
    for row in soup.select(".bbs_ListA tbody tr"):
        link = row.select_one("a.slpaInfoBtn")
        if not link:
            continue
        ident, ccr = link.get("data-id1"), link.get("data-id2")
        cells = row.find_all("td", recursive=False)
        if not ident or not ccr or len(cells) < 6:
            raise ParseError("공지/자료실 행 식별자 누락")
        region = row.select_one(".col3")
        subtype = row.select_one(".col2")
        posted = normalize_date(cells[-2].get_text())
        if not posted:
            raise ParseError("공지/자료실 게시일 누락")
        post = blank_post(f"bbs:{ccr}:{ident}", link.get_text(" ", strip=True), source,
                          BASE + BOARD_PATH + "view.do?" + urlencode({"bbsSn": ident, "ccrCnntSysDsCd": ccr, "mi": mi}),
                          region.get_text(" ", strip=True) if region else "", subtype.get_text(" ", strip=True) if subtype else cells[1].get_text(), posted)
        posts.append(post)
    check_rows(meta, posts, list_size)
    return meta, posts


def parse_bulletin_detail(html, post):
    soup = BeautifulSoup(html, "html.parser")
    view = soup.select_one(".bbs_ViewA")
    body = view.select_one(".bbsV_cont") if view else None
    if not view or not view.select_one("h3") or not body:
        raise ParseError("공지사항 상세 제목/본문 누락")
    post["title"] = clean(view.select_one("h3").get_text(" ", strip=True))
    text = clean(body.get_text(" ", strip=True))
    post["detailTextHash"] = digest(text)
    post["detailExcerpt"] = text[:800]
    post["attachments"] = [{"fileId": re.search(r"fileid=(\d+)", a["href"])[1],
                             "name": clean(a.get_text(" ", strip=True)), "url": urljoin(BASE, a["href"])}
                            for a in view.select('.bbsV_atchmnfl a[href]') if re.search(r"fileid=(\d+)", a["href"])]
    post["relatedPanIds"] = sorted({m[1] for a in body.select('a[href]') if (m := re.search(r"[?&]panId=([^&]+)", a["href"]))})
    classify(post, text + " " + " ".join(a["name"] for a in post["attachments"]))
    post["correction"] = any(x in post["title"] for x in CORRECTIONS)
    post["contentHash"] = content_hash(post)
    return post


def expanded_rows(table):
    """Expand actual rowspans so missing repeated regions cannot shift columns."""
    spans = {}
    result = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)
        if not cells or (len(cells) == 1 and int(cells[0].get("colspan", 1)) > 1):
            continue
        values, col = [], 0
        for cell in cells:
            while col in spans:
                value, left = spans[col]
                values.append(value)
                if left == 1: del spans[col]
                else: spans[col] = (value, left - 1)
                col += 1
            value = clean(cell.get_text(" ", strip=True))
            values.append(value)
            span = int(cell.get("rowspan", 1))
            if span > 1: spans[col] = (value, span - 1)
            col += 1
        while col in spans:
            value, left = spans[col]
            values.append(value)
            if left == 1: del spans[col]
            else: spans[col] = (value, left - 1)
            col += 1
        result.append(values)
    return result


def parse_plan_table(html, source, url, mode, list_size=100):
    soup = BeautifulSoup(html, "html.parser")
    meta = counts(soup)
    expected_cols = 7 if mode == "move" else None
    tables = soup.select("#sub_container table, .bbs_ListA table")
    table = next((t for t in tables if len(t.select("thead th")) >= 7), None)
    if not table:
        raise ParseError("입주/공급계획 표 구조 누락")
    posts = []
    headers = [clean(h.get_text(" ", strip=True)) for h in table.select("thead th")]
    def column(label, fallback):
        return next((i for i, h in enumerate(headers) if label in h), fallback)
    region_i, type_i, title_i = column("지역", 0), column("유형", 1), column("지구", 2)
    size_i = column("전용면적", 3)
    for cells in expanded_rows(table):
        if len(cells) != len(headers): raise ParseError("입주/공급계획 열 수 변경")
        # Identity includes unit size, but excludes supply counts and dates.
        stable = [cells[region_i], cells[type_i], cells[title_i]] + ([cells[size_i]] if mode != "move" else [])
        if source == "supplyLand": stable = cells[1:5]
        ident = f"plan:{source}:" + digest(stable)[:24]
        post = blank_post(ident, cells[title_i], source, url, cells[region_i] if source != "supplyLand" else "", cells[type_i])
        post["planValues"] = cells
        post["detailTextHash"] = digest(cells)
        post["detailExcerpt"] = " | ".join(cells)
        post["informationOnly"] = True
        post["contentHash"] = content_hash(post)
        posts.append(post)
    check_rows(meta, posts, list_size, allow_duplicates=True)
    return meta, posts


def parse_first_come(html, source, url):
    soup = BeautifulSoup(html, "html.parser")
    total = soup.select_one(".bbs_total")
    match = re.search(r"검색결과\s*([\d,]+)\s*건", clean(total.get_text(" ", strip=True)) if total else "")
    if not match: raise ParseError("선착순 계약 전체 건수 누락")
    count = int(match[1].replace(",", ""))
    hidden = soup.select_one('[name="dsDbsListJson"]')
    posts = []
    if hidden:
        rows = json.loads(hidden.get("value", ""))
        if not isinstance(rows, list): raise ParseError("선착순 계약 JSON 형식 변경")
        for row in rows:
            if row.get("allCnt") is not None and int(row["allCnt"]) != count: raise ParseError("선착순 JSON 전체 건수 불일치")
            stable = {k: row.get(k) for k in ("bzdtCd", "hcBlkCd", "bnm", "ddoAr", "ddoArCts", "hoAdmNo", "cfmt", "cfmtXpc", "stlSplPpNm")}
            if not row.get("bzdtCd") or not row.get("bzdtNm"): raise ParseError("선착순 지구 식별자 누락")
            ident = f"first:{source}:" + digest(stable)[:24]
            post = blank_post(ident, clean(str(row["bzdtNm"]) + " " + str(row.get("bnm", ""))), source, url, row.get("cnpNm", ""), row.get("splTpNm", "선착순 계약"))
            semantic = {k: v for k, v in row.items() if k not in ("rgsSn", "splYm", "allCnt", "ordr") and not k.endswith(("Rowspan", "UpperLimit"))}
            post["inventory"] = semantic
            post["detailTextHash"] = digest(semantic)
            post["applicationStart"], post["applicationEnd"] = normalize_date(row.get("ntStDt")), normalize_date(row.get("ntEdDt"))
            post["contentHash"] = content_hash(post)
            posts.append(post)
    else:
        table = next((t for t in soup.select("#sub_container table") if t.select_one('tbody[data-id="dsDbsList"]')), None)
        if not table: raise ParseError("선착순 표/JSON 누락")
        for cells in expanded_rows(table):
            if len(cells) < 6: raise ParseError("선착순 표 열 수 변경")
            ident = f"first:{source}:" + digest(cells[:3] + [cells[4]])[:24]
            post = blank_post(ident, cells[1] + " " + cells[2], source, url, cells[0], "선착순 계약")
            post["inventory"] = cells
            post["detailTextHash"] = digest(cells)
            post["contentHash"] = content_hash(post)
            posts.append(post)
    if len(posts) != count:
        raise ParseError(f"선착순 계약 전체/중복 건수 불일치: {len(posts)}/{count}")
    grouped = {}
    for post in posts:
        grouped.setdefault(post["panId"], []).append(post)
    unique = []
    for group in grouped.values():
        post = group[0]
        if len(group) > 1:
            inventory = sorted((p["inventory"] for p in group), key=digest)
            post["inventory"] = inventory
            post["detailTextHash"] = digest(inventory)
            post["contentHash"] = content_hash(post)
        unique.append(post)
    return {"totalCount": count, "parsedCount": count, "uniqueCount": len(unique), "totalPages": 1 if count else 0, "currentPage": 1 if count else 0}, unique


def request(client, url, fields=None, json_response=False):
    if fields is not None:
        parts = urlsplit(url)
        data = {**dict(parse_qsl(parts.query)), **fields}
        response = client.session.post(urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), data=data, timeout=client.timeout)
    else:
        response = client.session.get(url, timeout=client.timeout)
    response.raise_for_status()
    return response.json() if json_response else response.text


def paginate(client, url, fields, parser, aggregate=False):
    posts, first_meta, page = [], None, 1
    while True:
        html = request(client, url, {**fields, "currPage": str(page), "listCo": "100", "prevListCo": "100",
                                     "minSn": str((page - 1) * 100), "maxSn": str(page * 100)})
        meta, found = parser(html)
        if first_meta is None: first_meta = meta
        if meta["totalCount"] != first_meta["totalCount"] or meta["totalPages"] != first_meta["totalPages"] or meta["currentPage"] != (page if meta["totalPages"] else 0):
            raise ParseError("목록 페이지 이동 중 건수/순서 불일치")
        posts.extend(found)
        if page >= meta["totalPages"]: break
        page += 1
    if len(posts) != first_meta["totalCount"] or (not aggregate and len({p["panId"] for p in posts}) != len(posts)):
        raise ParseError("전체 페이지 합산/중복 검증 실패")
    meta = {**first_meta, "checkedPages": first_meta["totalPages"], "parsedCount": len(posts), "complete": True, "sourceUrl": url}
    if aggregate:
        groups = {}
        for post in posts: groups.setdefault(post["panId"], []).append(post)
        posts = []
        for group in groups.values():
            post = group[0]
            if len(group) > 1:
                values = sorted((p["planValues"] for p in group), key=digest)
                post["planValues"] = values
                post["detailTextHash"] = digest(values)
                post["contentHash"] = content_hash(post)
            posts.append(post)
        meta["uniqueCount"] = len(posts)
    return meta, posts


def collect_source(client, source, today, checked_at):
    if source == "calendar":
        records, day_count, raw_count = [], 0, 0
        next_month = today.replace(day=28) + timedelta(days=4)
        for month in (today.replace(day=1), next_month.replace(day=1)):
            fields = {"selectYear": str(month.year), "selectMonth": str(month.month), "calSrchType": "", "calSrchLocal": "", "srchPanSs": ""}
            html = request(client, CALENDAR, fields)
            days = parse_calendar_month(html, month.year, month.month)
            for day, expected in days.items():
                if expected:
                    payload = request(client, BASE + "/lhapply/apply/sc/detail.do", {**fields, "panDt": day}, True)
                    records.extend(parse_calendar_day(payload, day, expected))
                    raw_count += expected
                day_count += 1
        posts = merge_calendar_records(records)
        for post in posts:
            post["calendarWindowStart"] = today.replace(day=1).isoformat()
            post["calendarWindowEnd"] = date(next_month.year, next_month.month, calendar.monthrange(next_month.year, next_month.month)[1]).isoformat()
        return {"complete": True, "totalCount": len(posts), "parsedCount": len(posts), "totalPages": 2,
                "checkedPages": 2, "checkedDays": day_count, "calendarRowCount": raw_count, "sourceUrl": CALENDAR, "checkedAt": checked_at}, posts
    if source in BOARDS:
        kind, mi = BOARDS[source]
        url = BASE + BOARD_PATH + "list.do?" + urlencode({"slBbsKdCd": kind, "mi": mi})
        fields = {"slBbsKdCd": kind, "mi": mi, "startDt": f"{today.year}-01-01", "endDt": today.isoformat(), "srchNm": "", "srchTy": ""}
        if source == "documents": fields.pop("startDt"); fields.pop("endDt")
        return paginate(client, url, fields, lambda html: parse_bulletin_list(html, source, mi))
    if source in PLANS:
        path, fields, mode = PLANS[source]
        url = BASE + path + "?" + urlencode(fields)
        return paginate(client, url, {"srchY": "N", "hyCd": "99", **fields}, lambda html: parse_plan_table(html, source, url, mode), aggregate=True)
    index, mi = FIRST_COME[source]
    url = BASE + f"/lhapply/apply/bor_ctrt_psb_dst/{index}/lfn_getTabChange.do?mi={mi}"
    meta, posts = parse_first_come(request(client, url), source, url)
    return {**meta, "checkedPages": meta["totalPages"], "complete": True, "sourceUrl": url}, posts
