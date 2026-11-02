import { describeEnds, todayUtc } from './policyEnds';

// AC-8: a policy applies through its end date and allows nothing after it.
test('a policy with no end date never ends', () => {
  expect(describeEnds(null, '2026-11-01')).toBe('Never');
});

test('a policy is shown as ended only after its end date', () => {
  expect(describeEnds('2026-11-01', '2026-11-01')).toBe('2026-11-01');
  expect(describeEnds('2026-10-31', '2026-11-01')).toBe('Ended 2026-10-31');
});

test('today is the UTC day', () => {
  expect(todayUtc(new Date('2026-11-01T23:30:00-08:00'))).toBe('2026-11-02');
});
