"""Official LH listing requests. Every listing page is checked against LH's count."""

from __future__ import annotations

import math
import time
from datetime import date, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from parser import BASE, LIST_PATH, ParseError, parse_list

CATEGORIES = {
    "rental": ("1026", "061339"),
    "sale": ("1027", "053954"),
    "land": ("1062", "01"),
    "commercial": ("1069", "22"),
}
PRESALE_PATH = "/lhapply/apply/bfh/slpa/list.do"


class CollectionError(RuntimeError):
    def __init__(self, cause: Exception, total_count=None, total_pages=None, checked_pages=0, parsed_count=0):
        super().__init__(str(cause))
        self.total_count = total_count
        self.total_pages = total_pages
        self.checked_pages = checked_pages
        self.parsed_count = parsed_count


class LHClient:
    def __init__(self, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LH-Suwon-Monitor/1.0; public-notices)", "Accept-Language": "ko-KR,ko;q=0.9"})
        retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.timeout = timeout

    def get(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def content(self, url: str, max_bytes: int = 25_000_000, max_seconds: float = 90) -> bytes:
        started = time.monotonic()
        with self.session.get(url, timeout=self.timeout, stream=True) as response:
            response.raise_for_status()
            advertised = int(response.headers.get("Content-Length", "0"))
            if advertised > max_bytes:
                raise ValueError(f"첨부파일 크기 제한 초과: {advertised} bytes")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=16_384):
                if time.monotonic() - started > max_seconds:
                    raise requests.Timeout(f"첨부 다운로드 전체 시간 {max_seconds}초 초과")
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError(f"첨부파일 크기 제한 초과: {len(content)} bytes")
            return bytes(content)

    def collect_category(self, category: str, start: date, end: date, checked_at: str, keyword: str = "") -> tuple[dict, list[dict]]:
        mi, upper = CATEGORIES[category]
        source = f"{BASE}{LIST_PATH}?mi={mi}"
        total_count = pages = None
        checked = 0
        posts = []
        try:
            # The initial GET establishes the LH session required for POST search/paging.
            initial = self.get(source)
            if "srchForm" not in initial or "bbs_total" not in initial:
                raise ParseError(f"{category}: LH 첫 목록 응답이 정상 목록이 아님")
            fields = {
            "mi": mi, "currPage": "1", "listCo": "100", "prevListCo": "100",
            "panSs": "", "uppAisTpCd": upper, "srchUppAisTpCd": upper,
            "panStDt": start.strftime("%Y%m%d"), "panEdDt": end.strftime("%Y%m%d"),
            "xssChk": "N", "maxSn": "100", "minSn": "0",
            "cnpCd": "", "aisTpCd": "", "mvinQf": "", "viewType": "",
            "panNm": keyword,
            }
            first = self._page(fields, source)
            meta, first_posts = parse_list(first, category, mi, checked_at)
            total_count, pages = meta["totalCount"], meta["totalPages"]
            if meta["currentPage"] != (1 if pages else 0):
                raise ParseError(f"{category}: 첫 페이지 번호 불일치")
            posts = first_posts
            checked = 1 if pages else 0
            for page in range(2, pages + 1):
                fields["currPage"] = str(page)
                fields["minSn"] = str((page - 1) * 100)
                fields["maxSn"] = str(page * 100)
                html = self._page(fields, source)
                page_meta, page_posts = parse_list(html, category, mi, checked_at)
                if page_meta != {"totalCount": total_count, "totalPages": pages, "currentPage": page}:
                    raise ParseError(f"{category}: {page}페이지 메타데이터 변경 또는 누락")
                posts.extend(page_posts)
                checked += 1
            ids = [p["panId"] for p in posts]
            if len(posts) != total_count or len(set(ids)) != len(ids) or checked != pages:
                raise ParseError(f"{category}: 총 건수/중복/페이지 검증 실패 ({len(posts)}/{total_count}, {checked}/{pages})")
        except Exception as exc:
            raise CollectionError(exc, total_count, pages, checked, len(posts)) from exc
        return {
            "totalCount": total_count, "parsedCount": len(posts), "totalPages": pages,
            "checkedPages": checked, "complete": True, "sourceUrl": source,
            "checkedAt": checked_at, "error": None,
        }, posts

    def _page(self, fields: dict, referer: str) -> str:
        response = self.session.post(BASE + LIST_PATH, data=fields, headers={"Referer": referer}, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def collect_presale(self, checked_at: str) -> tuple[dict, list[dict]]:
        source = BASE + PRESALE_PATH + "?mi=1349"
        html = self.get(source)
        from bs4 import BeautifulSoup
        import re
        total = BeautifulSoup(html, "html.parser").select_one(".bbs_total")
        if not total:
            raise ParseError("사전청약 목록 구조 변경")
        match = re.search(r"전체\s*([\d,]+)\s*건\s*([\d,]+)\s*/\s*([\d,]+)\s*페이지", total.get_text(" ", strip=True))
        if not match:
            raise ParseError("사전청약 건수 표시 해석 실패")
        count, current, pages = (int(v.replace(",", "")) for v in match.groups())
        if count != 0 or current != 0 or pages != 0:
            # A separate format needs a verified parser before claiming success.
            raise ParseError(f"사전청약 공고 {count}건 발견: 전용 페이지 파서 필요")
        return {"totalCount": 0, "parsedCount": 0, "totalPages": 0, "checkedPages": 0,
                "complete": True, "sourceUrl": source, "checkedAt": checked_at, "error": None}, []
