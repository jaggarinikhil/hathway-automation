// Reuse the existing five-minute Cloudflare timer and repository-scoped token.
export function rvrSlot(timestamp) {
  const local = new Date(timestamp + 330 * 60000);
  const minute = local.getUTCHours() * 60 + local.getUTCMinutes();
  if (minute < 360 || minute % 10 !== 0) return null;
  return local.toISOString().slice(0, 16);
}

export async function scheduleRvr(env, timestamp, fetcher = fetch, now = Date.now()) {
  if (env.RVR_SCHEDULER_ENABLED === 'false') return;
  const slot = rvrSlot(timestamp);
  // Never replay a stale tick or run outside the India monitoring window.
  if (!slot || now - timestamp > 5 * 60000 || timestamp > now + 60000) return;
  const id = `rvr-${slot}`;
  const claimed = await env.DB.prepare("INSERT OR IGNORE INTO report_dispatches(id,report_type,report_date,state,created) VALUES(?,?,?,'dispatching',?)")
    .bind(id, 'rvr', slot.slice(0, 10), timestamp).run();
  if (!claimed.meta.changes) return;
  let state = 'uncertain', status = 0;
  try {
    const response = await fetcher(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/rvr-monitor.yml/dispatches`, {
      method: 'POST',
      headers: {Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: 'application/vnd.github+json', 'User-Agent': 'RVR-Scheduler', 'content-type': 'application/json'},
      body: JSON.stringify({ref: env.GITHUB_REF, inputs: {dry_run: 'false'}}),
      signal: AbortSignal.timeout(10000)
    });
    status = response.status;
    state = response.ok ? 'queued' : status >= 400 && status < 500 ? 'rejected' : 'uncertain';
  } catch { /* Do not duplicate a dispatch after an ambiguous network failure. */ }
  await env.DB.prepare('UPDATE report_dispatches SET state=?,http_status=? WHERE id=?').bind(state, status, id).run();
  console.log('rvr_schedule_dispatch', slot, state, status);
}
