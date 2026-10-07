import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_FEED_URL =
  "https://naver-exhibition-monitor.netlify.app/feed.txt";
const DEFAULT_OUTPUT_PATH = "data/naver-feed.json";

function clean(value) {
  return String(value ?? "").trim();
}

export function parseFeedText(text) {
  const normalized = String(text ?? "").replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");

  if (clean(lines[0]) !== "NAVER_EXHIBITION_MONITOR") {
    throw new Error("Invalid feed header");
  }

  const metadata = {};
  const postsByPosition = new Map();
  let readingPosts = false;

  for (const rawLine of lines.slice(1)) {
    const line = rawLine.trimEnd();

    if (line === "RECENT_POSTS") {
      readingPosts = true;
      continue;
    }

    if (!line) {
      continue;
    }

    if (!readingPosts) {
      const separator = line.indexOf("=");
      if (separator > 0) {
        metadata[line.slice(0, separator)] = line.slice(separator + 1);
      }
      continue;
    }

    const match = line.match(/^POST_(\d+)_(TITLE|LOGNO|URL|DATE)=(.*)$/);
    if (!match) {
      continue;
    }

    const position = Number(match[1]);
    const field = match[2];
    const value = match[3];
    const post = postsByPosition.get(position) ?? { position };

    if (field === "TITLE") post.title = value;
    if (field === "LOGNO") post.logNo = value;
    if (field === "URL") post.url = value;
    if (field === "DATE") post.publishedAt = value;

    postsByPosition.set(position, post);
  }

  const posts = [...postsByPosition.values()]
    .sort((left, right) => left.position - right.position)
    .filter((post) => post.logNo && post.title && post.url)
    .map((post) => ({
      position: post.position,
      title: clean(post.title),
      logNo: clean(post.logNo),
      url: clean(post.url),
      publishedAt: clean(post.publishedAt),
    }));

  if (posts.length === 0) {
    throw new Error("Feed contains no usable posts");
  }

  return { metadata, posts };
}

function createSnapshot(parsed, feedUrl) {
  const sourceStatus = clean(parsed.metadata.status || "unknown");
  if (sourceStatus !== "ok") {
    throw new Error(
      `Source status is ${sourceStatus}: ${clean(parsed.metadata.message || "collection did not succeed")}`,
    );
  }

  const postCount = parsed.metadata.postCount === undefined
    ? parsed.posts.length
    : Number(parsed.metadata.postCount);
  if (!Number.isInteger(postCount) || postCount !== parsed.posts.length) {
    throw new Error(
      `Feed post count mismatch: declared=${parsed.metadata.postCount} parsed=${parsed.posts.length}`,
    );
  }

  return {
    schemaVersion: 1,
    sourceUrl: feedUrl,
    sourceStatus,
    sourceUsed: clean(parsed.metadata.sourceUsed),
    sourceLastCheckedAt: clean(parsed.metadata.lastCheckedAt),
    sourceLastSuccessAt: clean(parsed.metadata.lastSuccessAt),
    latestLogNo: clean(
      parsed.metadata.latestLogNo || parsed.posts[0]?.logNo,
    ),
    postCount,
    syncedAt: new Date().toISOString(),
    posts: parsed.posts,
  };
}

export function stableSnapshot(snapshot) {
  const {
    syncedAt: _syncedAt,
    sourceLastCheckedAt: _sourceLastCheckedAt,
    sourceLastSuccessAt: _sourceLastSuccessAt,
    ...stable
  } = snapshot;
  return JSON.stringify(stable);
}

async function readExistingSnapshot(outputPath) {
  try {
    return JSON.parse(await readFile(outputPath, "utf-8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

async function writeJsonAtomically(outputPath, value) {
  await mkdir(dirname(outputPath), { recursive: true });
  const temporaryPath = `${outputPath}.tmp`;
  await writeFile(
    temporaryPath,
    `${JSON.stringify(value, null, 2)}\n`,
    "utf-8",
  );
  await rename(temporaryPath, outputPath);
}

export async function syncFeed({
  feedUrl = process.env.FEED_URL || DEFAULT_FEED_URL,
  outputPath = process.env.OUTPUT_PATH || DEFAULT_OUTPUT_PATH,
} = {}) {
  const response = await fetch(feedUrl, {
    headers: {
      accept: "text/plain",
      "user-agent": "github-actions-naver-feed-bridge/1.0",
    },
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    const detail = clean(await response.text()).replace(/\s+/g, " ").slice(0, 500);
    const requestId = response.headers.get("x-nf-request-id");
    throw new Error(
      `Feed request failed: HTTP ${response.status} ${response.statusText}; ${detail || "empty response"}${requestId ? `; requestId=${requestId}` : ""}`,
    );
  }

  const parsed = parseFeedText(await response.text());
  const nextSnapshot = createSnapshot(parsed, feedUrl);
  const absoluteOutputPath = resolve(outputPath);
  const currentSnapshot = await readExistingSnapshot(absoluteOutputPath);

  const announcementsChanged = !currentSnapshot ||
    stableSnapshot(currentSnapshot) !== stableSnapshot(nextSnapshot);

  await writeJsonAtomically(absoluteOutputPath, nextSnapshot);
  console.log(
    `Feed synchronized. sourceStatus=${nextSnapshot.sourceStatus} latestLogNo=${nextSnapshot.latestLogNo} posts=${nextSnapshot.posts.length} announcementsChanged=${announcementsChanged} syncedAt=${nextSnapshot.syncedAt} sourceLastCheckedAt=${nextSnapshot.sourceLastCheckedAt} sourceLastSuccessAt=${nextSnapshot.sourceLastSuccessAt}`,
  );

  return {
    changed: true,
    announcementsChanged,
    latestLogNo: nextSnapshot.latestLogNo,
    outputPath: absoluteOutputPath,
  };
}

async function main() {
  await syncFeed();
}

const invokedPath = process.argv[1]
  ? pathToFileURL(resolve(process.argv[1])).href
  : "";

if (import.meta.url === invokedPath) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
