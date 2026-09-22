"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const ROOT=path.resolve(__dirname,"..");
const core=require("../extension/capture_core.js");
const session=require("../extension/session_core.js");
const visible=require("../extension/visible_capture.js");

function element(attrs={},body=""){
  return {getAttribute:name=>attrs[name]??null,querySelector:selector=>selector==='[slot="comment"]'?{innerText:body}:null};
}

test("RC1 manifest auto-runs only on bounded Reddit and loopback hosts",()=>{
  const m=JSON.parse(fs.readFileSync(path.join(ROOT,"extension/manifest.json"),"utf8"));
  assert.equal(m.version_name,"1.0.0-rc1");
  assert.deepEqual(m.permissions,[]);
  assert.deepEqual(m.host_permissions,["https://www.reddit.com/*","http://127.0.0.1:43127/*"]);
  assert.equal(m.background.service_worker,"service_worker.js");
  assert.deepEqual(m.content_scripts[0].matches,["https://www.reddit.com/*"]);
  assert.deepEqual(m.content_scripts[0].js,["session_core.js","capture_core.js","visible_capture.js","auto_content.js"]);
  for(const forbidden of ["tabs","cookies","history","webRequest","nativeMessaging","clipboardRead","clipboardWrite"])
    assert.ok(!m.permissions.includes(forbidden));
  assert.equal(m.action?.default_popup,undefined);
});

test("only an exact public reddit URL is eligible",()=>{
  assert.equal(core.isAllowedRedditUrl("https://www.reddit.com/r/dogs/comments/abc/title/"),true);
  assert.equal(core.isAllowedRedditUrl("https://reddit.com.evil.test/r/dogs/comments/abc/title/"),false);
  assert.equal(core.isAllowedRedditUrl("http://www.reddit.com/r/dogs/comments/abc/title/"),false);
  assert.equal(core.isAllowedRedditUrl("https://www.reddit.com/settings/"),false);
});

test("comment extraction preserves id parent depth and visible body",()=>{
  const row=core.extractComment(element({thingid:"t1_c2",parentid:"t1_c1",depth:"2",author:"u",score:"7",created:"2026-01-01",permalink:"/r/dogs/comments/p1/x/c2/"},"Useful reply"),"https://www.reddit.com");
  assert.deepEqual(row,{comment_id:"c2",parent_id:"c1",depth:2,author:"u",body:"Useful reply",score:7,created_at:"2026-01-01",comment_url:"https://www.reddit.com/r/dogs/comments/p1/x/c2/"});
});

test("invalid and oversized capture batches are rejected before transport",()=>{
  assert.throws(()=>core.validateCapture({comments:[]}),/page_url/);
  assert.throws(()=>core.validateCapture({page_url:"https://www.reddit.com/r/x/comments/y/z/",comments:[{comment_id:"c1",body:""}]}),/body/);
  assert.throws(()=>core.validateCapture({page_url:"https://www.reddit.com/r/x/comments/y/z/",comments:Array.from({length:501},(_,i)=>({comment_id:`c${i}`,body:"x",comment_url:`https://www.reddit.com/r/x/comments/y/z/c${i}/`}))}),/500/);
});

test("only valid marked Reddit pages participate in a run",()=>{
  const run="AbcdEFGHijklMNOP_1234567890abcd";
  assert.deepEqual(session.routeMarkedUrl(`https://www.reddit.com/search/?q=dogs#reddit-voc-run=${run}`),{action:"idle",run_id:run});
  assert.deepEqual(session.routeMarkedUrl(`https://www.reddit.com/r/dogs/comments/p1/title/#reddit-voc-run=${run}`),{action:"capture",run_id:run});
  assert.deepEqual(session.routeMarkedUrl(`https://www.reddit.com/r/dogs/comments/p2/next/#reddit-voc-run=${run}`),{action:"capture",run_id:run});
  assert.equal(session.routeMarkedUrl("https://www.reddit.com/r/dogs/comments/p1/title/").action,"ignore");
  assert.equal(session.routeMarkedUrl(`https://example.com/#reddit-voc-run=${run}`).action,"reject");
  assert.equal(session.routeMarkedUrl(`https://www.reddit.com.evil.test/#reddit-voc-run=${run}`).action,"reject");
  assert.equal(session.routeMarkedUrl("https://www.reddit.com/#reddit-voc-run=short").action,"reject");
});

test("automatic capture fingerprint suppresses unchanged duplicate batches",()=>{
  const payload={page_url:"https://www.reddit.com/r/dogs/comments/p1/title/",comments:[{comment_id:"b"},{comment_id:"a"}]};
  assert.equal(session.captureFingerprint(payload),session.captureFingerprint({...payload,comments:[{comment_id:"a"},{comment_id:"b"}]}));
  assert.notEqual(session.captureFingerprint(payload),session.captureFingerprint({...payload,comments:[...payload.comments,{comment_id:"c"}]}));
});

test("service worker accepts messages only from marked sender tab and fixed extension",()=>{
  const source=fs.readFileSync(path.join(ROOT,"extension/service_worker.js"),"utf8");
  assert.ok(!/chrome\.tabs\./.test(source));
  assert.match(source,/edpfinibjpbkdnognnhealnfepkeopem/);
  assert.match(source,/sender\.tab\?\.url/);
  assert.match(source,/authorize/);
  for(const forbidden of ["chrome.cookies","chrome.history","document.cookie","localStorage","sessionStorage","chrome.storage"])
    assert.ok(!source.includes(forbidden),`forbidden API: ${forbidden}`);
});

test("unmarked content script exits before reading the document",()=>{
  const source=fs.readFileSync(path.join(ROOT,"extension/auto_content.js"),"utf8");
  assert.match(source,/routeMarkedUrl\(location\.href\)/);
  assert.match(source,/if\(route\.action==="ignore"\)return/);
  assert.ok(source.indexOf('if(route.action==="ignore")return')<source.indexOf("document"));
});

test("multiple replies and continue-thread expand recursively with checkpoint",async()=>{
  const html=(comments,controls=[],count=3)=>`<section data-comment-count="${count}">${comments.map(([id,parent,depth,body])=>`<shreddit-comment thingid="t1_${id}" parentid="${parent}" depth="${depth}" permalink="/r/dogs/comments/p1/x/${id}/"><div slot="comment">${body}</div></shreddit-comment>`).join("")}${controls.map(([key,label,href=""])=>`<a data-key="${key}" href="${href}">${label}</a>`).join("")}</section>`;
  const states=[
    html([["c1","t3_p1",0,"one"]],[["a","more replies"],["b","continue this thread","/r/dogs/comments/p1/x/c1/"]]),
    html([["c1","t3_p1",0,"one"],["c2","t1_c1",1,"two"]],[["b","continue this thread","/r/dogs/comments/p1/x/c1/"]]),
    html([["c1","t3_p1",0,"one"],["c2","t1_c1",1,"two"],["c3","t1_c2",2,"three"]],[],3)
  ];
  const result=await visible.runFixtureExpansion(states,{post_id:"p1",max_expand_actions:10,thread_timeout:60});
  assert.equal(result.status,"PASS");
  assert.equal(result.audit.max_depth,2);
  assert.deepEqual(result.comments.map(x=>x.comment_id),["c1","c2","c3"]);
  assert.equal(result.checkpoint.expansion_actions.length,2);
  assert.equal(result.checkpoint.incomplete_frontier.length,0);
});

test("offline HTML fixture keeps visible deleted-author replies and filters removed bodies",()=>{
  const html=fs.readFileSync(path.join(ROOT,"tests/fixtures/extension-reddit-thread.html"),"utf8");
  const attr=text=>Object.fromEntries([...text.matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));
  const rows=[...html.matchAll(/<shreddit-comment\s+([^>]+)>\s*<div slot="comment">([\s\S]*?)<\/div>\s*<\/shreddit-comment>/g)]
    .map(m=>core.extractComment(element(attr(m[1]),m[2].replace(/<[^>]+>/g,"").trim()),"https://www.reddit.com"))
    .filter(row=>row.body&&!['[deleted]','[removed]'].includes(row.body));
  assert.deepEqual(rows.map(r=>[r.comment_id,r.parent_id,r.depth,r.author]),[
    ["top1","post1",0,"dog_owner"],
    ["reply1","top1",1,"[deleted]"]
  ]);
});

test("capture v3 reports filtering and duplicate statistics",()=>{
  const elements=[
    element({thingid:"t1_c1",parentid:"t3_p1",depth:"0",author:"a",permalink:"/r/dogs/comments/p1/x/c1/"},"kept"),
    element({thingid:"t1_c2",parentid:"t3_p1",depth:"0",author:"b",permalink:"/r/dogs/comments/p1/x/c2/"},"[removed]"),
    element({thingid:"t1_c3",parentid:"t3_p1",depth:"0",author:"c",permalink:"/r/dogs/comments/p1/x/c3/"},""),
    element({thingid:"t1_c1",parentid:"t3_p1",depth:"0",author:"a",permalink:"/r/dogs/comments/p1/x/c1/"},"duplicate")
  ];
  const post=element({id:"t3_p1","post-title":"title","subreddit-name":"dogs","comment-count":"4"});
  const doc={title:"title",querySelector:s=>s==="shreddit-post"?post:null,querySelectorAll:s=>s==="shreddit-comment"?elements:[]};
  const payload=core.captureDocument(doc,"https://www.reddit.com/r/dogs/comments/p1/x/");
  assert.equal(payload.schema_version,"reddit_visible_capture_v3");
  assert.deepEqual(payload.capture_stats,{scanned:4,filtered_blank:1,filtered_deleted_removed:1,filtered_bot:0,duplicates:1});
  assert.deepEqual(payload.comments.map(x=>x.comment_id),["c1"]);
});
