# GitHub Feed Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copy the Netlify Naver announcement feed into a stable JSON file in GitHub so ChatGPT automation can read it through the connected GitHub repository.

**Architecture:** A dependency-free Node.js script fetches `/feed.txt`, parses its key/value records, and writes `data/naver-feed.json` only when announcement content changes. A GitHub Actions workflow runs the parser on push, hourly, and on manual dispatch, then commits the JSON through the built-in `GITHUB_TOKEN`.

**Tech Stack:** Node.js 20, Node test runner, GitHub Actions, Git.

## Global Constraints

- No paid API.
- No Gmail dependency.
- Do not commit when announcement content is unchanged.
- Store output at `data/naver-feed.json`.

---

### Task 1: Feed parser and sync command

**Files:**
- Create: `test/sync-github-feed.test.mjs`
- Create: `scripts/sync-github-feed.mjs`

- [ ] Write tests for parsing, validation, stable comparison, and HTTP synchronization.
- [ ] Run tests and confirm failure before implementation.
- [ ] Implement the parser and atomic JSON writer.
- [ ] Run tests and confirm success.

### Task 2: Scheduled GitHub workflow

**Files:**
- Create: `.github/workflows/sync-netlify-feed.yml`

- [ ] Add push, hourly schedule, and manual triggers.
- [ ] Grant `contents: write`.
- [ ] Run tests, synchronize, and commit only when JSON changes.
