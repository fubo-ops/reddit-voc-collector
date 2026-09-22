"use strict";
(function(root,factory){
  const api=factory();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  root.RedditCaptureCore=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  const MAX_COMMENTS=500;
  function strip(value){return String(value||"").replace(/^t[13]_/i,"")}
  function isAllowedRedditUrl(value){
    try{const u=new URL(value);return u.protocol==="https:"&&/^(www\.)?reddit\.com$/i.test(u.hostname)&&/^\/r\/[^/]+\/comments\/[^/]+\//i.test(u.pathname)}catch{return false}
  }
  function extractComment(el,origin){
    const permalink=el.getAttribute("permalink")||"";
    return{comment_id:strip(el.getAttribute("thingid")),parent_id:strip(el.getAttribute("parentid")||el.getAttribute("postid")),depth:Number(el.getAttribute("depth")||0),author:el.getAttribute("author")||"",body:String(el.querySelector('[slot="comment"]')?.innerText||"").trim(),score:Number(el.getAttribute("score")||0),created_at:el.getAttribute("created")||null,comment_url:new URL(permalink,origin).href}
  }
  function validateCapture(value){
    if(!value||!isAllowedRedditUrl(value.page_url))throw Error("page_url must be an exact public Reddit thread URL");
    if(!Array.isArray(value.comments))throw Error("comments must be an array");
    if(value.comments.length>MAX_COMMENTS)throw Error(`capture exceeds ${MAX_COMMENTS} comments`);
    const ids=new Set();
    for(const row of value.comments){
      if(!row.comment_id)throw Error("comment_id is required");
      if(!String(row.body||"").trim())throw Error("body is required");
      if(!isAllowedRedditUrl(row.comment_url))throw Error("comment_url must be a Reddit thread URL");
      if(ids.has(row.comment_id))throw Error("duplicate comment_id in capture"); ids.add(row.comment_id);
    }
    return value;
  }
  function captureDocument(doc,pageUrl){
    if(!isAllowedRedditUrl(pageUrl))throw Error("current tab is not an allowed Reddit thread");
    const post=doc.querySelector("shreddit-post"),elements=[...doc.querySelectorAll("shreddit-comment")],comments=[],seenIds=new Set(),seenUrls=new Set();
    let filteredBlank=0,filteredDeletedRemoved=0,filteredBot=0,duplicates=0;
    for(const el of elements){
      const row=extractComment(el,new URL(pageUrl).origin);
      if(!row.body){filteredBlank++;continue}
      if(["[deleted]","[removed]","版主已移除评论"].includes(row.body)){filteredDeletedRemoved++;continue}
      if(/\bi am a bot\b.*\b(action|performed|automatically)\b/is.test(row.body)){filteredBot++;continue}
      if(seenIds.has(row.comment_id)||seenUrls.has(row.comment_url)){duplicates++;continue}
      seenIds.add(row.comment_id);seenUrls.add(row.comment_url);comments.push(row);
    }
    const payload={schema_version:"reddit_visible_capture_v3",capture_id:crypto.randomUUID(),captured_at:new Date().toISOString(),page_url:pageUrl,post_id:strip(post?.getAttribute("id")||post?.getAttribute("post-id")||post?.getAttribute("thingid")),post_title:post?.getAttribute("post-title")||doc.title||"",subreddit:String(post?.getAttribute("subreddit-prefixed-name")||post?.getAttribute("subreddit-name")||"").replace(/^r\//i,""),platform_comment_count:Number(post?.getAttribute("comment-count")||0),unprocessed_expand_controls:doc.querySelectorAll('shreddit-comment a[slot="more-comments-permalink"]').length,capture_stats:{scanned:elements.length,filtered_blank:filteredBlank,filtered_deleted_removed:filteredDeletedRemoved,filtered_bot:filteredBot,duplicates},comments};
    return validateCapture(payload);
  }
  return{MAX_COMMENTS,isAllowedRedditUrl,extractComment,validateCapture,captureDocument};
});
