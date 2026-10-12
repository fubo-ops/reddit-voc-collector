---
name: reddit-voc-collector
description: Collect and audit public Reddit VOC comments for Amazon ASINs through OpenCLI and a collector-owned normal Chrome tab, with product-derived queries, per-comment relevance gates, recursive reply expansion, checkpoint resume, tiered counts, Excel validation and centralized delivery.
---

# Reddit VOC Collector — 2.1.0

## Current default

OpenCLI → doctor → product metadata → browser-page preflight → ready → serial discovery and recursive replies → independent comment gates → global deduplication → checkpoint → Excel → validate (actual exit 0) → verified delivery copy.

Control only collector-owned normal-Chrome tabs through the installed OpenCLI extension. Do not list/read user tabs, read authentication storage or browser profiles, start a dedicated Profile/CDP, probe 9222, type credentials, solve challenges, switch proxies, request pairing codes or require per-post extension clicks. Compatibility transports are opt-in, not fallback attempts.

Read [references/collection-guide.md](references/collection-guide.md) before running. For the comment, checkpoint and tier contracts, read [references/raw-record-schema.md](references/raw-record-schema.md).

## Inputs and defaults

Use `node scripts/reddit_playwright_collector.cjs` with `doctor`, `preflight`, `collect`, `export` or `validate`. ASIN inputs: `--asin ASIN`, `--asins ASIN1,ASIN2` or `--asin-file FILE` (TXT/CSV). `--target-comments NUMBER` is a global unique valid-comment target, not posts or summed per-ASIN workbook rows.

Defaults: OpenCLI, strict, new-run target-comments=500, concurrency=1, asin-workers=1, max-retries=0; 8–15 seconds between navigations, 1–3 seconds between expansion actions, max-posts-per-query=5, max-expand-actions=100, max-comments-per-post=500, thread-timeout=600 seconds, max-discovery-rounds=5. Resume retains the previous target unless explicitly changed. Stop without refresh/retry on nonready preflight, identity change, comment-load failure or visible CAPTCHA/login/403/429/security block/access denial.

Amazon public product DOM and recognized, ASIN-bound SellerSprite keyword DOM seed round 1. Record Amazon access/login, SellerSprite site and extension status separately. `--metadata-json FILE` may supply an already-observed product record; missing metadata is a stop, never a dog-bowl fallback. SellerSprite absence permits explicit Amazon-only degradation. Generated rules are product-specific lexical rules, not an assertion of human/LLM semantic certainty.

Later queries must use actual qualified comment language with evidence IDs, source terms and a product link. A relevant post never makes all its replies relevant. Preserve `direct_product`, `competitive_context` and `unmet_need` labels; indirect VOC is not an ASIN purchase review.

## Quality and resume

- **strict (default):** independently qualified PASS-thread comments alone count.
- **relevance (explicit user approval):** only `comment_count_not_reconciled` is relaxed. Qualified rows from otherwise complete PARTIAL trees are separately stored and counted; their audit status remains PARTIAL.
- Identity, visible body, independent product relevance, full ancestry/depth, cycles/orphans, unfinished controls, load failure and access restrictions are never relaxed. Blank/deleted/removed/bot bodies are excluded; visible bodies from `[deleted]` authors remain.
- Deduplicate by comment ID and canonical comment URL across both tiers and all ASINs; merge associations. Preserve old PASS rows, use the same `--out-dir`, and never truncate them to lower a target. Explicit PARTIAL re-audit (`--retry-partial --force-reaudit-partial`) is independent of completed keywords. Later pending rounds override an earlier empty/saturated round. Retain bodies/nodes in the expansion frontier so resume does not lose already expanded comments.
- On re-audit, newly PASS partials upgrade without double counting; now-unsafe partials remain candidates and do not count. Resume retains the checkpoint's prior quality mode unless `--quality-mode` is explicit.

## Excel and delivery

The maintained artifact-tool builder is `scripts/build_opencli_workbook.mjs`, orchestrated by `scripts/finalize_opencli_run.cjs`. No temporary builder is required. The Codex bundled Node/artifact-tool runtime is required for Excel; documented environment overrides support an external installation. The legacy Python workbook builder is compatibility-only.

Strict has six sheets. Relevance has eight: `Comments`, `Trusted_Comments`, `Validated_Partial_Comments`, `Partial_Candidates`, `Conversation_Map`, `Query_Performance`, `Community_Map`, `Run_Summary`. Only `Comments` combines counted tiers; candidates never count. Filters, frozen header, wrapped body, text IDs, control-character cleanup and formula-injection protection are mandatory.

Internal records/checkpoints/evidence stay in the run directory (default `outputs/reddit-comments`). Validate the exported workbook and evidence with a real exit code 0 before reporting success or copying the deliverable. Incomplete runs retain an internal Excel and FAIL diagnostics, not a false success.

Local delivery directory: `D:\Project\2026\SKILL\reddit评论采集` (override with `--delivery-dir`). Naming: `ASIN_reddit评论_COUNT条_YYYYMMDDTHHMMSSZ.xlsx`, UTC. Multi-ASIN runs generate one named workbook per ASIN, while the internal global target remains deduplicated. Never replace a historical file. Verify SHA256 and record `delivery_excel_path`, hash and per-ASIN deliveries in manifest.

## Regression fact

The B0HHNB798Q run had **438 PASS + 362 validated PARTIAL = 800**, including **312 reused-evidence comments + 50 fresh-search comments**. It was neither 800 Trusted nor 800 newly collected. Historical outputs are not migration fixtures to overwrite.

## Compatibility only

`--session-mode cdp` requires independently enabled CDP; `selected-chrome-tab` needs the Codex bridge and explicit selection; the RC1 `collector-owned-tab` extension/local bridge remains documented in [references/extension-bridge-design.md](references/extension-bridge-design.md). RC1 extension version/ID remain unchanged and separate from collector 2.1.0. None is auto-started when OpenCLI is unavailable.
