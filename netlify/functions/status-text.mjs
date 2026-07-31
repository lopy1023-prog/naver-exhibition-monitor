import { getStore } from "@netlify/blobs";

const STORE_NAME = "naver-exhibition-monitor";
const STATE_KEY = "state";

function clean(value) {
  return String(value ?? "")
    .replace(/\r?\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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

    const lines = [
      "NAVER_EXHIBITION_MONITOR",
      `status=${clean(data.status ?? "unknown")}`,
      `lastCheckedAt=${clean(data.lastCheckedAt ?? "")}`,
      `lastSuccessAt=${clean(data.lastSuccessAt ?? "")}`,
      `latestLogNo=${clean(data.latestLogNo ?? "")}`,
      `sourceUsed=${clean(data.sourceUsed ?? "")}`,
      `postCount=${clean(data.postCount ?? posts.length)}`,
      "",
      "RECENT_POSTS",
    ];

    posts.forEach((post, index) => {
      lines.push(`POST_${index + 1}_TITLE=${clean(post.title ?? post.subject ?? "")}`);
      lines.push(`POST_${index + 1}_LOGNO=${clean(post.logNo ?? post.id ?? "")}`);
      lines.push(`POST_${index + 1}_URL=${clean(post.url ?? post.link ?? "")}`);
      lines.push(
        `POST_${index + 1}_DATE=${clean(
          post.publishedAt ?? post.pubDate ?? post.date ?? post.createdAt ?? ""
        )}`
      );
      lines.push("");
    });

    return new Response(lines.join("\n"), {
      status: 200,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store, no-cache, must-revalidate",
        "x-robots-tag": "noindex",
      },
    });
  } catch (error) {
    return new Response(
      [
        "NAVER_EXHIBITION_MONITOR",
        "status=error",
        `message=${clean(error?.message ?? error)}`,
      ].join("\n"),
      {
        status: 500,
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "no-store",
        },
      }
    );
  }
}
