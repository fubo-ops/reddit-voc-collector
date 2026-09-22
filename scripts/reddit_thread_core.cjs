#!/usr/bin/env node
"use strict";
const fs=require("fs"),path=require("path"),crypto=require("crypto");

const utc=()=>new Date().toISOString();
const sha256=data=>crypto.createHash("sha256").update(data).digest("hex");
function normalizePostUrl(value){
  const u=new URL(value);
  if(u.protocol!=="https:"||u.hostname!=="www.reddit.com"||u.search||u.hash||/[\\\s\x00-\x1f]/.test(value))throw Error("invalid_reddit_thread_url");
  const m=u.pathname.match(/^\/r\/([A-Za-z0-9_]+)\/comments\/([a-z0-9]{2,16})(?:\/[^/?#\s]+)?\/?$/);
  if(!m)throw Error("invalid_reddit_thread_url");
  const pathname=u.pathname.replace(/\/$/,"");
  return{subreddit:m[1],post_id:m[2],post_url:`https://www.reddit.com${pathname}`,guard:`https://www.reddit.com/r/${m[1]}/comments/${m[2]}/`};
}
const ALLOWED={t3:["id","name","title","permalink","num_comments","subreddit","created_utc"],t1:["id","name","parent_id","link_id","body","author","permalink","created_utc","depth","score"],more:["id","name","count","parent_id","children","depth"]};
function projectPublicResponse(value){
  if(Array.isArray(value))return value.map(projectPublicResponse);
  if(!value||typeof value!=="object")throw Error("bad_public_schema");
  if(value.kind==="Listing"){
    const d=value.data;if(!d||!Array.isArray(d.children)||!("after" in d)||!("before" in d))throw Error("incomplete_listing");
    return{kind:"Listing",data:{after:d.after,before:d.before,children:d.children.map(projectPublicResponse)}};
  }
  if(Array.isArray(value.errors)&&Array.isArray(value.things))return{errors:value.errors.map(e=>Array.isArray(e)?[String(e[0]||"API_ERROR")]:["API_ERROR"]),things:value.things.map(projectPublicResponse)};
  const keys=ALLOWED[value.kind];if(!keys||!value.data)throw Error("unknown_thing");const data={};for(const key of keys)if(Object.hasOwn(value.data,key))data[key]=value.data[key];
  if(value.kind==="t1")data.replies=value.data.replies&&typeof value.data.replies==="object"?projectPublicResponse(value.data.replies):value.data.replies;
  return{kind:value.kind,data};
}
function validateRequestTarget(value,target,mode,allowedIds=[]){
  try{
    const u=new URL(value),postPath=new URL(target.post_url).pathname,ids=cleanList(allowedIds),q=u.searchParams;
    if(u.origin!=="https://www.reddit.com"||u.username||u.password||u.hash||/%(?:2f|5c)/i.test(u.pathname))return false;
    if(mode==="listing"&&u.pathname===postPath+".json"){
      const allowed=new Set(["raw_json","limit","sort","after","comment","context"]);if([...q.keys()].some(k=>!allowed.has(k)))return false;
      if(q.get("raw_json")!=="1"||q.get("sort")!=="old"||q.get("limit")!=="100")return false;
      if(q.has("comment")&&(!/^[a-z0-9]+$/.test(q.get("comment"))||!ids.includes(q.get("comment"))))return false;
      return true;
    }
    if(!ids.length||ids.length>100||ids.some(x=>!/^[a-z0-9]+$/.test(x)))return false;
    if(mode==="morechildren"&&u.pathname==="/api/morechildren.json")return q.get("link_id")===`t3_${target.post_id}`&&q.get("children")===ids.join(",")&&q.get("api_type")==="json"&&q.get("raw_json")==="1";
    if(mode==="listing"&&u.pathname==="/api/info.json")return q.get("id")===ids.map(x=>`t1_${x}`).join(",")&&q.get("raw_json")==="1";
    return false;
  }catch{return false}
}
async function browserFetchJson(page,url,label,mode,allowedIds,target){
  if(!validateRequestTarget(url,target,mode,allowedIds))return{state:"blocked",error_type:"request_outside_target",cleanup_verified:true,fetched_at:utc()};
  const result=await page.evaluate(async({url,target,mode,allowedIds})=>{
    const here=location.origin+location.pathname.replace(/\/?$/,"/");
    if(!here.startsWith(target.guard))return{state:"blocked",error_type:"target_changed"};
    const visible=(document.body?.innerText||"");
    if(document.querySelector('input[type="password"],iframe[src*="challenges.cloudflare.com"]')||/blocked by network security|captcha|robot check|too many requests|http\s*429|access denied|http\s*403|log in to reddit/i.test(visible))return{state:"blocked",error_type:"login_or_challenge"};
    try{
      const response=await fetch(url,{headers:{Accept:"application/json"},credentials:"same-origin",redirect:"error"});
      if(response.status!==200)return{state:"blocked",http_status:response.status};
      const type=response.headers.get("content-type")||"";if(!type.includes("json"))return{state:"non_json",http_status:response.status};
      const raw=await response.json();
      const allowed={t3:["id","name","title","permalink","num_comments","subreddit","created_utc"],t1:["id","name","parent_id","link_id","body","author","permalink","created_utc","depth","score"],more:["id","name","count","parent_id","children","depth"]};
      const project=v=>{if(Array.isArray(v))return v.map(project);if(!v||typeof v!=="object")throw Error("bad_schema");if(v.kind==="Listing"){const d=v.data;if(!d||!Array.isArray(d.children)||!("after" in d)||!("before" in d))throw Error("incomplete_listing");return{kind:"Listing",data:{after:d.after,before:d.before,children:d.children.map(project)}}}const keys=allowed[v.kind];if(!keys||!v.data)throw Error("unknown_thing");const data={};for(const key of keys)if(Object.hasOwn(v.data,key))data[key]=v.data[key];if(v.kind==="t1")data.replies=v.data.replies&&typeof v.data.replies==="object"?project(v.data.replies):v.data.replies;return{kind:v.kind,data}};
      if(mode==="morechildren"){const j=raw?.json;if(!j||!Array.isArray(j.errors)||!Array.isArray(j.data?.things))throw Error("malformed_morechildren");return{state:"done",http_status:200,public_response:{errors:j.errors.map(e=>Array.isArray(e)?[String(e[0]||"API_ERROR")]:["API_ERROR"]),things:j.data.things.map(project)}}}
      return{state:"done",http_status:200,public_response:project(raw)};
    }catch(error){return{state:"error",error_type:error?.name==="AbortError"?"timeout":"fetch_or_schema_error"}}
  },{url,target,mode,allowedIds});
  return{...result,label,fetched_at:utc(),cleanup_verified:true};
}
function writeJson(file,value){fs.writeFileSync(file,JSON.stringify(value,null,2)+"\n")}
function ensureNew(dir){if(fs.existsSync(dir)&&fs.readdirSync(dir).length)throw Error("evidence_directory_not_empty");fs.mkdirSync(path.join(dir,"raw"),{recursive:true})}
function cleanList(values){const out=[],seen=new Set();for(const value of values||[]){const s=String(value||"").trim();if(s&&!seen.has(s)){seen.add(s);out.push(s)}}return out}

async function collectThread({postUrl,evidenceDir,fetchJson,maxRequests=40,deadlineSeconds=150}){
  const target=normalizePostUrl(postUrl),link=`t3_${target.post_id}`,root=path.resolve(evidenceDir);ensureNew(root);
  const comments=new Map(),wanted=new Set(),attempted=new Set(),infoAttempted=new Set(),queue=[],queued=new Set(),processed=new Set(),issues=[],requests=[],events=[];
  let declared=null,blocked=false;const deadline=Date.now()+deadlineSeconds*1000;
  const issue=(reason,extra={})=>issues.push({reason,...extra});
  const enqueue=(kind,parent=link,after=null)=>{const key=JSON.stringify([kind,parent,after]);if(processed.has(key))issue("repeated_continuation",{kind,parent,after});else if(!queued.has(key)){queued.add(key);queue.push({kind,parent,after,key})}};
  function walk(node,parent=link){
    if(Array.isArray(node)){for(const child of node)walk(child,parent);return}
    if(!node||typeof node!=="object"||!node.data||typeof node.data!=="object")throw Error("invalid_thing");
    const d=node.data;
    if(node.kind==="Listing"){
      if(!Array.isArray(d.children)||!("after" in d)||!("before" in d))throw Error("incomplete_listing");
      if(d.after!==null){if(typeof d.after!=="string"||!d.after)throw Error("invalid_after");enqueue("after",parent,d.after)}
      for(const child of d.children)walk(child,parent);return;
    }
    if(node.kind==="t1"){
      const id=d.id;if(!id||d.name!==`t1_${id}`||d.link_id!==link||typeof d.body!=="string"||typeof d.parent_id!=="string")throw Error("comment_identity_mismatch");
      const row={};for(const key of ["id","name","parent_id","link_id","body","author","permalink","created_utc","depth","score"])if(Object.hasOwn(d,key))row[key]=d[key];
      const prior=comments.get(id);if(prior&&["parent_id","link_id","body","author"].some(k=>prior[k]!==row[k]))issue("conflicting_duplicate",{id});comments.set(id,row);
      if(d.replies&&typeof d.replies==="object")walk(d.replies,`t1_${id}`);else if(d.replies!==""&&d.replies!=null)throw Error("invalid_replies");return;
    }
    if(node.kind==="more"){
      if(!Array.isArray(d.children))throw Error("missing_more_children");
      if(d.children.length)for(const id of d.children)wanted.add(id);else if(String(d.parent_id||"").startsWith("t1_"))enqueue("continue",d.parent_id,null);else issue("unhandled_empty_more");return;
    }
    throw Error("unknown_thing_kind");
  }
  async function request(url,label,mode="listing",task={}){
    if(requests.length>=maxRequests||Date.now()>=deadline){issue("safety_budget_exhausted",{request_count:requests.length});return null}
    const result=await fetchJson(url,label,mode,task.ids||[],target);
    const entry={};for(const key of ["state","http_status","fetched_at","cleanup_verified","error_type"])if(Object.hasOwn(result,key))entry[key]=result[key];
    Object.assign(entry,{request_url:url,task,label});
    if(Object.hasOwn(result,"public_response")){
      const name=`raw/${String(requests.length+1).padStart(3,"0")}_${label}.json`,data=JSON.stringify(result.public_response);
      fs.writeFileSync(path.join(root,name),data);Object.assign(entry,{body_path:name,sha256:sha256(data)});
    }
    requests.push(entry);writeJson(path.join(root,"requests.json"),requests);
    if(result.state!=="done"||result.http_status!==200){blocked=["blocked","non_json"].includes(result.state)||[401,403,429].includes(result.http_status);issue("request_failed",{state:result.state,http_status:result.http_status});return null}
    if(mode==="morechildren"&&(!result.public_response||!Array.isArray(result.public_response.errors)||!Array.isArray(result.public_response.things))){issue("malformed_morechildren");return null}
    if(mode==="morechildren"&&result.public_response.errors.length){blocked=result.public_response.errors.some(x=>/RATELIMIT|USER_REQUIRED/.test(String(x)));issue("morechildren_api_errors");return null}
    return result.public_response;
  }
  function parseThread(data){
    if(!Array.isArray(data)||data.length!==2)throw Error("bad_thread_response");
    const post=data[0]?.data?.children?.[0];if(post?.kind!=="t3"||post.data?.id!==target.post_id)throw Error("wrong_post");
    const count=post.data.num_comments;if(declared!==null&&declared!==count)issue("counter_changed",{before:declared,after:count});declared=count;walk(data[1]);
  }
  const threadUrl=params=>{const u=new URL(target.post_url+".json");u.search=new URLSearchParams({raw_json:"1",limit:"100",sort:"old",...params});return u.href};
  try{
    const initial=await request(threadUrl({}),"initial","listing",{kind:"initial"});if(initial!==null)parseThread(initial);
    while(!issues.length){
      const pending=[...wanted].filter(x=>!comments.has(x)&&!attempted.has(x)).sort(),info=[...wanted].filter(x=>!comments.has(x)&&!infoAttempted.has(x)).sort();
      if(queue.length){
        const task=queue.shift();queued.delete(task.key);processed.add(task.key);const params={};if(task.parent.startsWith("t1_")){params.comment=task.parent.slice(3);params.context="0"}if(task.after)params.after=task.after;
        const scopedTask=params.comment?{...task,ids:[params.comment]}:task;const data=await request(threadUrl(params),`${task.kind}-${processed.size}`,"listing",scopedTask);if(data===null)break;const before=new Set(comments.keys());parseThread(data);const added=[...comments.keys()].filter(x=>!before.has(x));
        if(task.kind==="continue"&&!added.some(id=>isDescendant(id,task.parent,comments)))issue("continue_no_progress",{parent:task.parent});events.push({kind:task.kind,parent:task.parent,after:task.after,new_ids:added.sort()});
      }else if(pending.length){
        const ids=pending.slice(0,100),u=new URL("https://www.reddit.com/api/morechildren.json");u.search=new URLSearchParams({api_type:"json",raw_json:"1",link_id:link,children:ids.join(","),sort:"old",limit_children:"false"});const before=comments.size,data=await request(u.href,`morechildren-${requests.length}`,"morechildren",{kind:"morechildren",ids});if(data===null)break;walk(data.things);if(comments.size===before)ids.forEach(x=>attempted.add(x));
      }else if(info.length){
        const ids=info.slice(0,100);ids.forEach(x=>infoAttempted.add(x));const u=new URL("https://www.reddit.com/api/info.json");u.search=new URLSearchParams({id:ids.map(x=>`t1_${x}`).join(","),raw_json:"1"});const before=new Set(comments.keys()),data=await request(u.href,`info-${requests.length}`,"listing",{kind:"info",ids});if(data===null)break;if(data.kind!=="Listing")throw Error("bad_info_listing");walk(data);const live=[...comments.keys()].filter(x=>!before.has(x)&&!["[removed]","[deleted]"].includes(comments.get(x).body));if(live.length)issue("info_only_reply_coverage_unknown",{ids:live.sort()});
      }else break;
    }
  }catch(error){issue("parse_error",{detail:error.message})}
  const remaining=[...wanted].filter(x=>!comments.has(x)).sort();if(remaining.length)issue("unreturned_public_ids",{ids:remaining});if(queue.length)issue("unprocessed_continuations",{count:queue.length});
  const orphans=[...comments.values()].filter(c=>c.parent_id!==link&&(!String(c.parent_id).startsWith("t1_")||!comments.has(c.parent_id.slice(3)))).map(c=>c.id).sort();if(orphans.length)issue("orphan_ids",{ids:orphans});
  const rows=[...comments.values()].sort((a,b)=>a.id.localeCompare(b.id)),tombs=rows.filter(c=>["[removed]","[deleted]"].includes(c.body)),deleted=rows.filter(c=>c.body==="[deleted]"&&c.author==="[deleted]").map(c=>c.id),counter=rows.length-deleted.length,matched=Number.isInteger(declared)&&declared===counter;
  const status=blocked?"BLOCKED":(!issues.length&&matched?"PASS":"PARTIAL");
  fs.writeFileSync(path.join(root,"comments.jsonl"),rows.map(x=>JSON.stringify(x)).join("\n")+(rows.length?"\n":""));writeJson(path.join(root,"ids.json"),rows.map(x=>x.id));writeJson(path.join(root,"tombstones.json"),tombs);writeJson(path.join(root,"frontier.json"),{wanted_ids:[...wanted].sort(),attempted_morechildren:[...attempted].sort(),attempted_info:[...infoAttempted].sort(),remaining,queued:queue,processed:[...processed],events,issues});
  const summary={status,post_id:target.post_id,target_url:target.post_url,declared_num_comments:declared,unique_total:rows.length,unique_top_level:rows.filter(x=>x.parent_id===link).length,unique_replies:rows.filter(x=>x.parent_id!==link).length,readable_body_count:rows.filter(x=>!["[removed]","[deleted]"].includes(x.body)).length,tombstones:{total:tombs.length,removed:tombs.filter(x=>x.body==="[removed]").length,deleted:tombs.filter(x=>x.body==="[deleted]").length,ids:tombs.map(x=>x.id)},reachable_frontier_status:issues.length?"PARTIAL":"EXHAUSTED",platform_count_status:matched?"EXACT_NONDELETED_NODES":"UNRECONCILED",platform_counter_nodes:counter,deleted_placeholder_ids:deleted,platform_counter_delta:Number.isInteger(declared)?counter-declared:null,issues,remaining_child_ids:remaining,orphan_reply_ids:orphans,request_count:requests.length,safety_budget:{max_requests:maxRequests,deadline_seconds:deadlineSeconds},depth_cap:null};writeJson(path.join(root,"summary.json"),summary);return{summary,comments:rows};
}
function isDescendant(id,parent,comments){let p=comments.get(id)?.parent_id,seen=new Set();while(String(p).startsWith("t1_")&&!seen.has(p)){if(p===parent)return true;seen.add(p);p=comments.get(p.slice(3))?.parent_id}return false}
function aggregateAuditedComments(entries,target=Infinity){const out=[];for(const entry of entries||[]){if(entry.audit?.status!=="PASS")continue;for(const c of entry.comments||[]){if(!c.body||["[removed]","[deleted]"].includes(c.body))continue;const created=c.created_at||(Number.isFinite(c.created_utc)?new Date(c.created_utc*1000).toISOString():null);out.push({comment_id:c.comment_id||c.id,parent_id:c.parent_id,depth:Number(c.depth)||0,author:c.author,body:c.body,score:c.score??null,created_at:created,comment_url:c.comment_url||(c.permalink?new URL(c.permalink,"https://www.reddit.com").href:null),thread_audit_status:"PASS",thread_evidence_path:entry.evidence_path||null,...(entry.context||{})});if(out.length>=target)return out}}return out}
function shouldVisitThread(checkpoint,postUrl,retryPartial=false){const status=checkpoint?.thread_audits?.[normalizePostUrl(postUrl).post_url];return status!=="PASS"&&(retryPartial||status!=="PARTIAL")}

async function fixtureCli(argv){const get=k=>{const i=argv.indexOf(k);return i>=0?argv[i+1]:null},fixture=JSON.parse(fs.readFileSync(get("--fixture"),"utf8")),responses=[...fixture.responses];const fetchJson=async()=>responses.shift()||{state:"error",error_type:"fixture_exhausted",cleanup_verified:true};const result=await collectThread({postUrl:fixture.post_url,evidenceDir:get("--out"),fetchJson,maxRequests:Number(get("--max-requests")||40),deadlineSeconds:30});console.log(JSON.stringify(result.summary));process.exitCode={PASS:0,PARTIAL:2,BLOCKED:3}[result.summary.status]}
if(require.main===module){if(process.argv[2]==="fixture")fixtureCli(process.argv.slice(3)).catch(e=>{console.error(e.message);process.exitCode=1});else{console.log("Usage: node reddit_thread_core.cjs fixture --fixture FILE --out DIR [--max-requests N]")}}
module.exports={normalizePostUrl,projectPublicResponse,validateRequestTarget,browserFetchJson,collectThread,aggregateAuditedComments,shouldVisitThread};
