import { getStore } from "@netlify/blobs";

const STORE_NAME = "naver-exhibition-monitor";
const STATE_KEY = "state";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "기록 없음";

  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
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

    const data = state ?? {
      status: "uninitialized",
      message: "수집기가 아직 한 번도 실행되지 않았습니다.",
      lastCheckedAt: null,
      lastSuccessAt: null,
      latestLogNo: null,
      sourceUsed: null,
      postCount: 0,
      recentPosts: [],
      sourceErrors: [],
    };

    const posts = Array.isArray(data.recentPosts)
      ? data.recentPosts
      : [];

    const postHtml = posts.length
      ? posts
          .map((post) => {
            const title = escapeHtml(
              post.title ?? post.subject ?? "제목 없음"
            );

            const url = escapeHtml(
              post.url ?? post.link ?? "#"
            );

            const logNo = escapeHtml(
              post.logNo ?? post.id ?? "-"
            );

            const publishedAt = formatDate(
              post.publishedAt ??
                post.pubDate ??
                post.date ??
                post.createdAt
            );

            return `
              <article class="post">
                <a href="${url}" target="_blank" rel="noopener noreferrer">
                  ${title}
                </a>
                <div class="meta">
                  글번호 ${logNo} · ${escapeHtml(publishedAt)}
                </div>
              </article>
            `;
          })
          .join("")
      : `<p class="empty">수집된 게시물이 없습니다.</p>`;

    const errorHtml =
      Array.isArray(data.sourceErrors) &&
      data.sourceErrors.length
        ? `
          <section class="card error-card">
            <h2>수집 오류</h2>
            <pre>${escapeHtml(
              JSON.stringify(data.sourceErrors, null, 2)
            )}</pre>
          </section>
        `
        : "";

    const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>네이버 기획전 감시 상태</title>

  <style>
    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: #f5f7f9;
      color: #202124;
      font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
    }

    main {
      width: min(900px, calc(100% - 32px));
      margin: 40px auto;
    }

    h1 { margin: 0; font-size: 28px; }
    h2 { margin: 0 0 16px; font-size: 20px; }

    .description {
      margin: 6px 0 24px;
      color: #687078;
    }

    .card {
      margin-bottom: 18px;
      padding: 22px;
      background: white;
      border: 1px solid #e2e5e9;
      border-radius: 14px;
    }

    .status {
      display: inline-block;
      margin-bottom: 18px;
      padding: 6px 12px;
      border-radius: 999px;
      font-weight: 700;
      background: ${data.status === "ok" ? "#e9f8ef" : "#fff0f0"};
      color: ${data.status === "ok" ? "#08783e" : "#c73535"};
    }

    dl {
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 10px 16px;
      margin: 0;
    }

    dt { color: #6c737a; }
    dd {
      margin: 0;
      font-weight: 600;
      word-break: break-all;
    }

    .post {
      padding: 16px 0;
      border-bottom: 1px solid #edf0f2;
    }

    .post:last-child { border-bottom: 0; }

    .post a {
      color: #1d4ed8;
      font-size: 16px;
      font-weight: 700;
      text-decoration: none;
    }

    .post a:hover { text-decoration: underline; }

    .meta {
      margin-top: 5px;
      color: #7a828a;
      font-size: 13px;
    }

    .empty { color: #7a828a; }
    .error-card { border-color: #f1b8b8; }

    pre {
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }

    footer {
      padding: 10px;
      color: #8a9198;
      text-align: center;
      font-size: 13px;
    }

    @media (max-width: 600px) {
      main { margin: 22px auto; }
      dl {
        grid-template-columns: 1fr;
        gap: 2px;
      }
      dd { margin-bottom: 10px; }
    }
  </style>
</head>

<body>
  <main>
    <header>
      <h1>네이버 기획전 감시 상태</h1>
      <p class="description">
        네이버 쇼핑파트너 블로그 수집 결과입니다.
      </p>
    </header>

    <section class="card">
      <div class="status">${escapeHtml(data.status)}</div>

      <dl>
        <dt>마지막 확인</dt>
        <dd>${escapeHtml(formatDate(data.lastCheckedAt))}</dd>

        <dt>마지막 성공</dt>
        <dd>${escapeHtml(formatDate(data.lastSuccessAt))}</dd>

        <dt>수집 방식</dt>
        <dd>${escapeHtml(data.sourceUsed ?? "기록 없음")}</dd>

        <dt>수집 게시물 수</dt>
        <dd>${escapeHtml(data.postCount ?? posts.length)}</dd>

        <dt>최신 글번호</dt>
        <dd>${escapeHtml(data.latestLogNo ?? "기록 없음")}</dd>
      </dl>
    </section>

    ${errorHtml}

    <section class="card">
      <h2>최근 게시물</h2>
      ${postHtml}
    </section>

    <footer>
      페이지 생성 시각: ${escapeHtml(formatDate(new Date().toISOString()))}
    </footer>
  </main>
</body>
</html>`;

    return new Response(html, {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store, no-cache, must-revalidate",
      },
    });
  } catch (error) {
    const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>상태 확인 실패</title>
</head>
<body>
  <h1>상태 확인 실패</h1>
  <pre>${escapeHtml(error?.stack ?? error)}</pre>
</body>
</html>`;

    return new Response(html, {
      status: 500,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
      },
    });
  }
}
