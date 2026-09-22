#!/usr/bin/env node
"use strict";
const fs=require("fs"), path=require("path"), http=require("http"), {spawnSync}=require("child_process");
const threadCore=require("./reddit_thread_core.cjs");
const visibleCapture=require("./reddit_visible_capture.js");
const DEFAULT_OUT="outputs/reddit-comments";
const BLOCKS=[[/blocked by network security/i,"network_blocked"],[/captcha|robot check/i,"captcha"],[/too many requests|http\s*429/i,"rate_limited"],[/log in to reddit|you need to log in|sign in to reddit/i,"login_required"],[/access denied|http\s*403/i,"access_denied"]];
function help(){console.log(`Reddit VOC comments-only collector
Usage:
  node scripts/reddit_playwright_collector.cjs preflight [options]
  node scripts/reddit_playwright_collector.cjs collect --asin ASIN [options]
Inputs:
  --asin ASIN | --asins ASIN1,ASIN2 | --asin-file FILE
  --target-comments NUMBER (valid unique comments, default 100)
  --discovery-mode iterative --max-discovery-rounds 5
  --min-new-comments-per-round 10 --duplicate-rate-stop 0.85
  --max-posts-per-query 10 --max-comments-per-post 500
  --retry-partial --force-reaudit-partial
    Re-audit checkpoint PARTIAL threads before keyword discovery; completed keywords do not suppress this queue.
Access:
  --session-mode selected-chrome-tab
  Codex-only: requires an explicitly @mentioned Chrome tab and the Computer Use extension bridge.
  --session-mode cdp --cdp-url http://127.0.0.1:9222
  Independent Node CLI only. Connects to an existing visible Chrome only when it exposes CDP;
  it is not ordinary-Chrome direct control.
  --request-delay-min 8 --request-delay-max 15 --max-posts 20
  --failure-limit 1
  --max-expand-actions 100 --max-comments-per-post 500
  --expand-delay-min 1 --expand-delay-max 3 --thread-timeout 600
  --max-requests-per-thread 40 --thread-deadline-seconds 150
  --preflight-post-url URL --sellersprite-url URL
Output:
  --out-dir ${DEFAULT_OUT} --run-name NAME
  Per-thread evidence: ${DEFAULT_OUT}/evidence/POST_ID/
Commands: preflight, collect. Public visible content only; login is manual.`)}
function args(argv){const o={command:"collect",sessionMode:"cdp",cdpUrl:"http://127.0.0.1:9222",discoveryMode:"iterative",maxDiscoveryRounds:"5",minNewCommentsPerRound:"10",duplicateRateStop:"0.85",maxPostsPerQuery:"10",maxCommentsPerPost:"500"},booleanFlags=new Set(["--retry-partial","--force-reaudit-partial"]); let i=0;if(["collect","preflight"].includes(argv[0]))o.command=argv[i++];for(;i<argv.length;i++){const k=argv[i];if(k==="--help"||k==="-h"){o.help=true;continue}if(!k.startsWith("--"))throw Error(`Unknown argument: ${k}`);const name=k.slice(2).replace(/-([a-z])/g,(_,c)=>c.toUpperCase());if(booleanFlags.has(k)){o[name]=true;continue}const v=argv[++i];if(v===undefined||v.startsWith("--"))throw Error(`Missing value for ${k}`);o[name]=v}return o}
const DISCOVERY_VERSIONS={collector_version:"2.0.0",query_plan_version:"2.0",conversation_map_version:"1.0",audit_version:"2.0"};
function migrateDiscoveryCheckpoint(checkpoint={}){const cp={...checkpoint,...DISCOVERY_VERSIONS};cp.discovery_round=Number(cp.discovery_round||1);cp.round_history=cp.round_history||[];cp.query_metrics=cp.query_metrics||{};cp.community_map=cp.community_map||[];cp.conversation_coverage=cp.conversation_coverage||{};cp.trusted_comments=cp.trusted_comments||cp.comments||[];cp.partial_reaudit_frontier=Object.entries(cp.selected_visible_threads||{}).filter(([,v])=>(v?.audit_status||v?.status)==="PARTIAL").map(([id])=>id);return cp}
function discoveryStop(rounds=[],trustedTotal=0,o={}){const target=Number(o.targetComments||100),max=Number(o.maxDiscoveryRounds||5),min=Number(o.minNewCommentsPerRound||10),dup=Number(o.duplicateRateStop||.85);if(trustedTotal>=target)return{stop:true,stop_reason:"target_comments_reached"};if(rounds.length>=max)return{stop:true,stop_reason:"max_discovery_rounds_reached"};if(rounds.length>=2&&rounds.slice(-2).every(r=>Number(r.new_trusted||0)<min))return{stop:true,stop_reason:"semantic_saturation_low_yield"};if(rounds.length>=2&&rounds.slice(-2).every(r=>Number(r.duplicate_rate||0)>dup))return{stop:true,stop_reason:"duplicate_rate_saturation"};return{stop:false,stop_reason:null}}
function partialReauditQueue(checkpoint={},o={}){if(!o.retryPartial&&!o.forceReauditPartial)return[];const selected=checkpoint.selected_visible_threads||{};return Object.entries(selected).filter(([,v])=>(v?.audit_status||v?.status)==="PARTIAL").map(([post_id,v])=>({post_id,post_url:v.post_url||v.url||null,previous_status:"PARTIAL",force:!!o.forceReauditPartial}));}
function transportPlan(o){return o.sessionMode==="selected-chrome-tab"?{mode:"selected-chrome-tab",bridge:"codex-computer-use-extension",requires_cdp:false,auto_start_cdp:false,independent_cli:false}:{mode:"cdp",bridge:"playwright-connect-over-cdp",requires_cdp:true,auto_start_cdp:true,independent_cli:true}}
function selectedTabCapability(c={}){const base=!!(c.evaluate&&c.dom&&c.navigation&&c.owned_temp_tabs);return{capture_mode:base?(c.same_origin_fetch?"structured_same_origin":"visible_dom"):"unavailable",json_frontier_available:!!(base&&c.same_origin_fetch),visible_dom_available:base}}
function selectedTabExpansionOptions(o={}){return{max_expand_actions:Number(o.maxExpandActions||100),max_comments_per_post:Number(o.maxCommentsPerPost||500),expand_delay_min:Number(o.expandDelayMin||1),expand_delay_max:Number(o.expandDelayMax||3),thread_timeout:Number(o.threadTimeout||600)}}
async function runSelectedTabCommentExpansion(adapter,o={}){return visibleCapture.expandVisibleThread(adapter,{...selectedTabExpansionOptions(o),post_id:o.postId,checkpoint:o.checkpoint})}
function selectedTabPreflight(binding={},snapshot={}){
  const result={command:"preflight",browser:"selected-chrome-tab",status:"stopped",stop_reason:null,checks:{current_page:"not_checked"}};
  if(!binding.explicitly_selected||binding.browser_type!=="extension"||!binding.tab_id||!binding.provider_tab_id)return{...result,stop_reason:"explicit_chrome_tab_mention_required"};
  if(snapshot.closed)return{...result,stop_reason:"selected_tab_closed"};
  if(snapshot.tab_id!==binding.tab_id||snapshot.provider_tab_id!==binding.provider_tab_id)return{...result,stop_reason:"selected_tab_identity_changed"};
  let url;try{url=new URL(snapshot.url)}catch{return{...result,stop_reason:"selected_tab_invalid_url"}}
  if(url.protocol!=="https:"||!/(^|\.)reddit\.com$/i.test(url.hostname))return{...result,stop_reason:"selected_tab_left_reddit"};
  const state=classify(snapshot.body||"",0,snapshot.url);
  if(state.status!=="ready")return{...result,status:state.status==="login_required"?"waiting_for_manual_login":"access_denied",stop_reason:`current_page:${state.stop_reason}`,checks:{current_page:state.status}};
  if(!snapshot.reddit_root||!String(snapshot.body||"").trim())return{...result,status:"waiting_for_manual_login",stop_reason:"current_page:reddit_content_not_visible",checks:{current_page:"not_ready"}};
  return{...result,status:"ready",checks:{current_page:"ready"},selected_tab:{tab_id:binding.tab_id,provider_tab_id:binding.provider_tab_id,url:snapshot.url,title:snapshot.title||""}};
}
function asins(o){let v=[];if(o.asin)v.push(o.asin);if(o.asins)v.push(...o.asins.split(","));if(o.asinFile){const raw=fs.readFileSync(o.asinFile,"utf8");if(path.extname(o.asinFile).toLowerCase()===".csv")v.push(...raw.split(/[\r\n,]+/).filter(x=>x.trim().toLowerCase()!=="asin"));else v.push(...raw.split(/\r?\n/))}v=[...new Set(v.map(x=>x.trim().toUpperCase()).filter(Boolean))];for(const a of v)if(!/^[A-Z0-9]{10}$/.test(a))throw Error(`Invalid ASIN: ${a}`);if(!v.length)throw Error("Provide --asin, --asins, or --asin-file");return v}
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const now=()=>new Date().toISOString();
function classify(text,_ignoredStatus=0,url="") {
  const visible=String(text||"");
  if(/\/login(?:[/?#]|$)/i.test(url)||/log in to reddit|you need to log in|sign in to reddit/i.test(visible)) return {status:"login_required",stop_reason:"login_required"};
  for(const [re,status] of BLOCKS) if(re.test(visible)) return {status,stop_reason:status};
  return {status:"ready",stop_reason:null};
}function list(v){return Array.isArray(v)?v:(v?[v]:[])}
function clean(v){const seen=new Set(),out=[];for(const x of v.flat(Infinity)){const s=String(x||"").replace(/\s+/g," ").trim();if(s&&!seen.has(s.toLowerCase())){seen.add(s.toLowerCase());out.push(s)}}return out}
function csv(rows){const fields=["schema_version","platform","asin","matched_asins","query","matched_keywords","subreddit","post_id","post_title","post_url","comment_id","parent_id","depth","author","body","score","created_at","comment_url","collected_at","thread_audit_status","thread_evidence_path"];const esc=v=>`"${String(Array.isArray(v)?v.join("|"):(v??"")).replace(/"/g,'""')}"`;return [fields.join(","),...rows.map(r=>fields.map(f=>esc(r[f])).join(","))].join("\n")+"\n"}
function valid(r){const b=String(r.body||"").trim();return b&&!/^\[(deleted|removed)\]$/i.test(b)&&!/\bi am a bot\b.*\b(action|performed|automatically)\b/is.test(b)}
function merge(rows){const out=[],index=new Map();let filtered=0,deduped=0;for(const r0 of rows){if(!valid(r0)){filtered++;continue}const r={schema_version:"reddit_comment_v1",platform:"reddit",asin:r0.asin||list(r0.matched_asins)[0]||"",matched_asins:clean([...list(r0.matched_asins),r0.asin]),query:r0.query||null,matched_keywords:clean(list(r0.matched_keywords)),subreddit:r0.subreddit||null,post_id:r0.post_id||null,post_title:r0.post_title||null,post_url:r0.post_url||null,comment_id:String(r0.comment_id||"").replace(/^t1_/,""),parent_id:r0.parent_id||null,depth:Number(r0.depth)||0,author:r0.author||null,body:String(r0.body).trim(),score:r0.score??null,created_at:r0.created_at||null,comment_url:r0.comment_url||null,collected_at:r0.collected_at||now(),thread_audit_status:r0.thread_audit_status||null,thread_evidence_path:r0.thread_evidence_path||null};const keys=[r.comment_id&&`id:${r.comment_id}`,r.comment_url&&`url:${r.comment_url.replace(/\/$/,"")}`].filter(Boolean);let old=keys.map(k=>index.get(k)).find(Boolean);if(old){deduped++;old.matched_asins=clean([...old.matched_asins,...r.matched_asins]);old.matched_keywords=clean([...old.matched_keywords,...r.matched_keywords]);continue}out.push(r);for(const k of keys)index.set(k,r)}return{rows:out,filtered,deduped}}
function playwright(){try{return require("playwright")}catch(e){throw Error("Playwright is required. Install with: npm install playwright")}}
function probeCdp(cdpUrl,timeoutMs=2000) {
  return new Promise(resolve=>{
    let target;
    try { target=new URL("/json/version",cdpUrl); }
    catch(e) { resolve({status:"cdp_not_listening",stop_reason:`invalid_cdp_url:${e.message}`}); return; }
    const request=http.get(target,{timeout:timeoutMs},response=>{
      let body="";
      response.setEncoding("utf8");
      response.on("data",chunk=>body+=chunk);
      response.on("end",()=>{
        try {
          const metadata=JSON.parse(body);
          if(response.statusCode===200&&metadata.webSocketDebuggerUrl) resolve({status:"ready",cdp_url:cdpUrl,browser:metadata.Browser||null});
          else resolve({status:"cdp_not_listening",stop_reason:`cdp_version_unavailable:${response.statusCode||"unknown"}`});
        } catch { resolve({status:"cdp_not_listening",stop_reason:"cdp_version_invalid_json"}); }
      });
    });
    request.on("timeout",()=>request.destroy(new Error("timeout")));
    request.on("error",error=>resolve({status:"cdp_not_listening",stop_reason:`cdp_connection_failed:${error.code||error.message}`}));
  });
}
function runCdpStarter() {
  const script=path.join(__dirname,"start_reddit_cdp.ps1");
  const run=spawnSync("powershell.exe",["-NoProfile","-ExecutionPolicy","Bypass","-File",script],{encoding:"utf8",windowsHide:true});
  const lines=String(run.stdout||"").trim().split(/\r?\n/).filter(Boolean);
  let result;
  try { result=JSON.parse(lines[lines.length-1]||"{}"); }
  catch { result={status:"cdp_not_listening",reason:String(run.stderr||run.stdout||"CDP starter returned no JSON")}; }
  return {...result,starter_exit_code:run.status};
}
async function ensureCdp(o) {
  let probe=await probeCdp(o.cdpUrl);
  if(probe.status==="ready") return probe;
  const starter=runCdpStarter();
  if(starter.status!=="ready") return {status:starter.status||"cdp_not_listening",stop_reason:starter.reason||starter.action||"cdp_not_listening",starter};
  probe=await probeCdp(o.cdpUrl);
  return probe.status==="ready"?{...probe,starter}:{status:"cdp_not_listening",stop_reason:probe.stop_reason,starter};
}
async function connectExistingChrome(o) {
  if(o.sessionMode!=="cdp") throw Error("Only --session-mode cdp is supported; launch a dedicated visible Chrome CDP profile manually first.");
  const browser=await playwright().chromium.connectOverCDP(o.cdpUrl);
  const context=browser.contexts()[0];
  if(!context) throw Error("CDP connected, but Chrome exposed no browser context.");
  return {browser,context,connection:"existing-chrome-cdp",cdp_url:o.cdpUrl};
}
async function visibleState(page) {
  const body=await page.locator("body").innerText({timeout:15000}).catch(()=>"");
  return {...classify(body,0,page.url()),url:page.url(),title:await page.title().catch(()=>""),body_length:body.trim().length};
}
async function inspect(page,url) {
  await page.goto(url,{waitUntil:"domcontentloaded",timeout:60000});
  await page.waitForTimeout(1500);
  return visibleState(page);
}
async function preflight(o,context) {
  const result={command:"preflight",browser:"existing-chrome-cdp",cdp_url:o.cdpUrl,checks:{},status:"ready",stop_reason:null,collected_at:now()};
  const existing=context.pages().filter(p=>/https?:\/\/([\w-]+\.)?reddit\.com\//i.test(p.url()));
  if(!existing.length) return {...result,status:"waiting_for_manual_login",stop_reason:"current_page:no_open_reddit_tab",checks:{current_page:"waiting_for_manual_login"}};
  const current=existing[existing.length-1], currentState=await visibleState(current);
  const redditUi=await current.locator("shreddit-app, shreddit-post, [data-testid='post-container'], a[href*='/r/']").count().catch(()=>0);
  result.checks.current_page=currentState.status;
  if(currentState.status!=="ready"||(!redditUi&&currentState.body_length<20)) {
    result.status=currentState.status==="login_required"||currentState.status==="ready"?"waiting_for_manual_login":"access_denied";
    result.stop_reason=`current_page:${currentState.stop_reason||"reddit_content_not_visible"}`;
    return result;
  }
  const page=await context.newPage();
  try {
    const searchState=await inspect(page,o.preflightSearchUrl||"https://www.reddit.com/search/?q=reddit&sort=relevance");
    result.checks.search=searchState.status;
    if(searchState.status!=="ready") { result.status=searchState.status==="login_required"?"waiting_for_manual_login":"access_denied"; result.stop_reason=`search:${searchState.stop_reason}`; return result; }
    const links=await page.locator("a[href*='/comments/']").evaluateAll(es=>[...new Set(es.map(e=>e.href.split("?")[0]))]);
    if(!links.length) { result.status="waiting_for_manual_login"; result.stop_reason="search:no_visible_results"; result.checks.search="waiting_for_manual_login"; return result; }
    const postState=await inspect(page,o.preflightPostUrl||links[0]);
    result.checks.post=postState.status;
    if(postState.status!=="ready") { result.status=postState.status==="login_required"?"waiting_for_manual_login":"access_denied"; result.stop_reason=`post:${postState.stop_reason}`; return result; }
    const comments=await page.locator("shreddit-comment, .comment[data-fullname], [data-testid='comment']").count();
    result.checks.visible_search_results=links.length;
    result.checks.visible_comments=comments;
    if(!comments) { result.status="waiting_for_manual_login"; result.stop_reason="post:comments_not_loadable"; result.checks.post="waiting_for_manual_login"; }
    return result;
  } finally { await page.close().catch(()=>{}); }
}
async function amazonProduct(page,asin) {
  const url=`https://www.amazon.com/dp/${asin}`, access=await inspect(page,url);
  if(access.status!=="ready") return {asin,url,access_status:access.status,stop_reason:access.stop_reason};
  const data=await page.evaluate(()=>{
    const t=s=>document.querySelector(s)?.textContent?.replace(/\s+/g," ").trim()||null;
    const all=s=>[...document.querySelectorAll(s)].map(x=>x.textContent.replace(/\s+/g," ").trim()).filter(Boolean);
    const buckets={core_traffic:[],long_tail:[],related:[],competitor:[]};
    for(const node of document.querySelectorAll("[data-sellersprite], [class*='seller-sprite'], [id*='sellersprite']")) {
      const value=(node.textContent||"").replace(/\s+/g," ").trim(); if(!value) continue;
      const label=((node.parentElement?.textContent||"")+" "+(node.getAttribute("data-sellersprite")||"")).toLowerCase();
      if(/long.?tail|长尾/.test(label)) buckets.long_tail.push(value);
      else if(/competitor|竞品/.test(label)) buckets.competitor.push(value);
      else if(/related|关联/.test(label)) buckets.related.push(value);
      else buckets.core_traffic.push(value);
    }
    return {title:t("#productTitle"),brand:t("#bylineInfo")?.replace(/^Brand:\s*/i,"").replace(/^Visit the\s+/i,"").replace(/\s+Store$/i,""),category:all("#wayfinding-breadcrumbs_feature_div a").pop()||null,core_attributes:all("#feature-bullets li span.a-list-item"),amazon_login_state:/hello,\s*sign in/i.test(t("#nav-link-accountList")||"")?"login_required":"available",sellersprite_keywords:buckets};
  });
  const words=(data.title||"").replace(/[^\p{L}\p{N} ]/gu," ").split(/\s+/).filter(x=>x.length>2);
  data.asin=asin; data.url=url; data.access_status="ready";
  data.common_names=clean(words.slice(0,5).join(" ")?[words.slice(0,5).join(" ")]:[]);
  data.use_scenarios=clean(data.core_attributes.filter(x=>/for|use|indoor|outdoor|travel|home/i.test(x)).slice(0,5));
  data.main_functions=clean(data.core_attributes.slice(0,8));
  for(const key of Object.keys(data.sellersprite_keywords)) data.sellersprite_keywords[key]=clean(data.sellersprite_keywords[key]);
  return data;
}
function keywordPlan(product, seller={}) {
  const n=product.common_names||[], cat=product.category||"", brand=product.brand||"";
  return {
    category_core:clean([cat,...n,...list(seller.core_traffic)]),
    brand_product:clean([...n.map(x=>`${brand} ${x}`),...list(seller.long_tail)]),
    use_scenario:clean([...(product.use_scenarios||[]),...list(seller.related)]),
    problem_pain:clean((n.length?n:[cat]).flatMap(x=>[`${x} problem`,`${x} not working`])),
    recommend_compare_buy:clean([...(n.length?n:[cat]).flatMap(x=>[`${x} recommendation`,`${x} review`,`${x} vs`,`${x} worth it`]),...list(seller.competitor)])
  };
}
function runThreadAudit(evidenceDir) {
  const script=path.join(__dirname,"audit_thread_evidence.py");
  const command=process.platform==="win32"?"py":"python3";
  const prefix=process.platform==="win32"?["-3.11"]:[];
  const run=spawnSync(command,[...prefix,script,evidenceDir],{encoding:"utf8",windowsHide:true});
  const lines=String(run.stdout||"").trim().split(/\r?\n/).filter(Boolean);
  try{return JSON.parse(lines[lines.length-1]||"{}")}
  catch{return{status:"PARTIAL",failures:["audit_execution_error"],error_type:"InvalidAuditOutput"}}
}
async function collect(o, context) {
  const input=asins(o),target=Number(o.targetComments||100),maxPosts=Number(o.maxPosts||20),maxPer=Number(o.maxCommentsPerPost||500);
  const delayMin=Number(o.requestDelayMin||8),delayMax=Number(o.requestDelayMax||15),maxRequests=Number(o.maxRequestsPerThread||40),deadline=Number(o.threadDeadlineSeconds||150);
  const out=path.resolve(o.outDir||DEFAULT_OUT),run=o.runName||input.join("_").slice(0,80),evidenceRoot=path.join(out,"evidence");
  fs.mkdirSync(evidenceRoot,{recursive:true});const file=s=>path.join(out,`${run}_${s}`),checkpointPath=file("checkpoint.json");
  const defaults={searched_keywords:[],discovered_posts:[],completed_posts:[],thread_audits:{},processed_comment_ids:[],valid_comment_count:0,comments:[]};
  let checkpoint={...defaults};if(fs.existsSync(checkpointPath))checkpoint={...defaults,...JSON.parse(fs.readFileSync(checkpointPath,"utf8"))};checkpoint=migrateDiscoveryCheckpoint(checkpoint);
  const save=()=>{const current=merge(checkpoint.comments);checkpoint.processed_comment_ids=current.rows.map(x=>x.comment_id);checkpoint.valid_comment_count=current.rows.length;fs.writeFileSync(checkpointPath,JSON.stringify(checkpoint,null,2))};
  const manifest={schema_version:"reddit_comment_manifest_v3",...DISCOVERY_VERSIONS,discovery_mode:o.discoveryMode||"iterative",discovery_rounds:[],new_queries_by_round:[],new_communities_by_round:[],trusted_comments_by_round:[],partial_candidates_by_round:[],duplicate_rate_by_round:[],marginal_yield_by_round:[],saturation_reason:null,conversation_coverage:{},comments_by_relevance_tier:{},comments_by_query_family:{},comments_by_community:{},input_asin_count:input.length,amazon_products_resolved:0,amazon_access_status:{},amazon_login_status:{},sellersprite_website_status:o.sellerspriteUrl?"pending":"not_configured",sellersprite_extension_status:{},sellersprite_missing_reason:{},reddit_access_status:"not_checked",keyword_count:0,posts_found:0,thread_audit_counts:{PASS:0,PARTIAL:0,BLOCKED:0},comments_collected:0,partial_candidate_comments:0,filtered_count:0,deduplicated_count:0,comments_per_asin:{},target_comments:target,target_shortfall_reason:null,quality_gate_passed:false,stop_reason:null};
  const page=await context.newPage(),products={},plans={};let visitedPosts=0;const foundPosts=new Set(checkpoint.discovered_posts.map(x=>typeof x==="string"?x:x.post_url));
  try {
    for(const asin of input){
      await sleep((delayMin+Math.random()*(delayMax-delayMin))*1000);const product=await amazonProduct(page,asin);products[asin]=product;manifest.amazon_access_status[asin]=product.access_status;manifest.amazon_login_status[asin]=product.amazon_login_state||"unknown";if(product.access_status==="ready")manifest.amazon_products_resolved++;
      const seller=product.sellersprite_keywords||{core_traffic:[],long_tail:[],related:[],competitor:[]},count=Object.values(seller).flat().length;manifest.sellersprite_extension_status[asin]=count?"available":"unavailable";manifest.sellersprite_missing_reason[asin]=count?null:"SellerSprite extension data was not visible on the Amazon page; Amazon-visible fallback keywords used.";plans[asin]=keywordPlan(product,seller);manifest.keyword_count+=Object.values(plans[asin]).flat().length;
    }
    if(o.sellerspriteUrl){await sleep(delayMin*1000);const state=await inspect(page,o.sellerspriteUrl);manifest.sellersprite_website_status=state.status==="ready"?"available":state.status}
    const pf=await preflight(o,context);manifest.reddit_access_status=pf.status;if(pf.status!=="ready"){manifest.stop_reason=pf.stop_reason;throw Error(`STOP:${pf.stop_reason}`)}
    outer:for(const asin of input){
      for(const query of clean([asin,...Object.values(plans[asin]).flat()])){
        await sleep((delayMin+Math.random()*(delayMax-delayMin))*1000);const state=await inspect(page,`https://www.reddit.com/search/?q=${encodeURIComponent(query)}&sort=relevance&t=all`);if(state.status!=="ready"){manifest.stop_reason=`search:${state.stop_reason}`;break outer}
        const searchKey=`${asin}|${query}`;if(!checkpoint.searched_keywords.includes(searchKey))checkpoint.searched_keywords.push(searchKey);
        const rawLinks=await page.locator("a[href*='/comments/']").evaluateAll(es=>[...new Set(es.map(e=>e.href.split("?")[0]))]);const links=[];for(const value of rawLinks){try{const normalized=threadCore.normalizePostUrl(value).post_url;if(!links.includes(normalized))links.push(normalized)}catch{}}
        for(const postUrl of links){foundPosts.add(postUrl);if(!checkpoint.discovered_posts.some(x=>(typeof x==="string"?x:x.post_url)===postUrl))checkpoint.discovered_posts.push({post_url:postUrl,asin,query});save()}
        manifest.posts_found=foundPosts.size;
        for(const postUrl of links){
          if(!threadCore.shouldVisitThread(checkpoint,postUrl,false)){
            if(checkpoint.thread_audits[postUrl]==="PASS")for(const row of checkpoint.comments.filter(x=>x.post_url===postUrl)){row.matched_asins=clean([...list(row.matched_asins),asin]);row.matched_keywords=clean([...list(row.matched_keywords),query])}save();continue;
          }
          if(visitedPosts>=maxPosts)break outer;visitedPosts++;await sleep((delayMin+Math.random()*(delayMax-delayMin))*1000);const pageState=await inspect(page,postUrl);if(pageState.status!=="ready"){manifest.stop_reason=`post:${pageState.stop_reason}`;break outer}
          const bound=threadCore.normalizePostUrl(page.url().split("?")[0]),evidenceDir=path.resolve(evidenceRoot,bound.post_id);let audit,comments;
          if(fs.existsSync(evidenceDir)&&fs.readdirSync(evidenceDir).length){audit=runThreadAudit(evidenceDir);comments=fs.existsSync(path.join(evidenceDir,"comments.jsonl"))?fs.readFileSync(path.join(evidenceDir,"comments.jsonl"),"utf8").split(/\r?\n/).filter(Boolean).map(JSON.parse):[]}
          else{const captured=await threadCore.collectThread({postUrl:bound.post_url,evidenceDir,fetchJson:(url,label,mode,ids,targetInfo)=>threadCore.browserFetchJson(page,url,label,mode,ids,targetInfo),maxRequests,deadlineSeconds:deadline});comments=captured.comments;audit=runThreadAudit(evidenceDir)}
          checkpoint.thread_audits[bound.post_url]=audit.status;checkpoint.completed_posts=clean([...checkpoint.completed_posts,bound.post_url]);
          if(audit.status==="PASS"){
            const postTitle=await page.locator("h1").first().innerText().catch(()=>page.title());const rows=threadCore.aggregateAuditedComments([{audit,comments,evidence_path:evidenceDir,context:{schema_version:"reddit_comment_v1",platform:"reddit",asin,matched_asins:[asin],query,matched_keywords:[query],subreddit:bound.subreddit,post_id:bound.post_id,post_title:postTitle,post_url:bound.post_url,collected_at:now()}}],maxPer);checkpoint.comments.push(...rows);checkpoint.comments=merge(checkpoint.comments).rows;
          }
          save();if(audit.status==="BLOCKED"){manifest.stop_reason=`thread:${bound.post_id}:BLOCKED`;break outer}if(merge(checkpoint.comments).rows.length>=target)break outer;
        }
      }
    }
  }catch(error){if(!String(error.message).startsWith("STOP:"))manifest.stop_reason=manifest.stop_reason||error.message}finally{await page.close().catch(()=>{})}
  for(const status of Object.values(checkpoint.thread_audits))if(Object.hasOwn(manifest.thread_audit_counts,status))manifest.thread_audit_counts[status]++;
  const prepared=merge(checkpoint.comments),rows=prepared.rows.slice(0,target);manifest.comments_collected=rows.length;manifest.filtered_count=prepared.filtered;manifest.deduplicated_count=prepared.deduped;for(const asin of input)manifest.comments_per_asin[asin]=rows.filter(r=>r.matched_asins.includes(asin)).length;manifest.quality_gate_passed=rows.length>=target&&!manifest.stop_reason;if(rows.length<target)manifest.target_shortfall_reason=manifest.stop_reason||"audited_PASS_comments_below_target";
  fs.writeFileSync(file("comments_raw.jsonl"),rows.map(x=>JSON.stringify(x)).join("\n")+(rows.length?"\n":""));fs.writeFileSync(file("comments_raw.csv"),csv(rows));fs.writeFileSync(file("asin_keywords.json"),JSON.stringify({products,keywords:plans},null,2));const queryRows=[];for(const asin of input)for(const query of clean([asin,...Object.values(plans[asin]).flat()]))queryRows.push({asin,query,search_url:`https://www.reddit.com/search/?q=${encodeURIComponent(query)}&sort=relevance&t=all`});fs.writeFileSync(file("query_plan.json"),JSON.stringify({asins:input,target_comments:target,keywords:plans,queries:queryRows},null,2));fs.writeFileSync(file("manifest.json"),JSON.stringify(manifest,null,2));save();
  return{manifest,files:{jsonl:file("comments_raw.jsonl"),csv:file("comments_raw.csv"),keywords:file("asin_keywords.json"),query_plan:file("query_plan.json"),manifest:file("manifest.json"),checkpoint:checkpointPath,evidence:evidenceRoot}};
}
async function main() {
  let exitCode=0;
  try {
    const o=args(process.argv.slice(2));
    if(o.help){help();return}
    if(o.sessionMode==="selected-chrome-tab"){
      console.log(JSON.stringify({command:o.command,status:"codex_bridge_required",stop_reason:"Use $reddit-voc-collector in a Codex task with an explicitly @mentioned Chrome tab.",session_mode:"selected-chrome-tab",bridge:"codex-computer-use-extension",requires_cdp:false,auto_start_cdp:false},null,2));
      process.exit(2);
    }
    if(o.command==="collect") asins(o);
    const cdp=await ensureCdp(o);
    if(cdp.status!=="ready") {
      console.log(JSON.stringify({command:o.command,status:cdp.status,stop_reason:cdp.stop_reason||null,cdp_url:o.cdpUrl,starter:cdp.starter||null},null,2));
      process.exit(2);
    }
    const session=await connectExistingChrome(o);
    const result=o.command==="preflight"?await preflight(o,session.context):await collect(o,session.context);
    console.log(JSON.stringify(result,null,2));
    if((result.status&&result.status!=="ready")||result.manifest?.stop_reason) exitCode=2;
  } catch(e) {
    console.error(JSON.stringify({status:"unavailable",stop_reason:e.message})); exitCode=1;
  }
  process.exit(exitCode);
}if(require.main===module) main();
module.exports={args,asins,classify,clean,valid,merge,probeCdp,runCdpStarter,ensureCdp,visibleState,preflight,connectExistingChrome,transportPlan,selectedTabCapability,selectedTabPreflight,selectedTabExpansionOptions,runSelectedTabCommentExpansion,partialReauditQueue,migrateDiscoveryCheckpoint,discoveryStop,DISCOVERY_VERSIONS};
