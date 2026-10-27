import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { mergePosts } from "../lib/naver/parser.mjs";
import { collectPosts } from "../lib/naver/sources.mjs";

const RSS_URL = "https://rss.blog.naver.com/naver_seller.xml";
const MOBILE_URL = "https://m.blog.naver.com/PostList.naver?blogId=naver_seller&categoryNo=0&listStyle=style1";

function validatePosts(posts, allowEmpty = false) {
  if (!Array.isArray(posts) || (!allowEmpty && !posts.length)) {
    throw new Error("Naver collection contains no posts");
  }
  const ids = new Set();
  for (const post of posts) {
    if (!post || !/^\d{8,}$/.test(post.logNo) || ids.has(post.logNo)) {
      throw new Error("Invalid or duplicate Naver post ID");
    }
    if (typeof post.title !== "string" || !post.title.trim() ||
        post.title === `네이버 쇼핑파트너 글 ${post.logNo}`) {
      throw new Error(`Missing official title for ${post.logNo}`);
    }
    if (post.url !== `https://blog.naver.com/naver_seller/${post.logNo}`) {
      throw new Error(`Invalid official URL for ${post.logNo}`);
    }
    if (post.publishedAt && !Number.isFinite(Date.parse(post.publishedAt))) {
      throw new Error(`Invalid publication date for ${post.logNo}`);
    }
    ids.add(post.logNo);
  }
}

async function readPrevious(outputPath) {
  try {
    const previous = JSON.parse(await readFile(outputPath, "utf8"));
    if (previous.schemaVersion !== 1 || previous.postCount !== previous.posts?.length) {
      throw new Error("Existing feed schema or count is invalid; preserving file");
    }
    validatePosts(previous.posts, previous.sourceStatus === "error");
    return previous;
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

async function writeSnapshot(outputPath, snapshot) {
  await mkdir(dirname(outputPath), { recursive: true });
  const temporaryPath = `${outputPath}.${process.pid}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  await rename(temporaryPath, outputPath);
}

export async function collectNaverFeed({
  outputPath = process.env.OUTPUT_PATH || "data/naver-feed.json",
  collect = collectPosts,
  checkedAt = new Date().toISOString(),
} = {}) {
  if (!Number.isFinite(Date.parse(checkedAt))) throw new Error("Invalid collection time");
  const absolutePath = resolve(outputPath);
  const previous = await readPrevious(absolutePath);
  let next;
  try {
    const result = await collect();
    validatePosts(result.posts);
    const merged = mergePosts(previous?.posts ?? [], result.posts, checkedAt);
    validatePosts(merged);
    next = {
      schemaVersion: 1,
      collectionMode: "github-actions-direct",
      sourceUrl: result.sourceUsed === "rss" ? RSS_URL : MOBILE_URL,
      sourceStatus: "ok",
      sourceUsed: result.sourceUsed,
      sourceLastCheckedAt: checkedAt,
      sourceLastSuccessAt: checkedAt,
      latestLogNo: merged[0].logNo,
      postCount: merged.length,
      syncedAt: checkedAt,
      posts: merged.map((post, index) => ({
        position: index + 1,
        title: post.title,
        logNo: post.logNo,
        url: post.url,
        publishedAt: post.publishedAt ?? null,
        detectedAt: post.detectedAt ?? checkedAt,
      })),
      sourceErrors: result.errors ?? [],
      error: null,
    };
  } catch (error) {
    const failed = {
      ...(previous ?? { schemaVersion: 1, posts: [], postCount: 0, latestLogNo: null }),
      collectionMode: "github-actions-direct",
      sourceUrl: RSS_URL,
      sourceStatus: "error",
      sourceLastCheckedAt: checkedAt,
      sourceLastSuccessAt: previous?.sourceLastSuccessAt ?? null,
      syncedAt: checkedAt,
      sourceErrors: error.sourceErrors ?? [],
      error: error instanceof Error ? error.message : String(error),
    };
    await writeSnapshot(absolutePath, failed);
    throw error;
  }
  await writeSnapshot(absolutePath, next);
  console.log(JSON.stringify({
    sourceStatus: next.sourceStatus, sourceUsed: next.sourceUsed,
    posts: next.postCount, latestLogNo: next.latestLogNo,
    checkedAt, outputPath: absolutePath,
  }));
  return next;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  collectNaverFeed().catch(error => {
    console.error(JSON.stringify({
      sourceStatus: "error", error: error.message, sourceErrors: error.sourceErrors ?? [],
    }));
    process.exitCode = 1;
  });
}
