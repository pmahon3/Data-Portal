import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Notifications from './Notifications';

// The component's own loader isn't used here (each test passes one); keep axios (ES modules, which
// this Jest setup doesn't transform) and Keycloak out of the test.
jest.mock('axios', () => ({ create: () => ({ get: jest.fn() }) }));
jest.mock('../../utils/authUtils', () => ({ getAuthHeaders: async () => ({}) }));

// NT-1: the researcher is told in the portal when an upload is stored, and what failed if it wasn't.
const listed = [
  { id: 'b', kind: 'stored_with_failures', message: "Stored 2998 files; 2 failed and weren't stored",
    created_at: '2026-10-31T10:05:00Z' },
  { id: 'a', kind: 'stored', message: 'Stored scan.nii.gz', created_at: '2026-10-31T10:00:00Z' },
];

beforeEach(() => window.localStorage.clear());

test('shows how many notifications are new', async () => {
  render(<Notifications load={async () => listed} />);
  expect(await screen.findByRole('button', { name: 'notifications, 2 new' })).toBeInTheDocument();
});

test('opening the list shows each message and clears the count', async () => {
  render(<Notifications load={async () => listed} />);
  userEvent.click(await screen.findByRole('button', { name: 'notifications, 2 new' }));
  expect(await screen.findByText('Stored scan.nii.gz')).toBeInTheDocument();
  expect(screen.getByText(/2 failed/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button', { name: 'notifications', hidden: true })).toBeInTheDocument());
});

test('a notification already seen is not counted again', async () => {
  window.localStorage.setItem('notificationsSeenUntil', '2026-10-31T10:00:00Z');
  render(<Notifications load={async () => listed} />);
  expect(await screen.findByRole('button', { name: 'notifications, 1 new' })).toBeInTheDocument();
});

test('an empty list says so', async () => {
  render(<Notifications load={async () => []} />);
  userEvent.click(await screen.findByRole('button', { name: /notifications/i }));
  expect(await screen.findByText(/no notifications/i)).toBeInTheDocument();
});
