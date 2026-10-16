"""Historical official notice patterns and supply-vs-contact geography."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diff import compare
from parser import classify, parse_detail
from pipeline import comparison_baseline


def detail(table, title="[경기남부] 청년 매입임대주택 예비입주자 모집공고"):
    # LH repeats many empty supply tables before the populated table.
    prefix = "공급정보 합계 모집인원 조회된 데이터가 없습니다. " * 15
    return (f'<div id="sub_container"><div class="bbs_ViewA"><h3>{title}</h3></div>'
            f'<p>{prefix}</p>{table}</div>')


def post(title="[경기남부] 청년 매입임대주택 예비입주자 모집공고"):
    return {"panId": "historical", "title": title, "region": "경기도", "category": "rental",
            "attachments": [], "applicationStart": "", "applicationEnd": "", "status": "접수마감"}


class HistoricalGeographyTests(unittest.TestCase):
    def test_historical_list_examples_remain_inclusive(self):
        corpus = json.loads((Path(__file__).parent / "fixtures" / "historical-geography.json").read_text(encoding="utf-8"))
        self.assertEqual(len(corpus["examples"]), 338)
        for case in corpus["examples"]:
            with self.subTest(panId=case["panId"], title=case["title"]):
                actual = classify(copy.deepcopy(case))
                self.assertEqual(actual["directSuwon"], case["expectedDirectSuwon"])
                self.assertTrue(actual["directSuwon"] or actual["broadCandidate"])

    def test_real_purchase_supply_cell_confirms_suwon_after_long_prefix(self):
        table = ('<table><caption>공급정보 : 지자체명, 주택정보, 모집인원</caption>'
                 '<thead><tr><th>지자체명</th><th colspan="3">주택정보</th><th>모집인원</th></tr></thead>'
                 '<tbody><tr><td>매입다가구(경기수원시)</td><td></td><td>지도</td><td>홍보물</td><td>10</td></tr></tbody></table>')
        actual = parse_detail(detail(table), post())
        self.assertTrue(actual["directSuwon"])
        self.assertIn("수원", actual["confirmedRegions"])
        self.assertTrue(classify(actual, actual["_detailText"])["directSuwon"])

    def test_real_lease_reits_detailed_region_confirms_suwon(self):
        table = ('<table><caption>공급정보 : 지역, 상세지역, 주택유형</caption>'
                 '<thead><tr><th>지역</th><th>상세지역</th><th>주택유형</th></tr></thead>'
                 '<tbody><tr><td>경기도</td><td>(경기수원시) 서수원엠코타운르본느</td><td>전용59㎡</td></tr></tbody></table>')
        self.assertTrue(parse_detail(detail(table), post())["directSuwon"])

    def test_contact_tables_and_contact_columns_do_not_confirm_supply(self):
        table = ('<table><caption>접수처정보 : 소재지, 전화번호</caption>'
                 '<thead><tr><th>소재지</th><th>전화번호</th></tr></thead>'
                 '<tbody><tr><td>경기도 수원시 상담센터</td><td>1600</td></tr></tbody></table>'
                 '<table><caption>공급정보 : 지역, 문의처</caption>'
                 '<thead><tr><th>지역</th><th>문의처</th></tr></thead>'
                 '<tbody><tr><td>부산광역시</td><td>경기도 수원시 상담센터</td></tr></tbody></table>')
        title = "부산 청년주택 모집"
        actual = parse_detail(detail(table, title), {**post(title), "region": "부산광역시"})
        self.assertFalse(actual["directSuwon"])

    def test_ambiguous_complex_name_is_not_suwon_confirmation(self):
        for title in ("성남고등 공공임대 예비입주자 모집", "남양주금곡 국민임대 모집", "광교 행복주택 안내"):
            self.assertFalse(classify(post(title))["directSuwon"])

    def test_real_yongin_bulletin_with_suwon_attachment_name_is_included(self):
        # Official board bbsSn=9102431609 is headed Yongin, but its visible
        # attachment list also includes a Suwon Gwanggyo complex. No file body
        # needs to be opened to retain this notice.
        actual = classify({
            "panId": "bbs:02:9102431609", "category": "documents", "region": "",
            "title": "[서류제출대상자발표] 용인시 국민임대 예비입주자 서류제출 안내 [현장접수]",
            "attachments": [{"name": "[수원광교41단지]서류제출대상자명단(현장접수).pdf"}],
        })
        self.assertTrue(actual["directSuwon"])

    def test_real_northern_only_notice_is_not_broadened_by_generic_gyeonggi(self):
        title = "[경기북부] 청년 매입임대주택 선착순 예비입주자 모집공고 (김포시, 포천시)"
        table = ('<p>모집지역 : 경기도</p><table><caption>공급정보 : 지역, 상세지역</caption>'
                 '<thead><tr><th>지역</th><th>상세지역</th></tr></thead>'
                 '<tbody><tr><td>경기도</td><td>김포시, 포천시</td></tr></tbody></table>')
        actual = parse_detail(detail(table, title), post(title))
        self.assertFalse(actual["directSuwon"])
        self.assertFalse(actual["broadCandidate"])
        supplied_suwon = parse_detail(detail(table.replace("김포시, 포천시</td>", "수원시</td>"), title), post(title))
        self.assertTrue(supplied_suwon["directSuwon"])

    def test_body_rowspan_cannot_shift_contact_text_into_location_column(self):
        table = ('<table><caption>공급정보 : 지역, 문의처</caption>'
                 '<thead><tr><th>지역</th><th>문의처</th></tr></thead>'
                 '<tbody><tr><td rowspan="2">부산광역시</td><td>부산 상담센터</td></tr>'
                 '<tr><td colspan="2">경기도 수원시 상담센터</td></tr></tbody></table>')
        actual = parse_detail(detail(table), post())
        self.assertFalse(actual["directSuwon"])

    def test_geography_migration_does_not_backfill_but_keeps_real_changes(self):
        old = {**post(), "directSuwon": False, "hashVersion": 2, "detailTextHash": "same"}
        current = {**old, "directSuwon": True, "geographyVersion": 2}
        baseline = comparison_baseline([old], [current], {})
        self.assertEqual(compare(baseline, [current]), [])
        changed = {**current, "status": "접수중"}
        events = compare(comparison_baseline([old], [changed], {}), [changed])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["fields"], ["status"])


if __name__ == "__main__":
    unittest.main()
