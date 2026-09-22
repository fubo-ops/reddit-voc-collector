#!/usr/bin/env python3
"""Build an ASIN-based Reddit comment query plan."""
from __future__ import annotations
import argparse, csv, json, re, importlib.util
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
GROUPS = ("category_core", "brand_product", "use_scenario", "problem_pain", "recommend_compare_buy")

def _discovery_module():
    path=Path(__file__).with_name("reddit_conversation_discovery.py")
    spec=importlib.util.spec_from_file_location("reddit_conversation_discovery",path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def _tokens(value):
    if not value: return []
    return [x for x in re.split(r"[,\r\n]+", str(value)) if x.strip()]

def parse_asin_inputs(asin=None, asins=None, asin_file=None):
    values = _tokens(asin) + _tokens(asins)
    if asin_file:
        path = Path(asin_file)
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows=list(csv.reader(f))
            values += [cell for row in rows for cell in row if cell.strip().casefold() != "asin"]
        else: values += path.read_text(encoding="utf-8-sig").splitlines()
    out=[]; seen=set()
    for raw in values:
        value=str(raw).strip().upper()
        if not ASIN_RE.fullmatch(value): raise ValueError(f"Invalid ASIN: {raw!r}")
        if value not in seen: seen.add(value); out.append(value)
    if not out: raise ValueError("Provide --asin, --asins, or --asin-file")
    return out

def clean_keywords(values):
    out=[]; seen=set()
    for raw in values or []:
        value=re.sub(r"\s+", " ", str(raw)).strip(" ,;|-")
        if not value: continue
        key=value.casefold()
        if key not in seen: seen.add(key); out.append(value)
    return out

def reddit_search_url(query): return f"https://www.reddit.com/search/?q={quote(query)}&sort=relevance&t=all"

def build_keyword_groups(product, seller=None):
    seller=seller or {}; brand=product.get("brand",""); title=product.get("title",""); category=product.get("category","")
    names=product.get("common_names",[]) or []
    groups={
      "category_core": [category,*names,*seller.get("core_traffic",[])],
      "brand_product": [f"{brand} {n}" for n in names] + ([f"{brand} {title}"] if brand and title else []) + seller.get("long_tail",[]),
      "use_scenario": product.get("use_scenarios",[]) + seller.get("related",[]),
      "problem_pain": [f"{n} problem" for n in (names or [category]) if n] + [f"{n} not working" for n in (names or [category]) if n],
      "recommend_compare_buy": [f"{n} recommendation" for n in (names or [category]) if n] + [f"{n} vs" for n in (names or [category]) if n] + seller.get("competitor",[]),
    }
    return {k:clean_keywords(v) for k,v in groups.items()}

def build_plan(asins, products=None, seller_keywords=None, target_comments=100):
    products=products or {}; seller_keywords=seller_keywords or {}; queries=[]; keywords={}
    for asin in asins:
        product=products.get(asin,{"asin":asin,"common_names":[]})
        groups=build_keyword_groups(product,seller_keywords.get(asin,{})); keywords[asin]=groups
        candidates=clean_keywords([asin]+[x for group in GROUPS for x in groups[group]])
        for q in candidates:
            queries.append({"asin":asin,"query":q,"keyword_group":"asin" if q==asin else next((g for g in GROUPS if q in groups[g]),"category_core"),"search_url":reddit_search_url(q)})
    return {"schema_version":"reddit_comment_query_plan_v1","source":"reddit","target_comments":target_comments,"created_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"asins":asins,"keywords":keywords,"queries":queries}

def build_iterative_plan(asins, products=None, seller_keywords=None, target_comments=100):
    discovery=_discovery_module(); products=products or {}; seller_keywords=seller_keywords or {}; maps={}; queries=[]
    for asin in asins:
        product={"asin":asin,**products.get(asin,{})}; cmap=discovery.build_conversation_map(product,seller_keywords.get(asin,{})); maps[asin]=cmap
        queries.extend({"asin":asin,**q,"search_url":reddit_search_url(q["query"])} for q in discovery.generate_seed_queries(cmap,asin))
    return {"schema_version":"reddit_conversation_query_plan_v2","query_plan_version":"2.0","discovery_mode":"iterative","target_comments":target_comments,"created_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"asins":asins,"conversation_maps":maps,"queries":queries}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asin"); p.add_argument("--asins"); p.add_argument("--asin-file",type=Path); p.add_argument("--target-comments",type=int,default=100)
    p.add_argument("--metadata-json",type=Path,help="Optional offline Amazon/SellerSprite metadata JSON."); p.add_argument("--output",type=Path)
    p.add_argument("--discovery-mode",choices=["static","iterative"],default="iterative")
    a=p.parse_args()
    try: asins=parse_asin_inputs(a.asin,a.asins,a.asin_file)
    except ValueError as e: p.error(str(e))
    metadata=json.loads(a.metadata_json.read_text(encoding="utf-8")) if a.metadata_json else {}
    builder=build_iterative_plan if a.discovery_mode=="iterative" else build_plan
    plan=builder(asins,metadata.get("products"),metadata.get("seller_keywords"),a.target_comments)
    text=json.dumps(plan,ensure_ascii=False,indent=2)
    if a.output: a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(text+"\n",encoding="utf-8")
    else: print(text)
    return 0
if __name__=="__main__": raise SystemExit(main())
