/**
 * fantasy-trigger: the scheduler and Telegram command bot for the fantasy workflows.
 *
 * GitHub Actions does the work; this Worker only decides WHEN. GitHub's own cron queue delivered about
 * one scheduled run every 2-3 hours for the whole repo (measured Oct 2026), so the workflows no longer
 * carry a schedule. Cloudflare ticks this Worker every 10 minutes, it works out which Central-time slot
 * (if any) falls inside that tick, and starts the matching workflow through the workflow_dispatch API,
 * which GitHub serves immediately. The same dispatch call answers Telegram commands (/check, /waivers,
 * ...) so a report can be requested from the phone at any time.
 *
 * Secrets (set with setup.sh): GITHUB_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_SECRET
 * Vars (wrangler.toml): GITHUB_REPO, GITHUB_REF, DASHBOARD_URL
 */

const TICK_MIN = 10; // must match the cron in wrangler.toml
const TZ = "America/Chicago";

export const JOBS = {
  check:   { workflow: "check.yml",   label: "lineup check" },
  waivers: { workflow: "waivers.yml", label: "waiver report" },
  recap:   { workflow: "recap.yml",   label: "weekly recap" },
  live:    { workflow: "live.yml",    label: "live update" },
  watch:   { workflow: "watch.yml",   label: "status watch" },
};

// Central-time weekly schedule. days: 0=Sun .. 6=Sat. `at` fires once; `every` fires on that minute
// interval inside [from, to), which defaults to the whole day. DST is handled by asking Intl for the
// Central wall clock, so nothing here needs a second copy per offset.
export const SCHEDULE = [
  { job: "check",   days: [1, 3, 4, 5, 6, 0], at: "08:00" },  // every morning except Tuesday
  { job: "recap",   days: [2],                at: "08:00" },  // Tuesday's morning ping is the recap
  { job: "check",   days: [4],                at: "16:00" },  // before Thursday night kickoff
  { job: "check",   days: [0],                at: "11:30" },  // before the noon kickoffs
  { job: "waivers", days: [2],                at: "20:00" },
  { job: "watch",   days: [4, 5, 6, 0, 1],    from: "00:10", every: 30 },   // Thu-Mon; :10/:40 so it never shares a tick with a report
  { job: "live",    days: [0],                from: "12:00", to: "24:00", every: 10 },  // Sunday
  { job: "live",    days: [4, 1],             from: "19:00", to: "24:00", every: 10 },  // Thu and Mon night
  { job: "live",    days: [5, 1, 2],          from: "00:00", to: "01:00", every: 10 },  // games that run past midnight
];

// Telegram command (or plain word) -> job
const COMMANDS = {
  check: "check", lineup: "check", lineups: "check",
  waivers: "waivers", waiver: "waivers", wire: "waivers",
  recap: "recap",
  live: "live", score: "live", scores: "live",
  watch: "watch",
};

const HELP = [
  "/check: lineup check now (also rebuilds the dashboard)",
  "/waivers: waiver targets and trade ideas",
  "/recap: last week's recap",
  "/live: score update (only says anything during games)",
  "/watch: injury and projection changes, pre-kickoff nudges",
  "/status: last run of each job",
  "/dashboard: the link",
].join("\n");

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const hm = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };

export function central(date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ, weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  const get = (t) => parts.find((p) => p.type === t)?.value;
  return { dow: DOW.indexOf(get("weekday")), minutes: Number(get("hour")) * 60 + Number(get("minute")) };
}

// Jobs whose slot falls inside the tick that starts at `date` (deduplicated, in schedule order).
export function dueJobs(date, schedule = SCHEDULE) {
  const { dow, minutes } = central(date);
  const due = new Set();
  for (const s of schedule) {
    if (!s.days.includes(dow)) continue;
    if (s.at !== undefined) {
      const at = hm(s.at);
      if (minutes <= at && at < minutes + TICK_MIN) due.add(s.job);
    } else {
      const from = hm(s.from ?? "00:00"), to = hm(s.to ?? "24:00");
      if (minutes >= from && minutes < to && (minutes - from) % s.every === 0) due.add(s.job);
    }
  }
  return [...due];
}

const ghHeaders = (env) => ({
  authorization: `Bearer ${env.GITHUB_TOKEN}`,
  accept: "application/vnd.github+json",
  "x-github-api-version": "2022-11-28",
  "user-agent": "fantasy-trigger",
  "content-type": "application/json",
});
const actionsUrl = (env, job) => `https://github.com/${env.GITHUB_REPO}/actions/workflows/${JOBS[job].workflow}`;

// Start a workflow. GitHub answers 204 at once and the run appears within a few seconds; the workflow
// posts its own report to Telegram, so nothing more is needed here.
async function dispatch(env, job) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${JOBS[job].workflow}/dispatches`;
  let last = "";
  for (const wait of [0, 3000, 8000]) {
    if (wait) await new Promise((r) => setTimeout(r, wait));
    try {
      const r = await fetch(url, { method: "POST", headers: ghHeaders(env), body: JSON.stringify({ ref: env.GITHUB_REF || "main" }) });
      if (r.status === 204) return { ok: true };
      last = `HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`;
      if (r.status < 500 && r.status !== 429) break; // a bad token or missing workflow will not fix itself
    } catch (e) {
      last = String(e);
    }
  }
  console.log(`dispatch ${job} failed: ${last}`);
  return { ok: false, error: last };
}

async function tg(env, text) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text, disable_web_page_preview: true }),
  });
  if (!r.ok) console.log("telegram sendMessage failed", r.status, await r.text());
}

async function status(env) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/runs?per_page=40`, { headers: ghHeaders(env) });
  if (!r.ok) return `GitHub said HTTP ${r.status} when asked for recent runs.`;
  const { workflow_runs: runs } = await r.json();
  const latest = new Map();
  for (const run of runs) if (!latest.has(run.name)) latest.set(run.name, run);
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", hour: "numeric", minute: "2-digit" });
  const lines = [...latest.values()].map((run) => {
    const how = run.event === "workflow_dispatch" ? "trigger" : run.event;
    return `${run.name}: ${run.conclusion ?? run.status}, ${fmt.format(new Date(run.created_at))} (${how})`;
  });
  return lines.length ? `Last run of each job:\n${lines.join("\n")}` : "No runs yet.";
}

async function handleUpdate(env, update) {
  const msg = update?.message;
  if (!msg?.text) return;
  if (String(msg.chat?.id) !== String(env.TELEGRAM_CHAT_ID)) return; // anyone else gets silence
  const word = msg.text.trim().replace(/^\//, "").split(/[\s@]+/)[0].toLowerCase();
  const job = COMMANDS[word];
  if (job) {
    const r = await dispatch(env, job);
    await tg(env, r.ok
      ? `On it: ${JOBS[job].label} started, report in about a minute.`
      : `⚠️ Couldn't start the ${JOBS[job].label} (${r.error}). Run it by hand: ${actionsUrl(env, job)}`);
  } else if (word === "status") {
    await tg(env, await status(env));
  } else if (word === "dashboard") {
    await tg(env, env.DASHBOARD_URL);
  } else {
    await tg(env, HELP);
  }
}

export default {
  async scheduled(event, env) {
    const when = new Date(event.scheduledTime);
    const jobs = dueJobs(when);
    console.log(`${when.toISOString()} due: ${jobs.join(", ") || "nothing"}`);
    for (const job of jobs) {
      const r = await dispatch(env, job);
      if (!r.ok) await tg(env, `⚠️ Couldn't start the ${JOBS[job].label} (${r.error}). Run it by hand: ${actionsUrl(env, job)}`);
    }
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/telegram") {
      if (request.headers.get("x-telegram-bot-api-secret-token") !== env.TELEGRAM_WEBHOOK_SECRET) {
        return new Response("forbidden", { status: 403 });
      }
      const update = await request.json().catch(() => null);
      ctx.waitUntil(handleUpdate(env, update)); // answer Telegram now; it re-sends slow webhooks
      return new Response("ok");
    }
    if (url.pathname === "/") return new Response("fantasy-trigger ok\n");
    return new Response("not found", { status: 404 });
  },
};
