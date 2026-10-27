import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { collectNaverFeed } from "../scripts/collect-naver-feed.mjs";

const before = "2026-10-27T04:00:00.000Z";
const after = "2026-10-27T06:00:00.000Z";
const post = (id = "224455000001", title = "리빙 기획전", date = before) => ({
  logNo: id, title, url: `https://blog.naver.com/naver_seller/${id}`,
  publishedAt: date,
});
const previous = (posts = [post()]) => ({
  schemaVersion: 1, sourceStatus: "ok", sourceLastCheckedAt: before,
  sourceLastSuccessAt: before, syncedAt: before, latestLogNo: posts[0].logNo,
  postCount: posts.length, posts: posts.map((p, i) => ({ position: i + 1, ...p })),
});
async function setup(initial = previous()) {
  const dir = await mkdtemp(join(tmpdir(), "naver-collector-"));
  const outputPath = join(dir, "feed.json");
  if (initial) await writeFile(outputPath, JSON.stringify(initial));
  return { outputPath, checkedAt: after };
}
const read = async (options) => JSON.parse(await readFile(options.outputPath, "utf8"));
const collected = (posts = [post()]) => async () => ({ posts, sourceUsed: "rss", errors: [] });

test("direct collection migrates the existing feed without resetting records", async () => {
  const options = await setup();
  await collectNaverFeed({ ...options, collect: collected() });
  const result = await read(options);
  assert.equal(result.schemaVersion, 1);
  assert.equal(result.sourceStatus, "ok");
  assert.equal(result.sourceUrl, "https://rss.blog.naver.com/naver_seller.xml");
  assert.equal(result.posts[0].logNo, post().logNo);
  assert.equal(result.posts[0].position, 1);
  assert.equal(result.sourceLastSuccessAt, after);
});

test("unchanged successful collection refreshes all collection timestamps", async () => {
  const options = await setup();
  await collectNaverFeed({ ...options, collect: collected() });
  const result = await read(options);
  assert.equal(result.syncedAt, after);
  assert.equal(result.sourceLastCheckedAt, after);
  assert.equal(result.sourceLastSuccessAt, after);
});

test("public feed excludes large source descriptions and per-fetch metadata", async () => {
  const options = await setup();
  await collectNaverFeed({ ...options, collect: collected([{ ...post(), description: "x".repeat(1500), source: "rss" }]) });
  const result = await read(options);
  assert.equal(result.posts[0].description, undefined);
  assert.equal(result.posts[0].lastSeenAt, undefined);
  assert.equal(result.posts[0].source, undefined);
});

test("short fallback merges history and updates an existing notice", async () => {
  const options = await setup(previous([post(), post("224455000002")]));
  await collectNaverFeed({ ...options, collect: collected([post("224455000001", "리빙 모집 기간 연장")]) });
  const result = await read(options);
  assert.equal(result.postCount, 2);
  assert.equal(result.posts.find(p => p.logNo === "224455000001").title, "리빙 모집 기간 연장");
});

test("new notices enter the feed and retention is bounded at fifty", async () => {
  const retained = Array.from({ length: 50 }, (_, i) => post(String(224455000000 + i)));
  const options = await setup(previous(retained));
  await collectNaverFeed({ ...options, collect: collected([post("224455000999", "새 공고", after)]) });
  const result = await read(options);
  assert.equal(result.posts.length, 50);
  assert.equal(result.postCount, 50);
  assert.equal(result.latestLogNo, "224455000999");
  assert.deepEqual(result.posts.map(p => p.position), Array.from({ length: 50 }, (_, i) => i + 1));
});

test("source failure publishes error and preserves previous posts and success time", async () => {
  const options = await setup();
  const error = Object.assign(new Error("all Naver sources failed"), { sourceErrors: [{ source: "rss", message: "HTTP 503" }] });
  await assert.rejects(collectNaverFeed({ ...options, collect: async () => { throw error; } }), /all Naver sources failed/);
  const result = await read(options);
  assert.equal(result.sourceStatus, "error");
  assert.deepEqual(result.posts, previous().posts);
  assert.equal(result.sourceLastSuccessAt, before);
  assert.equal(result.sourceLastCheckedAt, after);
  assert.equal(result.error, error.message);
  assert.deepEqual(result.sourceErrors, error.sourceErrors);
});

for (const [name, posts] of [
  ["empty source", []],
  ["duplicate IDs", [post(), post()]],
  ["wrong official link", [{ ...post(), url: "https://example.com/untrusted" }]],
  ["missing title", [{ ...post(), title: "" }]],
  ["invalid publication date", [{ ...post(), publishedAt: "not a date" }]],
  ["placeholder parser title", [post("224455000001", "네이버 쇼핑파트너 글 224455000001")]],
]) {
  test(`rejects ${name} without losing last successful data`, async () => {
    const options = await setup();
    await assert.rejects(collectNaverFeed({ ...options, collect: collected(posts) }));
    const result = await read(options);
    assert.equal(result.sourceStatus, "error");
    assert.deepEqual(result.posts, previous().posts);
    assert.equal(result.sourceLastSuccessAt, before);
  });
}

test("valid RSS fallback warnings do not mark successful collection as failed", async () => {
  const options = await setup();
  await collectNaverFeed({ ...options, collect: async () => ({ posts: [post()], sourceUsed: "mobile-html", errors: [{ source: "rss", message: "HTTP 503" }] }) });
  const result = await read(options);
  assert.equal(result.sourceStatus, "ok");
  assert.equal(result.sourceUsed, "mobile-html");
  assert.equal(result.sourceErrors.length, 1);
});

test("successful run recovers from an error and clears the old error", async () => {
  const options = await setup({ ...previous(), sourceStatus: "error", error: "old failure" });
  await collectNaverFeed({ ...options, collect: collected() });
  const result = await read(options);
  assert.equal(result.sourceStatus, "ok");
  assert.equal(result.error, null);
});

test("malformed existing JSON is not silently overwritten", async () => {
  const options = await setup();
  await writeFile(options.outputPath, "{broken");
  await assert.rejects(collectNaverFeed({ ...options, collect: collected() }));
  assert.equal(await readFile(options.outputPath, "utf8"), "{broken");
});

test("first successful run initializes a valid feed", async () => {
  const options = await setup(null);
  await collectNaverFeed({ ...options, collect: collected() });
  const result = await read(options);
  assert.equal(result.sourceStatus, "ok");
  assert.equal(result.postCount, 1);
});
