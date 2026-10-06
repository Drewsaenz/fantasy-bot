// node test.mjs: the schedule table against known instants (CDT in October, CST in November).
import assert from "node:assert/strict";
import { dueJobs, central } from "./src/worker.js";

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
];
let failed = 0;
for (const [iso, want, why] of cases) {
  const got = dueJobs(new Date(iso));
  const expect = want;
  try { assert.deepEqual(got, expect); console.log("ok  ", iso, why); }
  catch { failed++; console.log("FAIL", iso, why, "got", got, "want", expect); }
}
const c = central(new Date("2026-10-02T13:00:00Z"));
assert.deepEqual(c, { dow: 5, minutes: 480 });
console.log(failed ? `${failed} failed` : "all good");
process.exit(failed ? 1 : 0);
