import { render, screen } from '@testing-library/react';
import PolicyManagement from './index';

// Keep axios (ES modules, which this Jest setup doesn't transform), Keycloak and the data grid out of
// the test; the page loads no instances or policies here.
jest.mock('axios', () => ({ create: () => ({ get: jest.fn(async () => ({ data: {} })) }) }));
jest.mock('@react-keycloak/web', () => ({ useKeycloak: () => ({ initialized: true }) }));
jest.mock('../../../utils/authUtils', () => ({ getAuthHeaders: async () => ({}) }));
jest.mock('@mui/x-data-grid', () => ({ DataGrid: () => null }));

// AC-5: a policy path is one file, a folder and everything in it, or everything; literal, not a pattern.
test('the resource field says what a policy path can be', async () => {
  render(<PolicyManagement />);
  const field = await screen.findByPlaceholderText('bucket/folder/* or bucket/path/file.ext');
  const help = document.getElementById(field.getAttribute('aria-describedby'));
  expect(help).toHaveTextContent('a folder and everything in it, including files added later');
  expect(help).toHaveTextContent('Paths are literal, not patterns');
});
