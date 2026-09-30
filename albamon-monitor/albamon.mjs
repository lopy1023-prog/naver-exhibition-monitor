import { MAX_KEYWORD_PAGES, REMOTE_URL, REQUEST_PAUSE_MS, SEARCH_URL } from './config.mjs';
import { canonicalJob, sleep } from './utils.mjs';

export class SourceError extends Error {
  constructor(message, blocked = false) { super(message); this.blocked = blocked; }
}

export function parseListing(html, { kind, page, keyword = '' }) {
  const match = html.match(/<script\b[^>]*\bid=["']__NEXT_DATA__["'][^>]*>([\s\S]*?)<\/script>/i);
  if (!match) {
    const blocked = /captcha|자동입력방지|접근이 제한|비정상적인 접근/i.test(html);
    throw new SourceError(blocked ? '접근 제한 또는 CAPTCHA 화면' : '공식 목록 데이터 누락', blocked);
  }
  let next;
  try { next = JSON.parse(match[1]); }
  catch { throw new SourceError('공식 목록 JSON 해석 실패'); }
  const expectedKey = kind === 'remote_list' ? 'RECRUIT_TELECOMMUTING' : 'SEARCH_RECRUIT_LIST';
  const pageProps = next?.props?.pageProps;
  const query = pageProps?.dehydratedState?.queries?.find(value => value?.queryKey?.[0] === expectedKey);
  const data = query?.state?.data;
  const pagination = data?.base?.pagination;
  if (!pagination || !Number.isInteger(pagination.totalCount) || !Number.isInteger(pagination.size)
      || pagination.size < 1 || Number(pagination.page) !== page) {
    throw new SourceError(`${kind}: 공식 목록 페이지/건수 구조 변경 (${page}페이지)`);
  }
  if (kind === 'keyword_search' && pageProps?.query?.keyword !== keyword) {
    throw new SourceError(`검색어 불일치: ${keyword}`);
  }
  const main = data.base.normal?.collection;
  if (!Array.isArray(main) || (pagination.totalCount > 0 && main.length === 0)) {
    throw new SourceError(`${kind}: ${page}페이지 공고 행 누락`);
  }
  const paid = Object.values(data.paid || {}).flatMap(section => section?.collection || []);
  const source = kind === 'remote_list' ? 'remote_list' : keyword;
  const items = [...main, ...paid].map(entry => {
    const id = String(entry?.recruitNo || '');
    if (!/^\d+$/.test(id) || !entry.companyName || !entry.recruitTitle) {
      throw new SourceError(`${kind}: 공고번호/업체명/제목 누락`);
    }
    const canonical = canonicalJob(`/jobs/detail/${id}`);
    return {
      ...canonical,
      company: String(entry.companyName).trim(),
      title: String(entry.recruitTitle).trim(),
      pay_text: [entry.payType?.description, entry.pay].filter(Boolean).join(' ') || null,
      work_text: [entry.workingPeriod, entry.workingWeek, entry.workingTime].filter(Boolean).join(' / ') || null,
      source_queries: [source],
    };
  });
  return { items, total_count: pagination.totalCount, page: Number(pagination.page),
    page_size: pagination.size, total_pages: Math.ceil(pagination.totalCount / pagination.size) };
}

export async function fetchListing(url, options, fetcher = fetch) {
  let response;
  try { response = await fetcher(url, { signal: AbortSignal.timeout(30000) }); }
  catch (error) { throw new SourceError(`공식 페이지 요청 실패: ${error.message}`); }
  if (response.status === 403 || response.status === 429) {
    throw new SourceError(`알바몬 접근 제한 HTTP ${response.status}`, true);
  }
  if (!response.ok) throw new SourceError(`알바몬 HTTP ${response.status}`);
  return parseListing(await response.text(), options);
}

export async function collectPages({ kind, keyword = '', pauseMs = REQUEST_PAUSE_MS,
  maxPages = kind === 'remote_list' ? Infinity : MAX_KEYWORD_PAGES, fetcher = fetch }) {
  const items = [];
  let page = 1;
  let totalPages = null;
  let totalCount = null;
  let changedCount = false;
  while (totalPages === null || page <= Math.min(totalPages, maxPages)) {
    if (page > 1) await sleep(pauseMs);
    const url = kind === 'remote_list' ? new URL(REMOTE_URL) : new URL(SEARCH_URL);
    if (kind !== 'remote_list') {
      url.searchParams.set('keyword', keyword);
      url.searchParams.set('sortType', 'POSTED_DATE');
    }
    if (page > 1) url.searchParams.set('page', String(page));
    const result = await fetchListing(url, { kind, page, keyword }, fetcher);
    if (totalPages === null) { totalPages = result.total_pages; totalCount = result.total_count; }
    else if (result.total_count !== totalCount) {
      changedCount = true;
      totalPages = Math.max(totalPages, result.total_pages);
    }
    items.push(...result.items);
    page++;
  }
  return { items, stats: { status: 'ok', total_count: totalCount, total_pages: totalPages,
    pages_checked: page - 1, truncated: Number.isFinite(maxPages) && totalPages > maxPages,
    changed_during_scan: changedCount } };
}
