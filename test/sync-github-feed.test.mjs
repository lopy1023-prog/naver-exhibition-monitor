import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  parseFeedText,
  stableSnapshot,
  syncFeed,
} from "../scripts/sync-github-feed.mjs";

const SAMPLE_FEED = `NAVER_EXHIBITION_MONITOR
feedVersion=2
status=ok
lastCheckedAt=2026-08-03T06:00:00.000Z
lastSuccessAt=2026-08-03T06:00:00.000Z
latestLogNo=224400000001
sourceUsed=rss
postCount=2

RECENT_POSTS
POST_1_TITLE=[리빙] 주방용품 기획전 모집
POST_1_LOGNO=224400000001
POST_1_URL=https://blog.naver.com/naver_seller/224400000001
POST_1_DATE=2026-08-03T05:00:00.000Z

POST_2_TITLE=N배송 지원 안내=a=b
POST_2_LOGNO=224399999999
POST_2_URL=https://blog.naver.com/naver_seller/224399999999
POST_2_DATE=2026-08-02T05:00:00.000Z
`;

test("parses metadata and ordered posts", () => {
  const parsed = parseFeedText(SAMPLE_FEED);
  assert.equal(parsed.metadata.latestLogNo, "224400000001");
  assert.equal(parsed.posts.length, 2);
  assert.deepEqual(parsed.posts[0], {
    position: 1,
    title: "[리빙] 주방용품 기획전 모집",
    logNo: "224400000001",
    url: "https://blog.naver.com/naver_seller/224400000001",
    publishedAt: "2026-08-03T05:00:00.000Z",
  });
  assert.equal(parsed.posts[1].title, "N배송 지원 안내=a=b");
});

test("rejects a feed without usable posts", () => {
  assert.throws(
    () => parseFeedText("NAVER_EXHIBITION_MONITOR\nstatus=ok\nRECENT_POSTS\n"),
    /usable posts/i,
  );
});

test("stableSnapshot excludes refresh times from announcement comparison", () => {
  const first = {
    schemaVersion: 1,
    syncedAt: "2026-08-03T01:00:00.000Z",
    sourceLastCheckedAt: "2026-08-03T00:00:00.000Z",
    sourceLastSuccessAt: "2026-08-03T00:00:00.000Z",
    latestLogNo: "1",
    posts: [{ logNo: "1" }],
  };
  const second = {
    ...first,
    syncedAt: "2026-08-03T02:00:00.000Z",
    sourceLastCheckedAt: "2026-08-03T01:00:00.000Z",
    sourceLastSuccessAt: "2026-08-03T01:00:00.000Z",
  };
  assert.equal(stableSnapshot(first), stableSnapshot(second));
  assert.notEqual(
    stableSnapshot(first),
    stableSnapshot({ ...second, latestLogNo: "2" }),
  );
});

async function createFeedFixture(t) {
  const fixture = { status: 200, text: SAMPLE_FEED };
  const server = createServer((request, response) => {
    response.writeHead(fixture.status, { "content-type": "text/plain; charset=utf-8" });
    response.end(fixture.text);
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());

  const address = server.address();
  const feedUrl = `http://127.0.0.1:${address.port}/feed.txt`;
  const directory = await mkdtemp(join(tmpdir(), "naver-feed-"));
  const outputPath = join(directory, "data", "naver-feed.json");
  return { fixture, feedUrl, outputPath };
}

test("syncFeed refreshes syncedAt when announcements are unchanged", async (t) => {
  const { feedUrl, outputPath } = await createFeedFixture(t);
  const first = await syncFeed({ feedUrl, outputPath });
  assert.equal(first.changed, true);

  const saved = JSON.parse(await readFile(outputPath, "utf-8"));
  assert.equal(saved.latestLogNo, "224400000001");
  assert.equal(saved.posts.length, 2);

  saved.syncedAt = "2000-01-01T00:00:00.000Z";
  await writeFile(outputPath, JSON.stringify(saved));

  const second = await syncFeed({ feedUrl, outputPath });
  const refreshed = JSON.parse(await readFile(outputPath, "utf-8"));
  assert.equal(second.changed, true);
  assert.equal(second.announcementsChanged, false);
  assert.ok(Date.parse(refreshed.syncedAt) > Date.parse(saved.syncedAt));
  assert.deepEqual(refreshed.posts, saved.posts);
  assert.equal(refreshed.sourceLastCheckedAt, "2026-08-03T06:00:00.000Z");
  assert.equal(refreshed.sourceLastSuccessAt, "2026-08-03T06:00:00.000Z");
});

test("syncFeed includes a newly collected announcement", async (t) => {
  const { fixture, feedUrl, outputPath } = await createFeedFixture(t);
  await syncFeed({ feedUrl, outputPath });
  fixture.text = SAMPLE_FEED.replaceAll("224400000001", "224400000002")
    .replace("주방용품 기획전 모집", "새 주방용품 기획전 모집");

  const result = await syncFeed({ feedUrl, outputPath });
  const saved = JSON.parse(await readFile(outputPath, "utf-8"));
  assert.equal(result.announcementsChanged, true);
  assert.equal(saved.latestLogNo, "224400000002");
  assert.equal(saved.posts[0].logNo, "224400000002");
  assert.equal(saved.posts[0].title, "[리빙] 새 주방용품 기획전 모집");
});

test("syncFeed preserves the snapshot when the source reports an error", async (t) => {
  const { fixture, feedUrl, outputPath } = await createFeedFixture(t);
  await syncFeed({ feedUrl, outputPath });
  const saved = await readFile(outputPath, "utf-8");
  fixture.text = SAMPLE_FEED.replace("status=ok", "status=error");

  await assert.rejects(syncFeed({ feedUrl, outputPath }), /source.*status.*error/i);
  assert.equal(await readFile(outputPath, "utf-8"), saved);
});

test("syncFeed preserves the snapshot when a declared post is missing", async (t) => {
  const { fixture, feedUrl, outputPath } = await createFeedFixture(t);
  await syncFeed({ feedUrl, outputPath });
  const saved = await readFile(outputPath, "utf-8");
  fixture.text = SAMPLE_FEED.replace("postCount=2", "postCount=3");

  await assert.rejects(syncFeed({ feedUrl, outputPath }), /post count mismatch/i);
  assert.equal(await readFile(outputPath, "utf-8"), saved);
});

test("syncFeed reports HTTP failure details and preserves the snapshot", async (t) => {
  const { fixture, feedUrl, outputPath } = await createFeedFixture(t);
  await syncFeed({ feedUrl, outputPath });
  const saved = await readFile(outputPath, "utf-8");
  fixture.status = 503;
  fixture.text = "Upstream temporarily unavailable";

  await assert.rejects(syncFeed({ feedUrl, outputPath }), (error) => {
    assert.match(error.message, /503/);
    assert.match(error.message, /Upstream temporarily unavailable/);
    return true;
  });
  assert.equal(await readFile(outputPath, "utf-8"), saved);
});
