#!/usr/bin/env python3
"""Loopback receiver for collector-owned Reddit tabs marked with a short-lived RUN_ID."""
from __future__ import annotations
import argparse, hashlib, hmac, json, re, secrets, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

LISTEN_HOST="127.0.0.1"; LISTEN_PORT=43127; MAX_BODY_BYTES=5*1024*1024; MAX_CLOCK_SKEW=60
FIXED_EXTENSION_ID="edpfinibjpbkdnognnhealnfepkeopem"; FIXED_ORIGIN="chrome-extension://"+FIXED_EXTENSION_ID
RUN_ID_RE=re.compile(r"^[A-Za-z0-9_-]{24,64}$")
class SecurityError(ValueError): pass

def strip_fragment(value):
    try:
        u=urlsplit(value); return urlunsplit((u.scheme,u.netloc,u.path,u.query,""))
    except Exception: return ""
def exact_extension_origin(extension_id,origin): return extension_id==FIXED_EXTENSION_ID and origin==FIXED_ORIGIN
def extension_id_from_origin(origin): return FIXED_EXTENSION_ID if origin==FIXED_ORIGIN else None
def allowed_host_header(value,port=LISTEN_PORT): return value==f"127.0.0.1:{port}"
def cors_preflight_allowed(origin,method,requested_headers):
    allowed={"content-type","x-extension-id","x-extension-origin","x-run-id","x-session-id","x-timestamp","x-nonce","x-signature"}
    requested={x.strip().lower() for x in requested_headers.split(",") if x.strip()}
    return origin==FIXED_ORIGIN and method.upper()=="POST" and requested.issubset(allowed)
def allowed_reddit_page(value):
    try:
        u=urlsplit(value); return u.scheme=="https" and u.hostname=="www.reddit.com"
    except Exception: return False
def allowed_reddit_thread(value):
    try:
        u=urlsplit(value); return allowed_reddit_page(value) and bool(re.match(r"^/r/[^/]+/comments/[^/]+/",u.path,re.I))
    except Exception: return False
def post_id_from_url(value):
    try:
        parts=[x for x in urlsplit(value).path.split("/") if x]; i=parts.index("comments"); return parts[i+1]
    except Exception: return ""

class BridgeState:
    def __init__(self,run_id,output_dir=None,now=time.time,ttl_seconds=1800):
        if not RUN_ID_RE.fullmatch(str(run_id or "")): raise ValueError("invalid RUN_ID")
        self.run_id=str(run_id); self.output_dir=Path(output_dir) if output_dir else None; self.now=now; self.expires_at=now()+ttl_seconds; self.active=True
        self.sessions={}; self.nonces=set(); self.checkpoints={}; self.posts={}; self.root_urls={}
        if self.output_dir: self.output_dir.mkdir(parents=True,exist_ok=True)
    def _live(self):
        if not self.active: raise SecurityError("bridge_stopped")
        if self.now()>self.expires_at: raise SecurityError("run_expired")
    def authorize(self,run_id,extension_id,origin,page_url):
        self._live()
        if not hmac.compare_digest(str(run_id),self.run_id): raise SecurityError("invalid_RUN_ID")
        if not exact_extension_origin(extension_id,origin): raise SecurityError("invalid_extension_origin")
        page_url=strip_fragment(page_url)
        if not allowed_reddit_page(page_url): raise SecurityError("invalid_reddit_page")
        post_id=post_id_from_url(page_url)
        if post_id and post_id not in self.root_urls: self.root_urls[post_id]=page_url
        session_id=secrets.token_urlsafe(24); session_key=secrets.token_urlsafe(32); expires=min(self.expires_at,self.now()+900)
        self.sessions[session_id]={"extension_id":extension_id,"run_id":self.run_id,"session_key":session_key,"expires_at":expires}
        return{"session_id":session_id,"session_key":session_key,"expires_in":max(0,int(expires-self.now())),"checkpoint":{"posts":self.checkpoints},"root_url":self.root_urls.get(post_id)}
    def verify_signed(self,path,raw,headers):
        if len(raw)>MAX_BODY_BYTES: raise SecurityError("request_body_too_large")
        self._live(); extension_id=headers.get("X-Extension-ID",""); origin=headers.get("Origin") or headers.get("X-Extension-Origin","")
        if not exact_extension_origin(extension_id,origin): raise SecurityError("invalid_extension_origin")
        run_id=headers.get("X-Run-ID","")
        if not hmac.compare_digest(run_id,self.run_id): raise SecurityError("invalid_RUN_ID")
        session=self.sessions.get(headers.get("X-Session-ID",""))
        if not session or session["expires_at"]<self.now() or session["run_id"]!=run_id or session["extension_id"]!=extension_id: raise SecurityError("expired_or_invalid_session")
        try: timestamp=int(headers.get("X-Timestamp",""))
        except Exception: raise SecurityError("invalid_timestamp")
        if abs(self.now()-timestamp)>MAX_CLOCK_SKEW: raise SecurityError("stale_timestamp")
        nonce=headers.get("X-Nonce","")
        if len(nonce)<2 or nonce in self.nonces: raise SecurityError("invalid_or_replayed_nonce")
        digest=hashlib.sha256(raw).hexdigest(); canonical=f"POST\n{path}\n{run_id}\n{timestamp}\n{nonce}\n{digest}".encode()
        expected=hmac.new(session["session_key"].encode(),canonical,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,headers.get("X-Signature","")): raise SecurityError("invalid_signature")
        try: payload=json.loads(raw.decode("utf-8"))
        except Exception: raise SecurityError("invalid_JSON")
        self.nonces.add(nonce); return payload
    def _write_json(self,name,value):
        if not self.output_dir:return
        target=self.output_dir/name; temp=target.with_suffix(target.suffix+".tmp"); temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8"); temp.replace(target)
    def accept_checkpoint(self,payload):
        self._live(); post_id=str(payload.get("post_id") or "")
        if not post_id: raise SecurityError("checkpoint_missing_post_id")
        clean={k:v for k,v in payload.items() if k!="run_id"}; clean["page_url"]=strip_fragment(clean.get("page_url",""))
        for key in ("expanded_control_keys","collected_comment_ids","incomplete_frontier","expansion_actions"):
            if key in clean and not isinstance(clean[key],list): raise SecurityError("invalid_checkpoint")
        self.checkpoints[post_id]=clean; self._write_json("checkpoint.json",{"schema_version":"reddit_voc_checkpoint_v3","posts":self.checkpoints}); return{"status":"checkpoint_saved","post_id":post_id}
    def _validate_comment(self,row):
        cid=str(row.get("comment_id") or ""); body=str(row.get("body") or "").strip(); url=strip_fragment(row.get("comment_url", ""))
        if not cid or not body or body.lower() in {"[deleted]","[removed]"} or not allowed_reddit_thread(url): raise SecurityError("invalid_comment_record")
        clean=dict(row); clean["comment_id"]=cid; clean["comment_url"]=url; return clean
    def accept_capture(self,payload):
        self._live(); page_url=strip_fragment(payload.get("page_url",""))
        if not allowed_reddit_thread(page_url): raise SecurityError("invalid_capture_page")
        post_id=str(payload.get("post_id") or post_id_from_url(page_url)); comments=payload.get("comments")
        if not post_id or not isinstance(comments,list) or len(comments)>500: raise SecurityError("invalid_capture_batch")
        post=self.posts.setdefault(post_id,{"comments":{},"urls":set(),"raw_count":0,"filtered_count":0,"duplicate_count":0,"platform_comment_count":0,"final_scanned":0,"blocked":False,"final":False})
        stats=payload.get("capture_stats") or {}; post["raw_count"]+=int(stats.get("scanned") or len(comments)); post["filtered_count"]+=sum(int(stats.get(k) or 0) for k in ("filtered_blank","filtered_deleted_removed","filtered_bot")); post["duplicate_count"]+=int(stats.get("duplicates") or 0)
        for row in comments:
            clean=self._validate_comment(row); cid=clean["comment_id"]; url=clean["comment_url"].rstrip("/")
            if cid in post["comments"] or url in post["urls"]: post["duplicate_count"]+=1; continue
            post["comments"][cid]=clean; post["urls"].add(url)
        post["platform_comment_count"]=max(post["platform_comment_count"],int(payload.get("platform_comment_count") or 0))
        if payload.get("final"): post["final_scanned"]=int(stats.get("scanned") or len(comments)); post["final"]=True
        if (payload.get("audit") or {}).get("status")=="BLOCKED": post["blocked"]=True
        clean_payload={k:v for k,v in payload.items() if k!="run_id"}; clean_payload["page_url"]=page_url
        if self.output_dir:
            with (self.output_dir/"captures.jsonl").open("a",encoding="utf-8") as f:f.write(json.dumps(clean_payload,ensure_ascii=False,separators=(",",":"))+"\n")
        audit=self._audit(post_id); self._write_json("audit.json",{"schema_version":"reddit_voc_audit_v3","posts":{pid:self._audit(pid) for pid in self.posts}})
        return{"status":"accepted","comments_received":len(comments),"unique_comments":len(post["comments"]),"audit_status":audit["status"]}
    def _audit(self,post_id,final=None):
        post=self.posts[post_id]; checkpoint=self.checkpoints.get(post_id,{}) ; rows=list(post["comments"].values()); ids=set(post["comments"]); orphans=[]
        if final is None: final=post.get("final",False)
        for row in rows:
            parent=str(row.get("parent_id") or ""); parent=parent[3:] if parent.startswith(("t1_","t3_")) else parent
            if parent and parent!=post_id and parent not in ids: orphans.append(row["comment_id"])
        remaining=len(checkpoint.get("incomplete_frontier") or []); stable=int(checkpoint.get("stable_rounds") or 0); failures=[]
        if post["blocked"]: status="BLOCKED"; failures.append("visible_access_block")
        else:
            if not final: failures.append("capture_not_final")
            if remaining: failures.append("unprocessed_expand_controls")
            if stable<2: failures.append("two_stable_rounds_not_reached")
            if orphans: failures.append("orphan_parent_ids")
            if post["platform_comment_count"] and post["final_scanned"]!=post["platform_comment_count"]: failures.append("comment_count_not_reconciled")
            status="PARTIAL" if failures else "PASS"
        return{"status":status,"reasons":failures,"raw_comment_count":post["raw_count"],"filtered_count":post["filtered_count"],"duplicate_count":post["duplicate_count"],"unique_comment_count":len(rows),"max_depth":max([int(x.get("depth") or 0) for x in rows] or [0]),"orphan_parent_id_count":len(orphans),"orphan_comment_ids":orphans,"platform_comment_count":post["platform_comment_count"],"remaining_expand_controls":remaining,"expanded_actions":len(checkpoint.get("expansion_actions") or [])}
    def stop(self): self.active=False; self.sessions.clear()

class Handler(BaseHTTPRequestHandler):
    server_version="RedditVOCBridge/1.0-rc1"; state=None
    def log_message(self,fmt,*args): pass
    def reply(self,status,value,cors_origin=None):
        data=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store")
        if cors_origin==FIXED_ORIGIN:self.send_header("Access-Control-Allow-Origin",FIXED_ORIGIN);self.send_header("Vary","Origin")
        self.end_headers(); self.wfile.write(data)
    def do_OPTIONS(self):
        origin=self.headers.get("Origin",""); requested=self.headers.get("Access-Control-Request-Headers","")
        if not allowed_host_header(self.headers.get("Host",""),self.server.server_port) or not cors_preflight_allowed(origin,self.headers.get("Access-Control-Request-Method",""),requested):self.reply(403,{"error":"CORS_preflight_denied"});return
        allowed="content-type, x-extension-id, x-extension-origin, x-run-id, x-session-id, x-timestamp, x-nonce, x-signature"
        self.send_response(204);self.send_header("Access-Control-Allow-Origin",FIXED_ORIGIN);self.send_header("Access-Control-Allow-Methods","POST");self.send_header("Access-Control-Allow-Headers",allowed);self.send_header("Access-Control-Max-Age","60");self.send_header("Vary","Origin");self.end_headers()
    def do_POST(self):
        origin=self.headers.get("Origin") or self.headers.get("X-Extension-Origin","")
        try:
            if not allowed_host_header(self.headers.get("Host",""),self.server.server_port):raise SecurityError("invalid_Host")
            length=int(self.headers.get("Content-Length","0"));
            if length<0 or length>MAX_BODY_BYTES:raise SecurityError("request_body_too_large")
            raw=self.rfile.read(length); headers={k:v for k,v in self.headers.items()}
            if self.path=="/v1/authorize":
                body=json.loads(raw or b"{}"); value=self.state.authorize(body.get("run_id",""),headers.get("X-Extension-ID") or body.get("extension_id",""),origin,body.get("page_url",""));self.reply(200,value,origin);return
            if self.path in {"/v1/checkpoint","/v1/capture"}:
                payload=self.state.verify_signed(self.path,raw,headers); value=self.state.accept_checkpoint(payload) if self.path.endswith("checkpoint") else self.state.accept_capture(payload);self.reply(200,value,origin);return
            self.reply(404,{"error":"not_found"},origin)
        except (SecurityError,ValueError,json.JSONDecodeError) as error:self.reply(403,{"error":str(error)},origin)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--port",type=int,default=LISTEN_PORT);parser.add_argument("--output-dir",type=Path,default=Path("outputs/reddit-comments/bridge_inbox"));parser.add_argument("--ttl-seconds",type=int,default=1800);args=parser.parse_args()
    run_id=secrets.token_urlsafe(24);Handler.state=BridgeState(run_id,args.output_dir,ttl_seconds=args.ttl_seconds);server=ThreadingHTTPServer((LISTEN_HOST,args.port),Handler)
    print(json.dumps({"status":"ready","listen":f"http://{LISTEN_HOST}:{args.port}","run_id":run_id,"expires_in":args.ttl_seconds,"output_dir":str(args.output_dir.resolve()),"extension_id":FIXED_EXTENSION_ID},ensure_ascii=False),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:Handler.state.stop();server.server_close()
    return 0
if __name__=="__main__":raise SystemExit(main())
