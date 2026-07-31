import { getStore } from "@netlify/blobs";

const STORE_NAME = "naver-exhibition-monitor";
const SOURCE_STATE_KEY = "state";
const EMAIL_STATE_KEY = "email-dispatch-state-v1";
const RECIPIENT = "lopy1023@gmail.com";
const FORM_ENDPOINT = `https://formsubmit.co/ajax/${RECIPIENT}`;

function clean(value) {
  return String(value ?? "")
    .replace(/\r?\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function postLogNo(post) {
  return clean(post?.logNo ?? post?.id ?? "");
}

function postDate(post) {
  const value = post?.publishedAt ?? post?.pubDate ?? post?.date ?? post?.createdAt;
  const time = value ? Date.parse(value) : 0;
  return Number.isFinite(time) ? time : 0;
}

function normalizePost(post) {
  return {
    logNo: postLogNo(post),
    title: clean(post?.title ?? post?.subject ?? "제목 없음"),
    url: clean(post?.url ?? post?.link ?? ""),
    publishedAt: clean(
      post?.publishedAt ?? post?.pubDate ?? post?.date ?? post?.createdAt ?? ""
    ),
  };
}

async function sendPost(post) {
  const normalized = normalizePost(post);
  const subject = `[NAVER_EXHIBITION_NEW] ${normalized.logNo || "UNKNOWN"}`;
  const message = [
    "NAVER_EXHIBITION_MONITOR",
    "status=ok",
    `logNo=${normalized.logNo}`,
    `title=${normalized.title}`,
    `url=${normalized.url}`,
    `publishedAt=${normalized.publishedAt}`,
  ].join("\n");

  const response = await fetch(FORM_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "User-Agent": "naver-exhibition-monitor/1.0",
    },
    body: JSON.stringify({
      _subject: subject,
      _template: "table",
      _captcha: "false",
      name: "Naver Exhibition Monitor",
      message,
      logNo: normalized.logNo,
      title: normalized.title,
      url: normalized.url,
      publishedAt: normalized.publishedAt,
    }),
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = { message: await response.text().catch(() => "") };
  }

  const responseMessage = clean(
    payload?.message ?? payload?.error ?? payload?.errors ?? ""
  );
  const lowerMessage = responseMessage.toLowerCase();
  const activationNeeded =
    lowerMessage.includes("activate") ||
    lowerMessage.includes("activation") ||
    lowerMessage.includes("confirm your email") ||
    lowerMessage.includes("confirmation");

  return {
    ok: response.ok && payload?.success !== false && !activationNeeded,
    status: response.status,
    activationNeeded,
    responseMessage,
    payload,
  };
}

export default async function handler() {
  const store = getStore({
    name: STORE_NAME,
    consistency: "strong",
  });

  try {
    const sourceState =
      (await store.get(SOURCE_STATE_KEY, { type: "json" })) ?? {};
    const posts = Array.isArray(sourceState.recentPosts)
      ? sourceState.recentPosts.filter((post) => postLogNo(post))
      : [];

    if (!posts.length) {
      console.log("No recent posts found. Nothing to email.");
      return new Response(null, { status: 204 });
    }

    const dispatchState =
      (await store.get(EMAIL_STATE_KEY, { type: "json" })) ?? {
        activationStartedAt: null,
        seenLogNos: [],
      };

    const seen = new Set(
      Array.isArray(dispatchState.seenLogNos)
        ? dispatchState.seenLogNos.map(clean).filter(Boolean)
        : []
    );

    const newestFirst = [...posts].sort((a, b) => postDate(b) - postDate(a));
    const latest = newestFirst[0];

    // First run triggers FormSubmit's one-time email confirmation.
    // The post is intentionally not marked as delivered yet.
    if (!dispatchState.activationStartedAt) {
      const result = await sendPost(latest);
      const nextState = {
        ...dispatchState,
        activationStartedAt: new Date().toISOString(),
        initialLogNo: postLogNo(latest),
        lastAttemptAt: new Date().toISOString(),
        lastAttemptResult: result,
        seenLogNos: [...seen],
      };
      await store.setJSON(EMAIL_STATE_KEY, nextState);
      console.log("FormSubmit activation request sent.", result);
      return new Response(null, { status: 204 });
    }

    let pending;
    if (seen.size === 0) {
      // After confirmation, send the latest current post once as a test.
      pending = [latest];
    } else {
      // Send newly discovered posts, oldest first, up to 20 per run.
      pending = newestFirst
        .filter((post) => !seen.has(postLogNo(post)))
        .sort((a, b) => postDate(a) - postDate(b))
        .slice(0, 20);
    }

    if (!pending.length) {
      console.log("No new posts to email.");
      return new Response(null, { status: 204 });
    }

    const results = [];

    for (const post of pending) {
      const result = await sendPost(post);
      const logNo = postLogNo(post);
      results.push({ logNo, ...result });

      if (!result.ok) {
        console.error("Email delivery failed or activation is pending.", {
          logNo,
          result,
        });
        break;
      }

      seen.add(logNo);

      if (dispatchState.seenLogNos?.length === 0) {
        // First successful test becomes the baseline.
        for (const currentPost of posts) {
          seen.add(postLogNo(currentPost));
        }
      }
    }

    const nextState = {
      ...dispatchState,
      seenLogNos: [...seen].filter(Boolean).slice(-300),
      lastAttemptAt: new Date().toISOString(),
      lastAttemptResults: results,
      lastSuccessAt: results.some((result) => result.ok)
        ? new Date().toISOString()
        : dispatchState.lastSuccessAt ?? null,
    };

    await store.setJSON(EMAIL_STATE_KEY, nextState);
    console.log("Email dispatch finished.", results);
    return new Response(null, { status: 204 });
  } catch (error) {
    console.error("Email dispatch error", error);
    return new Response(null, { status: 500 });
  }
}

export const config = {
  schedule: "@hourly",
};
