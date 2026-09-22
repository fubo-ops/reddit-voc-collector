"""Independent evidence verifier: does NOT import collector or trust its summary.
Recompute all counts and frontier requirements directly from public raw responses.
Exit 0: all requested acceptance gates pass; 2: partial; 3: blocked.
"""

import collections
import hashlib
import json
import pathlib
from urllib.parse import urlsplit, parse_qs


def safe_file(root, relative):
    # Native Windows Path objects stringify with backslashes; normalize objects,
    # while rejecting untrusted string drive/UNC paths before any filesystem IO.
    text = relative.as_posix() if isinstance(relative, pathlib.PurePath) else str(relative)
    path = pathlib.Path(text)
    if (
        path.is_absolute()
        or "\\" in text
        or ":" in text
        or ".." in path.parts
        or pathlib.PureWindowsPath(text).drive
    ):
        raise ValueError("unsafe_evidence_path")
    candidate = (root / path).resolve()
    if root.resolve() not in candidate.parents or (root / path).is_symlink():
        raise ValueError("unsafe_evidence_path")
    return candidate


def audit(root):
    root = pathlib.Path(root).resolve()
    failures = []
    request_evidence = []
    requests = json.loads(safe_file(root, "requests.json").read_text(encoding="utf-8"))
    records = {}
    occurrences = collections.Counter()
    provenance = collections.defaultdict(list)
    wanted = set()
    open_frontier = set()
    listing_ids = set()
    declared = set()
    post_ids = set()
    blocked = False
    more_count = 0
    empty_count = 0
    after_count = 0
    listings = 0
    tracked_files = set()

    def visit(v, source, parent=None):
        nonlocal more_count, empty_count, after_count, listings
        if isinstance(v, list):
            for x in v:
                visit(x, source, parent)
            return
        if not isinstance(v, dict):
            return
        kind = v.get("kind")
        d = v.get("data", {})
        if kind == "t3":
            post_ids.add(d.get("id"))
            declared.add(d.get("num_comments"))
            return
        if kind == "Listing":
            listings += 1
            if "after" not in d or "before" not in d or not isinstance(d.get("children"), list):
                failures.append("incomplete_listing_schema")
            if d.get("after"):
                after_count += 1
                open_frontier.add(("after", parent, d["after"]))
            for c in d.get("children", []):
                visit(c, source, parent)
            return
        if kind == "t1":
            cid = d.get("id")
            occurrences[cid] += 1
            provenance[cid].append(source)
            if not isinstance(d.get("body"), str) or not isinstance(d.get("parent_id"), str):
                failures.append("invalid_comment_fields")
            if not cid or d.get("name") != "t1_" + str(cid):
                failures.append("invalid_comment_id")
            if cid in records and any(
                records[cid].get(k) != d.get(k) for k in ("body", "parent_id", "link_id", "author")
            ):
                failures.append("conflicting_raw_id:" + str(cid))
            records[cid] = {k: x for k, x in d.items() if k != "replies"}
            if "/api/info.json" not in source:
                listing_ids.add(cid)
            visit(d.get("replies"), source, "t1_" + str(cid))
            return
        if kind == "more":
            more_count += 1
            if not isinstance(d.get("children"), list):
                failures.append("missing_more_children")
            wanted.update(d.get("children") or [])
            if not d.get("children"):
                empty_count += 1
                open_frontier.add(("continue", d.get("parent_id"), None))
            return
        if "errors" in v:
            if v["errors"]:
                failures.append("api_errors:" + str(v["errors"]))
            if not isinstance(v.get("things"), list):
                failures.append("missing_things")
            visit(v.get("things"), source, parent)
            return
        failures.append("unknown_thing_kind")

    for index, r in enumerate(requests):
        url = r.get("request_url", "")
        q = parse_qs(urlsplit(url).query)
        inferred_pid = urlsplit(url).path.split("/comments/")[-1].split("/")[0] if "/comments/" in url else None
        if inferred_pid and inferred_pid.endswith(".json"):
            inferred_pid = inferred_pid[:-5]
        if inferred_pid:
            post_ids.add(inferred_pid)
        parent = (
            "t1_" + q["comment"][0]
            if q.get("comment")
            else ("t3_" + inferred_pid if inferred_pid else None)
        )
        continuation = ("continue", parent, None)
        needs_subtree_progress = (
            not q.get("after") and q.get("comment") and continuation in open_frontier
        )
        if q.get("after"):
            open_frontier.discard(("after", parent, q["after"][0]))
        elif needs_subtree_progress:
            open_frontier.discard(continuation)
        if r.get("state") != "done" or r.get("http_status") != 200:
            failures.append("request_not_done:" + str(r.get("state")))
            if r.get("http_status") in (401, 403, 429) or r.get("state") in ("blocked", "non_json"):
                blocked = True
        bp = pathlib.Path(r.get("body_path", "missing"))
        try:
            fp = safe_file(root, bp)
            if not bp.parts or bp.parts[0] != "raw":
                raise ValueError("unsafe_evidence_path")
        except ValueError:
            failures.append("unsafe_evidence_path")
            continue
        if not fp.is_file():
            failures.append("missing_raw:" + str(bp))
            continue
        tracked_files.add(fp.resolve())
        body = fp.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        hash_ok = digest == r.get("sha256")
        if not hash_ok:
            failures.append("raw_hash_mismatch:" + str(bp))
        payload = json.loads(body)
        if "/comments/" in url:
            valid = (
                isinstance(payload, list)
                and len(payload) == 2
                and all(isinstance(x, dict) and x.get("kind") == "Listing" for x in payload)
            )
            if not valid:
                failures.append("malformed_thread_envelope")
        before_ids = set(records)
        # Every thread listing must carry the exact t3 identity; info/morechildren t1s checked below.
        if isinstance(payload, list) and len(payload) == 2:
            visit(payload[0], url, parent)
            visit(payload[1], url, parent)
        else:
            visit(payload, url, parent)
        if needs_subtree_progress:
            progressed = False
            for cid in set(records) - before_ids:
                ancestor = records[cid].get("parent_id")
                seen = set()
                while (
                    isinstance(ancestor, str)
                    and ancestor.startswith("t1_")
                    and ancestor not in seen
                ):
                    if ancestor == parent:
                        progressed = True
                        break
                    seen.add(ancestor)
                    ancestor = records.get(ancestor[3:], {}).get("parent_id")
            if not progressed:
                failures.append("continue_no_subtree_progress:" + str(parent))
                open_frontier.add(continuation)
        request_evidence.append(
            {
                "index": index + 1,
                "label": r.get("label"),
                "url": url,
                "sha256": digest,
                "sha256_matches_ledger": hash_ok,
                "file": str(fp),
                "fetched_at": r.get("fetched_at"),
            }
        )
    if len(post_ids) != 1:
        failures.append("post_identity_not_unique")
    pid = next(iter(post_ids)) if len(post_ids) == 1 else None
    link = "t3_" + str(pid)
    for cid, c in records.items():
        if c.get("link_id") != link:
            failures.append("foreign_comment:" + str(cid))
    rows = [
        json.loads(s)
        for s in safe_file(root, "comments.jsonl").read_text(encoding="utf-8").splitlines()
        if s.strip()
    ]
    exports = collections.Counter(r["id"] for r in rows)
    tombs = (
        json.loads(safe_file(root, "tombstones.json").read_text(encoding="utf-8"))
        if (root / "tombstones.json").exists()
        else []
    )
    tomb_ids = {t["id"] for t in tombs}
    combined = set(exports) | tomb_ids
    if any(n != 1 for n in exports.values()):
        failures.append("duplicate_export_id")
    if combined != set(records):
        failures.append("raw_export_id_set_mismatch")
    for row in rows + tombs:
        rawrow = records.get(row["id"], {})
        if any(
            row.get(k) != rawrow.get(k) for k in ("body", "parent_id", "link_id", "name", "author")
        ):
            failures.append("raw_export_field_mismatch:" + row["id"])
    if wanted - set(records):
        failures.append("unresolved_more_ids")
    if open_frontier:
        failures.append("unconsumed_continuations")
    if len(declared) != 1:
        failures.append("counter_missing_or_changed")
    orphans = []
    cycles = []
    for cid, c in records.items():
        parent = c.get("parent_id")
        if parent != link and (
            not isinstance(parent, str) or not parent.startswith("t1_") or parent[3:] not in records
        ):
            orphans.append(cid)
        seen = set()
        pointer = cid
        while pointer in records:
            if pointer in seen:
                cycles.append(cid)
                break
            seen.add(pointer)
            par = records[pointer].get("parent_id", "")
            pointer = par[3:] if par.startswith("t1_") else None
    if orphans:
        failures.append("orphans")
    if cycles:
        failures.append("cycles")
    info_only_readable = sorted(
        cid
        for cid, c in records.items()
        if cid not in listing_ids and c.get("body") not in ("[removed]", "[deleted]")
    )
    if info_only_readable:
        failures.append("info_only_readable_reply_coverage_unknown")
    unledgered = [
        str(f) for f in sorted((root / "raw").glob("*.json")) if f.resolve() not in tracked_files
    ]
    if unledgered:
        failures.append("unledgered_raw_files")
    tombset = {cid for cid, c in records.items() if c.get("body") in ("[removed]", "[deleted]")}
    readable = set(records) - tombset
    roots = {cid for cid, c in records.items() if c.get("parent_id") == link}
    den = next(iter(declared)) if len(declared) == 1 else None
    # Independent raw-node classification; do not consume collector summaries.
    deleted_ids = {
        cid
        for cid, node in records.items()
        if node.get("body") == "[deleted]" and node.get("author") == "[deleted]"
    }
    counter_nodes = len(records) - len(deleted_ids)
    count_match = type(den) is int and den == counter_nodes
    status = "BLOCKED" if blocked else ("PASS" if not failures and count_match else "PARTIAL")
    return {
        "status": status,
        "source_directory": str(root),
        "post_id": pid,
        "declared_num_comments": den,
        "unique_ids": len(records),
        "top_level_ids": len(roots),
        "reply_ids": len(records) - len(roots),
        "readable_bodies": len(readable),
        "readable_root_bodies": len(readable & roots),
        "readable_reply_bodies": len(readable - roots),
        "tombstones": {
            "total": len(tombset),
            "removed": sum(records[i]["body"] == "[removed]" for i in tombset),
            "deleted": sum(records[i]["body"] == "[deleted]" for i in tombset),
            "ids": sorted(tombset),
        },
        "frontier_status": "EXHAUSTED_PUBLIC_ID_FRONTIER" if not failures else "PARTIAL",
        "platform_count_status": "EXACT_NONDELETED_NODES" if count_match else "UNRECONCILED",
        "platform_counter_nodes": counter_nodes,
        "deleted_placeholder_ids": sorted(deleted_ids),
        "platform_counter_delta": counter_nodes - den if type(den) is int else None,
        "counter_semantics_source": "Archived official POST_del; model validated against this capture, not a current-internals guarantee",
        "count_delta": len(records) - den if isinstance(den, int) else None,
        "failures": sorted(set(failures)),
        "orphans": orphans,
        "cycles": cycles,
        "remaining_child_ids": sorted(wanted - set(records)),
        "remaining_continuations": sorted(open_frontier, key=str),
        "info_only_readable": info_only_readable,
        "raw_duplicate_occurrences": sum(occurrences.values()) - len(occurrences),
        "raw_ids": sorted(records),
        "export_ids": sorted(exports),
        "export_union_tombstone_ids": sorted(combined),
        "readable_ids": sorted(readable),
        "root_ids": sorted(roots),
        "id_set_sha256": hashlib.sha256(("\n".join(sorted(records)) + "\n").encode()).hexdigest(),
        "request_count": len(requests),
        "more_nodes_observed": more_count,
        "empty_children_more_observed": empty_count,
        "listing_after_observed": after_count,
        "listings_observed": listings,
        "request_evidence": request_evidence,
        "unledgered_raw": unledgered,
        "id_provenance": dict(provenance),
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Independently audit one Reddit thread evidence directory.")
    parser.add_argument("evidence_dir", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        report = audit(args.evidence_dir)
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        report = {"status": "PARTIAL", "failures": ["audit_execution_error"], "error_type": type(exc).__name__}
    output = args.output or (args.evidence_dir / "audit.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit({"PASS": 0, "PARTIAL": 2, "BLOCKED": 3}[report["status"]])
