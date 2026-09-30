import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

export async function readJson(path, fallback) {
  try { return JSON.parse(await readFile(path, 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT') return fallback;
    throw error;
  }
}

export async function writeJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value)}\n`, 'utf8');
  await rename(temporary, path);
}

export function canonicalJob(value) {
  const url = new URL(String(value), 'https://www.albamon.com');
  if (url.hostname !== 'www.albamon.com') throw new Error('알바몬 외부 공고 URL');
  const match = url.pathname.match(/^\/jobs\/detail\/(\d+)\/?$/);
  if (!match) throw new Error(`알바몬 공고번호를 찾지 못함: ${url.pathname}`);
  return { job_id: match[1], url: `https://www.albamon.com/jobs/detail/${match[1]}` };
}

export function normalizeTitle(value) {
  return String(value || '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase();
}

export function deduplicate(rows) {
  const byKey = new Map();
  for (const row of rows) {
    const key = row.job_id || row.url || `${row.company}|${normalizeTitle(row.title)}`;
    const current = byKey.get(key);
    if (!current) {
      byKey.set(key, { ...row, source_queries: [...new Set(row.source_queries)] });
      continue;
    }
    current.source_queries = [...new Set([...current.source_queries, ...row.source_queries])];
    if (!current.pay_text && row.pay_text) current.pay_text = row.pay_text;
    if (!current.work_text && row.work_text) current.work_text = row.work_text;
  }
  return [...byKey.values()].sort((a, b) => Number(b.job_id) - Number(a.job_id));
}

export function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
