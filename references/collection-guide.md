# Collection guide — collector 2.1.0

## Preparation and default workflow

The current transport is OpenCLI, not the old Reddit local bridge. Install the OpenCLI CLI/Chrome extension separately, connect it to normal Chrome, and log in manually if needed. `OPENCLI_ENTRY` may point to its installed `dist/src/main.js`. On Windows the collector discovers the usual global npm installation. Only owned page handles are inspected; no tab inventory or authentication/network capture is used.

Before browser collection:
```powershell
node scripts/reddit_playwright_collector.cjs doctor
node scripts/reddit_playwright_collector.cjs preflight --asin ASIN --out-dir RUN_DIR
node scripts/reddit_playwright_collector.cjs collect --asin ASIN --target-comments 500 --out-dir RUN_DIR
```
Commands are run from the Skill folder. `preflight` checks one Reddit home page, one product-derived search page and one observed related thread's visible comments; it exports no comments and closes its owned tab. `collect` repeats doctor and preflight before admitting any records. Amazon metadata preparation may navigate the same owned tab before Reddit preflight. Missing product data stops the run. Nonready or access failure does not trigger another transport, browser refresh or automatic retry.

## Product records and keywords

New ASINs are read from Amazon US visible product DOM. Extract title, brand, leaf category and visible feature bullets; common names, attributes, contexts and problem terms may be supplied as observed metadata where the DOM does not expose separate fields. Product-derived rules never inherit another ASIN's seed list. Generic titles/ambiguous category names need better documented aliases rather than fabricated pain points.

Accepted metadata JSON:
```json
{
  "products": {
    "B000VAC001": {
      "asin": "B000VAC001", "title": "Example cordless vacuum cleaner",
      "brand": "Example", "category": "Vacuum Cleaners",
      "common_names": ["cordless vacuum", "vacuum cleaner"],
      "functions": ["carpet cleaning"], "source_url": "https://www.amazon.com/dp/B000VAC001"
    }
  },
  "seller_keywords": {},
  "access": {"B000VAC001": {"sellersprite_website_status": "not_checked", "sellersprite_extension_status": "not_visible", "seller_missing_reason": "Amazon-only seeds"}}
}
```
This is an illustrative metadata fixture, not live product evidence. `--metadata-json FILE` supports cached, source-preserving records and offline preparation. A CLI without supplied metadata reads Amazon first. Site login state, extension-panel visibility and Amazon login/access are separate facts. Recognized SellerSprite `[data-keyword]` data must be bound to the input ASIN; unrecognized UI or missing login is recorded as unavailable. `--sellersprite-url URL` optionally inspects the visible site in an owned page; it does not read a pre-existing user tab, credentials, cookies or extension storage.

Round 1 uses observed Amazon/SellerSprite fields and neutral review/comparison query templates. Later queries are actual comment phrases with `evidence_comment_ids`, `source_terms`, `generation_source` and `semantic_link`. Competitor terms must be evidenced in supplied metadata or subsequently observed category comparisons; do not invent competitor names. Product relevance is independent for each comment; short acknowledgements and implicit-only replies may be conservatively excluded.

## Serial tree traversal and stop rules

Navigation waits 8–15 seconds; each expansion waits 1–3 seconds. One control is clicked per scan inside the current comment tree, scoped to its owner comment. No ads/recommendations/community links are expanded. Same-post continuations use owned child tabs, return to the parent frontier and close only owned children. Two stable scans with no new IDs or remaining entries end the visible frontier. Tree nodes and captured bodies are checkpointed per expansion, thread and query.

识别当前评论树中的 more replies、more comments、view more replies、continue this thread、load more comments、show more 及中文控件。连续两轮无新增 comment_id 且无剩余展开入口才结束。作者为 `[deleted]` 但正文可见时保留；仅过滤删除/移除/空正文和机器人模板。

`--max-posts-per-query 5 --max-expand-actions 100 --max-comments-per-post 500 --thread-timeout 600` bound work. Thresholds can be lowered for smoke. `--concurrency 1 --asin-workers 1 --max-retries 0` are enforced. CAPTCHA, login wall, network-security block, visible 403/429/access denial, tab identity change or comment load failure stops all later work. No refresh, proxy switch or access retry is attempted.

## Modes and resume

Strict is the default on a new checkpoint. Relevance requires user approval plus explicit `--quality-mode relevance`; only count reconciliation may be relaxed. Orphans/cycles/depth conflicts, unfinished controls and load/access failures remain excluded. Audit remains PARTIAL even when an independently valid row counts. Existing quality mode is retained on resume unless the flag is explicit.

```powershell
# Single ASIN and cached observed metadata
node scripts/reddit_playwright_collector.cjs collect --asin ASIN --metadata-json PRODUCT_JSON --target-comments 500 --out-dir RUN_DIR
# Multi-ASIN or TXT/CSV; target is globally unique comments
node scripts/reddit_playwright_collector.cjs collect --asins ASIN1,ASIN2 --target-comments 500 --out-dir RUN_DIR
node scripts/reddit_playwright_collector.cjs collect --asin-file ASIN_FILE --target-comments 500 --out-dir RUN_DIR
# Explicit relaxed mode and PARTIAL re-audit, keeping old PASS
node scripts/reddit_playwright_collector.cjs collect --asin ASIN --quality-mode relevance --retry-partial --force-reaudit-partial --target-comments 800 --out-dir EXISTING_RUN_DIR
```
Do not use a fresh directory to resume. Completed keywords cannot suppress the explicit PARTIAL re-audit queue or later pending queries. Re-audited valid partials can upgrade to PASS with no extra count; unsafe partials are preserved only as candidates. `--historical-partial-limit NUMBER` caps newly admitted evidence-reuse rows in addition to the preserved baseline, not the total final quota; zero disables new partial reuse. New-run target defaults to 500, but resume preserves its previous target unless `--target-comments` is explicit. Target admission caps both accepted tiers; lowering a target below preserved counted data is an error, never truncation.

## Maintained export, validation and delivery

Collection automatically exports/validates/delivers after a ready preflight; use `--no-export` to defer that offline phase. Deferred export and read-only validation:
```powershell
node scripts/reddit_playwright_collector.cjs export --out-dir RUN_DIR --delivery-dir "D:\Project\2026\SKILL\reddit评论采集"
node scripts/reddit_playwright_collector.cjs validate --out-dir RUN_DIR
python -X utf8 scripts/validate_opencli_run.py --out-dir RUN_DIR --read-only
```
The maintained artifact-tool builder needs Codex bundled Node packages. `ARTIFACT_NODE_MODULES`, `ARTIFACT_NODE`, `REDDIT_PYTHON` or `--python` can identify equivalent external runtimes. There is no runtime dependency on the original VOC project or a temporary-directory script. Export failure is surfaced; no library fallback silently weakens validation.

Strict sheets: Trusted_Comments, Partial_Candidates, Conversation_Map, Query_Performance, Community_Map, Run_Summary. Relevance adds Comments first and Validated_Partial_Comments separately. Counted and candidate records never mix. The actual validator checks identity/body, eligibility, evidence ancestry, duplicate IDs/URLs, global/per-ASIN counts, tier sheets and projection, filters/freeze, absence of formulas, manifest/JSONL/audit consistency and delivery hashes. Failed/incomplete runs retain an internal workbook; only exit 0 authorizes validated delivery.

Each ASIN gets `ASIN_reddit评论_COUNT条_UTC_TIMESTAMP.xlsx`; historical filenames are never replaced. Internal files remain in RUN_DIR. Exclusive delivery copying verifies SHA256 and writes `delivery_excel_path` and `deliveries` to manifest. Repeating delivery of the identical already-present file is idempotent; differing content at that filename is an error.

## Compatibility

The previous CDP and selected-tab/RC1 local-bridge workflows are opt-in compatibility interfaces, not the default and not auto-retries. Legacy extension identity/version stays RC1; OpenCLI uses its own extension. CDP's readiness/port/Profile behavior is never invoked by OpenCLI. Legacy bridge details: [extension-bridge-design.md](extension-bridge-design.md). Compatibility-only scripts `build_voc_workbook.py` and `finalize_collector_batch.py` do not define the current quality/export contract.

Legacy selected-chrome-tab is **Codex task only**, requires explicit @Chrome selection and a supported bridge, and does not probe port 9222. Its visible-DOM frontier does not make that bridge an independent CLI transport. These boundaries do not change the collector-owned OpenCLI default.

## Offline acceptance

Use `npm test`, `npm run check`, Python unittest discovery, all CLI `--help`, `python -X utf8 scripts/quick_validate.py .` and `doctor.ps1 -Offline`. Export integration tests use only synthetic records and isolated temporary folders. Do not run live doctor/preflight/collect for a request restricted to offline verification. Historical B0HHNB798Q files must remain byte-for-byte unchanged: 438 PASS + 362 validated PARTIAL = 800, with 312 reused and 50 fresh, not 800 Trusted/new.
