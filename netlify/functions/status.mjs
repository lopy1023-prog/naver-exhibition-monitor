import { getStore } from "@netlify/blobs";

const STORE_NAME = "naver-exhibition-monitor";
const STATE_KEY = "state";

export default async function handler() {
  const store = getStore({ name: STORE_NAME, consistency: "strong" });
  const state = await store.get(STATE_KEY, { type: "json" });

  const body = state ?? {
    version: 1,
    status: "uninitialized",
    message: "수집기가 아직 한 번도 실행되지 않았습니다. /api/collect를 열어 최초 실행하세요.",
    lastCheckedAt: null,
    lastSuccessAt: null,
    recentPosts: [],
  };

  return new Response(JSON.stringify(body, null, 2), {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
    },
  });
}
