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
- [x] 1. Baseline: 19 tests passed; collector and failure regression tests were written before implementation.
- [x] 2. Reused modules in lib/naver and implemented the atomic collector. Compact public post records exclude large descriptions and transient source metadata.
- [x] 3. Replaced the bridge workflow; removed functions and runtime dependency; updated tests/README.
- [x] 4. Local direct collection returned 50 posts. LH/Albamon paths have no diff. An isolated branch was pushed. PR creation returned integration permission error 403, so no PR was created.
- [x] 5. User-authorized main deployment: run 40464089161 passed tests, direct RSS collection, and data publication. A skip-host validation commit kept the old host until GitHub succeeded. Its feed commit then deployed retirement page 6ae04b30b986201c6d86f0ac with zero functions and zero schedules. Old API returns 404.
- [x] 6. Company-account prompt and setup message are delivered outside the public repository. Actual company-account Gmail connection and scheduled delivery remain for that account to verify.

## Execution rulings
- Native execution was already requested by the user; no additional planning/branch approval was requested.
- GitHub connector cannot create PRs in this installation. The authorized native Git push was used; the main run provided hosted end-to-end verification.
- No Netlify project/account was permanently deleted. Production scheduled functions are removed, and further feed-only commits skip the retired site's build.
