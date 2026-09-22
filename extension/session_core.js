"use strict";
(function(root,factory){
  const api=factory();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  root.RedditSessionCore=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  const RUN_ID_RE=/^[A-Za-z0-9_-]{24,64}$/;
  function stripFragment(value){try{const u=new URL(value);u.hash="";return u.href}catch{return""}}
  function parseRunId(value){try{const u=new URL(value),run=new URLSearchParams(u.hash.slice(1)).get("reddit-voc-run")||"";return RUN_ID_RE.test(run)?run:null}catch{return null}}
  function routeMarkedUrl(value){
    let u;try{u=new URL(value)}catch{return{action:"reject",run_id:null}}
    const rawMarker=new URLSearchParams(u.hash.slice(1)).get("reddit-voc-run"),run=parseRunId(value);
    if(!rawMarker)return{action:"ignore",run_id:null};
    if(u.protocol!=="https:"||u.hostname!=="www.reddit.com"||!run)return{action:"reject",run_id:null};
    return{action:/^\/r\/[^/]+\/comments\/[^/]+\//i.test(u.pathname)?"capture":"idle",run_id:run};
  }
  function withRunFragment(value,runId){if(!RUN_ID_RE.test(String(runId||"")))throw Error("invalid RUN_ID");const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="www.reddit.com")throw Error("not a Reddit URL");u.hash=`reddit-voc-run=${runId}`;return u.href}
  function captureFingerprint(payload){const ids=(payload?.comments||[]).map(x=>String(x.comment_id||"")).sort();return`${stripFragment(payload?.page_url||"")}\n${ids.join("\n")}`}
  return{RUN_ID_RE,stripFragment,parseRunId,routeMarkedUrl,withRunFragment,captureFingerprint};
});
