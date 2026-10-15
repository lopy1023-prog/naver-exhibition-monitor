import copy
import json
import sys
import unittest
from unittest.mock import MagicMock
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import additional_sources as extra
from parser import ParseError


def board_html(rows, count=None):
    count = len(rows) if count is None else count
    return ('<form id="srchForm"><p class="bbs_total">전체 <strong>' + str(count) +
            '</strong>건 <strong>1</strong>/1페이지</p><div class="bbs_ListA"><table><tbody>' +
            ''.join('<tr><td>1</td><td>국민임대</td><td><a class="slpaInfoBtn" data-id1="' +
                    ident + '" data-id2="03"><span>' + title +
                    '</span></a></td><td>경기남부지역본부</td><td></td><td>2026.10.15</td><td>10</td></tr>'
                    for ident, title in rows) + '</tbody></table></div></form>')


class SupplementalParserTests(unittest.TestCase):
    def test_empty_list_is_valid_and_request_does_not_duplicate_query_fields(self):
        html = '<form id="srchForm"><p class="bbs_total">전체 0건 0/0페이지</p><div class="bbs_ListA"><table><tbody><tr><td colspan="8">조회 결과 없음</td></tr></tbody></table></div></form>'
        self.assertEqual(extra.parse_bulletin_list(html, 'notice', '1079')[1], [])
        client = MagicMock(timeout=30)
        extra.request(client, 'https://apply.lh.or.kr/list.do?mi=1079&slBbsKdCd=03', {'mi': '1079', 'slBbsKdCd': '03'})
        args, kwargs = client.session.post.call_args
        self.assertEqual(args[0], 'https://apply.lh.or.kr/list.do')
        self.assertEqual(kwargs['data'], {'mi': '1079', 'slBbsKdCd': '03'})

    def test_calendar_month_requires_every_day_and_counts_hidden_items(self):
        import calendar
        cells = ''.join('<td id="202610%02d"><a class="btn_more_mob"><span>%d</span></a></td>' %
                        (d, 12 if d == 15 else 0) for d in range(1, 32))
        html = '<form id="calForm"><input name="selectMonth" value="10"><select name="selectYear"><option selected>2026</option></select><table><tbody>' + cells + '</tbody></table></form>'
        result = extra.parse_calendar_month(html, 2026, 10)
        self.assertEqual(result['20261015'], 12)
        self.assertEqual(len(result), 31)
        with self.assertRaises(ParseError):
            extra.parse_calendar_month(html.replace('id="20261031"', 'id="other"'), 2026, 10)

    def test_calendar_same_notice_different_days_is_one_canonical_post(self):
        row = {'panId': 'p1', 'panNm': '수원 국민임대 예비입주자 모집', 'ccrCnntSysDsCd': '03',
               'uppAisTpCd': '06', 'aisTpCd': '07', 'aisTpCdNm': '국민임대', 'mi': '1026',
               'panDtNm': '2026.09.01', 'acpStDttm': '2026.10.14', 'acpEdDttm': '2026.10.16',
               'panSs': '접수', 'cnpCdListCts': '41|'}
        first = extra.parse_calendar_day({'panList': [row]}, '20261015', 1)
        second = extra.parse_calendar_day({'panList': [row]}, '20261016', 1)
        merged = extra.merge_calendar_records(first + second)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['panId'], 'p1')
        self.assertEqual(len(merged[0]['calendarSchedules']), 1)
        self.assertEqual(merged[0]['applicationStart'], '2026-10-14')
        self.assertEqual(merged[0]['applicationEnd'], '2026-10-16')
        with self.assertRaises(ParseError):
            extra.parse_calendar_day({'panList': [row]}, '20261015', 2)
        with self.assertRaises(ParseError):
            extra.parse_calendar_day({'resultAt': 'N', 'panList': []}, '20261015', 0)

    def test_bulletin_ids_do_not_collide_with_pan_ids_and_count_mismatch_fails(self):
        meta, posts = extra.parse_bulletin_list(board_html([('123', '수원 서류제출 안내')]), 'notice', '1079')
        self.assertEqual(meta['totalCount'], 1)
        self.assertEqual(posts[0]['panId'], 'bbs:03:123')
        self.assertIn('bbsSn=123', posts[0]['detailUrl'])
        with self.assertRaises(ParseError):
            extra.parse_bulletin_list(board_html([('123', '수원 안내')], 2), 'notice', '1079')

    def test_board_content_hash_ignores_views_but_keeps_new_instructions(self):
        _, posts = extra.parse_bulletin_list(board_html([('123', '수원 안내')]), 'notice', '1079')
        html = '<div class="bbs_ViewA"><h3>수원 안내</h3><ul class="bbsV_data"><li><strong>조회수</strong>1</li></ul><div class="bbsV_cont">서류를 10월 20일까지 제출</div><div class="bbsV_atchmnfl"><a href="/lhapply/lhFile.do?fileid=55">안내.pdf</a></div></div>'
        a = extra.parse_bulletin_detail(html, copy.deepcopy(posts[0]))
        b = extra.parse_bulletin_detail(html.replace('조회수</strong>1', '조회수</strong>20'), copy.deepcopy(posts[0]))
        c = extra.parse_bulletin_detail(html.replace('20일까지', '21일까지'), copy.deepcopy(posts[0]))
        self.assertEqual(a['detailTextHash'], b['detailTextHash'])
        self.assertNotEqual(a['detailTextHash'], c['detailTextHash'])

    def test_plan_identity_survives_row_reordering_and_supply_changes(self):
        rows = [['경기도', '국민임대', '수원당수 A1', '36', '100', '2026년12월', '2027년12월', '경기남부', ''],
                ['경기도', '행복주택', '오산세교 A2', '26', '50', '2026년11월', '2027년11월', '경기남부', '']]
        def html(values):
            return '<p class="bbs_total">전체 2건 1/1페이지</p><div class="bbs_ListA"><table><thead><tr>' + ''.join('<th>x</th>' for _ in range(9)) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + c + '</td>' for c in r) + '</tr>' for r in values) + '</tbody></table></div>'
        _, a = extra.parse_plan_table(html(rows), 'supplyRental', 'https://apply.lh.or.kr/plans', 'supply')
        rows[0][4] = '120'
        _, b = extra.parse_plan_table(html(rows[::-1]), 'supplyRental', 'https://apply.lh.or.kr/plans', 'supply')
        self.assertEqual({p['title']: p['panId'] for p in a}, {p['title']: p['panId'] for p in b})
        self.assertNotEqual(a[0]['detailTextHash'], b[1]['detailTextHash'])

    def test_first_come_inventory_checks_declared_count_and_stable_unit_identity(self):
        row = {'bzdtCd': 'suwon', 'bzdtNm': '수원당수', 'cnpNm': '경기도', 'bnm': 'A1', 'hcBlkCd': '01', 'ddoAr': 39, 'nslCnt': 2, 'allCnt': 1, 'rgsSn': 1}
        def html(r, count=1):
            from html import escape
            return '<p class="bbs_total">검색결과 ' + str(count) + '건</p><input name="dsDbsListJson" value=\'' + escape(json.dumps([r], ensure_ascii=False), quote=True) + '\'>'
        a = extra.parse_first_come(html(row), 'firstComeRental', 'https://apply.lh.or.kr/first')[1][0]
        changed = {**row, 'rgsSn': 200, 'nslCnt': 3}
        b = extra.parse_first_come(html(changed), 'firstComeRental', 'https://apply.lh.or.kr/first')[1][0]
        self.assertEqual(a['panId'], b['panId'])
        self.assertNotEqual(a['detailTextHash'], b['detailTextHash'])
        with self.assertRaises(ParseError):
            extra.parse_first_come(html(row, 2), 'firstComeRental', 'https://apply.lh.or.kr/first')


if __name__ == '__main__':
    unittest.main()
