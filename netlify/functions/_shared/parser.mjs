const BLOG_ID = "naver_seller";

export function decodeEntities(value = "") {
  const entities = {
    amp: "&",
    lt: "<",
    gt: ">",
    quot: '"',
    apos: "'",
    nbsp: " ",
  };

  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/&([a-z]+);/gi, (match, name) => entities[name.toLowerCase()] ?? match);
}

export function stripHtml(value = "") {
  return decodeEntities(value)
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractTag(block, tag) {
  const pattern = new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, "i");
  const match = block.match(pattern);
  return match ? decodeEntities(match[1]).trim() : "";
}

export function extractLogNo(value = "") {
  const candidates = [
    /blog\.naver\.com\/(?:PostView\.naver\?[^#]*?logNo=|[^/?#]+\/)(\d{8,})/i,
    /[?&]logNo=(\d{8,})/i,
    /\/(\d{8,})(?:[/?#]|$)/,
  ];

  for (const pattern of candidates) {
    const match = value.match(pattern);
    if (match) return match[1];
  }
  return "";
}

function normalizeDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

export function parseRss(xml) {
  const itemBlocks = xml.match(/<item(?:\s[^>]*)?>[\s\S]*?<\/item>/gi) ?? [];

  return itemBlocks
    .map((block) => {
      const link = extractTag(block, "link") || extractTag(block, "guid");
      const logNo = extractLogNo(link);
      if (!logNo) return null;

      return {
        logNo,
        title: stripHtml(extractTag(block, "title")) || `네이버 쇼핑파트너 글 ${logNo}`,
        url: `https://blog.naver.com/${BLOG_ID}/${logNo}`,
        publishedAt: normalizeDate(extractTag(block, "pubDate") || extractTag(block, "dc:date")),
        description: stripHtml(extractTag(block, "description")).slice(0, 1500),
        source: "rss",
      };
    })
    .filter(Boolean);
}

function readMeta(html, key) {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const patterns = [
    new RegExp(`<meta[^>]+(?:property|name)=["']${escaped}["'][^>]+content=["']([^"']*)["'][^>]*>`, "i"),
    new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]+(?:property|name)=["']${escaped}["'][^>]*>`, "i"),
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match) return decodeEntities(match[1]).trim();
  }
  return "";
}

export function extractLogNosFromHtml(html) {
  const results = new Set();
  const patterns = [
    /(?:m\.)?blog\.naver\.com\/naver_seller\/(\d{8,})/gi,
    /[?&]logNo=(\d{8,})/gi,
    /["']logNo["']\s*[:=]\s*["']?(\d{8,})/gi,
  ];

  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(html)) !== null) results.add(match[1]);
  }

  return [...results];
}

export function parsePostHtml(html, logNo) {
  const title = readMeta(html, "og:title") || readMeta(html, "twitter:title");
  const description = readMeta(html, "og:description") || readMeta(html, "description");
  const publishedAt = readMeta(html, "article:published_time") || null;

  return {
    logNo,
    title: stripHtml(title) || `네이버 쇼핑파트너 글 ${logNo}`,
    url: `https://blog.naver.com/${BLOG_ID}/${logNo}`,
    publishedAt: normalizeDate(publishedAt),
    description: stripHtml(description).slice(0, 1500),
    source: "mobile-html",
  };
}

export function mergePosts(existingPosts = [], fetchedPosts = [], detectedAt) {
  const byLogNo = new Map(existingPosts.map((post) => [post.logNo, post]));

  for (const post of fetchedPosts) {
    const previous = byLogNo.get(post.logNo);
    byLogNo.set(post.logNo, {
      ...previous,
      ...post,
      detectedAt: previous?.detectedAt ?? detectedAt,
      lastSeenAt: detectedAt,
    });
  }

  return [...byLogNo.values()]
    .sort((a, b) => {
      const aDate = Date.parse(a.publishedAt || a.detectedAt || 0) || 0;
      const bDate = Date.parse(b.publishedAt || b.detectedAt || 0) || 0;
      return bDate - aDate || Number(b.logNo) - Number(a.logNo);
    })
    .slice(0, 50);
}
