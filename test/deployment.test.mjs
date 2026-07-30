import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);

test("public collect route targets a non-scheduled function", async () => {
  const [toml, manualSource, scheduledSource] = await Promise.all([
    readFile(new URL("netlify.toml", root), "utf8"),
    readFile(new URL("netlify/functions/collect-now.mjs", root), "utf8"),
    readFile(new URL("netlify/functions/collect-rss.mjs", root), "utf8"),
  ]);

  assert.match(toml, /from\s*=\s*"\/api\/collect"[\s\S]*?to\s*=\s*"\/\.netlify\/functions\/collect-now"/);
  assert.doesNotMatch(manualSource, /schedule\s*:/);
  assert.match(scheduledSource, /schedule\s*:\s*"@hourly"/);
});
