# GitHub-only Naver monitoring implementation plan

> For agentic workers: use superpowers:executing-plans inline. No delegation requested.

**Goal:** Collect official Naver notices directly in GitHub Actions, retain the existing public JSON contract, and deliver a company-ChatGPT prompt using only GitHub.

**Architecture:** Reuse the existing parser and Naver RSS/mobile collector as plain Node modules. Replace the bridge with an atomic JSON collector. Keep previous posts and last-success time on failure, publish the error status, and fail the job. Remove active Netlify functions and its package dependency after GitHub validation.

**Tech stack:** Node 20+, node:test, GitHub Actions, no runtime npm dependencies.

**Spec:** User instruction in this chat, 2026-10-27: remove Netlify dependency; preserve LH/Albamon; same Gmail and recipient; company account prompt; existing data/naver-feed.json remains compatible.

## Constraints and decisions
- Never change LH, Albamon, their workflows or their data.
- Keep hourly cron at minute 12; report actual schedule evidence separately from push runs.
- Keep at most 50 notices. Validate fresh and stored records, reject empty/duplicate/malformed data.
- Keep schemaVersion=1, position, sourceStatus, sourceLastCheckedAt, sourceLastSuccessAt, syncedAt, latestLogNo and postCount.
- Successful unchanged collection still advances successful collection time.
- Do not publish Gmail account/recipient in the public repository. Deliver the private prompt outside the repo.
- Source failures are recorded with previous posts intact, never converted into an empty successful feed.
- Company prompt freshness: 12 hours, explicitly changed from 5 because observed schedule gaps reach 7 hours.
- Netlify account/project deletion is not needed for operation. Retire only this project's scheduled functions after direct collection is proven.

## Review focus
- Failed collection or malformed response must preserve prior data and success time.
- A short fallback response must merge with retained history, not lose existing notices.
- Failed tests must not publish data; collection errors should publish error state and remain failed.
- Concurrent LH/Albamon commits must not be overwritten by feed publication.
- No active collector, workflow or final prompt may read a Netlify endpoint.

## Tasks
- [ ] 1. Baseline: 19 tests pass. Write failing collector tests for migration, unchanged refresh, new/changed notices, cap, malformed input, failure persistence and recovery.
- [ ] 2. Move reusable modules to lib/naver; implement scripts/collect-naver-feed.mjs. Run the focused tests and full suite.
- [ ] 3. Replace the bridge workflow with a direct-collection workflow. Remove bridge tests/script, Netlify functions/dependency, and update deployment tests/README.
- [ ] 4. Run a real local collection into a temporary output; verify no unrelated paths changed. Push an isolated branch and validate in GitHub through a pull request before merging.
- [ ] 5. Publish to main, observe the GitHub job and public JSON, and retire this project's Netlify functions without deleting unrelated sites.
- [ ] 6. Deliver a final company-account prompt, setup message, and verification record. Distinguish completed collection migration from pending company-account mail verification.
