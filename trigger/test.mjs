// node test.mjs: the schedule table against known instants (CDT in October, CST in November).
import assert from "node:assert/strict";
import { dueJobs, central, missedInARow } from "./src/worker.js";

const cases = [
  ["2026-10-02T13:00:00Z", ["check"],          "Fri 08:00 CDT morning report"],
  ["2026-10-02T13:10:00Z", ["watch"],          "Fri 08:10: watch tick only, the 08:00 check is not repeated"],
  ["2026-10-06T13:00:00Z", ["recap"],          "Tue 08:00, recap owns Tuesday"],
  ["2026-10-07T01:00:00Z", ["waivers"],        "Tue 20:00 CDT waivers"],
  ["2026-10-08T21:00:00Z", ["check"],          "Thu 16:00 CDT pre-TNF"],
  ["2026-10-09T00:50:00Z", ["live"],           "Thu 19:50 CDT live"],
  ["2026-10-09T05:50:00Z", ["live"],           "Fri 00:50 CDT overrun"],
  ["2026-10-09T06:00:00Z", [],                 "Fri 01:00 CDT: overrun window closed, watch waits for :10"],
  ["2026-10-09T06:10:00Z", ["watch"],          "Fri 01:10 CDT watch"],
  ["2026-10-04T16:30:00Z", ["check"],          "Sun 11:30 CDT"],
  ["2026-10-04T17:00:00Z", ["live"],           "Sun 12:00 CDT: first live tick"],
  ["2026-10-04T17:40:00Z", ["watch", "live"],  "Sun 12:40 CDT: watch and live share a tick"],
  ["2026-10-04T17:20:00Z", ["live"],           "Sun 12:20 CDT live only"],
  ["2026-10-03T13:00:00Z", ["check"],          "Sat 08:00 morning report"],
  ["2026-11-03T14:00:00Z", ["recap"],          "Tue 08:00 CST after fall back"],
  ["2026-11-03T13:00:00Z", [],                 "Tue 07:00 CST, nothing"],
  ["2026-11-04T14:00:00Z", ["check"],          "Wed 08:00 CST"],
  ["2026-11-11T08:00:00Z", ["claims"],         "Wed 02:00 CST: waivers process"],
  ["2026-11-11T09:50:00Z", ["claims"],         "Wed 03:50 CST: last claims tick"],
  ["2026-11-11T10:00:00Z", [],                 "Wed 04:00 CST: claims window closed"],
  ["2026-11-08T08:10:00Z", ["watch", "claims"], "Sun 02:10 CST: watch and claims share a tick"],
];
let failed = 0;
for (const [iso, want, why] of cases) {
  const got = dueJobs(new Date(iso));
  const expect = want;
  try { assert.deepEqual(got, expect); console.log("ok  ", iso, why); }
  catch { failed++; console.log("FAIL", iso, why, "got", got, "want", expect); }
}
// missedInARow: watch/live only warn once WARN_AFTER (3) slots in a row have come and gone without a run.
const misses = [
  ["watch", "2026-11-05T16:10:00Z", "2026-11-05T15:40:36Z", 1, "Thu 10:10 CST, the 09:40 watch ran"],
  ["watch", "2026-11-05T17:10:00Z", "2026-11-05T15:40:36Z", 3, "10:10, 10:40, 11:10 all missed"],
  ["live",  "2026-11-08T18:00:00Z", "2026-11-06T06:50:30Z", 1, "Sun 12:00, first live tick since Thu night's game"],
  ["live",  "2026-11-08T18:20:00Z", "2026-11-06T06:50:30Z", 3, "Sun 12:00-12:20 missed"],
];
for (const [job, iso, last, want, why] of misses) {
  const got = missedInARow(job, new Date(iso), Date.parse(last));
  if (got === want) console.log("ok  ", iso, why);
  else { failed++; console.log("FAIL", iso, why, "got", got, "want", want); }
}
const c = central(new Date("2026-10-02T13:00:00Z"));
assert.deepEqual(c, { dow: 5, minutes: 480 });
console.log(failed ? `${failed} failed` : "all good");
process.exit(failed ? 1 : 0);
