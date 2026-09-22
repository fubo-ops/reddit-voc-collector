#!/usr/bin/env python3
"""Normalize, filter and globally deduplicate Reddit comment JSONL."""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
FIELDS=("schema_version","platform","asin","matched_asins","query","matched_keywords","subreddit","post_id","post_title","post_url","comment_id","parent_id","depth","author","body","score","created_at","comment_url","collected_at","relevance_tier","association_reason","evidence_terms","relevance_score","comment_relevance_score","discovery_round","query_family","source_query","community_source","comment_record_status","thread_audit_status","thread_evidence_path")
def utc_now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def _list(v): return v if isinstance(v,list) else ([] if v in (None,"") else [v])
def normalize_comment(row,collected_at=None):
    matched=[]
    for value in _list(row.get("matched_asins"))+_list(row.get("asin")):
        value=str(value).upper()
        if value and value not in matched: matched.append(value)
    data={"schema_version":"reddit_comment_v2","platform":"reddit","asin":str(row.get("asin") or (matched[0] if matched else "")).upper(),"matched_asins":matched,"query":row.get("query"),"matched_keywords":list(dict.fromkeys(_list(row.get("matched_keywords")))),"subreddit":row.get("subreddit"),"post_id":row.get("post_id"),"post_title":row.get("post_title"),"post_url":row.get("post_url"),"comment_id":str(row.get("comment_id") or row.get("id") or ""),"parent_id":row.get("parent_id"),"depth":int(row.get("depth") or 0),"author":row.get("author"),"body":str(row.get("body") or row.get("text") or "").strip(),"score":row.get("score"),"created_at":row.get("created_at"),"comment_url":row.get("comment_url") or row.get("url"),"collected_at":row.get("collected_at") or collected_at or utc_now(),"relevance_tier":row.get("relevance_tier"),"association_reason":row.get("association_reason"),"evidence_terms":list(dict.fromkeys(_list(row.get("evidence_terms")))),"relevance_score":row.get("relevance_score"),"comment_relevance_score":row.get("comment_relevance_score",row.get("relevance_score")),"discovery_round":row.get("discovery_round",1),"query_family":row.get("query_family"),"source_query":row.get("source_query") or row.get("query"),"community_source":row.get("community_source") or row.get("subreddit"),"comment_record_status":row.get("comment_record_status"),"thread_audit_status":row.get("thread_audit_status"),"thread_evidence_path":row.get("thread_evidence_path")}
    return {k:data[k] for k in FIELDS}
def flatten_comment_tree(tree,context=None):
    context=dict(context or {}); out=[]
    def walk(nodes,parent=None,depth=0):
        for node in nodes or []:
            row={**context,**node,"comment_id":node.get("comment_id") or node.get("id"),"parent_id":node.get("parent_id") or parent or context.get("post_id"),"depth":depth}; row.pop("replies",None); out.append(row)
            walk(node.get("replies",[]),row["comment_id"],depth+1)
    walk(tree); return out
BOT_RE=re.compile(r"\bi am a bot\b.*\b(action|performed|automatically)\b",re.I|re.S)
def is_valid_comment(row):
    body=str(row.get("body") or row.get("text") or "").strip()
    return bool(body and body.casefold() not in {"[deleted]","[removed]","deleted","removed"} and not BOT_RE.search(body))
def dedupe_comments(rows):
    kept=[]; by_id={}; by_url={}; duplicates=0
    for source in rows:
        row=normalize_comment(source); key=row["comment_id"].casefold(); url=(row["comment_url"] or "").rstrip("/").casefold()
        existing=by_id.get(key) if key else None
        if existing is None and url: existing=by_url.get(url)
        if existing is not None:
            duplicates+=1
            existing["matched_asins"]=list(dict.fromkeys(existing["matched_asins"]+row["matched_asins"]))
            existing["matched_keywords"]=list(dict.fromkeys(existing["matched_keywords"]+row["matched_keywords"]))
            continue
        kept.append(row)
        if key: by_id[key]=row
        if url: by_url[url]=row
    return kept,{"deduplicated":duplicates}
def prepare_comments(rows):
    valid=[r for r in rows if is_valid_comment(r)]; kept,stats=dedupe_comments(valid); stats["filtered"]=len(rows)-len(valid); return kept,stats
def target_comments_reached(rows,target): return len(prepare_comments(rows)[0])>=target
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("input",type=Path); p.add_argument("output",type=Path); p.add_argument("--target-comments",type=int)
    a=p.parse_args(); rows=[]
    for n,line in enumerate(a.input.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            item=json.loads(line); rows.extend(flatten_comment_tree(item["comments"],item) if isinstance(item.get("comments"),list) else [item])
    kept,stats=prepare_comments(rows)
    if a.target_comments: kept=kept[:a.target_comments]
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in kept),encoding="utf-8")
    print(json.dumps({"written":len(kept),**stats,"output":str(a.output.resolve())},ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
