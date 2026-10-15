// No portal access or browser runtime. D1 is the durable source of truth.
const json = (data, status=200) => new Response(JSON.stringify(data), {status, headers:{'content-type':'application/json'}});
const ids = value => new Set((value || '').split(',').map(x=>x.trim()).filter(Boolean));
export function memberName(message) {
  const parts=[message.from?.first_name,message.from?.last_name]
    .filter(value=>typeof value==='string');
  return parts.join(' ').replace(/[\p{Cc}\p{Cf}]/gu,' ').replace(/\s+/g,' ').trim().slice(0,80) || 'Telegram member';
}
async function requesterName(env,row) {
  const entry=await env.DB.prepare('SELECT display_name FROM requester_names WHERE request_id=?').bind(row.id).first();
  return entry?.display_name || 'Telegram member';
}
export function validate(update, env) {
  const m=update.message;
  if ((!Number.isSafeInteger(update.update_id) || update.update_id < 0) || !m || m.chat?.type !== 'private' ||
      !ids(env.TELEGRAM_ALLOWED_USER_IDS).has(String(m.from?.id)) ||
      !ids(env.TELEGRAM_ALLOWED_CHAT_IDS).has(String(m.chat?.id))) return null;
  if (typeof m.text !== 'string' || m.text.length > 128) return null;
  return {id:`tg-${update.update_id}`, update_id:update.update_id, chat_id:String(m.chat.id), text:m.text.trim(), requester_name:memberName(m)};
}
export async function telegram(env, chat, text, fetcher=fetch) {
  let response;
  try {response=await fetcher(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method:'POST', headers:{'content-type':'application/json'},
    body:JSON.stringify({chat_id:chat,text}), signal:AbortSignal.timeout(10000)
  });
  } catch {
    console.warn('telegram_send_transport_failed');
    throw new Error('Telegram connection failed');
  }
  if (!response.ok) {
    console.warn('telegram_send_http_error', response.status);
    throw new Error('Telegram notification rejected');
  }
  let result;
  try {result=await response.json();} catch {
    console.warn('telegram_send_invalid_response');
    throw new Error('Telegram response invalid');
  }
  if (!result.ok) {
    console.warn('telegram_send_api_rejected', Number.isInteger(result.error_code)?result.error_code:0);
    throw new Error('Telegram notification rejected');
  }
  console.info('telegram_reply_sent');
}
export async function dispatch(env, row, fetcher=fetch) {
  return fetcher(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.GITHUB_WORKFLOW_FILE}/dispatches`, {
    method:'POST', headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'Hathway-Telegram','content-type':'application/json'},
    body:JSON.stringify({ref:env.GITHUB_REF,inputs:{box_number:row.box,telegram_enabled:'true',telegram_chat_id:row.chat_id,telegram_request_id:row.id}}),
    signal:AbortSignal.timeout(15000)
  });
}
export function notificationChats(env, requester) {
  return [...new Set([String(requester), ...ids(env.TELEGRAM_ADMIN_CHAT_IDS)])]
    .filter(chat => /^\d+$/.test(chat));
}
async function broadcast(env, requester, text, fetcher=fetch) {
  const results=await Promise.allSettled(notificationChats(env,requester).map(chat=>telegram(env,chat,text,fetcher)));
  if(results.some(result=>result.status==='rejected')) throw new Error('Notification delivery incomplete');
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
  try { await broadcast(env,row.chat_id,`Renewal request received.\nBox: ${row.box}\nRequested by: ${await requesterName(env,row)}\nStatus: Queued\nRequest: ${row.id}`,fetcher); } catch {}
}
async function notify(env,id,fetcher=fetch) {
  const row=await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind(id).first();
  if (!row || row.notified || !row.message) return;
  await broadcast(env,row.chat_id,`${row.message}\nBox: ${row.box}\nRequested by: ${await requesterName(env,row)}\nRequest: ${row.id}${row.run_id?`\nRun: https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${row.run_id}`:''}`,fetcher);
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
      const descriptions={navigation_failure:'Package Management navigation failed; renewal was not reached.',confirmed_success:'Renewal successful.\nVerification: Confirmed.',confirmed_failure:'Renewal failed.\nVerification: Confirmed unsuccessful.',reported_success:'Renewal automation completed successfully.\nVerification: Success reported by automation; independent portal check unavailable.',unknown:'Renewal automation did not confirm completion.\nPortal result: Unverified. Check Hathway before retrying.',login_failure:'Hathway login failed; renewal was not reached.',browser_failure:'Browser execution failed; renewal result is unknown.',captcha_failure:'CAPTCHA/login attempts failed; renewal was not reached.',configuration_error:'Configuration invalid; renewal was not started.'};
      const reasons={final_confirmation_error:'Final confirmation error',confirmation_error:'Confirmation step error',submission_error:'Submission step error',plan_selection_error:'Plan selection error',bouquet_selection_error:'Bouquet selection error',add_plan_error:'Add Plan error',main_tv_error:'Main TV selection error',box_search_error:'Box search error'};
      const stages={configuration:'Configuration',login:'Hathway login',captcha:'CAPTCHA recognition',navigation:'Package Management navigation',box_search:'Box search',main_tv:'Main TV selection',add_plan:'Add Plan',bouquet_selection:'Bouquet selection',plan_selection:'Plan selection',submission:'Submit',confirmation:'Confirm',final_confirmation:'Final confirmation',verification:'Portal verification',browser:'Browser execution',renewal:'Renewal processing'};
      const details={verified:'Portal verification confirmed success.',automation_reported_success:'The existing renewal flow returned success.',portal_confirmed_failure:'Portal verification confirmed the renewal did not complete.',invalid_configuration:'Required configuration or input is missing or invalid.',login_not_completed:'Hathway login did not complete after its attempts.',captcha_attempts_exhausted:'CAPTCHA recognition/login attempts were exhausted.',package_management_unavailable:'Package Management could not be opened.',browser_execution_error:'Browser execution raised an error; transaction state could not be verified.',confirmation_control_missing:'The Confirm button was not found or was not visible.',popup_blocked_action:'An open popup blocked the required action.',element_timeout:'A required page element did not become usable before timeout.',required_element_missing:'A required portal element was not found.',submission_outcome_uncertain:'Submission may have occurred; automatic retries were stopped.',no_verified_result:'The automation returned no verified renewal result.'};
      const detail=stages[data.stage_code]&&details[data.reason_code]?`\nStage: ${stages[data.stage_code]}\nReason: ${details[data.reason_code]}`:'';
      const reason=reasons[data.failure_reason_code]?`\nFailure stage: ${reasons[data.failure_reason_code]}`:'';
      const retrackStatuses={completed:'Completed (portal reported success)',already_requested:'Already requested; Hathway did not accept a new request',failed:'Failed',unknown:'Unverified'};
      const retrackStages={wait:'One-minute wait',context:'Box context check',button:'Retrack button',confirm:'Retrack confirmation',result:'Retrack response',ok:'Retrack OK acknowledgment'};
      const retrackReasons={portal_reported_success:'Hathway reported successful request submission.',cooldown_15_minutes:'Hathway requires a 15-minute gap between retrack requests for the same customer. No automatic retry.',portal_rejected:'Hathway rejected the retrack request.',unrecognized_response:'The retrack response did not confirm success.',box_context_mismatch:'The page no longer showed the requested box; no Retrack click was made.',control_missing_or_timeout:'The required control was missing, blocked or timed out. No automatic retry.'};
      const retrack=retrackStatuses[data.retrack_status]?`\nRetrack: ${retrackStatuses[data.retrack_status]}\nRetrack stage: ${retrackStages[data.retrack_stage]||'Unavailable'}\nRetrack reason: ${retrackReasons[data.retrack_reason]||'Unavailable'}\nDo not repeat renewal to retry Retrack.`:'';
      const duration=Number.isFinite(data.duration_seconds)?`\nDuration: ${Math.floor(data.duration_seconds/60)}m ${Math.floor(data.duration_seconds%60)}s`:'';
      // First terminal report wins. Unknown/reported-success keeps box locked for review.
      await env.DB.prepare("UPDATE requests SET state='completed', outcome=?, message=?, run_id=?, active=?, notified=0, notify_after=? WHERE id=? AND outcome IS NULL")
        .bind(data.outcome,descriptions[data.outcome]+detail+(detail?'':reason)+retrack+duration,String(data.run_id),['confirmed_success','confirmed_failure','navigation_failure','login_failure','captcha_failure','configuration_error'].includes(data.outcome)?0:1,Date.now()+300000,row.id).run();
      const stored=await env.DB.prepare('SELECT * FROM requests WHERE id=?').bind(row.id).first();
      return json({accepted:true,notify:!stored.notified,additional_chat_ids:notificationChats(env,stored.chat_id).filter(chat=>chat!==stored.chat_id),message:`${stored.message}\nBox: ${stored.box}\nRequested by: ${await requesterName(env,stored)}\nRequest: ${stored.id}\nRun: https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${stored.run_id}`});
    }
    if(path!=='/telegram/webhook') return json({error:'not found'},404);
    // Identity lookup grants no renewal access and works only in the sender's private chat.
    const identityMessage=data.message;
    if(identityMessage?.chat?.type==='private' && identityMessage.text?.trim()==='/whoami' &&
       Number.isSafeInteger(identityMessage.from?.id) && Number.isSafeInteger(identityMessage.chat.id) &&
       identityMessage.from.id===identityMessage.chat.id) {
      ctx.waitUntil(telegram(env,String(identityMessage.chat.id),
        `Your Telegram User ID: ${identityMessage.from.id}\nYour Private Chat ID: ${identityMessage.chat.id}\nShare these IDs with the bot owner to request access. This command does not authorize renewals.`).catch(()=>{}));
      return json({ok:true});
    }
    const input=validate(data,env);
    if(!input) {
      const message=data.message;
      if(!message || message.chat?.type!=='private') console.info('telegram_update_ignored_not_private_message');
      else if(!ids(env.TELEGRAM_ALLOWED_USER_IDS).has(String(message.from?.id))) console.warn('telegram_sender_not_in_allowlist');
      else if(!ids(env.TELEGRAM_ALLOWED_CHAT_IDS).has(String(message.chat?.id))) console.warn('telegram_chat_not_in_allowlist');
      else console.info('telegram_update_ignored_unsupported_format');
      return json({ignored:true});
    }
    console.info('telegram_authorized_message_received');
    const commands={'/start':'Welcome to Hathway Renewal Bot.\n\nSend your box number to start a renewal.','/help':`Send one box number. Format: ${env.BOX_PATTERN || '^[A-Za-z0-9-]{1,64}$'}\n/start /help /status\nDo not repeat an uncertain renewal.`, '/status':'Completion notifications arrive automatically. A queued acknowledgment means GitHub accepted the request, not that renewal has started.'};
    if(commands[input.text]) {ctx.waitUntil(telegram(env,input.chat_id,commands[input.text]).catch(()=>{}));return json({ok:true});}
    let pattern; try { pattern=new RegExp(env.BOX_PATTERN || '^[A-Za-z0-9-]{1,64}$'); } catch { return json({error:'pattern configuration'},500); }
    const match=pattern.exec(input.text);
    if(!match || match[0]!==input.text || !input.text) {ctx.waitUntil(telegram(env,input.chat_id,'Invalid box number. Send /help for the configured format.').catch(()=>{}));return json({ok:true});}
    try {
      await env.DB.prepare('INSERT OR IGNORE INTO requester_names(request_id,display_name) VALUES(?,?)').bind(input.id,input.requester_name).run();
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
          .bind(`Renewal result could not be verified.\nStage: Workflow completion\nReason: Workflow ended (${run.conclusion}) without a usable completion result. Check Hathway before retrying.`,String(run.id),row.id).run();
        await notify(env,row.id,fetcher);
      } else if(!run && Date.now()-row.created>3600000) {
        await env.DB.prepare("UPDATE requests SET state='uncertain', outcome='unknown', message=? WHERE id=? AND outcome IS NULL")
          .bind('GitHub dispatch could not be reconciled. Renewal result is unknown; inspect Actions and the portal before retrying.',row.id).run();
        await notify(env,row.id,fetcher);
      }
    } catch { /* Retry notifications/reconciliation later, never a claimed dispatch. */ }
  }
}
