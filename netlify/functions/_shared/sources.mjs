import { extractLogNosFromHtml, parsePostHtml, parseRss } from "./parser.mjs";

const RSS_URL = "https://rss.blog.naver.com/naver_seller.xml";
const MOBILE_LIST_URL = "https://m.blog.naver.com/PostList.naver?blogId=naver_seller&categoryNo=0&listStyle=style1";

const REQUEST_HEADERS = {
  "user-agent": "Mozilla/5.0 (compatible; DreamKitchenExhibitionMonitor/1.0; +https://naver-exhibition-monitor.netlify.app)",
  accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "accept-language": "ko-KR,ko;q=0.9,en;q=0.5",
  "cache-control": "no-cache",
};

async function fetchText(url, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      headers: REQUEST_HEADERS,
      redirect: "follow",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const text = await response.text();
    if (!text.trim()) throw new Error("empty response");
    return text;
  } finally {
    clearTimeout(timer);
  }
}

export async function collectFromRss() {
  const xml = await fetchText(RSS_URL);
  const posts = parseRss(xml);
  if (!posts.length) throw new Error("RSS parsed but no posts were found");
  return posts;
}

async function mapWithConcurrency(values, concurrency, mapper) {
  const results = new Array(values.length);
  let cursor = 0;

  async function worker() {
    while (cursor < values.length) {
      const index = cursor++;
      try {
        results[index] = await mapper(values[index], index);
      } catch {
        results[index] = null;
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, values.length) }, worker));
  return results.filter(Boolean);
}

export async function collectFromMobileHtml() {
  const listHtml = await fetchText(MOBILE_LIST_URL);
  const logNos = extractLogNosFromHtml(listHtml).slice(0, 20);
  if (!logNos.length) throw new Error("mobile list parsed but no post numbers were found");

  const posts = await mapWithConcurrency(logNos, 4, async (logNo) => {
    const html = await fetchText(`https://m.blog.naver.com/naver_seller/${logNo}`);
    return parsePostHtml(html, logNo);
  });

  if (!posts.length) throw new Error("mobile posts could not be fetched");
  return posts;
}

export async function collectPosts() {
  const errors = [];

  try {
    const posts = await collectFromRss();
    return { posts, sourceUsed: "rss", errors };
  } catch (error) {
    errors.push({ source: "rss", message: error instanceof Error ? error.message : String(error) });
  }

  try {
    const posts = await collectFromMobileHtml();
    return { posts, sourceUsed: "mobile-html", errors };
  } catch (error) {
    errors.push({ source: "mobile-html", message: error instanceof Error ? error.message : String(error) });
  }

  throw Object.assign(new Error("all Naver sources failed"), { sourceErrors: errors });
}
