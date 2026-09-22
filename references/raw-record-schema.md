# Reddit comment record schema

Each JSONL/CSV row represents exactly one public Reddit comment. Post content is excluded; post fields are provenance only.

Extension bridge 1.0.0-rc1 writes signed capture batches using `reddit_visible_capture_v3`; the bridge strips the RUN_ID fragment before persisting URLs and later normalizes only PASS-thread comments into this row schema.

```json
{
  "schema_version": "reddit_comment_v2",
  "platform": "reddit",
  "asin": "B012345678",
  "matched_asins": ["B012345678", "B087654321"],
  "query": "washable dog bed",
  "matched_keywords": ["washable dog bed", "dog bed problem"],
  "subreddit": "dogs",
  "post_id": "abc123",
  "post_title": "Which bed is easiest to wash?",
  "post_url": "https://www.reddit.com/r/dogs/comments/abc123/example/",
  "comment_id": "def456",
  "parent_id": "abc123",
  "depth": 0,
  "author": "example_user",
  "body": "The removable cover saves me time.",
  "score": 8,
  "created_at": "2026-09-01T10:00:00Z",
  "comment_url": "https://www.reddit.com/r/dogs/comments/abc123/example/def456/",
  "collected_at": "2026-09-14T18:00:00Z",
  "relevance_tier": "direct_product",
  "association_reason": "matched Cosequin",
  "evidence_terms": ["Cosequin"],
  "relevance_score": 0.81,
  "comment_relevance_score": 0.81,
  "discovery_round": 2,
  "query_family": "problem_symptom",
  "source_query": "dog struggling to get up after sleeping",
  "community_source": "dogs",
  "comment_record_status": "valid",
  "thread_audit_status": "PASS",
  "thread_evidence_path": "C:\\absolute\\outputs\\reddit-comments\\evidence\\abc123"
}
```

## Rules

1. Filter blank, `[deleted]`, `[removed]`, and pure bot-notice bodies. 作者为 `[deleted]` 但正文仍可见时保留。
2. Deduplicate globally by `comment_id` and normalized `comment_url`.
3. If one comment matches multiple ASINs, retain one row and merge all values into `matched_asins`.
4. Keep positive, neutral, and negative content without sentiment filtering.
5. Count only remaining unique comment rows toward `target_comments`.
6. `Trusted_Comments` accepts only valid `thread_audit_status: PASS`; stable PARTIAL records go only to `Partial_Candidates`; BLOCKED records are excluded.
7. `direct_product` requires an explicit product/brand identifier. `competitive_context` covers competitors or equivalent solutions. `unmet_need` covers relevant problems/contexts without claiming a target-product review.
8. Comment relevance is scored independently from post relevance. `source_query`, family, round, community, and evidence terms preserve discovery provenance.

## Thread evidence and status

The independent auditor reads `raw/*.json` and `requests.json`, not the collector summary. It verifies hashes, contained paths, exact post identity, comment field consistency, duplicates, orphans, cycles, continuation progress, unresolved IDs, unledgered raw files and counter reconciliation.

- `PASS`: closed frontier, consistent evidence and exact counter model.
- `PARTIAL`: incomplete frontier, exhausted budget, conflict, missing ID or unreconciled count; stable valid comments are preserved only as `Partial_Candidates`.
- `BLOCKED`: visible login/security challenge, 403/429, denial or non-JSON challenge; checkpoint is saved and later work stops.

Counter model: all observed IDs minus only nodes whose `body` and `author` are both `[deleted]`. `[removed]` remains counted, and deleted IDs remain evidence rather than recovered text.

### Transport-specific evidence

- `cdp` uses `capture_mode: target_bound_json`; audit validates Listing, `after`, `morechildren`, continuation and `api/info` evidence.
- `selected-chrome-tab` uses `capture_mode: visible_dom`; evidence records DOM snapshots, collector-owned page identity, expansion actions, before/after IDs and remaining visible load controls. It never claims JSON-frontier coverage because the Codex extension evaluation sandbox does not expose same-origin `fetch`.
- A visible-DOM thread reaches `PASS` only when no load control remains, observed IDs and parents are consistent, and the visible platform counter reconciles. Otherwise it is `PARTIAL` and contributes no final comments.

### Selected-tab checkpoint

Each post checkpoint records `expanded_control_keys`, `collected_comment_ids`, `incomplete_frontier`, `expansion_actions`, `stable_rounds`, `owned_temp_tabs`, and `stop_reason`. Each action entry contains the clicked label/key, action kind, newly observed ID count, current total, and maximum depth. Reaching `max-expand-actions`, `max-comments-per-post`, or `thread-timeout` preserves the unfinished frontier and marks the thread `PARTIAL`.

## Manifest contract

The manifest also records round count; new queries/communities; trusted/partial yield; duplicate rate and marginal yield by round; saturation reason; conversation coverage; and counts by relevance tier, query family, and community.

## Conversation/query/community contracts

`conversation_map.json` contains `product_entities`, `user_problems`, `usage_contexts`, `decision_conversations`, and `community_language`. Only the last layer may claim Reddit language, and every observed expression carries evidence comment IDs.

Each query stores `query`, `query_family`, `generation_source`, `source_terms`, `evidence_comment_ids`, `discovery_round`, `priority`, `relevance_score`, `communities_searched`, `posts_found`, `qualified_posts`, `valid_comments`, `duplicate_comments`, and `marginal_yield`.

Each community row stores `subreddit`, `community_topic`, `product_relevance`, `problem_relevance`, `estimated_post_yield`, `actual_comment_yield`, `discovered_from`, and `status`. Examples are not treated as discovered facts.
