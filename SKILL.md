---
name: reddit-voc-collector
description: Use when discovering, collecting, or auditing public Reddit VOC conversations for Amazon ASINs through an explicitly selected Chrome tab in Codex or CDP in an independent CLI, including iterative conversation maps, semantic relevance tiers, comment-tree traversal, evidence audits, checkpoint resume, and comments-only output.
---

# Reddit VOC Collector

Collect public, visible Reddit comments related to Amazon ASINs by iteratively learning real community language. Amazon and SellerSprite seed round 1 only; later rounds must be traceable to observed Reddit posts/comments. Posts are discovery and provenance only.

## Inputs

Use exactly one or combine the supported sources; duplicates are removed:

```powershell
node scripts/reddit_playwright_collector.cjs collect --asin B012345678 --target-comments 10
node scripts/reddit_playwright_collector.cjs collect --asins B012345678,B087654321 --target-comments 50
node scripts/reddit_playwright_collector.cjs collect --asin-file .\asins.csv --target-comments 100
```

`--target-comments` counts valid globally unique comments, never posts.

## Required workflow

1. Run offline validation before browser access: Python tests, `node --check`, CLI `--help`, and Skill quick validation.
2. In a Codex task with extension 1.0.0-rc1, default to `collector-owned-tab`: start the loopback bridge, append its short-lived RUN_ID as a URL fragment, and create exactly one Chrome tab through Computer Use. Do not enumerate or inspect user tabs.
3. Navigate only that recorded tab handle. The extension ignores unmarked tabs, waits on marked search pages, and automatically expands/captures marked post pages. Close only the collector-owned handle and stop the bridge PID at the end.
4. Resolve product metadata and build `conversation_map.json` with product entities, user problems, usage contexts, decision conversations, and observed community language. Do not label ecommerce terms as community language.
5. Run iterative discovery with seven query families. Round 1 uses product seeds; later queries require `generation_source`, evidence comment IDs, a specific semantic link, and no existing-query coverage. Build communities only from observed results.
6. Score every post and comment independently. Label qualified comments `direct_product`, `competitive_context`, or `unmet_need`; never describe indirect tiers as direct reviews. Expand the thread frontier and checkpoint every action.
7. Send valid PASS-thread rows to `Trusted_Comments`, stable PARTIAL-thread rows to `Partial_Candidates`, and no BLOCKED rows to deliverables. Only trusted rows count toward `target-comments`.
8. Stop on target, round limit, two low-yield rounds, two high-duplicate rounds, semantic saturation, visible access restriction, or manual stop.

## Iterative controls

```powershell
node scripts/reddit_playwright_collector.cjs collect --asin B003ULL1NQ `
  --discovery-mode iterative --max-discovery-rounds 5 `
  --min-new-comments-per-round 10 --duplicate-rate-stop 0.85 `
  --max-posts-per-query 10 --max-comments-per-post 500 `
  --target-comments 300 --retry-partial --force-reaudit-partial `
  --session-mode selected-chrome-tab
```

## Access limits

`collector-owned-tab` is Codex-task only. Computer Use creates a temporary normal-Chrome tab and retains its handle; the extension activates only when the URL carries the bridge RUN_ID fragment. Never list or inspect unrelated tabs, launch another Chrome profile, probe CDP, copy a browser profile, export cookies, or close the user's Chrome. The collector closes only its temporary handle.

`cdp` is retained only for an independently invoked Node CLI. Its local readiness probe may read `http://127.0.0.1:9222/json/version`; none of that behavior applies to `selected-chrome-tab`. In both modes, never type credentials, solve CAPTCHA, bypass login/private/age walls, change proxies, or evade platform controls. Stop on visible access restrictions without refresh or retry. Read [references/collection-guide.md](references/collection-guide.md) before browser access.

## Selected-tab expansion limits

Defaults are `--max-expand-actions 100`, `--max-comments-per-post 500`, `--expand-delay-min 1`, `--expand-delay-max 3`, and `--thread-timeout 600`. The checkpoint stores `expanded_control_keys`, `collected_comment_ids`, `incomplete_frontier`, the action ledger, and owned temporary-tab IDs. Resume skips completed control keys. Only collector-owned tabs used for `continue this thread` may be closed.

Use `--retry-partial --force-reaudit-partial` to build the re-audit queue directly from checkpoint `PARTIAL` threads before any new keyword discovery. This queue is independent of `searched_keywords`; forced re-audit resets the per-run expansion frontier while preserving existing `PASS` rows and prior evidence.

## Outputs

Default directory: `outputs/reddit-comments` under the current working directory.

- `*_trusted_comments.jsonl`, `*_partial_candidates.jsonl`, and Excel with six separate audit sheets.
- `*_conversation_map.json` and `*_query_plan.json`: five semantic layers, seven query families, provenance, round metrics, and marginal yield.
- `*_community_map.json`, `*_manifest.json`, and `*_checkpoint.json`: observed communities, versioned resume state, access/quality counts, saturation, and stop reason.
- `evidence/POST_ID/`: hashed raw projections, request ledger, comment IDs/tree, frontier, collector summary and independent `audit.json`.

Read [references/collection-guide.md](references/collection-guide.md) for commands and [references/raw-record-schema.md](references/raw-record-schema.md) for the exact comment contract.

## Collector-owned-tab extension bridge

Version 1.0.0-rc1 in `extension/` has no popup or pairing-code workflow. The bridge generates a memory-only RUN_ID; the collector places it in the fragment of its own Chrome tab. Unmarked tabs exit before DOM access. Read [references/extension-bridge-design.md](references/extension-bridge-design.md) for permissions, fixed extension ID, signing protocol, threat model and audit rules.
