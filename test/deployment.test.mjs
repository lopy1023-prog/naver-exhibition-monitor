import test from "node:test";
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";

const root = new URL("../", import.meta.url);

test("workflow collects directly and publishes both success and error snapshots", async () => {
  const workflow = await readFile(new URL(".github/workflows/naver-monitor.yml", root), "utf8");
  assert.match(workflow, /cron: "12 \* \* \* \*"/);
  assert.match(workflow, /node scripts\/collect-naver-feed\.mjs/);
  assert.match(workflow, /id: collect/);
  assert.match(workflow, /always\(\).*steps\.collect\.outcome != 'skipped'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /git pull --rebase origin main/);
  assert.doesNotMatch(workflow, /netlify|FEED_URL/i);
});

test("runtime and repository have no active Netlify functions or dependency", async () => {
  const pkg = JSON.parse(await readFile(new URL("package.json", root), "utf8"));
  assert.equal(Object.keys(pkg.dependencies ?? {}).length, 0);
  const functions = await readdir(new URL("netlify/functions/", root)).catch(error => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  assert.equal(functions.filter(name => name.endsWith(".mjs") || name.endsWith(".js")).length, 0);
});
