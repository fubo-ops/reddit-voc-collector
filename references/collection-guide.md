# Collection guide

> Default Codex bridge: version 1.0.0-rc1 uses one collector-created Chrome tab marked by a short-lived URL-fragment RUN_ID. No popup, pairing-code entry, activeTab click, CDP or dedicated Profile is used. See [extension-bridge-design.md](extension-bridge-design.md).

## Collector-owned-tab run

1. Start `python local_bridge/reddit_bridge_server.py --output-dir ABSOLUTE_SMOKE_DIR` and read `run_id` from the first stdout JSON line.
2. Through Codex Computer Use, call `createBrowserTab("chrome", TARGET_URL + "#reddit-voc-run=" + RUN_ID, {sessionName:"🧪 Reddit VOC"})`. Keep the returned handle; do not list user tabs.
3. Wait for `audit.json` and `checkpoint.json`. Navigate the same handle to later marked URLs only after the current post reaches a terminal audit state.
4. Stop immediately on BLOCKED or bridge/extension failure. At the end, close only the retained tab handle and terminate only the recorded bridge PID.
5. Never persist RUN_ID/session keys or merge PARTIAL/BLOCKED batches into Trusted Comments.

## Resume and force-re-audit PARTIAL threads

```powershell
node scripts\reddit_playwright_collector.cjs collect --asin B003ULL1NQ --target-comments 300 --retry-partial --force-reaudit-partial --session-mode selected-chrome-tab
```

In a Codex task this command defines the checkpoint contract; browser work uses the explicitly selected Chrome tab bridge. The PARTIAL queue runs before discovery, ignores completed keyword markers, saves after every thread/action, preserves existing PASS comments, and globally merges only newly audited PASS comments.

## 1. Offline preparation

Requirements: Python 3.10+, Node.js, Google Chrome, and local `playwright`. Offline validation runs Python tests, JavaScript syntax checks, CLI help, and Skill quick validation without opening a browser.

## 2. Codex selected Chrome tab (default)

`selected-chrome-tab` is **Codex task only**. The user must @Chrome mention the exact, already-open Reddit tab. The mention supplies the browser and tab identity; bind it directly and do not call tab inventory APIs to discover alternatives.

Preflight procedure:

1. Verify the binding is an extension-backed Chrome tab explicitly selected by the user.
2. Snapshot its tab ID/provider ID, URL and title; require an HTTPS Reddit host.
3. Read visible DOM only and classify login, CAPTCHA, network block, 403/429 and access-denied text.
4. Stop if the tab closes, its identity changes, or it navigates outside Reddit.
5. Create temporary pages only through the same browser bridge, record their IDs as collector-owned, and close only those pages.

This mode does not probe port 9222, does not run `start_reddit_cdp.ps1`, and does not expose itself as an independent Node CLI transport. It never reads cookies, passwords, tokens, Profile files or authentication storage.

The bridge supports URL/title/DOM reads, navigation, locators, clicks, collector-owned temporary tabs, and read-only page evaluation. Its evaluation sandbox currently omits `fetch` and `AbortController`; selected mode therefore uses this visible-DOM frontier:

1. Scan only the current post comment tree for `more replies`, `more comments`, `view more replies`, `continue this thread`, `load more comments`, `show more`, `查看更多回复`, `更多评论`, and `继续此讨论串`.
2. Click one inline control, wait 1–3 seconds for DOM stability, scroll the comment area, recapture IDs/parents/depth, and save checkpoint. Never click advertisements, recommendations, community links, or unrelated posts.
3. Open `continue this thread` only in a collector-created, marked temporary tab. Require the same original post ID, merge the subtree, then close only that temporary tab.
4. Finish after 连续两轮 scans show no new `comment_id` and no eligible control. Resume skips keys already present in `expanded_control_keys` and starts from `incomplete_frontier`.
5. Stop without refresh or retry on CAPTCHA, login wall, visible 403/429, network-security block, access denial, comment-load failure, action limit, comment limit, or timeout.

Defaults: `--max-expand-actions 100 --max-comments-per-post 500 --expand-delay-min 1 --expand-delay-max 3 --thread-timeout 600`. Evidence records `capture_mode: visible_dom`, every control/action delta, current total, maximum depth, `collected_comment_ids`, and remaining frontier. It must not claim JSON `after`, `morechildren`, or `api/info` completeness.

`PASS` requires a closed frontier, two stable rounds, no orphan parent, and a reconcilable visible platform count. Any unfinished control, failed load, orphan, or unreconciled count is `PARTIAL`; a visible access restriction is `BLOCKED`. Valid PASS records enter `Trusted_Comments`; stable PARTIAL records enter the clearly separated `Partial_Candidates`; BLOCKED records are excluded.

The local Node entry point recognizes the boundary but cannot acquire a Codex tab handle:

```powershell
node scripts\reddit_playwright_collector.cjs preflight --session-mode selected-chrome-tab
```

It returns `codex_bridge_required` without checking port 9222. Invoke `$reddit-voc-collector` in Codex with an @Chrome tab instead.

## 3. Independent CLI CDP connection

A normal Chrome process can be connected only when it was launched with remote debugging. Do not copy, export, or reuse the daily Chrome profile. If the currently running Chrome has no CDP endpoint, launch a separate visible profile:

```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$cdpProfile = Join-Path (Resolve-Path .) "outputs\reddit-comments\chrome-cdp-profile"
Start-Process -FilePath $chrome -ArgumentList @(
  "--remote-debugging-port=9222",
  "--remote-debugging-address=127.0.0.1",
  "--user-data-dir=$cdpProfile",
  "--no-first-run",
  "https://www.reddit.com/"
)
```

Keep that window open. Complete any permitted login manually and confirm that a Reddit page and search results render normally. The collector connects to `http://127.0.0.1:9222`; it does not read or export credentials or cookies.

The checked-in one-command launcher performs the same operation, checks port 9222 first, and waits at most 15 seconds:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_reddit_cdp.ps1
```

If the port already listens, it returns `ready` without launching another Chrome. If the dedicated profile is already owned by a process but its CDP port is unavailable, it reports that process and asks the user to handle only that dedicated window; it never uses `taskkill` or closes normal Chrome.

## 4. CDP page-only preflight

```powershell
node scripts\reddit_playwright_collector.cjs preflight `
  --session-mode cdp `
  --cdp-url http://127.0.0.1:9222
```

Preflight requires an already-open Reddit tab. It checks visible DOM content on that page, opens a temporary Reddit search page, confirms at least one visible result, opens one result or `--preflight-post-url`, and confirms visible comments. It closes only its temporary tab. It does not collect records, use background HTTP status, close Chrome, refresh, or retry.

Before connecting, the collector reads only the local Chrome metadata endpoint `http://127.0.0.1:9222/json/version`. If it is not listening, preflight runs the launcher once. This local probe never determines whether Reddit is available.

## 5. Stop conditions

If the visible browser page contains a network-security block, CAPTCHA/robot check, login wall, HTTP 403/429 message, access denial, or an unloadable comment tree, preflight returns `stop_reason` and ends immediately. A normal browser page is not rejected merely because an unrelated HTTP layer reports 403.

Preflight states are `cdp_not_listening`, `waiting_for_manual_login`, `ready`, and `access_denied`. Connection refusal maps only to `cdp_not_listening`. Visible login or an unprepared page maps to `waiting_for_manual_login`; visible security and access errors map to `access_denied`.

## 6. CDP collection after a ready preflight

Only after user confirmation, use the same CDP endpoint with `collect`, ASIN inputs and low-frequency limits:

```powershell
node scripts\reddit_playwright_collector.cjs collect `
  --asin ASIN `
  --target-comments 10 `
  --max-posts 3 `
  --max-comments-per-post 10 `
  --max-requests-per-thread 40 `
  --thread-deadline-seconds 150 `
  --session-mode cdp `
  --cdp-url http://127.0.0.1:9222
```

Each collector-created post page is an explicit target. Its in-page JSON requests are restricted to that post Listing, its observed continuation cursors, its own `morechildren`, and already-observed comment IDs. Redirects, cross-post IDs and arbitrary API paths are rejected before the request.

Every post writes `outputs/reddit-comments/evidence/POST_ID/` with `raw/*.json`, `requests.json`, `comments.jsonl`, `ids.json`, `tombstones.json`, `frontier.json`, `summary.json`, and independently recomputed `audit.json`. Only `PASS` comments count toward `target-comments`; `PARTIAL` is preserved but excluded, while `BLOCKED` stops the batch.

## 7. Iterative conversation discovery

Round 1 derives seeds from Amazon and available SellerSprite evidence. It produces all seven families: `product_entity`, `category_solution`, `problem_symptom`, `usage_context`, `decision_intent`, `competitor`, and `natural_language_question`.

After each round, extract candidate language only from qualified observed posts/comments. A new query must contain `generation_source`, `source_terms`, `evidence_comment_ids`, `discovery_round`, and a product/problem/context/competitor link. Reject generic phrases and queries already covered. Communities are marked observed only after actual search or thread evidence supplies the subreddit.

For every candidate post calculate product, solution, problem/context, community, generic-topic penalty, and ambiguity penalty components. Then score every comment independently. A relevant post never makes an unrelated comment qualified.

Stop when trusted comments reach target, the round limit is reached, two rounds have fewer than the configured new trusted comments, two rounds exceed the duplicate threshold, conversation coverage saturates, visible access is blocked, or the user stops.

## 8. Versioned checkpoint and Excel

Checkpoint versions are `collector_version`, `query_plan_version`, `conversation_map_version`, and `audit_version`. Migration preserves trusted PASS rows and completed PASS threads. Old PARTIAL threads populate `partial_reaudit_frontier`; `--retry-partial --force-reaudit-partial` processes that frontier regardless of old completed-query markers. A new discovery round is never suppressed by legacy `searched_keywords`.

Build the workbook with the bundled Python runtime:

```powershell
python scripts\build_voc_workbook.py --trusted RUN_trusted_comments.jsonl `
  --partial RUN_partial_candidates.jsonl --conversation-map RUN_conversation_map.json `
  --query-plan RUN_query_plan.json --community-map RUN_community_map.json `
  --manifest RUN_manifest.json --output RUN_reddit_voc.xlsx
```

The six sheets are `Trusted_Comments`, `Partial_Candidates`, `Conversation_Map`, `Query_Performance`, `Community_Map`, and `Run_Summary`. Only trusted rows count toward the target.
