import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import PolicyManagement from './index';

// Keep axios (ES modules, which this Jest setup doesn't transform), Keycloak and the data grid out of
// the test. The API answers with one instance holding one folder and two files.
const mockPost = jest.fn();
const mockGet = jest.fn();
const answer = async (url) => {
  if (url === '/instances/') return { data: { instances: [{ name: 'demo', uuid: 'u1' }] } };
  if (url.startsWith('/tree/dashboard/u1')) {
    return { data: { assets: [
      { id: '1', parent: '#', text: 'study', li_attr: { type: 'folder', bucket: 'study' } },
      { id: '2', parent: '1', text: 'patient-7', li_attr: { type: 'folder', bucket: 'study', full_path: '/patient-7/' } },
      { id: 'file-3', parent: '1', text: 'protocol.pdf', li_attr: { type: 'file', bucket: 'study', key: 'protocol.pdf' } },
    ] } };
  }
  return { data: {} };
};
jest.mock('axios', () => ({ create: () => ({ get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) }) }));
jest.mock('@react-keycloak/web', () => ({ useKeycloak: () => ({ initialized: true }) }));
jest.mock('../../../utils/authUtils', () => ({ getAuthHeaders: async () => ({}) }));
jest.mock('@mui/x-data-grid', () => ({ DataGrid: () => null }));
// The virtualizer measures the scroll container, which jsdom can't do, so render every row.
jest.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }) => ({
    getTotalSize: () => count * 40,
    getVirtualItems: () => Array.from({ length: count }, (_, index) => ({ index, key: index, start: index * 40, size: 40 })),
  }),
}));

// The Jest setup resets mocks before each test, implementations included.
beforeEach(() => {
  mockGet.mockImplementation(answer);
  window.alert = jest.fn();
});

// AC-5: a policy path is one file, a folder and everything in it, or everything; literal, not a pattern.
test('the resource field says what a policy path can be', async () => {
  render(<PolicyManagement />);
  const field = await screen.findByPlaceholderText('bucket/folder/* or bucket/path/file.ext');
  const help = document.getElementById(field.getAttribute('aria-describedby'));
  expect(help).toHaveTextContent('a folder and everything in it, including files added later');
  expect(help).toHaveTextContent('Paths are literal, not patterns');
});

function rowFor(text) {
  return screen.getByText(text, { selector: '.tree-node-text' }).closest('.tree-node-label');
}

async function chooseFromTree() {
  render(<PolicyManagement />);
  fireEvent.change(screen.getByPlaceholderText('alice'), { target: { value: 'alice' } });
  await screen.findByRole('option', { name: 'demo' });
  fireEvent.change(screen.getByRole('combobox', { name: /Instance/ }), { target: { value: 'demo' } });
  fireEvent.click(screen.getByRole('button', { name: 'Choose from the tree' }));
  await screen.findByText('study', { selector: '.tree-node-text' });
  fireEvent.click(within(rowFor('study')).getByText('\u25B6'));
  // Opening a folder loads its children first.
  await screen.findByText('patient-7', { selector: '.tree-node-text' });
}

// AC-10: unticking something inside a ticked folder leaves it out of that folder's policy.
test('the tree help says unticking inside a ticked folder leaves it out', async () => {
  await chooseFromTree();
  const help = screen.getByText(/A ticked folder covers everything in it/);
  expect(help).toHaveTextContent('Untick something inside a ticked folder to leave it out');
});

// AC-5, AC-4: rules chosen from the tree are saved through the policy API, one policy each.
test('a selection from the tree creates one policy per rule', async () => {
  mockPost.mockResolvedValue({ data: {} });
  await chooseFromTree();
  fireEvent.click(rowFor('patient-7'));
  fireEvent.click(rowFor('protocol.pdf'));
  fireEvent.click(screen.getByRole('button', { name: 'Create 2 Policies' }));
  await waitFor(() => expect(window.alert).toHaveBeenCalledWith('2 policies created.'));
  expect(mockPost.mock.calls.map(([, body]) => body)).toEqual([
    { username: 'alice', instance_name: 'demo', resource: 'study/patient-7/*', action: 'read' },
    { username: 'alice', instance_name: 'demo', resource: 'study/protocol.pdf', action: 'read' },
  ]);
});

test('a rule the API refuses is named, and the others are still created', async () => {
  mockPost
    .mockResolvedValueOnce({ data: {} })
    .mockRejectedValueOnce({ response: { status: 403, data: { detail: 'Not allowed' } } });
  await chooseFromTree();
  fireEvent.click(rowFor('patient-7'));
  fireEvent.click(rowFor('protocol.pdf'));
  fireEvent.click(screen.getByRole('button', { name: 'Create 2 Policies' }));
  expect(await screen.findByText(/Not created: study\/protocol.pdf/)).toBeInTheDocument();
  expect(mockPost).toHaveBeenCalledTimes(2);
});

// AC-8: a policy can be given an end date, sent with it when it's saved.
test('a typed policy is saved with its end date', async () => {
  mockPost.mockResolvedValue({ data: {} });
  render(<PolicyManagement />);
  fireEvent.change(screen.getByPlaceholderText('alice'), { target: { value: 'alice' } });
  await screen.findByRole('option', { name: 'demo' });
  fireEvent.change(screen.getByRole('combobox', { name: /Instance/ }), { target: { value: 'demo' } });
  fireEvent.change(screen.getByPlaceholderText('bucket/folder/* or bucket/path/file.ext'), { target: { value: 'study/*' } });
  fireEvent.change(screen.getByLabelText(/^Ends/), { target: { value: '2999-12-31' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Policy' }));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][1]).toEqual(
    { username: 'alice', instance_name: 'demo', resource: 'study/*', action: 'read', ends: '2999-12-31' });
});

// AC-10: a typed folder policy can leave out paths inside it, one per line.
test('a typed folder policy is saved with what it leaves out', async () => {
  mockPost.mockResolvedValue({ data: {} });
  render(<PolicyManagement />);
  fireEvent.change(screen.getByPlaceholderText('alice'), { target: { value: 'alice' } });
  await screen.findByRole('option', { name: 'demo' });
  fireEvent.change(screen.getByRole('combobox', { name: /Instance/ }), { target: { value: 'demo' } });
  fireEvent.change(screen.getByPlaceholderText('bucket/folder/* or bucket/path/file.ext'), { target: { value: 'study/*' } });
  fireEvent.change(screen.getByLabelText(/^Leave out/), { target: { value: 'study/sub-03/*\n study/notes.txt \n' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Policy' }));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][1]).toEqual({ username: 'alice', instance_name: 'demo', resource: 'study/*',
    action: 'read', excluded: ['study/sub-03/*', 'study/notes.txt'] });
});

// AC-6: a typed folder policy can be limited to file endings.
test('a typed folder policy is saved with its file endings', async () => {
  mockPost.mockResolvedValue({ data: {} });
  render(<PolicyManagement />);
  fireEvent.change(screen.getByPlaceholderText('alice'), { target: { value: 'alice' } });
  await screen.findByRole('option', { name: 'demo' });
  fireEvent.change(screen.getByRole('combobox', { name: /Instance/ }), { target: { value: 'demo' } });
  fireEvent.change(screen.getByPlaceholderText('bucket/folder/* or bucket/path/file.ext'), { target: { value: 'study/*' } });
  fireEvent.change(screen.getByLabelText(/^Only files ending in/), { target: { value: '.nii, .nii.gz' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Policy' }));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][1]).toEqual({ username: 'alice', instance_name: 'demo', resource: 'study/*',
    action: 'read', endings: ['.nii', '.nii.gz'] });
});

// AC-6: a typed folder policy can be limited to kinds of data.
test('a typed folder policy is saved with its kinds of data', async () => {
  mockPost.mockResolvedValue({ data: {} });
  render(<PolicyManagement />);
  fireEvent.change(screen.getByPlaceholderText('alice'), { target: { value: 'alice' } });
  await screen.findByRole('option', { name: 'demo' });
  fireEvent.change(screen.getByRole('combobox', { name: /Instance/ }), { target: { value: 'demo' } });
  fireEvent.change(screen.getByPlaceholderText('bucket/folder/* or bucket/path/file.ext'), { target: { value: 'study/*' } });
  fireEvent.change(screen.getByLabelText(/^Only kinds of data/), { target: { value: 'anat, func' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Policy' }));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][1]).toEqual({ username: 'alice', instance_name: 'demo', resource: 'study/*',
    action: 'read', kinds: ['anat', 'func'] });
});
