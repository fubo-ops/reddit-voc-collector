# Reddit comment records — collector 2.1.0

Every row is one public comment, never a post body. Post ID/title/URL/subreddit are provenance only. New OpenCLI records use `schema_version: reddit_comment_v3`; prior v1/v2 records remain readable and are not rewritten merely to migrate.

Required fields: schema_version, platform, asin, matched_asins, query, matched_keywords, subreddit, post_id, post_title, post_url, comment_id, parent_id, depth, author, body, score, created_at, comment_url, collected_at, audit_status, semantic_relevance, comment_gate. `quality_tier` distinguishes trusted_PASS from validated_partial_count_mismatch where applicable.

`comment_gate` stores version, accepted/status, quality_mode, thread_status, reasons, semantic_relevance, semantic_evidence, matched_asins and checked_at. Its PASS is a **record admission decision**, not a claim that a PARTIAL thread passed completeness. Normalization retains both new fields and legacy relevance/thread fields.

## Body, identity and tree

Blank/[deleted]/[removed]/bot-notice bodies are excluded; a visible body with deleted author is retained. Deduplicate globally by ID and canonical URL and merge matched ASINs/keywords. URLs must identify the same Reddit post and comment. Depth 0 has the post as parent; every deeper level has the actual parent comment. Validate the whole ancestry for missing nodes, cycles and depth mismatch, including observed tombstone nodes. Preserve positive/neutral/negative comments without sentiment filtering.

## Tiers and quality

- direct_product: explicit brand/model plus independent product context in the comment; not proof of purchase.
- competitive_context: observed/supplied competitor entity tied to this product category.
- unmet_need: independently evidenced relevant category usage/problem.

A relevant title/query alone is insufficient. Product rules are generated from current-ASIN observed metadata, not a dog-bowl list. Missing or ambiguous metadata should yield conservative exclusions or a metadata-required stop.

Strict counts only eligible PASS rows. Explicit relevance counts those plus independently gated PARTIAL rows whose sole failure is comment_count_not_reconciled, with no orphan/frontier/blocked metadata. Never relax identity, body, relevance, graph consistency, unfinished controls, load or access failures. Unsafe PARTIAL and BLOCKED cannot enter counted sheets. Preserve audit_status PARTIAL for admitted partials. Re-audit promotion transfers one row to Trusted without duplicate count; new unsafe audit quarantines prior partials as candidates.

## Checkpoint and evidence

Checkpoint stores asins, target_comments, quality_mode, product_profile, queries, posts, trusted_comments, validated_partial_comments, partial_candidates, query_metrics, round_history, run_counts, preflight status, stop detail and owned-tab cleanup. The frontier stores expanded_control_keys, comments, observed_nodes, collected_comment_ids, incomplete_frontier, expansion_actions and stable rounds. Action ledgers include clicked label/key, new IDs, current total and max depth.

Per post: evidence/POST_ID/comments.jsonl, audit.json, frontier.json, comment_gates.json; recovery/revalidation adds its own gate ledger. Root audit.json mirrors checkpoint post audits. PASS means the **visible** frontier is closed and platform count reconciles; it does not prove access to hidden/deleted/private data or all Reddit comments. PARTIAL retains explicit failure codes; visible restrictions become BLOCKED and stop the run.

## Manifest, Excel and delivery

Manifest records input ASINs/products/access sources, quality mode, global effective/trusted/validated/candidate counts, PASS/PARTIAL/BLOCKED counts, stop reason/detail, doctor/preflight, checkpoint path, owned-tab cleanup, run_counts, workbooks, validation and delivery hashes. Reused evidence, preserved baseline and fresh discovery are distinct counts.

Relevance sheets: Comments (counted union), Trusted_Comments (PASS only), Validated_Partial_Comments (eligible PARTIAL only), Partial_Candidates (uncounted), Conversation_Map, Query_Performance, Community_Map, Run_Summary. Strict omits the combined and validated-partial sheets. Multi-ASIN sheets filter by matched_asins; their row-count sum may exceed the globally deduplicated target.

Excel projection preserves IDs, body, identity URL and audit grade with safe text formatting, wrapped bodies, frozen/filter headers and control-character/formula-injection handling. Validator checks these against checkpoint and evidence, including consistency of JSONL, manifest and audit. Only actual validation exit 0 permits success/delivery.

Final names: ASIN_reddit评论_COUNT条_YYYYMMDDTHHMMSSZ.xlsx in D:\Project\2026\SKILL\reddit评论采集 (configurable). No historical file overwrite. Delivery SHA256 must match the internal workbook; record delivery_excel_path/deliveries. Internal checkpoint, JSONL and evidence remain in the original run directory.

Regression: B0HHNB798Q = 438 PASS + 362 validated PARTIAL = 800; 312 reused plus 50 fresh. This is a reporting invariant, not permission to modify historical files.
