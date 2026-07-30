import { getStore } from "@netlify/blobs";
import { mergePosts } from "./_shared/parser.mjs";
import { collectPosts } from "./_shared/sources.mjs";

const STORE_NAME = "naver-exhibition-monitor";
const STATE_KEY = "state";

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
    },
  });
}

export default async function handler() {
  const checkedAt = new Date().toISOString();
  const store = getStore({ name: STORE_NAME, consistency: "strong" });
  const previous = (await store.get(STATE_KEY, { type: "json" })) ?? {
    version: 1,
    status: "uninitialized",
    recentPosts: [],
    lastCheckedAt: null,
    lastSuccessAt: null,
  };

  try {
    const result = await collectPosts();
    const recentPosts = mergePosts(previous.recentPosts, result.posts, checkedAt);
    const latestPost = recentPosts[0] ?? null;

    const state = {
      version: 1,
      status: "ok",
      lastCheckedAt: checkedAt,
      lastSuccessAt: checkedAt,
      sourceUsed: result.sourceUsed,
      sourceErrors: result.errors,
      latestLogNo: latestPost?.logNo ?? null,
      postCount: recentPosts.length,
      recentPosts,
      error: null,
    };

    await store.setJSON(STATE_KEY, state);
    return json(state);
  } catch (error) {
    const state = {
      ...previous,
      version: 1,
      status: "error",
      lastCheckedAt: checkedAt,
      sourceErrors: error?.sourceErrors ?? [],
      error: error instanceof Error ? error.message : String(error),
    };

    await store.setJSON(STATE_KEY, state);
    return json(state, 503);
  }
}

export const config = {
  schedule: "@hourly",
};
