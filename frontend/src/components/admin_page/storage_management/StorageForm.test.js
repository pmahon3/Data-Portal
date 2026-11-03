import { render, screen } from '@testing-library/react';
import StorageInstanceForm from './StorageForm';

// Keep axios (ES modules, which this Jest setup doesn't transform) and Keycloak out of the test.
jest.mock('axios', () => ({ create: () => ({ get: async () => ({ data: [] }) }) }));
jest.mock('../../../utils/authUtils', () => ({ getAuthHeaders: async () => ({}) }));

// Jest 27 has no test.failing: this passes only while the check fails, and fails once it passes,
// so the fix has to replace it with test().
function knownFailing(name, check) {
  test(`${name} (known failing)`, async () => {
    let failed = false;
    try {
      await check();
    } catch {
      failed = true;
    }
    if (!failed) throw new Error('This now passes: replace knownFailing with test.');
  });
}

// An instance gets a random UUID when it's created; its name is only what the portal shows, and
// it can be renamed.
knownFailing('the instance name help says what the name is for', async () => {
  render(<StorageInstanceForm onCreate={jest.fn()} creating={false} initialized />);
  await screen.findByText('No projects available.');
  const field = screen.getByPlaceholderText('my-instance-name').closest('label');
  expect(field).not.toHaveTextContent('UUID');
  expect(field).toHaveTextContent('Shown in the portal. You can rename it later.');
});
