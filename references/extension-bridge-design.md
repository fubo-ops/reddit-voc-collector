# Reddit VOC Local Bridge 1.0.0-rc1 — collector-owned-tab design

## Execution contract

The collector starts `local_bridge/reddit_bridge_server.py`, reads its short-lived `run_id`, then creates one Chrome tab through Codex Computer Use with a URL shaped like:

```text
https://www.reddit.com/r/SUB/comments/POST/SLUG/#reddit-voc-run=RUN_ID
```

URL fragments are not included in HTTP requests to Reddit. The extension content script checks the fragment locally. An unmarked Reddit page returns before reading `document`; a malformed marker or non-Reddit URL is rejected. The extension never queries the tab list. Only the collector-owned marked tab sends messages.

The same marked tab is navigated serially. Search pages are idle. Exact `/r/.../comments/.../` pages expand and capture. Leaving Reddit, run expiry, bridge shutdown or tab close ends activity. The collector retains the Computer Use tab handle and closes only that tab.

## Manifest permissions

```json
{
  "permissions": [],
  "host_permissions": [
    "https://www.reddit.com/*",
    "http://127.0.0.1:43127/*"
  ],
  "content_scripts": [{
    "matches": ["https://www.reddit.com/*"],
    "js": ["capture_core.js", "visible_capture.js", "auto_content.js"]
  }]
}
```

There is no `activeTab`, `tabs`, `scripting`, `storage`, `cookies`, `history`, `webRequest`, `nativeMessaging`, clipboard or `<all_urls>` permission. There is no popup workflow. It does not read passwords, Cookie values, Reddit tokens, browser history, Profile files or authentication storage.

## Automatic expansion

`auto_content.js` uses the existing visible-DOM expansion engine. It scans only the current comment tree and handles these labels one at a time:

- `more replies`, `more comments`, `view more replies`
- `continue this thread`, `load more comments`, `show more`
- `查看更多回复`, `更多评论`, `继续此讨论串`

After each action it waits 1–3 seconds, scrolls the comment region, rescans IDs and writes checkpoint state. Two scans with no new comment IDs and no eligible control finish the frontier. Defaults are 100 expansion actions, 500 comments and 600 seconds. A `continue this thread` navigation preserves the RUN_ID fragment, saves before navigation, captures the subtree, then returns to the original post and skips the completed control key.

Visible CAPTCHA, login wall, 403/429, network-security block, access denial, load failure, action limit or timeout stops the thread. No refresh, proxy switching or retry loop is used.

## Local authorization and signing

The bridge binds only `127.0.0.1:43127`, creates a 24–64 character random RUN_ID in memory and prints it once to stdout. It accepts only extension ID `edpfinibjpbkdnognnhealnfepkeopem` and exact Origin `chrome-extension://edpfinibjpbkdnognnhealnfepkeopem`.

`POST /v1/authorize` requires the current RUN_ID, fixed extension ID, fixed extension Origin and a valid public `www.reddit.com` URL. It returns a short-lived in-memory session ID/key. Signed `/v1/checkpoint` and `/v1/capture` requests include RUN_ID, session ID, timestamp, nonce, body hash and HMAC-SHA256. The bridge rejects wrong RUN_ID, wrong extension/Origin, stale or expired sessions, nonce replay, invalid signatures, non-loopback Host, non-Reddit URLs, payloads over 5 MiB and captures over 500 comments.

CORS permits only the fixed extension Origin and a fixed header allowlist. Ordinary webpages cannot read authorization responses or submit accepted requests. A local malicious process running with the user's OS permissions is outside the browser-CORS threat model and is not claimed to be contained.

RUN_ID and session keys are memory-only. `captures.jsonl`, `checkpoint.json` and `audit.json` contain no session key and strip URL fragments before disk writes.

## Data and audit

Each accepted comment contains `comment_id`, `parent_id`, `depth`, `author`, `body`, `score`, `created_at` and `comment_url`. Visible bodies survive when author is `[deleted]`. Blank, `[deleted]`, `[removed]` and bot-template bodies are filtered. Comment ID and normalized comment URL are global per-post dedupe keys.

Audit output records raw observations, filter count, duplicate count, unique count, maximum depth, orphan parent count, platform count, expansion action count and remaining frontier. PASS requires a final capture, two stable rounds, empty frontier, no orphan parent and a reconciled visible count. Unfinished or inconsistent threads are PARTIAL. Visible access restrictions are BLOCKED. Only PASS may later enter Trusted Comments; this bridge never edits formal Trusted output directly.

## Installation and shutdown

Version 1.0.0-rc1 requires one manual Chrome “Reload” because Manifest V3 source changed. After that, runs require no extension click, popup, pairing-code entry or per-post authorization. Disable/remove through `chrome://extensions`. Stop the bridge with `Ctrl+C` or terminate only its recorded PID; close only the collector-owned tab handle.
