/**
 * How a policy's end date reads in the policy tables (AC-8). A policy applies through its end
 * date and allows nothing after it; days are UTC, as the backend judges them.
 */
export function todayUtc(now = new Date()) {
  return now.toISOString().slice(0, 10);
}

export function describeEnds(ends, today = todayUtc()) {
  if (!ends) return "Never";
  return ends < today ? `Ended ${ends}` : ends;
}
