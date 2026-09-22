"use strict";
importScripts("session_core.js");
const ENDPOINT="http://127.0.0.1:43127";
const FIXED_EXTENSION_ID="edpfinibjpbkdnognnhealnfepkeopem";
const sessions=new Map(),enc=new TextEncoder();
const hex=bytes=>[...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,"0")).join("");
async function sha256(text){return hex(await crypto.subtle.digest("SHA-256",enc.encode(text)))}
async function hmacHex(keyText,message){const key=await crypto.subtle.importKey("raw",enc.encode(keyText),{name:"HMAC",hash:"SHA-256"},false,["sign"]);return hex(await crypto.subtle.sign("HMAC",key,enc.encode(message)))}
async function postJson(path,body,headers={}){const response=await fetch(ENDPOINT+path,{method:"POST",headers:{"Content-Type":"application/json",...headers},body});const text=await response.text();let value;try{value=JSON.parse(text)}catch{value={error:text}}if(!response.ok)throw Error(value.error||`bridge HTTP ${response.status}`);return value}
function validateSender(message,sender){
  if(chrome.runtime.id!==FIXED_EXTENSION_ID||sender.id!==FIXED_EXTENSION_ID)throw Error("extension_id_mismatch");
  const senderUrl=sender.tab?.url||"",route=RedditSessionCore.routeMarkedUrl(senderUrl);
  if(route.action==="ignore")throw Error("unmarked_tab");if(route.action==="reject")throw Error("invalid_marked_url");
  if(route.run_id!==message.run_id)throw Error("run_id_mismatch");return{route,url:RedditSessionCore.stripFragment(senderUrl)};
}
async function authorize(runId,pageUrl){
  const origin=`chrome-extension://${FIXED_EXTENSION_ID}`;
  const value=await postJson("/v1/authorize",JSON.stringify({run_id:runId,extension_id:FIXED_EXTENSION_ID,page_url:pageUrl}),{"X-Extension-ID":FIXED_EXTENSION_ID,"X-Extension-Origin":origin});
  const session={sessionId:value.session_id,sessionKey:value.session_key,expiresAt:Date.now()+Number(value.expires_in||0)*1000,checkpoint:value.checkpoint||null,rootUrl:value.root_url||null};sessions.set(runId,session);return session;
}
async function signedSubmit(path,runId,payload,pageUrl){
  const session=await authorize(runId,pageUrl),body=JSON.stringify(payload),timestamp=String(Math.floor(Date.now()/1000)),nonce=crypto.randomUUID(),digest=await sha256(body);
  const canonical=`POST\n${path}\n${runId}\n${timestamp}\n${nonce}\n${digest}`,origin=`chrome-extension://${FIXED_EXTENSION_ID}`;
  return postJson(path,body,{"X-Extension-ID":FIXED_EXTENSION_ID,"X-Extension-Origin":origin,"X-Run-ID":runId,"X-Session-ID":session.sessionId,"X-Timestamp":timestamp,"X-Nonce":nonce,"X-Signature":await hmacHex(session.sessionKey,canonical)});
}
chrome.runtime.onMessage.addListener((message,sender,sendResponse)=>{(async()=>{
  if(!["bridge-authorize","bridge-submit"].includes(message?.type))return{status:"ignored"};
  const verified=validateSender(message,sender),session=await authorize(message.run_id,verified.url);
  if(message.type==="bridge-authorize")return{status:"ready",checkpoint:session.checkpoint,root_url:session.rootUrl};
  if(!["/v1/checkpoint","/v1/capture"].includes(message.path))throw Error("invalid_bridge_path");
  return signedSubmit(message.path,message.run_id,message.payload,verified.url);
})().then(sendResponse).catch(error=>sendResponse({status:"error",error:String(error.message||error)}));return true});
