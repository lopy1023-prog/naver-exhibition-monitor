# LH Suwon official-source expansion implementation plan

> Execute inline under test-driven development and verification-before-completion. The user explicitly authorized implementation, publication, simulation, and the existing task update without further discretionary approvals.

**Goal:** Keep the existing GitHub → JSON → ChatGPT pipeline and detect Suwon-related recruitment and follow-up information across official LH sources without duplicate or retroactive alerts.

**Architecture:** Preserve canonical notice panId and old alert IDs. Add validated calendar, bulletin, supply-plan and first-come adapters to the existing collector. Store additive source baselines in the existing successful state; publish only after a complete successful collection. Existing public JSON paths and workflow cadence remain unchanged.

**Tech stack:** Python 3.11+, requests, BeautifulSoup, unittest; existing Node regression suite.

**Spec:** User's task specification and subsequent authorization in this conversation; requirements below are the binding recorded scope.

## Global constraints
- Keep all existing alertHistory entries and alertIds byte-for-byte; never reset the baseline.
- Keep the current cron and 55-minute freshness gate.
- Modify only LH files plus this LH documentation; no other monitor behavior changes.
- Collect rental, sale, land, commercial, presale, full calendar day records, notices, move-in notices/plans, documents, supply plans and first-come inventory.
- Prioritize Suwon; retain the originally requested Hwaseong/Osan coverage as additional confirmed regions. Broad candidates are explicitly unconfirmed.
- Do not prefilter by age, income, household size or floor area. Never infer room count from area.
- Do not download attachment bodies. Read attachment names/official links only.
- First successful addition of a source establishes its baseline without retroactive alerts.
- Errors preserve successful snapshots and alert history, and cannot be interpreted as an empty source.
- ChatGPT reads only the existing report JSON, keeps its established dedup state, and emits no stale-sync warnings or no-change messages.
- Do not publish the user's private age/income/assets to the public repository.

## Review focus
1. Calendar UI hides all but six items per day: validate complete day API results against rendered counts.
2. Rolling calendar windows must not create removal/new alerts when days enter/leave the window.
3. Changing parser/hash policy must not generate mass changes on deployment.
4. IDs for plan/first-come rows must not use row positions or refresh dates.
5. Unrelated contact addresses must not prove supply in Suwon; broad references stay unconfirmed.

## Task 1: Validate and normalize official supplemental sources
Files: create `additional_sources.py`, `tests/test_additional_sources.py`.
- [ ] Write and observe failing parser/count/identity/calendar tests.
- [ ] Implement calendar-month/day, bulletin-list/detail, plan-table and first-come parsers.
- [ ] Implement GET requests using observed official form fields; reject malformed/count-mismatched responses.
- [ ] Verify actual downloaded official pages and the parser tests.

## Task 2: Merge sources and maintain history safely
Files: modify `monitor.py`, `parser.py`, `diff.py`; extend tests.
- [ ] Write and observe failing baseline/dedup/failure/migration/region tests.
- [ ] Integrate supplemental collection and canonical notice enrichment into the existing run.
- [ ] Add per-source baseline state, stable semantic content, calendar reception schedules, and explicit geography/unknown metadata.
- [ ] Preserve prior history in every error report and preserve successful state on any source failure.
- [ ] Verify repeated runs, source order changes, date/attachment/follow-up changes, and failure/recovery simulations in temporary directories only.

## Task 3: Publish and verify operation
Files: update LH README; add final task prompt and validation report under `lh-monitor/docs/`.
- [ ] Run LH suite and complete existing Node suite.
- [ ] Run live collection in an isolated temporary data directory using a copy of operating state.
- [ ] Compare complete old history prefix; run a second/third unchanged snapshot simulation, with zero duplicate events.
- [ ] Review the complete change; fix material findings with regression tests.
- [ ] Publish only LH changes atomically against the current GitHub main tree; preserve concurrently updated data.
- [ ] Update the existing ChatGPT task only, retaining schedule and dedup continuity.
- [ ] Verify GitHub execution, resulting JSON and task settings; report concrete limitations.
