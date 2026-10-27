import test from "node:test";
import assert from "node:assert/strict";
import { collectPosts } from "../lib/naver/sources.mjs";

test("partial mobile fetch failure is not reported as successful collection", async t => {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.includes("rss.blog")) return new Response("unavailable", { status: 503 });
    if (url.includes("PostList")) return new Response('<a href="https://m.blog.naver.com/naver_seller/224455000001">a</a><a href="https://m.blog.naver.com/naver_seller/224455000002">b</a>');
    if (url.endsWith("224455000001")) return new Response("unavailable", { status: 503 });
    return new Response('<meta property="og:title" content="리빙 모집">');
  });
  await assert.rejects(collectPosts(), error => {
    assert.equal(error.message, "all Naver sources failed");
    assert.match(error.sourceErrors.find(e => e.source === "mobile-html").message, /incomplete/);
    return true;
  });
});

test("healthy mobile fallback includes the RSS error for diagnostics", async t => {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.includes("rss.blog")) return new Response("unavailable", { status: 503 });
    if (url.includes("PostList")) return new Response('<a href="https://m.blog.naver.com/naver_seller/224455000001">a</a>');
    return new Response('<meta property="og:title" content="리빙 모집">');
  });
  const result = await collectPosts();
  assert.equal(result.sourceUsed, "mobile-html");
  assert.equal(result.posts.length, 1);
  assert.equal(result.errors[0].source, "rss");
});
