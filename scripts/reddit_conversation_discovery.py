#!/usr/bin/env python3
"""Offline conversation-map, iterative-query, relevance, and checkpoint helpers."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

VERSIONS = {
    "collector_version": "2.0.0",
    "query_plan_version": "2.0",
    "conversation_map_version": "1.0",
    "audit_version": "2.0",
}
QUERY_FAMILIES = (
    "product_entity", "category_solution", "problem_symptom", "usage_context",
    "decision_intent", "competitor", "natural_language_question",
)


def _clean(values):
    out, seen = [], set()
    for value in values or []:
        value = re.sub(r"\s+", " ", str(value)).strip(" ,;|-.")
        key = value.casefold()
        if value and key not in seen:
            seen.add(key); out.append(value)
    return out


def _terms(text, candidates):
    folded = str(text or "").casefold()
    return [term for term in _clean(candidates) if term.casefold() in folded]


def build_conversation_map(product, seller=None, evidence_comments=None):
    seller = seller or {}; evidence_comments = evidence_comments or []
    product_entities = {
        "brand": _clean([product.get("brand")]),
        "product_names": _clean([product.get("product_name"), product.get("title")]),
        "aliases": _clean(product.get("aliases", [])),
        "product_types": _clean(product.get("product_types", []) + [product.get("category")]),
        "ingredients": _clean(product.get("ingredients", []) + seller.get("ingredients", [])),
        "functions": _clean(product.get("functions", [])),
        "technical_names": _clean(product.get("technical_names", [])),
        "specifications": _clean(product.get("specifications", [])),
        "competitor_brands": _clean(product.get("competitor_brands", []) + seller.get("competitor_brands", [])),
        "competitor_products": _clean(product.get("competitor_products", []) + seller.get("competitor_products", [])),
    }
    user_problems = {
        "problems": _clean(product.get("problems", [])), "symptoms": _clean(product.get("symptoms", [])),
        "pain_points": _clean(product.get("pain_points", [])), "usage_barriers": _clean(product.get("usage_barriers", [])),
        "effect_dissatisfaction": _clean(product.get("effect_dissatisfaction", [])), "side_effects": _clean(product.get("side_effects", [])),
        "unmet_needs": _clean(product.get("unmet_needs", [])),
    }
    usage_contexts = {
        "user_types": _clean(product.get("user_types", [])), "pet_profiles": _clean(product.get("pet_profiles", [])),
        "life_stages": _clean(product.get("life_stages", [])), "daily_scenarios": _clean(product.get("contexts", [])),
        "health_conditions": _clean(product.get("health_conditions", [])), "perioperative": _clean(product.get("perioperative", [])),
        "combinations": _clean(product.get("combinations", [])),
    }
    decision_conversations = {
        "recommendation": ["recommend", "what helped"], "comparison": ["versus", "vs", "switch"],
        "effectiveness": ["does it work", "actually worked"], "value": ["worth it", "worth buying"],
        "time_to_effect": ["how long to work"], "safety": ["safe", "side effects"], "dosage": ["dose", "dosage"],
        "alternatives": ["alternative", "replacement"], "vet_advice": ["vet recommend", "veterinarian"],
        "retention": ["repurchase", "stopped using"],
    }
    observed = _clean([c.get("body") for c in evidence_comments if c.get("body")])
    community_language = {
        "observed_expressions": observed, "abbreviations": [], "symptom_phrases": [],
        "competitor_mentions": [], "community_terms": [], "question_patterns": [],
        "evidence_comment_ids": _clean([c.get("comment_id") for c in evidence_comments]),
    }
    return {
        "schema_version": "reddit_conversation_map_v1", **VERSIONS,
        "asin": product.get("asin"),
        "layers": {"product_entities": product_entities, "user_problems": user_problems,
                   "usage_contexts": usage_contexts, "decision_conversations": decision_conversations,
                   "community_language": community_language},
    }


def _flatten(layer):
    return _clean(x for values in layer.values() for x in (values if isinstance(values, list) else [values]))


def _query(query, family, source, terms, round_number, priority=50, evidence=None):
    return {"query": query, "query_family": family, "generation_source": source,
            "source_terms": _clean(terms), "evidence_comment_ids": _clean(evidence or []),
            "discovery_round": round_number, "priority": priority, "relevance_score": 0.8,
            "communities_searched": [], "posts_found": 0, "qualified_posts": 0,
            "valid_comments": 0, "duplicate_comments": 0, "marginal_yield": 0.0}


def generate_seed_queries(cmap, asin):
    layers = cmap["layers"]; e = layers["product_entities"]; p = layers["user_problems"]; u = layers["usage_contexts"]
    brand = (e["brand"] or [""])[0]; name = (e["aliases"] or e["product_names"] or [asin])[0]
    category = (e["product_types"] or e["ingredients"] or ["product"])[0]
    problem = (_flatten(p) or ["problem"])[0]; context = (_flatten(u) or ["daily use"])[0]
    competitor = (e["competitor_products"] or e["competitor_brands"] or [category + " alternative"])[0]
    values = [
        (f"{brand} {name}".strip(), "product_entity", [brand, name], 100),
        (category, "category_solution", [category], 85),
        (problem, "problem_symptom", [problem], 80),
        (context, "usage_context", [context], 75),
        (f"{name} reviews worth it", "decision_intent", [name], 90),
        (f"{name} vs {competitor}", "competitor", [name, competitor], 90),
        (f"what helped your {context} with {problem}", "natural_language_question", [context, problem], 88),
    ]
    return [_query(q, family, "amazon_sellersprite_seed", terms, 1, priority) for q, family, terms, priority in values]


def generate_next_round_queries(cmap, comments, round_number, existing_queries=None):
    existing = {str(x).casefold() for x in (existing_queries or [])}; out = []
    layers = cmap["layers"]; anchors = _flatten(layers["product_entities"]) + _flatten(layers["user_problems"]) + _flatten(layers["usage_contexts"])
    patterns = [
        (r"\b(struggl(?:e|ed|ing) to [a-z ]{2,35})", "problem_symptom"),
        (r"\b([A-Z][A-Za-z]+ (?:helped|worked|upset)[^.?!]{0,35})", "competitor"),
        (r"\b(what does your vet recommend[^?]{0,45})", "natural_language_question"),
        (r"\b(senior dog[^.?!]{0,45})", "usage_context"),
    ]
    for comment in comments:
        body = str(comment.get("body") or "")
        linked = bool(_terms(body, anchors))
        for pattern, family in patterns:
            for match in re.findall(pattern, body, re.I):
                phrase = _clean([match])[0]
                if len(phrase.split()) < 3 or phrase.casefold() in existing or (not linked and family != "natural_language_question"):
                    continue
                out.append(_query(phrase, family, "observed_reddit_comment", [phrase], round_number, 82, [comment.get("comment_id")]))
                existing.add(phrase.casefold())
    return out


def _all_relevance_terms(cmap):
    layers = cmap["layers"]
    direct = layers["product_entities"]["brand"] + layers["product_entities"]["product_names"] + layers["product_entities"]["aliases"]
    competitive = layers["product_entities"]["competitor_brands"] + layers["product_entities"]["competitor_products"] + layers["product_entities"]["ingredients"] + layers["product_entities"]["product_types"]
    unmet = _flatten(layers["user_problems"]) + _flatten(layers["usage_contexts"])
    return _clean(direct), _clean(competitive), _clean(unmet)


def score_post_relevance(post, cmap):
    text = " ".join(str(post.get(k) or "") for k in ("title", "body", "subreddit"))
    direct, competitive, unmet = _all_relevance_terms(cmap)
    hits = {"product": _terms(text, direct), "solution": _terms(text, competitive), "problem_context": _terms(text, unmet)}
    score = min(1.0, len(hits["product"]) * .45 + len(hits["solution"]) * .2 + len(hits["problem_context"]) * .2)
    generic_penalty = .25 if not any(hits.values()) else 0
    score = max(0.0, score - generic_penalty)
    return {"score": round(score, 3), "qualified": score >= .35, "evidence_terms": _clean(sum(hits.values(), [])), "components": hits}


def classify_comment_relevance(comment, cmap, context=None, min_score=.35):
    body = str(comment.get("body") or ""); direct, competitive, unmet = _all_relevance_terms(cmap)
    direct_hits, competitive_hits, unmet_hits = _terms(body, direct), _terms(body, competitive), _terms(body, unmet)
    if direct_hits: tier, hits, score = "direct_product", direct_hits, min(1.0, .65 + .08 * len(direct_hits))
    elif competitive_hits: tier, hits, score = "competitive_context", competitive_hits, min(.9, .5 + .07 * len(competitive_hits))
    elif unmet_hits: tier, hits, score = "unmet_need", unmet_hits, min(.8, .42 + .05 * len(unmet_hits))
    else: tier, hits, score = None, [], 0.0
    return {"relevance_tier": tier, "association_reason": f"matched {', '.join(hits)}" if hits else "no comment-level semantic evidence",
            "evidence_terms": hits, "relevance_score": round(score, 3), "comment_relevance_score": round(score, 3), "qualified": score >= min_score}


def _stable(row):
    return all(row.get(k) not in (None, "") for k in ("comment_id", "comment_url", "body", "parent_id")) and row.get("depth") is not None


def partition_comment_records(thread_status, comments, cmap, min_score=.35):
    trusted, partial, excluded = [], [], []
    for source in comments:
        row = dict(source); relevance = classify_comment_relevance(row, cmap, min_score=min_score); row.update(relevance)
        row["thread_audit_status"] = thread_status
        row["comment_record_status"] = "valid" if relevance["qualified"] and _stable(row) else "excluded"
        if thread_status == "PASS" and row["comment_record_status"] == "valid": trusted.append(row)
        elif thread_status == "PARTIAL" and row["comment_record_status"] == "valid": partial.append(row)
        else: excluded.append(row)
    return trusted, partial, excluded


def build_community_map(observed):
    grouped = {}
    for item in observed:
        name = str(item.get("subreddit") or "")
        if name.startswith("r/"): name = name[2:]
        if not name: continue
        entry = grouped.setdefault(name, {"subreddit":name, "community_topic":item.get("community_topic") or "observed Reddit discussion",
            "product_relevance":0, "problem_relevance":0, "estimated_post_yield":0, "actual_comment_yield":0,
            "discovered_from":[], "status":"observed"})
        entry["product_relevance"] = max(entry["product_relevance"], .8 if item.get("qualified") else .2)
        entry["problem_relevance"] = max(entry["problem_relevance"], .7 if item.get("qualified") else .2)
        entry["estimated_post_yield"] += 1; entry["actual_comment_yield"] += int(item.get("valid_comments") or 0)
        entry["discovered_from"] = _clean(entry["discovered_from"] + [item.get("discovered_from") or "search_result"])
    return list(grouped.values())


def evaluate_stop(rounds, trusted_total, target_comments, max_rounds, min_new, duplicate_stop, coverage=None):
    if trusted_total >= target_comments: return {"stop":True, "stop_reason":"target_comments_reached", "saturation_reason":None}
    if len(rounds) >= max_rounds: return {"stop":True, "stop_reason":"max_discovery_rounds_reached", "saturation_reason":"round_limit"}
    if len(rounds) >= 2 and all(r.get("new_trusted", 0) < min_new for r in rounds[-2:]):
        return {"stop":True, "stop_reason":"semantic_saturation_low_yield", "saturation_reason":"two_low_yield_rounds"}
    if len(rounds) >= 2 and all(r.get("duplicate_rate", 0) > duplicate_stop for r in rounds[-2:]):
        return {"stop":True, "stop_reason":"duplicate_rate_saturation", "saturation_reason":"two_high_duplicate_rounds"}
    if coverage and coverage.get("saturated"):
        return {"stop":True, "stop_reason":"conversation_map_saturated", "saturation_reason":coverage.get("reason")}
    return {"stop":False, "stop_reason":None, "saturation_reason":None}


def migrate_checkpoint(checkpoint):
    migrated = dict(checkpoint or {}); migrated.update(VERSIONS)
    migrated.setdefault("discovery_round", 1); migrated.setdefault("round_history", [])
    migrated.setdefault("query_metrics", {}); migrated.setdefault("community_map", [])
    migrated.setdefault("conversation_coverage", {}); migrated.setdefault("trusted_comments", migrated.get("comments", []))
    threads = migrated.get("selected_visible_threads", {})
    migrated["partial_reaudit_frontier"] = [key for key, value in threads.items() if (value.get("audit_status") or value.get("status")) == "PARTIAL"]
    return migrated


def partial_reaudit_queue(checkpoint, force=False):
    return list(checkpoint.get("partial_reaudit_frontier", [])) if force else []


def build_manifest_metrics(rounds, trusted, partial, stop):
    return {"discovery_rounds":len(rounds), "new_queries_by_round":[r.get("new_queries",0) for r in rounds],
        "new_communities_by_round":[r.get("new_communities",0) for r in rounds], "trusted_comments_by_round":[r.get("new_trusted",0) for r in rounds],
        "partial_candidates_by_round":[r.get("new_partial",0) for r in rounds], "duplicate_rate_by_round":[r.get("duplicate_rate",0) for r in rounds],
        "marginal_yield_by_round":[r.get("marginal_yield",0) for r in rounds], "trusted_comments":len(trusted),
        "partial_candidate_comments":len(partial), "saturation_reason":stop.get("saturation_reason"), "stop_reason":stop.get("stop_reason")}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--discovery-mode", choices=["iterative"], default="iterative")
    p.add_argument("--max-discovery-rounds", type=int, default=5)
    p.add_argument("--min-new-comments-per-round", type=int, default=10)
    p.add_argument("--duplicate-rate-stop", type=float, default=.85)
    p.add_argument("--max-posts-per-query", type=int, default=10)
    p.add_argument("--max-comments-per-post", type=int, default=500)
    p.add_argument("--target-comments", type=int, default=100)
    p.add_argument("--retry-partial", action="store_true")
    p.add_argument("--force-reaudit-partial", action="store_true")
    p.add_argument("--product-json", type=Path, help="Offline product metadata input")
    p.add_argument("--comments-json", type=Path, help="Offline observed comments input")
    p.add_argument("--output", type=Path, help="Write conversation map and query samples")
    args = p.parse_args(argv)
    if args.product_json:
        product = json.loads(args.product_json.read_text(encoding="utf-8")); comments = json.loads(args.comments_json.read_text(encoding="utf-8")) if args.comments_json else []
        cmap = build_conversation_map(product, evidence_comments=comments)
        result = {"conversation_map":cmap, "round_1":generate_seed_queries(cmap, product.get("asin")), "round_2":generate_next_round_queries(cmap, comments, 2)}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text + "\n", encoding="utf-8")
        else: print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
