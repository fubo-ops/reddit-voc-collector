# Reddit VOC Collector 2.1.0

Current default: **OpenCLI + collector-owned normal Chrome** → doctor → product metadata → browser DOM preflight → recursive comment tree → per-comment product gates → global dedup/checkpoint → Excel → validate exit 0 → ASIN-named delivery. No CDP/Profile launch, per-post extension clicks, pairing codes, user-tab inventory or authentication-data reads.

## Environment

Node.js 20+; Python 3.10–3.13 (Codex bundled Python 3.12 recommended); manually logged-in Chrome with the separately installed OpenCLI extension/CLI. Codex's bundled `@oai/artifact-tool` runtime authors Excel. `OPENCLI_ENTRY`, `ARTIFACT_NODE_MODULES`, `ARTIFACT_NODE` and `REDDIT_PYTHON` support external runtime locations. Playwright and the RC1 Reddit bridge/extension are compatibility-only, not primary prerequisites.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\doctor.ps1 -Offline
node scripts/reddit_playwright_collector.cjs doctor
```
Installation copies Skill code without removing outputs or starting Chrome. The offline doctor is environment-only, not a claim of a connected browser.

## Use

```powershell
node scripts/reddit_playwright_collector.cjs preflight --asin ASIN --out-dir RUN_DIR
node scripts/reddit_playwright_collector.cjs collect --asin ASIN --target-comments 500 --out-dir RUN_DIR
node scripts/reddit_playwright_collector.cjs collect --asins ASIN1,ASIN2 --target-comments 500 --out-dir RUN_DIR
node scripts/reddit_playwright_collector.cjs collect --asin-file ASIN_FILE --target-comments 500 --out-dir RUN_DIR
```
Amazon visible product information supplies seeds; recognized SellerSprite keywords are optional with explicit missing-status records. `--metadata-json FILE` supports cached, source-preserving product records. Query expansion uses actual community language/evidence IDs. Controls are serial with 8–15-second navigation delays; nonready, load failure and visible access restrictions stop without refresh/retry.

Strict counts only qualified PASS. Explicit `--quality-mode relevance` relaxes count reconciliation alone and counts independently validated PARTIAL separately. Preserve the original directory on resume; `--retry-partial --force-reaudit-partial` is independent of completed keywords. Target is globally unique comments across both eligible tiers and all ASINs.

## Excel / validation / delivery

```powershell
node scripts/reddit_playwright_collector.cjs export --out-dir RUN_DIR
node scripts/reddit_playwright_collector.cjs validate --out-dir RUN_DIR
```
The maintained builder is `scripts/build_opencli_workbook.mjs`, not a temporary script. Relevance has eight tier/audit sheets; strict has six. Finalization uses actual validator process exit 0, then exclusive copy/SHA256.

Default delivery: `D:\Project\2026\SKILL\reddit评论采集`; override `--delivery-dir`. Files: `ASIN_reddit评论_COUNT条_YYYYMMDDTHHMMSSZ.xlsx` (UTC), never overwrite historical files. Multi-ASIN runs deliver one file per ASIN; summed workbook associations are not the global unique count. Checkpoint/JSONL/audit evidence remain in RUN_DIR.

B0HHNB798Q regression: **438 PASS + 362 validated PARTIAL = 800**, of which 312 were reused evidence and 50 fresh-search comments. Do not call this 800 Trusted/new or verified purchases.

## Offline checks

```powershell
python -X utf8 -m unittest discover -s tests
npm test
npm run check
python -X utf8 scripts/quick_validate.py .
```
Browser tests use injected fixtures and forbid real browser transport. Artifact-tool integration uses isolated synthetic runs. CI does not assume logged-in Chrome; export integration is explicitly skipped if the external bundled SDK is missing. No original VOC project or previous collector runtime dependency.

See [collection guide](references/collection-guide.md) and [record schema](references/raw-record-schema.md) for defaults, quality invariants, commands and current visible-DOM/lexical limits. Legacy RC1 bridge version/ID stay unchanged and are documented only in [compatibility design](references/extension-bridge-design.md).
