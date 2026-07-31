import { getStore } from "@netlify/blobs";

const STORE_NAME = "naver-exhibition-monitor";
const STATE_KEY = "state";
const SITE_URL = "https://naver-exhibition-monitor.netlify.app";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function clean(value) {
  return String(value ?? "")
    .replace(/\r?\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function dateValue(post) {
  return (
    post?.publishedAt ??
    post?.pubDate ??
    post?.date ??
    post?.createdAt ??
    ""
  );
}

export default async function handler() {
  try {
    const store = getStore({
      name: STORE_NAME,
      consistency: "strong",
    });

    const state = await store.get(STATE_KEY, {
      type: "json",
    });

    const data = state ?? {};
    const posts = Array.isArray(data.recentPosts) ? data.recentPosts : [];

    const postItems = posts.map((post, index) => {
      const title = clean(post?.title ?? post?.subject ?? "제목 없음");
      const logNo = clean(post?.logNo ?? post?.id ?? "");
      const url = clean(post?.url ?? post?.link ?? "");
      const publishedAt = clean(dateValue(post));

      return {
        position: index + 1,
        title,
        logNo,
        url,
        publishedAt,
      };
    });

    const postHtml = postItems.length
      ? postItems
          .map(
            (post) => `
        <article class="post" data-log-no="${escapeHtml(post.logNo)}">
          <h2>
            <a href="${escapeHtml(post.url)}" rel="noopener noreferrer">
              ${escapeHtml(post.title)}
            </a>
          </h2>
          <dl>
            <dt>글번호</dt>
            <dd>${escapeHtml(post.logNo || "기록 없음")}</dd>
            <dt>게시 시각</dt>
            <dd><time datetime="${escapeHtml(post.publishedAt)}">${escapeHtml(post.publishedAt || "기록 없음")}</time></dd>
            <dt>원문</dt>
            <dd><a href="${escapeHtml(post.url)}">${escapeHtml(post.url)}</a></dd>
          </dl>
        </article>`
          )
          .join("\n")
      : `<p>현재 저장된 최근 게시물이 없습니다.</p>`;

    const itemListJsonLd = {
      "@context": "https://schema.org",
      "@type": "ItemList",
      name: "네이버 쇼핑파트너 최근 공고",
      numberOfItems: postItems.length,
      itemListElement: postItems.map((post) => ({
        "@type": "ListItem",
        position: post.position,
        url: post.url,
        name: post.title,
        identifier: post.logNo,
        datePublished: post.publishedAt || undefined,
      })),
    };

    const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>네이버 쇼핑파트너 최근 공고 피드</title>
  <meta name="description" content="네이버 쇼핑파트너 블로그의 최근 게시물을 자동 수집해 공개하는 서버 렌더링 피드입니다.">
  <link rel="canonical" href="${SITE_URL}/feed">
  <link rel="alternate" type="text/plain" href="${SITE_URL}/feed.txt" title="순수 텍스트 피드">
  <script type="application/ld+json">${JSON.stringify(itemListJsonLd).replaceAll("<", "\\u003c")}</script>
  <style>
    body {
      max-width: 920px;
      margin: 40px auto;
      padding: 0 20px;
      color: #1f2937;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
    }
    h1 { margin-bottom: 8px; }
    .summary, .post {
      margin-top: 20px;
      padding: 18px;
      border: 1px solid #d1d5db;
      border-radius: 12px;
    }
    .summary dl, .post dl {
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 6px 14px;
      margin: 0;
    }
    dt { color: #6b7280; }
    dd { margin: 0; overflow-wrap: anywhere; }
    .post h2 { margin: 0 0 12px; font-size: 18px; }
    a { color: #1d4ed8; }
    .machine-note {
      margin-top: 16px;
      padding: 12px;
      background: #f3f4f6;
      border-radius: 8px;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <main>
    <h1>네이버 쇼핑파트너 최근 공고 피드</h1>
    <p>네이버 쇼핑파트너 블로그의 최근 게시물을 서버에서 직접 출력합니다.</p>

    <section class="summary" aria-labelledby="feed-status">
      <h2 id="feed-status">수집 상태</h2>
      <dl>
        <dt>상태</dt>
        <dd>${escapeHtml(data.status ?? "unknown")}</dd>
        <dt>마지막 확인</dt>
        <dd>${escapeHtml(data.lastCheckedAt ?? "기록 없음")}</dd>
        <dt>마지막 성공</dt>
        <dd>${escapeHtml(data.lastSuccessAt ?? "기록 없음")}</dd>
        <dt>최신 글번호</dt>
        <dd>${escapeHtml(data.latestLogNo ?? "기록 없음")}</dd>
        <dt>게시물 수</dt>
        <dd>${escapeHtml(data.postCount ?? postItems.length)}</dd>
      </dl>
      <p class="machine-note">
        자동화용 순수 텍스트 주소:
        <a href="${SITE_URL}/feed.txt">${SITE_URL}/feed.txt</a>
      </p>
    </section>

    <section aria-labelledby="recent-posts">
      <h2 id="recent-posts">최근 게시물</h2>
      ${postHtml}
    </section>
  </main>
</body>
</html>`;

    return new Response(html, {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "public, max-age=60, s-maxage=60, stale-while-revalidate=300",
        "access-control-allow-origin": "*",
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    return new Response(
      `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>피드 오류</title></head><body><h1>피드 오류</h1><pre>${escapeHtml(
        error?.stack ?? error
      )}</pre></body></html>`,
      {
        status: 500,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "public, max-age=30, s-maxage=30",
          "access-control-allow-origin": "*",
          "x-content-type-options": "nosniff",
        },
      }
    );
  }
}
