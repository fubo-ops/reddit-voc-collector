'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const DEFAULT_DELIVERY=String.raw`D:\Project\2026\SKILL\reddit评论采集`;
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function filename(asin,count,stamp){if(!/^[A-Z0-9]{10}$/.test(asin)||!Number.isInteger(count)||count<0||!/^\d{8}T\d{6}Z$/.test(stamp))throw Error('invalid_delivery_filename');return `${asin}_reddit评论_${count}条_${stamp}.xlsx`;}
function copyExclusive(source,destination){fs.mkdirSync(path.dirname(destination),{recursive:true});fs.copyFileSync(source,destination,fs.constants.COPYFILE_EXCL);const sha256=hash(source);if(hash(destination)!==sha256)throw Error('delivery_hash_mismatch');return {path:path.resolve(destination),sha256};}
function deliver(dir,destination=DEFAULT_DELIVERY){
  const read=n=>JSON.parse(fs.readFileSync(path.join(dir,n),'utf8').replace(/^\uFEFF/,'')),m=read('manifest.json'),v=read('validate.json');
  if(v.exit_code!==0||v.status!=='PASS')throw Error('delivery_validate_not_PASS');
  const copies=[];for(const f of m.workbooks||[{asin:m.asin,count:m.effective_comments??m.trusted_comments,path:m.excel_path,stamp:m.export_timestamp}]){
    const name=filename(f.asin,f.count,f.stamp),target=path.join(destination,name);
    if(fs.existsSync(target)){if(hash(target)!==hash(f.path))throw Error('delivery_destination_exists');copies.push({asin:f.asin,path:path.resolve(target),sha256:hash(target)});}else copies.push({asin:f.asin,...copyExclusive(f.path,target)});
  }
  m.deliveries=copies;m.delivery_excel_path=copies[0]?.path;m.delivery_excel_sha256=copies[0]?.sha256;
  fs.writeFileSync(path.join(dir,'manifest.json'),JSON.stringify(m,null,2));return copies;
}
module.exports={filename,hash,copyExclusive,deliver,DEFAULT_DELIVERY};
