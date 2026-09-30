import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { collectPages } from './albamon.mjs';
import { KEYWORDS, MAX_SEEN_JOBS, REQUEST_PAUSE_MS, SEEN_RETENTION_DAYS } from './config.mjs';
import { canonicalJob, deduplicate, readJson, sleep, writeJson } from './utils.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const FEED = join(ROOT, 'data', 'albamon-feed.json');
const SEEN = join(ROOT, 'data', 'albamon-seen.json');
const STATUS = join(ROOT, 'data', 'collector-status.json');

function emptySource() { return { status: 'error', pages_checked: 0, total_pages: null, error: null }; }

async function markFailure(reason) {
  const previous = await readJson(STATUS, {});
  await writeJson(STATUS, {
    schema_version: 1, generated_at: new Date().toISOString(), collector_status: 'error',
    sources: previous.sources || { remote_list: emptySource(), keyword_search: emptySource() },
    errors: [...new Set([...(previous.errors || []), reason])],
  });
}

function retainSeen(jobs, currentTime) {
  const oldest = Date.parse(currentTime) - SEEN_RETENTION_DAYS * 86_400_000;
  return Object.fromEntries(Object.entries(jobs)
    .filter(([, value]) => Date.parse(value.last_seen_at || value.first_seen_at) >= oldest)
    .sort((a, b) => (b[1].last_seen_at || '').localeCompare(a[1].last_seen_at || ''))
    .slice(0, MAX_SEEN_JOBS));
}

async function collect() {
  const timestamp = new Date().toISOString();
  const previous = await readJson(FEED, { items: [] });
  const seenFile = await readJson(SEEN, { jobs: {} });
  const seen = { ...seenFile.jobs };
  for (const item of previous.items || []) {
    if (item.job_id && !seen[item.job_id]) {
      seen[item.job_id] = { first_seen_at: item.first_seen_at, last_seen_at: item.last_seen_at };
    }
  }
  const errors = [];
  const rows = [];
  const sources = {
    remote_list: emptySource(),
    keyword_search: { status: 'error', queries_checked: 0, queries_total: KEYWORDS.length,
      pages_checked: 0, truncated_queries: [], queries: {}, error: null },
  };
  let blocked = false;
  try {
    const result = await collectPages({ kind: 'remote_list' });
    rows.push(...result.items);
    sources.remote_list = result.stats;
    console.log(`remote_list ${result.stats.pages_checked}/${result.stats.total_pages} pages, ${result.items.length} rows`);
  } catch (error) {
    blocked = Boolean(error.blocked);
    sources.remote_list.error = error.message;
    errors.push(`remote_list: ${error.message}`);
  }
  for (const keyword of KEYWORDS) {
    if (blocked) break;
    await sleep(REQUEST_PAUSE_MS);
    try {
      const result = await collectPages({ kind: 'keyword_search', keyword });
      rows.push(...result.items);
      sources.keyword_search.queries_checked++;
      sources.keyword_search.pages_checked += result.stats.pages_checked;
      sources.keyword_search.queries[keyword] = result.stats;
      if (result.stats.truncated) sources.keyword_search.truncated_queries.push(keyword);
      console.log(`${keyword}: ${result.stats.pages_checked}/${result.stats.total_pages} pages, ${result.items.length} rows`);
    } catch (error) {
      blocked = Boolean(error.blocked);
      sources.keyword_search.queries[keyword] = { status: 'error', error: error.message };
      errors.push(`${keyword}: ${error.message}`);
      console.error(`${keyword}: ${error.message}`);
    }
  }
  const searched = sources.keyword_search.queries_checked;
  sources.keyword_search.status = searched === KEYWORDS.length ? 'ok' : searched > 0 ? 'partial' : 'error';
  if (sources.keyword_search.status !== 'ok') {
    sources.keyword_search.error = blocked ? '접근 제한으로 검색 중단' : '일부 검색어 수집 실패';
  }
  if (blocked) errors.push('접근 제한 또는 CAPTCHA: 추가 요청 중단');
  const anySuccess = sources.remote_list.status === 'ok' || searched > 0;
  const collectorStatus = !anySuccess ? 'error' : errors.length ? 'partial' : 'ok';
  const status = { schema_version: 1, generated_at: timestamp, collector_status: collectorStatus,
    sources, errors };
  if (!anySuccess) {
    await writeJson(STATUS, status);
    console.error(JSON.stringify({ collector_status: collectorStatus, errors }, null, 2));
    return 1;
  }
  const items = deduplicate(rows).map(item => {
    const old = seen[item.job_id];
    const firstSeen = old?.first_seen_at || timestamp;
    seen[item.job_id] = { first_seen_at: firstSeen, last_seen_at: timestamp };
    return { ...item, first_seen_at: firstSeen, last_seen_at: timestamp, is_new: !old };
  });
  const feed = { schema_version: 1, generated_at: timestamp, collector_status: collectorStatus,
    total_items: items.length, sources, errors, items };
  await writeJson(FEED, feed);
  await writeJson(SEEN, { schema_version: 1, updated_at: timestamp, jobs: retainSeen(seen, timestamp) });
  await writeJson(STATUS, { ...status, total_items: items.length });
  console.log(JSON.stringify({ collector_status: collectorStatus, total_items: items.length,
    new_items: items.filter(item => item.is_new).length, sources: {
      remote_list: sources.remote_list.pages_checked,
      keyword_search: sources.keyword_search.queries_checked,
    } }));
  return 0;
}

async function validate() {
  const feed = await readJson(FEED, null);
  const status = await readJson(STATUS, null);
  if (!feed || !status || !['ok', 'partial'].includes(feed.collector_status)
      || !['ok', 'partial'].includes(status.collector_status)) throw new Error('정상 또는 부분수집 피드 없음');
  if (feed.total_items !== feed.items?.length) throw new Error('공고 건수 불일치');
  const ids = new Set();
  for (const item of feed.items) {
    const canonical = canonicalJob(item.url);
    if (canonical.job_id !== item.job_id || canonical.url !== item.url || !item.company || !item.title
        || !Array.isArray(item.source_queries) || item.source_queries.length === 0 || ids.has(item.job_id)) {
      throw new Error(`공고 필드/중복 검증 실패: ${item.job_id}`);
    }
    ids.add(item.job_id);
  }
  if (status.generated_at !== feed.generated_at) throw new Error('수집 상태 시각 불일치');
  console.log(`validated ${feed.total_items} Albamon jobs`);
}

const action = process.argv[2];
try {
  if (action === '--validate') await validate();
  else if (action === '--mark-failure') await markFailure(process.argv.slice(3).join(' ') || '수집/검증 실패');
  else process.exitCode = await collect();
} catch (error) {
  console.error(error);
  if (action !== '--validate') await markFailure(error.message);
  process.exitCode = 1;
}
