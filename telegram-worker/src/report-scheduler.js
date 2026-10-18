// Read-only reports only: Chromium remains in GitHub Actions.
export function dueReports(timestamp) {
  const local=new Date(timestamp+330*60000);
  const date=local.toISOString().slice(0,10);
  const minute=local.getUTCHours()*60+local.getUTCMinutes();
  const jobs=[];
  // Catch up for up to six hours after a delayed Worker invocation.
  if(minute>=600 && minute<960) {
    jobs.push({id:`expiry-${date}`,type:'expiry',date});
    if(local.getUTCDay()===0)jobs.push({id:`weekly-${date}`,type:'weekly',date});
  }
  if(minute>=1140 && minute<1440)jobs.push({id:`renewals-${date}`,type:'renewals',date});
  return jobs;
}
export async function scheduleReports(env,timestamp,fetcher=fetch) {
  if(env.REPORT_SCHEDULER_ENABLED!=='true')return;
  for(const job of dueReports(timestamp)) {
    const claimed=await env.DB.prepare("INSERT OR IGNORE INTO report_dispatches(id,report_type,report_date,state,created) VALUES(?,?,?,'dispatching',?)").bind(job.id,job.type,job.date,timestamp).run();
    if(!claimed.meta.changes)continue;
    let state='uncertain',status=0;
    try {
      const response=await fetcher(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.GITHUB_REPORT_WORKFLOW_FILE||'daily-reports.yml'}/dispatches`,{
        method:'POST',headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'Hathway-Reports','content-type':'application/json'},
        body:JSON.stringify({ref:env.GITHUB_REF,inputs:{report_type:job.type,report_date:job.date,send_telegram:'true'}}),signal:AbortSignal.timeout(10000)
      });
      status=response.status;
      state=response.ok?'queued':status>=400&&status<500?'rejected':'uncertain';
    } catch { /* Never blindly repeat a potentially accepted dispatch. */ }
    await env.DB.prepare('UPDATE report_dispatches SET state=?,http_status=? WHERE id=?').bind(state,status,job.id).run();
    console.log('report_schedule_dispatch',job.id,state,status);
    if(state!=='queued') {
      // Fixed operational notice only; no tokens, portal data, or raw errors.
      try {
        const {telegram}=await import('./index.js');
        for(const chat of (env.TELEGRAM_ADMIN_CHAT_IDS||'').split(',').map(x=>x.trim()).filter(Boolean))
          await telegram(env,chat,`Scheduled ${job.type} report for ${job.date}: GitHub dispatch ${state} (HTTP ${status||'unconfirmed'}). Check Actions before manually running this read-only report.`,fetcher);
      } catch { console.warn('report_schedule_notice_failed'); }
    }
  }
}
