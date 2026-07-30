import test from "node:test";
import assert from "node:assert/strict";
import { extractLogNo, extractLogNosFromHtml, mergePosts, parsePostHtml, parseRss } from "../netlify/functions/_shared/parser.mjs";

test("extractLogNo handles canonical blog URLs", () => {
  assert.equal(extractLogNo("https://blog.naver.com/naver_seller/224354025826"), "224354025826");
});

test("parseRss extracts post fields", () => {
  const xml = `<?xml version="1.0"?><rss><channel><item><title><![CDATA[홈리빙 기획전]]></title><link>https://blog.naver.com/naver_seller/224354025826</link><description><![CDATA[<b>모집 안내</b>]]></description><pubDate>Thu, 30 Jul 2026 10:00:00 +0900</pubDate></item></channel></rss>`;
  const posts = parseRss(xml);
  assert.equal(posts.length, 1);
  assert.equal(posts[0].logNo, "224354025826");
  assert.equal(posts[0].title, "홈리빙 기획전");
  assert.equal(posts[0].description, "모집 안내");
});

test("extractLogNosFromHtml deduplicates post numbers", () => {
  const html = `<a href="https://m.blog.naver.com/naver_seller/224354025826">A</a><script>{"logNo":"224354025826"}</script>`;
  assert.deepEqual(extractLogNosFromHtml(html), ["224354025826"]);
});

test("parsePostHtml reads OpenGraph metadata", () => {
  const html = `<meta property="og:title" content="주방 기획전"><meta property="og:description" content="모집 중">`;
  const post = parsePostHtml(html, "224354025826");
  assert.equal(post.title, "주방 기획전");
  assert.equal(post.description, "모집 중");
});

test("mergePosts keeps original detection time", () => {
  const previous = [{ logNo: "1", title: "old", detectedAt: "2026-07-30T00:00:00.000Z" }];
  const merged = mergePosts(previous, [{ logNo: "1", title: "updated" }, { logNo: "2", title: "new" }], "2026-07-30T01:00:00.000Z");
  assert.equal(merged.find((post) => post.logNo === "1").detectedAt, "2026-07-30T00:00:00.000Z");
  assert.equal(merged.find((post) => post.logNo === "2").detectedAt, "2026-07-30T01:00:00.000Z");
});
