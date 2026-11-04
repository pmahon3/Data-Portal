/**
 * Show a policy's end date in the policy tables (AC-8). A policy applies through its end date and
 * allows nothing after it; days are UTC, as the backend judges them.
 */

/** Return today's date in UTC. Example: "2026-11-02" */
export function todayUtc(now = new Date()) {
  return now.toISOString().slice(0, 10);
}

/**
 * Return how an end date reads.
 * Example: none -> "Never"; a past date -> "Ended 2026-10-31"; otherwise the date
 */
export function describeEnds(ends, today = todayUtc()) {
  if (!ends) return "Never";
  if (ends < today) return `Ended ${ends}`;
  return ends;
}
