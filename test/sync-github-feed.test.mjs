import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
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

test("stableSnapshot ignores only syncedAt", () => {
  const first = {
    schemaVersion: 1,
    syncedAt: "2026-08-03T01:00:00.000Z",
    latestLogNo: "1",
    posts: [{ logNo: "1" }],
  };
  const second = { ...first, syncedAt: "2026-08-03T02:00:00.000Z" };
  assert.equal(stableSnapshot(first), stableSnapshot(second));
  assert.notEqual(
    stableSnapshot(first),
    stableSnapshot({ ...second, latestLogNo: "2" }),
  );
});

test("syncFeed writes once and skips unchanged feed", async (t) => {
  const server = createServer((request, response) => {
    response.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
    response.end(SAMPLE_FEED);
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());

  const address = server.address();
  const feedUrl = `http://127.0.0.1:${address.port}/feed.txt`;
  const directory = await mkdtemp(join(tmpdir(), "naver-feed-"));
  const outputPath = join(directory, "data", "naver-feed.json");

  const first = await syncFeed({ feedUrl, outputPath });
  assert.equal(first.changed, true);

  const saved = JSON.parse(await readFile(outputPath, "utf-8"));
  assert.equal(saved.latestLogNo, "224400000001");
  assert.equal(saved.posts.length, 2);

  const second = await syncFeed({ feedUrl, outputPath });
  assert.equal(second.changed, false);
});
