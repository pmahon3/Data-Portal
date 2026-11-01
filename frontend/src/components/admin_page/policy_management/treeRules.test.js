import { describeRule, fileRule, folderRule, nextFolderGrants, rulesFromSelection } from './treeRules';

// AC-5: the rules the picker makes are the ones typing would: a file, or a folder and everything in it.
const nodes = [
  { id: '1', parent: '#', li_attr: { type: 'folder', bucket: 'study' } },
  { id: '2', parent: '1', li_attr: { type: 'folder', bucket: 'study', full_path: '/patient-7/' } },
  { id: 'file-3', parent: '2', li_attr: { type: 'file', bucket: 'study', key: 'patient-7/scan.nii' } },
];

test('rule paths have the form the policy API accepts', () => {
  expect(folderRule(nodes[0])).toBe('study/*');
  expect(folderRule({ li_attr: { bucket: 'study', full_path: 'patient-7' } })).toBe('study/patient-7/*');
  expect(fileRule(nodes[2])).toBe('study/patient-7/scan.nii');
  expect(fileRule({ li_attr: { bucket: 'study', key: '/patient-7/scan.nii' } })).toBe('study/patient-7/scan.nii');
});

test('a folder rule is described as covering files added later', () => {
  expect(describeRule('study/patient-7/*')).toBe('everything in study/patient-7/, including files added later');
  expect(describeRule('study/patient-7/scan.nii')).toBe('study/patient-7/scan.nii');
});

// AC-4: a folder selected under a filter stands only for the files the filter shows.
test('a folder grant made before the selection was cleared does not come back under a filter', () => {
  const ticked = new Set(['2', 'file-3']);
  const grants = nextFolderGrants(new Set(), new Set(), ticked, nodes, false);
  expect(grants).toEqual(new Set(['2']));
  // A search clears the selection; the folder is then selected again under the filter.
  const after = nextFolderGrants(grants, new Set(), ticked, nodes, true);
  expect(rulesFromSelection(nodes, ticked, after)).toEqual(['study/patient-7/scan.nii']);
});
