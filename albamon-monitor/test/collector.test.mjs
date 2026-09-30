import test from 'node:test';
import assert from 'node:assert/strict';
import { collectPages, fetchListing, parseListing } from '../albamon.mjs';
import { canonicalJob, deduplicate } from '../utils.mjs';

function listing({ kind = 'keyword_search', page = 1, count = 2, jobs = [] } = {}) {
  const key = kind === 'remote_list' ? 'RECRUIT_TELECOMMUTING' : 'SEARCH_RECRUIT_LIST';
  const data = { props: { pageProps: { query: { keyword: '상품등록' }, dehydratedState: {
    queries: [{ queryKey: [key, 'list'], state: { data: { base: {
      pagination: { page, size: 20, totalCount: count }, normal: { collection: jobs },
    }, paid: {} } } }],
  } } } };
  return `<html><script id="__NEXT_DATA__" type="application/json">${JSON.stringify(data)}</script></html>`;
}

const sample = { recruitNo: 12345, companyName: '업체', recruitTitle: '상품 등록',
  payType: { description: '건별' }, pay: '700원', workingWeek: '요일협의', managerPhoneNumber: 'private' };

test('official page data yields only public summary fields and canonical URL', () => {
  const parsed = parseListing(listing({ jobs: [sample], count: 1 }),
    { kind: 'keyword_search', page: 1, keyword: '상품등록' });
  assert.equal(parsed.total_pages, 1);
  assert.deepEqual(parsed.items[0], {
    job_id: '12345', company: '업체', title: '상품 등록',
    url: 'https://www.albamon.com/jobs/detail/12345', pay_text: '건별 700원',
    work_text: '요일협의', source_queries: ['상품등록'],
  });
  assert.deepEqual(canonicalJob('https://www.albamon.com/jobs/detail/12345?sc=547'),
    { job_id: '12345', url: 'https://www.albamon.com/jobs/detail/12345' });
});

test('same job from remote list and searches is stored once with all paths', () => {
  const row = { ...parseListing(listing({ jobs: [sample], count: 1 }),
    { kind: 'keyword_search', page: 1, keyword: '상품등록' }).items[0] };
  const merged = deduplicate([row, { ...row, source_queries: ['remote_list'] },
    { ...row, source_queries: ['스마트스토어'] }]);
  assert.equal(merged.length, 1);
  assert.deepEqual(merged[0].source_queries, ['상품등록', 'remote_list', '스마트스토어']);
});

test('pagination visits the final remote page and verifies its number', async () => {
  const calls = [];
  const fetcher = async url => {
    const page = Number(url.searchParams.get('page') || 1);
    calls.push(page);
    return { ok: true, status: 200, text: async () => listing({ kind: 'remote_list', page,
      count: 21, jobs: [{ ...sample, recruitNo: 12345 + page }] }) };
  };
  const result = await collectPages({ kind: 'remote_list', pauseMs: 0, fetcher });
  assert.deepEqual(calls, [1, 2]);
  assert.equal(result.stats.pages_checked, 2);
  assert.equal(result.items.length, 2);
});

test('403 stops collection without retry or workaround', async () => {
  let requests = 0;
  await assert.rejects(fetchListing('https://www.albamon.com/jobs/telecommuting',
    { kind: 'remote_list', page: 1 }, async () => { requests++; return { status: 403, ok: false }; }),
  error => error.blocked === true);
  assert.equal(requests, 1);
});

test('missing or inconsistent official data fails', () => {
  assert.throws(() => parseListing('<html></html>', { kind: 'remote_list', page: 1 }), /공식 목록 데이터 누락/);
  assert.throws(() => parseListing(listing({ page: 1, jobs: [sample] }),
    { kind: 'keyword_search', page: 2, keyword: '상품등록' }), /페이지\/건수 구조 변경/);
});
