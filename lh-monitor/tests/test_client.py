"""Official list date-window contract, including an ignored search filter."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lh_client import CollectionError, LHClient


def list_html(start, end, posted="2022.03.07", count=1):
    rows = (f'<tr><td>1</td><td>국민임대</td><td><a class="wrtancInfoBtn" '
            f'data-id1="historical" data-id2="03" data-id3="06" data-id4="07">'
            f'<span>수원시 국민임대 예비입주자 모집</span></a></td><td>경기도</td><td></td>'
            f'<td>{posted}</td><td>2022.03.31</td><td>접수마감</td><td>0</td></tr>') if count else ""
    return (f'<form id="srchForm"><input name="startDt" value="{start}">'
            f'<input name="endDt" value="{end}"></form>'
            f'<p class="bbs_total">전체 {count}건 {1 if count else 0}/{1 if count else 0}페이지</p>'
            f'<div class="bbs_ListA"><table><tbody>{rows}</tbody></table></div>')


class Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class OfficialFormSession:
    """Like LH, old parameter names silently fall back to the default period."""
    def __init__(self, ignore_dates=False, wrong_post_date=False):
        self.ignore_dates = ignore_dates
        self.wrong_post_date = wrong_post_date
        self.submitted = []

    def get(self, url, **kwargs):
        return Response(list_html("2026-08-16", "2026-10-16", count=0))

    def post(self, url, data, **kwargs):
        self.submitted.append(dict(data))
        if self.ignore_dates or "startDt" not in data or "endDt" not in data:
            return Response(list_html("2026-08-16", "2026-10-16", count=0))
        return Response(list_html(data["startDt"], data["endDt"],
                                  posted="2021.01.01" if self.wrong_post_date else "2022.03.07"))


class OfficialDateWindowTests(unittest.TestCase):
    def client(self, **kwargs):
        client = LHClient()
        client.session = OfficialFormSession(**kwargs)
        return client

    def test_requested_archive_period_reaches_official_form(self):
        client = self.client()
        info, posts = client.collect_category("rental", date(2022, 1, 1), date(2026, 10, 16), "now", "수원")
        self.assertEqual([p["panId"] for p in posts], ["historical"])
        self.assertEqual(info["parsedCount"], 1)
        self.assertEqual(client.session.submitted[0]["startDt"], "2022-01-01")
        self.assertEqual(client.session.submitted[0]["endDt"], "2026-10-16")
        self.assertEqual(client.session.submitted[0]["schTy"], "0")
        self.assertEqual(client.session.submitted[0]["srchY"], "N")

    def test_ignored_period_is_failure_even_with_valid_zero_count(self):
        with self.assertRaises(CollectionError):
            self.client(ignore_dates=True).collect_category("rental", date(2022, 1, 1), date(2026, 10, 16), "now")

    def test_outside_period_row_is_failure_even_when_dates_echo_correctly(self):
        with self.assertRaises(CollectionError):
            self.client(wrong_post_date=True).collect_category("rental", date(2022, 1, 1), date(2026, 10, 16), "now")


if __name__ == "__main__":
    unittest.main()
