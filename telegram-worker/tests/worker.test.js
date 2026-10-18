import {dueReports,scheduleReports} from '../src/report-scheduler.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker, {validate,process,dispatch,reconcile} from '../src/index.js';
function environment(){
 const sql=new DatabaseSync(':memory:');sql.exec(readFileSync(new URL('../schema.sql',import.meta.url),'utf8'));
 const env={TELEGRAM_BOT_TOKEN:'mock',TELEGRAM_WEBHOOK_SECRET:'secret',RESULT_CALLBACK_SECRET:'callback',TELEGRAM_ALLOWED_USER_IDS:'42',TELEGRAM_ALLOWED_CHAT_IDS:'42',GITHUB_TOKEN:'mock',GITHUB_OWNER:'owner',GITHUB_REPO:'repo',GITHUB_WORKFLOW_FILE:'renew.yml',GITHUB_REF:'main',BOX_PATTERN:'^[A-Za-z0-9-]{1,64}$'};
 env.DB={prepare(query){return {bind(...params){return {async run(){return {meta:{changes:Number(sql.prepare(query).run(...params).changes)}};},async first(){return sql.prepare(query).get(...params)||null;},async all(){return {results:sql.prepare(query).all(...params)};}};},async all(){return {results:sql.prepare(query).all()};}};}};
 return env;
}
const update=(text='000123',id=1)=>({update_id:id,message:{text,from:{id:42,first_name:'Test',last_name:'Member'},chat:{id:42,type:'private'}}});
const request=(data,path='/telegram/webhook',secret='secret')=>new Request('https://worker.example'+path,{method:'POST',headers:{'content-type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret,Authorization:'Bearer callback'},body:JSON.stringify(data)});
async function invoke(env,data,fetcher,path){
 const tasks=[];const original=globalThis.fetch;globalThis.fetch=fetcher;
 try{const response=await worker.fetch(request(data,path),env,{waitUntil(p){tasks.push(p);}});await Promise.all(tasks);return response;}
 finally{globalThis.fetch=original;}
}
function api(calls,status=204){return async(url,opts)=>{calls.push({url,body:JSON.parse(opts.body)});return url.includes('api.github.com')?new Response(null,{status}):Response.json({ok:true});};}
test('valid messages preserve leading zeros; user and private-chat authorization',()=>{
 const env=environment();assert.equal(validate(update(),env).text,'000123');
 const bad=update();bad.message.from.id=99;assert.equal(validate(bad,env),null);
 bad.message.from.id=42;bad.message.chat.type='group';assert.equal(validate(bad,env),null);
 bad.message.chat.type='private';bad.message.chat.id=99;assert.equal(validate(bad,env),null);
});
test('webhook authentication rejects invalid secret',async()=>{assert.equal((await worker.fetch(request(update(),undefined,'bad'),environment(),{})).status,401);});
test('valid dispatch sends queued acknowledgment only after acceptance; duplicate update and active box do not dispatch',async()=>{
 const env=environment(),calls=[];
 await invoke(env,update(),api(calls));await invoke(env,update(),api(calls));await invoke(env,update('000123',2),api(calls));
 assert.equal(calls.filter(x=>x.url.includes('api.github.com')).length,1);
 assert.equal(calls[0].body.inputs.box_number,'000123');assert.equal(calls[0].body.inputs.telegram_request_id,'tg-1');
 assert.match(calls[1].body.text,/Status: Queued/);
});
test('invalid box, unauthorized sender and commands never dispatch',async()=>{
 const env=environment(),calls=[];await invoke(env,update('invalid box'),api(calls));
 const bad=update();bad.message.from.id=99;await invoke(env,bad,api(calls));
 for(const text of ['/start','/help','/status'])await invoke(env,update(text),api(calls));
 assert.equal(calls.filter(x=>x.url.includes('api.github.com')).length,0);
 assert.match(calls[0].body.text,/Invalid box/);
});
test('GitHub rejection sends failure, not queued, and releases rejected box',async()=>{
 const env=environment(),calls=[];await invoke(env,update(),api(calls,401));
 assert.equal((await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind('tg-1').first()).active,0);
 assert.match(calls[1].body.text,/HTTP 401/);assert.doesNotMatch(calls[1].body.text,/Queued/);
});
test('ambiguous dispatch is claimed persistently and never resubmitted',async()=>{
 const env=environment();await invoke(env,update(),async()=>{throw Error('network');});
 let calls=0;await process(env,{id:'tg-1',box:'000123',chat_id:'42'},async()=>{calls++;});assert.equal(calls,0);
 assert.equal((await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind('tg-1').first()).state,'uncertain');
});
test('completion success/failure/unknown produce honest text and uncertain results retain lock',async()=>{
 for(const outcome of ['confirmed_success','confirmed_failure','reported_success','unknown','login_failure','captcha_failure','browser_failure']){
  const env=environment();await invoke(env,update(),api([]));
  const payload={request_id:'tg-1',chat_id:'42',run_id:'123',outcome,duration_seconds:134};
  const response=await invoke(env,payload,api([]),'/complete');assert.equal(response.status,200);
  const data=await response.json();assert.equal(data.notify,true);assert.match(data.message,/2m 14s/);
  const row=await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind('tg-1').first();
  if(['unknown','reported_success','browser_failure'].includes(outcome))assert.equal(row.active,1);
  else assert.equal(row.active,0);
  await invoke(env,payload,api([]),'/notified');
  assert.equal((await (await invoke(env,payload,api([]),'/complete')).json()).notify,false);
 }
});
test('callback rejects wrong chat and run and arbitrary outcome',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 assert.equal((await invoke(env,{request_id:'tg-1',chat_id:'99',run_id:'123',outcome:'unknown'},api([]),'/complete')).status,404);
 assert.equal((await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'made_up'},api([]),'/complete')).status,400);
});
test('cancelled workflow reconciliation reports unknown, never success',async()=>{
 const env=environment();await invoke(env,update(),api([]));const calls=[];
 await reconcile(env,async(url,opts)=>{
  if(url.includes('api.github.com'))return Response.json({workflow_runs:[{id:123,display_title:'Hathway Renewal tg-1',status:'completed',conclusion:'cancelled',updated_at:'2020-01-01T00:00:00Z'}]});
  calls.push(JSON.parse(opts.body));return Response.json({ok:true});
 });assert.match(calls[0].text,/cancelled/);assert.match(calls[0].text,/could not be verified/);
});
test('failed Telegram ack never redispatches; completion notification can be retried',async()=>{
 const env=environment();let dispatches=0;
 await invoke(env,update(),async(url)=>{if(url.includes('api.github.com')){dispatches++;return new Response(null,{status:204});}return Response.json({ok:false});});
 await invoke(env,update(),api([]));assert.equal(dispatches,1);
});
test('current GitHub API 200 records returned run ID and sends acknowledgment',async()=>{
 const env=environment(),calls=[];
 await invoke(env,update(),async(url,opts)=>{
  calls.push({url,body:JSON.parse(opts.body)});
  return url.includes('api.github.com')?Response.json({workflow_run_id:123}):Response.json({ok:true});
 });assert.equal((await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind('tg-1').first()).run_id,'123');assert.match(calls[1].body.text,/Queued/);
});
test('concurrent duplicate webhooks dispatch only once',async()=>{
 const env=environment(),calls=[],tasks=[],original=globalThis.fetch;globalThis.fetch=api(calls);
 try{
  const ctx={waitUntil(p){tasks.push(p);}};
  await Promise.all([worker.fetch(request(update()),env,ctx),worker.fetch(request(update()),env,ctx)]);
  await Promise.all(tasks);assert.equal(calls.filter(x=>x.url.includes('api.github.com')).length,1);
 }finally{globalThis.fetch=original;}
});
test('notification failure is retried by reconciliation without renewing again',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'unknown'},api([]),'/complete');
 await env.DB.prepare('UPDATE requests SET notify_after=0 WHERE id=?').bind('tg-1').run();
 let count=0;
 await reconcile(env,async()=>Response.json({ok:false}));
 assert.equal((await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind('tg-1').first()).notified,0);
 await reconcile(env,async(url)=>{assert.ok(!url.includes('api.github.com'));count++;return Response.json({ok:true});});
 assert.equal(count,1);assert.equal((await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind('tg-1').first()).notified,1);
});
test('blocked update stays a tombstone even after original box lock is released',async()=>{
 const env=environment(),calls=[];await invoke(env,update(),api(calls));await invoke(env,update('000123',2),api(calls));
 await env.DB.prepare('UPDATE requests SET active=0 WHERE id=?').bind('tg-1').run();
 await invoke(env,update('000123',2),api(calls));assert.equal(calls.filter(x=>x.url.includes('api.github.com')).length,1);
});

test('unauthorized member can request only their own IDs without renewal access',async()=>{
 const env=environment(),calls=[];
 const member=update('/whoami');member.message.from.id=99;member.message.chat.id=99;
 await invoke(env,member,api(calls));
 assert.equal(calls.length,1);assert.equal(calls[0].body.chat_id,'99');
 assert.match(calls[0].body.text,/User ID: 99/);assert.match(calls[0].body.text,/Chat ID: 99/);
 member.message.text='BOX123';await invoke(env,member,api(calls));assert.equal(calls.length,1);
 const rows=await env.DB.prepare('SELECT * FROM requests').all();assert.equal(rows.results.length,0);
});
test('identity command does not answer group chats',async()=>{
 const env=environment(),calls=[],member=update('/whoami');member.message.chat.type='group';
 await invoke(env,member,api(calls));assert.equal(calls.length,0);
});
test('member request notifies requester and owner; completion supplies owner for GitHub',async()=>{
 const env=environment(),calls=[];env.TELEGRAM_ADMIN_CHAT_IDS='99,42,99';
 await invoke(env,update(),api(calls));
 const queued=calls.filter(x=>x.url.includes('sendMessage'));
 assert.deepEqual(queued.map(x=>x.body.chat_id).sort(),['42','99']);
 assert.match(queued[1].body.text,/Requested by: Test Member/);
 const result=await (await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success'},api([]),'/complete')).json();
 assert.deepEqual(result.additional_chat_ids,['99']);
});
test('reconciled result also reaches owner and original member',async()=>{
 const env=environment();env.TELEGRAM_ADMIN_CHAT_IDS='99';await invoke(env,update(),api([]));
 await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'unknown'},api([]),'/complete');
 await env.DB.prepare('UPDATE requests SET notify_after=0 WHERE id=?').bind('tg-1').run();
 const recipients=[];
 await reconcile(env,async(url,opts)=>{recipients.push(JSON.parse(opts.body).chat_id);return Response.json({ok:true});});
 assert.deepEqual(recipients.sort(),['42','99']);
});

test('member name is retained for queued, completion and reconciled owner messages',async()=>{
 const env=environment(),calls=[];env.TELEGRAM_ADMIN_CHAT_IDS='99';
 const message=update();message.message.from.first_name='Ravi';message.message.from.last_name='Kumar';
 await invoke(env,message,api(calls));
 assert.match(calls[1].body.text,/Requested by: Ravi Kumar/);
 assert.doesNotMatch(calls[1].body.text,/Requested by chat/);
 const result=await (await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success'},api([]),'/complete')).json();
 assert.match(result.message,/Requested by: Ravi Kumar/);
 await env.DB.prepare('UPDATE requests SET notify_after=0 WHERE id=?').bind('tg-1').run();
 const notices=[];
 await reconcile(env,async(url,opts)=>{notices.push(JSON.parse(opts.body).text);return Response.json({ok:true});});
 assert.equal(notices.length,2);assert.ok(notices.every(text=>text.includes('Requested by: Ravi Kumar')));
});
test('names cannot inject extra message lines; numeric ID still controls authorization',async()=>{
 const env=environment(),message=update();
 message.message.from.first_name='Ravi\nStatus: Success';message.message.from.last_name='\u202E';
 assert.equal(validate(message,env).requester_name,'Ravi Status: Success');
 message.message.from.id=999;assert.equal(validate(message,env),null);
});

test('completion includes clear stage and safe reason without declaring uncertain submission failed',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 const result=await (await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'unknown',stage_code:'confirmation',reason_code:'confirmation_control_missing'},api([]),'/complete')).json();
 assert.match(result.message,/Stage: Confirm/);assert.match(result.message,/Reason: The Confirm button was not found/);
 assert.match(result.message,/Portal result: Unverified/);assert.doesNotMatch(result.message,/Renewal failed/);
});
test('retrack information is omitted while renewal result remains unchanged',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 const result=await (await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success',retrack_status:'failed',retrack_stage:'button',retrack_reason:'control_missing_or_timeout'},api([]),'/complete')).json();
 assert.match(result.message,/Renewal automation completed successfully/);
 assert.doesNotMatch(result.message,/retrack|Do not repeat renewal/i);
});
test('portal rejection reason, stage, attempts and account reach notifications',async()=>{
 for(const [reason,text] of [['insufficient_balance','Insufficient balance.'],['vc_terminated_or_missing','VC which you are searching is either Terminated or does not exist.']]) {
  const env=environment();await invoke(env,update(),api([]));
  const response=await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'confirmed_failure',stage_code:'submission',reason_code:reason,attempts:2,account_number:1,customer:{phone:'9000000000'}},api([]),'/complete');
  const result=await response.json();
  assert.ok(result.message.includes(text));assert.match(result.message,/Attempts: 2\/2/);assert.match(result.message,/Account: 1/);
  assert.doesNotMatch(result.message,/9000000000/);
 }
});
test('successful notification contains customer fields and account; missing fields are honest',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 const response=await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success',account_number:2,customer:{first_name:'Test\nPerson',last_name:'Member',phone:'+91 9000000000'}},api([]),'/complete');
 const result=await response.json();assert.match(result.message,/Customer name: Test Person Member/);assert.match(result.message,/Phone: \+91 9000000000/);assert.match(result.message,/Account: 2/);
 const second=environment();await invoke(second,update(),api([]));
 const missing=await (await invoke(second,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success'},api([]),'/complete')).json();
 assert.match(missing.message,/Customer name: Unavailable/);assert.match(missing.message,/Phone: Unavailable/);
});
test('older stored completion messages also omit Retrack details',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 await env.DB.prepare("UPDATE requests SET outcome='reported_success', message=?, run_id='123' WHERE id=?").bind('Renewal automation completed successfully.\nRetrack: Completed\nRetrack stage: Retrack response\nRetrack reason: Successful\nDo not repeat renewal to retry Retrack.','tg-1').run();
 const result=await (await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success'},api([]),'/complete')).json();
 assert.match(result.message,/Renewal automation completed successfully/);
 assert.doesNotMatch(result.message,/retrack/i);
});
test('Customer Name is delivered verbatim without splitting first and last names',async()=>{
 const env=environment();await invoke(env,update(),api([]));
 const result=await (await invoke(env,{request_id:'tg-1',chat_id:'42',run_id:'123',outcome:'reported_success',account_number:2,customer:{full_name:'Example Full Customer Name',phone:'9000000000'}},api([]),'/complete')).json();
 assert.match(result.message,/Customer name: Example Full Customer Name/);
 assert.match(result.message,/Phone: 9000000000/);
 assert.match(result.message,/Account: 2/);
 assert.doesNotMatch(result.message,/First name:|Last name:|Retrack/i);
});


test('report times use IST, Sunday includes weekly, and catch-up is bounded',()=>{
 assert.deepEqual(dueReports(Date.parse('2026-10-19T04:29:00Z')),[]);
 assert.deepEqual(dueReports(Date.parse('2026-10-19T04:30:00Z')).map(x=>x.type),['expiry']);
 assert.deepEqual(dueReports(Date.parse('2026-10-18T04:30:00Z')).map(x=>x.type),['expiry','weekly']);
 assert.deepEqual(dueReports(Date.parse('2026-10-19T13:30:00Z')).map(x=>x.type),['renewals']);
 assert.deepEqual(dueReports(Date.parse('2026-10-19T11:00:00Z')),[]);
});
test('report dispatch is persistent and uses existing report workflow, not renewal',async()=>{
 const env=environment();env.REPORT_SCHEDULER_ENABLED='true';const calls=[];
 const time=Date.parse('2026-10-19T04:30:00Z');
 await scheduleReports(env,time,api(calls));await scheduleReports(env,time+300000,api(calls));
 assert.equal(calls.length,1);assert.ok(calls[0].url.includes('/daily-reports.yml/dispatches'));
 assert.deepEqual(calls[0].body.inputs,{report_type:'expiry',report_date:'2026-10-19',send_telegram:'true'});
});
test('uncertain report dispatch is not repeated',async()=>{
 const env=environment();env.REPORT_SCHEDULER_ENABLED='true';let calls=0;
 const fetcher=async()=>{calls++;throw Error('mock network failure');};const time=Date.parse('2026-10-19T13:30:00Z');
 await scheduleReports(env,time,fetcher);await scheduleReports(env,time+300000,fetcher);assert.equal(calls,1);
 const row=await env.DB.prepare('SELECT * FROM report_dispatches WHERE id=?').bind('renewals-2026-10-19').first();assert.equal(row.state,'uncertain');
});
