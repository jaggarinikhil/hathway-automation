// No portal access or browser runtime. D1 is the durable source of truth.
const json = (data, status=200) => new Response(JSON.stringify(data), {status, headers:{'content-type':'application/json'}});
const ids = value => new Set((value || '').split(',').map(x=>x.trim()).filter(Boolean));
export function validate(update, env) {
  const m=update.message;
  if ((!Number.isSafeInteger(update.update_id) || update.update_id < 0) || !m || m.chat?.type !== 'private' ||
      !ids(env.TELEGRAM_ALLOWED_USER_IDS).has(String(m.from?.id)) ||
      !ids(env.TELEGRAM_ALLOWED_CHAT_IDS).has(String(m.chat?.id))) return null;
  if (typeof m.text !== 'string' || m.text.length > 128) return null;
  return {id:`tg-${update.update_id}`, update_id:update.update_id, chat_id:String(m.chat.id), text:m.text.trim()};
}
export async function telegram(env, chat, text, fetcher=fetch) {
  const response=await fetcher(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({chat_id:chat,text}), signal:AbortSignal.timeout(10000)
  });
  if (!response.ok || !(await response.json()).ok) throw new Error('Telegram notification rejected');
}
export async function dispatch(env, row, fetcher=fetch) {
  return fetcher(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.GITHUB_WORKFLOW_FILE}/dispatches`, {
    method:'POST', headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'Hathway-Telegram','content-type':'application/json'},
    body:JSON.stringify({ref:env.GITHUB_REF,inputs:{box_number:row.box,telegram_enabled:'true',telegram_chat_id:row.chat_id,telegram_request_id:row.id}}),
    signal:AbortSignal.timeout(15000)
  });
}
export async function process(env, row, fetcher=fetch) {
  // Atomic claim BEFORE external dispatch: ambiguous network outcomes are never retried.
  const claimed=await env.DB.prepare("UPDATE requests SET state='dispatching' WHERE id=? AND state='pending'").bind(row.id).run();
  if (!claimed.meta.changes) return;
  let response;
  try { response=await dispatch(env,row,fetcher); }
  catch {
    await env.DB.prepare("UPDATE requests SET state='uncertain' WHERE id=? AND state='dispatching'").bind(row.id).run();
    try {await telegram(env,row.chat_id,`GitHub dispatch could not be confirmed. Request: ${row.id}. Do not retry until Actions and portal status are checked.`,fetcher);} catch {}
    return;
  }
  if (![200,204].includes(response.status)) {
    // 5xx may be ambiguous; keep box locked. 4xx explicitly rejected the dispatch.
    const rejected=response.status >=400 && response.status <500;
    await env.DB.prepare('UPDATE requests SET state=?, active=?, outcome=?, message=? WHERE id=?')
      .bind(rejected?'rejected':'uncertain',rejected?0:1,'dispatch_failure',`GitHub dispatch returned HTTP ${response.status}. No renewal success is confirmed.`,row.id).run();
    await notify(env,row.id,fetcher); return;
  }
  let runId=null;
  if(response.status===200) {
    try {const data=await response.json(); if(Number.isSafeInteger(data.workflow_run_id))runId=String(data.workflow_run_id);} catch {}
  }
  await env.DB.prepare("UPDATE requests SET state='queued', run_id=? WHERE id=? AND state='dispatching'").bind(runId,row.id).run();
  // If acknowledgment fails, do not dispatch again. Completion still proceeds.
  try { await telegram(env,row.chat_id,`Renewal request received.\nBox: ${row.box}\nStatus: Queued\nRequest: ${row.id}`,fetcher); } catch {}
}
async function notify(env,id,fetcher=fetch) {
  const row=await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind(id).first();
  if (!row || row.notified || !row.message) return;
  await telegram(env,row.chat_id,`${row.message}\nBox: ${row.box}\nRequest: ${row.id}${row.run_id?`\nRun: https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${row.run_id}`:''}`,fetcher);
  await env.DB.prepare('UPDATE requests SET notified=1 WHERE id=?').bind(id).run();
}
const outcomes=new Set(['confirmed_success','confirmed_failure','reported_success','unknown','navigation_failure','login_failure','browser_failure','captcha_failure','configuration_error']);
export default {
  async fetch(request,env,ctx) {
    const path=new URL(request.url).pathname;
    if(request.method!=='POST') return json({error:'method'},405);
    const expected=path==='/telegram/webhook'?env.TELEGRAM_WEBHOOK_SECRET:env.RESULT_CALLBACK_SECRET;
    const supplied=path==='/telegram/webhook'?request.headers.get('X-Telegram-Bot-Api-Secret-Token'):request.headers.get('Authorization')?.replace(/^Bearer /,'');
    if(!expected || supplied!==expected) return json({error:'unauthorized'},401);
    if(Number(request.headers.get('content-length'))>16384) return json({error:'size'},413);
    let data; try { const text=await request.text(); if(text.length>16384) return json({error:'size'},413); data=JSON.parse(text); } catch { return json({error:'json'},400); }
    if(path==='/notified') {
      if(!/^tg-\d+$/.test(data.request_id || '') || !/^\d+$/.test(String(data.run_id))) return json({error:'result'},400);
      await env.DB.prepare('UPDATE requests SET notified=1 WHERE id=? AND run_id=? AND chat_id=?').bind(data.request_id,String(data.run_id),String(data.chat_id)).run();
      return json({accepted:true});
    }
    if(path==='/complete') {
      if(!/^tg-\d+$/.test(data.request_id || '') || !outcomes.has(data.outcome) || !/^\d+$/.test(String(data.run_id))) return json({error:'result'},400);
      const row=await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind(data.request_id).first();
      if(!row || row.chat_id!==String(data.chat_id)) return json({error:'request'},404);
      if(row.run_id && row.run_id!==String(data.run_id)) return json({error:'run mismatch'},409);
      // Fixed outcome labels avoid accepting arbitrary portal content into messages.
      const descriptions={navigation_failure:'Package Management navigation failed; renewal was not reached.',confirmed_success:'Renewal verified successfully.',confirmed_failure:'Renewal confirmed unsuccessful.',reported_success:'Automation reported success. Independent portal verification is unavailable.',unknown:'Renewal result is unknown. Check the portal before retrying.',login_failure:'Hathway login failed; renewal was not reached.',browser_failure:'Browser execution failed; renewal result is unknown.',captcha_failure:'CAPTCHA/login attempts failed; renewal was not reached.',configuration_error:'Configuration invalid; renewal was not started.'};
      const reasons={final_confirmation_error:'Final confirmation error',confirmation_error:'Confirmation step error',submission_error:'Submission step error',plan_selection_error:'Plan selection error',bouquet_selection_error:'Bouquet selection error',add_plan_error:'Add Plan error',main_tv_error:'Main TV selection error',box_search_error:'Box search error'};
      const reason=reasons[data.failure_reason_code]?`\nFailure stage: ${reasons[data.failure_reason_code]}`:'';
      const duration=Number.isFinite(data.duration_seconds)?`\nDuration: ${Math.floor(data.duration_seconds/60)}m ${Math.floor(data.duration_seconds%60)}s`:'';
      // First terminal report wins. Unknown/reported-success keeps box locked for review.
      await env.DB.prepare("UPDATE requests SET state='completed', outcome=?, message=?, run_id=?, active=?, notified=0, notify_after=? WHERE id=? AND outcome IS NULL")
        .bind(data.outcome,descriptions[data.outcome]+reason+duration,String(data.run_id),['confirmed_success','confirmed_failure','navigation_failure','login_failure','captcha_failure','configuration_error'].includes(data.outcome)?0:1,Date.now()+300000,row.id).run();
      const stored=await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind(row.id).first();
      return json({accepted:true,notify:!stored.notified,message:`${stored.message}\nBox: ${stored.box}\nRequest: ${stored.id}\nRun: https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${stored.run_id}`});
    }
    if(path!=='/telegram/webhook') return json({error:'not found'},404);
    const input=validate(data,env); if(!input) return json({ignored:true});
    const commands={'/start':'Welcome to Hathway Renewal Bot.\n\nSend your box number to start a renewal.','/help':`Send one box number. Format: ${env.BOX_PATTERN || '^[A-Za-z0-9-]{1,64}$'}\n/start /help /status\nDo not repeat an uncertain renewal.`, '/status':'Completion notifications arrive automatically. A queued acknowledgment means GitHub accepted the request, not that renewal has started.'};
    if(commands[input.text]) {ctx.waitUntil(telegram(env,input.chat_id,commands[input.text]).catch(()=>{}));return json({ok:true});}
    let pattern; try { pattern=new RegExp(env.BOX_PATTERN || '^[A-Za-z0-9-]{1,64}$'); } catch { return json({error:'pattern configuration'},500); }
    const match=pattern.exec(input.text);
    if(!match || match[0]!==input.text || !input.text) {ctx.waitUntil(telegram(env,input.chat_id,'Invalid box number. Send /help for the configured format.').catch(()=>{}));return json({ok:true});}
    try {
      const inserted=await env.DB.prepare('INSERT OR IGNORE INTO requests(id,update_id,chat_id,box,created) VALUES(?,?,?,?,?)').bind(input.id,input.update_id,input.chat_id,input.text,Date.now()).run();
      if(!inserted.meta.changes) {
        const existing=await env.DB.prepare('SELECT id FROM requests WHERE update_id=?').bind(input.update_id).first();
        if(!existing) {
          // Tombstone blocked updates, so later redelivery cannot become a new renewal.
          await env.DB.prepare("INSERT OR IGNORE INTO requests(id,update_id,chat_id,box,created,state,active) VALUES(?,?,?,?,?,'blocked',0)").bind(input.id,input.update_id,input.chat_id,input.text,Date.now()).run();
          ctx.waitUntil(telegram(env,input.chat_id,'This box has an active or uncertain request. Check its portal outcome before retrying.').catch(()=>{}));
        }
        return json({duplicate:true});
      }
    } catch { return json({error:'storage unavailable'},503); }
    ctx.waitUntil(process(env,{...input,box:input.text}).catch(()=>{}));
    return json({accepted:true});
  },
  async scheduled(event,env,ctx) {ctx.waitUntil(reconcile(env));}
};
export async function reconcile(env,fetcher=fetch) {
  const {results}=await env.DB.prepare("SELECT * FROM requests WHERE state IN ('pending','dispatching','uncertain','queued') AND outcome IS NULL UNION SELECT * FROM requests WHERE message IS NOT NULL AND notified=0 LIMIT 5").all();
  let runs;
  for(const row of results) {
    try {
      if(row.message) {if(Date.now() >= row.notify_after) await notify(env,row.id,fetcher);continue;}
      if(row.state==='pending') {await process(env,row,fetcher);continue;}
      let run;
      if(row.run_id) {
        const response=await fetcher(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${row.run_id}`,{headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','User-Agent':'Hathway-Telegram'},signal:AbortSignal.timeout(10000)});
        if(!response.ok)continue;
        run=await response.json();
      } else {
      if(!runs) {
        const response=await fetcher(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.GITHUB_WORKFLOW_FILE}/runs?event=workflow_dispatch&per_page=100`,{headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','User-Agent':'Hathway-Telegram'},signal:AbortSignal.timeout(10000)});
        if(!response.ok) return;
        runs=(await response.json()).workflow_runs;
      }
      run=runs.find(r=>r.display_title===`Hathway Renewal ${row.id}`);
      }
      // Give the completion callback five minutes to arrive. Never infer portal result from job conclusion.
      if(run?.status==='completed' && Date.now()-Date.parse(run.updated_at)>300000) {
        await env.DB.prepare("UPDATE requests SET state='completed', outcome='unknown', message=?, run_id=? WHERE id=? AND outcome IS NULL")
          .bind(`Workflow finished (${run.conclusion}). Renewal result is unknown; inspect the portal before retrying.`,String(run.id),row.id).run();
        await notify(env,row.id,fetcher);
      } else if(!run && Date.now()-row.created>3600000) {
        await env.DB.prepare("UPDATE requests SET state='uncertain', outcome='unknown', message=? WHERE id=? AND outcome IS NULL")
          .bind('GitHub dispatch could not be reconciled. Renewal result is unknown; inspect Actions and the portal before retrying.',row.id).run();
        await notify(env,row.id,fetcher);
      }
    } catch { /* Retry notifications/reconciliation later, never a claimed dispatch. */ }
  }
}
