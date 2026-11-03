import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useKeycloak } from "@react-keycloak/web";
import { CircularProgress } from '@mui/material';
import { DataGrid } from "@mui/x-data-grid";
import "./PolicyManagement.css";
import { formatError } from "../../../utils/errorUtils";
import { getAuthHeaders } from '../../../utils/authUtils';
import useEndpointAssetTree from "../asset_management/useEndpointAssetTree.js";
import TreePicker from "./TreePicker.js";
import CheckAccess from "./CheckAccess.js";
import { broadExtent, describeConditions, describeRule, describeWho } from "./treeRules.js";
import { describeEnds, todayUtc } from "../../../utils/policyEnds";
// Constants and the component states
// const http = axios.create({ baseURL: "http://localhost:8000" });
const http = axios.create({ baseURL: "/api" });    
const INSTANCES_BASE = "/instances";   
const POLICIES_BASE  = "/policies";    

export default function PolicyManagement() {
  const { initialized } = useKeycloak();

  const [policies, setPolicies] = useState([]);
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState("");

  const [username, setUsername] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [resource, setResource] = useState("");
  const [action, setAction] = useState("read");
  const [ends, setEnds] = useState(""); // the last day the policy applies; "" for no end (AC-8)
  const [leaveOut, setLeaveOut] = useState(""); // typed paths a folder policy leaves out, one per line (AC-10)
  const [endingsText, setEndingsText] = useState(""); // typed file endings, e.g. ".nii, .nii.gz" (AC-6)
  const [kindsText, setKindsText] = useState(""); // typed kinds of data, e.g. "anat, func" (AC-6)
  // "path": type the resource; "tree": choose it from the instance's file tree (DS-policy-from-selection)
  const [resourceMode, setResourceMode] = useState("path");
  const [treeSelection, setTreeSelection] = useState(new Set());
  const [treeRules, setTreeRules] = useState([]);

  const instanceUuid = instances.find(i => i?.name === instanceName)?.uuid || "";
  const {
    treesByAccess,
    loadingNodeIdsByAccess,
    loadingAssets,
    assetError,
    fetchBrowseRoots,
    fetchSearchAssets,
    fetchChildAssets,
  } = useEndpointAssetTree({
    endpointName: instanceName,
    endpointUuid: instanceUuid,
    activeAccess: "read",
    selectedByAccess: { read: treeSelection },
    onSelectedChange: (_access, next) => setTreeSelection(new Set(next)),
    http,
  });
  const onRulesChange = useCallback(rules => setTreeRules(rules), []);

  // Load the chosen instance's tree when choosing from it; a new instance starts a new selection.
  useEffect(() => {
    setTreeSelection(new Set());
    if (resourceMode === "tree" && instanceUuid) fetchBrowseRoots("read", true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceMode, instanceUuid]);

  /////////////////////////////////////////////

  // Load instances to be displayed in a deop down list
  async function loadInstances() {
    const headers = await getAuthHeaders();
    const { data } = await http.get(`${INSTANCES_BASE}/`, { headers });
    setInstances(Array.isArray(data?.instances) ? data.instances : []);
  }

  // Load polices to be displayed
  // TODO ----> policies are returned based user_uuid and instance_uuid , which are not human readable. This needs to be changed to return username and instance names. These changes impact th ebody request of create/delete policies.  
  async function loadPolicies() {
    const headers = await getAuthHeaders();
    const { data } = await http.get(`${POLICIES_BASE}/`, { headers });
    console.log("These are policies")
    console.log(data)
    setPolicies(Array.isArray(data?.details) ? data.details : []);
  }

  useEffect(() => {
    (async () => {
      if (!initialized) return;
      try {
        await Promise.all([loadInstances(), loadPolicies()]);
      } catch (e) {
        setErr(formatError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [initialized]);

  // What a typed policy leaves out and is limited to, from the form fields (AC-6, AC-10).
  const typedExcluded = leaveOut.split("\n").map(line => line.trim()).filter(Boolean);
  const typedEndings = endingsText.split(/[\s,]+/).map(e => e.trim()).filter(Boolean);
  const typedKinds = kindsText.split(/[\s,]+/).map(k => k.trim()).filter(Boolean);

  // Create new policy
  async function handleCreate(e) {
    e.preventDefault();
    setErr("");
    setCreating(true);

    const u = username.trim();
    const i = instanceName.trim();
    const r = resource.trim();
    const a = action.trim();
    const fromTree = resourceMode === "tree";

    if (!u) { setCreating(false); return setErr("Username is required."); }
    if (!i) { setCreating(false); return setErr("Instance name is required."); }
    if (!fromTree && !r) { setCreating(false); return setErr("Resource is required."); }
    if (fromTree && treeRules.length === 0) { setCreating(false); return setErr("Tick files or folders to grant."); }
    if (!a) { setCreating(false); return setErr("Action is required."); }

    // From the tree, one policy per rule, each through the same API as a typed one.
    let resources = treeRules;
    if (!fromTree) {
      resources = [{ resource: r, excluded: typedExcluded, endings: typedEndings, kinds: typedKinds }];
    }
    const failed = [];
    try {
      const headers = await getAuthHeaders();
      for (const { resource: res, excluded, endings = [], kinds = [] } of resources) {
        // Example: { username: "alice", instance_name: "minio", resource: "study/*", action: "read",
        //            excluded: ["study/sub-03/*"] }; empty conditions are left out
        const body = { username: u, instance_name: i, resource: res, action: a };
        if (excluded.length) body.excluded = excluded;
        if (endings.length) body.endings = endings;
        if (kinds.length) body.kinds = kinds;
        if (ends) body.ends = ends;
        try {
          await http.post(`${POLICIES_BASE}/`, body, { headers });
        } catch (e2) {
          failed.push(`${res}: ${formatError(e2)}`);
        }
      }
      await loadPolicies();
      if (failed.length > 0) {
        setErr(`Not created: ${failed.join("; ")}`);
      } else {
        setResource("");
        setTreeSelection(new Set());
        setAction("read");
        setEnds("");
        setLeaveOut("");
        setEndingsText("");
        setKindsText("");
        alert(resources.length === 1 ? "Policy created." : `${resources.length} policies created.`);
      }
    } catch (e2) {
      setErr(formatError(e2));
    } finally {
      setCreating(false);
    }
  }

  // Delete a policy
  async function handleDelete(p) {
    console.dir(p);
    if (!window.confirm(`Delete policy:\nresource="${p.resource}" action="${p.action}" ?`)) return;
    setErr("");

    try {
      const headers = await getAuthHeaders();
      await http.delete(`${POLICIES_BASE}/`, {
        headers,
        data: {
          user_uuid: p.user_uuid,
          instance_uuid: p.instance_uuid,
          resource: p.resource,
          action: p.action,
        },
      });
      await loadPolicies();
    } catch (e) {
      const message = formatError(e);
      if (e?.response?.status === 403) {
        alert(message);
      }
      setErr(message);
    }
  }

  // Creates a saved list of policies with a unique composite ID added for MUI data grid
  const policyRows = useMemo(
    () => policies.map((p, idx) => ({
      id: `${p.user_uuid}-${p.instance_uuid}-${p.resource}-${p.action}`,
      ...p,
    })),
    [policies]
  );

  // Configurations for the policy table to be rendered with MUI data grid
  const policyColumns = [
    { field: "username", headerName: "Username", flex: 1, minWidth: 160, renderCell: params => {String(params.value || "")}},
    { field: "instance_name", headerName: "Instance Name", flex: 1, minWidth: 180, renderCell: params => {String(params.value || "")}},
    { field: "resource", headerName: "Resource", flex: 1.5, minWidth: 220 },
    { field: "action", headerName: "Action", width: 120 },
    { field: "endings", headerName: "File types", width: 140, valueGetter: (value, row) => [...(value || []), ...(row.kinds || [])].join(", ") },
    { field: "excluded", headerName: "Leaves out", flex: 1, minWidth: 180, valueGetter: (value) => (value || []).join(", ") },
    { field: "ends", headerName: "Ends", width: 160, valueGetter: (value) => describeEnds(value) },
    {
      field: "delete",
      headerName: "",
      width: 120,
      sortable: false,
      filterable: false,
      renderCell: params => (
        <button className="pm-btn pm-btn-danger" onClick={() => handleDelete(params.row)}>Delete</button>
      ),
    },
  ];

  // sorted list of instances for the drop down 
  const instanceOptions = instances
    .map(i => i?.name)
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));

    // HTML part
  let createLabel = "Create Policy";
  if (resourceMode === "tree" && treeRules.length > 1) createLabel = `Create ${treeRules.length} Policies`;
  let resourcesToSave = [resource.trim()];
  if (resourceMode === "tree") resourcesToSave = treeRules.map((rule) => rule.resource);
  const broadWarnings = [...new Set(resourcesToSave.map(broadExtent).filter(Boolean))];

  return (
    <div className="pm-root policy-management">
      <h1>Policy Management</h1>
    {/* Showing error on the top of the page */}
      {err && (
        <div className="pm-error" style={{ marginBottom: "12px", fontWeight: 600 }}>
          {err}
        </div>
      )}
    {/* Create policy part */}
      <section className="pm-card">
        <h3>Create Policy</h3>
        <form onSubmit={handleCreate} className="pm-form">
          <div className="pm-row">
            <label className="pm-field">
              <span>Username *</span>
              <input value={username} onChange={e => setUsername(e.target.value)} placeholder="alice" />
            </label>
            <label className="pm-field">
              <span>Instance *</span>
              <select value={instanceName} onChange={e => setInstanceName(e.target.value)}>
                <option value="">— Select —</option>
                {instanceOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <small className="pm-muted">Choose by instance <em>name</em></small>
            </label>
          </div>

          <div className="pm-mode" role="group" aria-label="How to choose the resource">
            <button
              type="button"
              className="pm-btn"
              aria-pressed={resourceMode === "path"}
              onClick={() => setResourceMode("path")}
            >
              Type a path
            </button>
            <button
              type="button"
              className="pm-btn"
              aria-pressed={resourceMode === "tree"}
              onClick={() => setResourceMode("tree")}
            >
              Choose from the tree
            </button>
          </div>

          {resourceMode === "tree" ? (
            <div className="pm-field">
              <span>Resource *</span>
              {!instanceUuid ? (
                <small className="pm-muted">Select an instance to see its files.</small>
              ) : loadingAssets ? (
                <CircularProgress size={20} />
              ) : assetError ? (
                <div className="pm-error">{assetError}</div>
              ) : (
                <TreePicker
                  nodes={treesByAccess.read || []}
                  selected={treeSelection}
                  onSelectedChange={setTreeSelection}
                  username={username.trim()}
                  action={action}
                  onRulesChange={onRulesChange}
                  onSearch={() => {
                    setTreeSelection(new Set());
                    return fetchSearchAssets("read", false, false);
                  }}
                  onClearSearch={() => {
                    setTreeSelection(new Set());
                    return fetchBrowseRoots("read", false);
                  }}
                  onLoadChildren={(node) => fetchChildAssets("read", node)}
                  loadingNodeIds={loadingNodeIdsByAccess.read || new Set()}
                />
              )}
              <small className="pm-muted">
                A ticked folder covers everything in it, including files added later. Untick something
                inside a ticked folder to leave it out. Ticked files are granted one by one, and under a
                filter only the files it shows are granted.
              </small>
            </div>
          ) : (
          <label className="pm-field">
            <span>Resource *</span>
            <input
              value={resource}
              onChange={e => setResource(e.target.value)}
              placeholder="bucket/folder/* or bucket/path/file.ext"
              aria-describedby="pm-resource-help"
            />
            <small id="pm-resource-help" className="pm-muted">
              One file (<code>bucket/path/file.ext</code>), a folder and everything in it, including
              files added later (<code>bucket/folder/*</code>), or <code>*</code> for the whole
              instance. Paths are literal, not patterns: <code>.*</code> and a <code>*</code> mid-path
              are refused.
            </small>
          </label>
          )}

          {resourceMode === "path" && (
          <label className="pm-field">
            <span>Leave out</span>
            <textarea
              value={leaveOut}
              onChange={e => setLeaveOut(e.target.value)}
              rows={2}
              placeholder="bucket/folder/sub/*"
              aria-describedby="pm-leave-out-help"
            />
            <small id="pm-leave-out-help" className="pm-muted">
              Optional, for a folder policy: files or folders inside it to leave out, one per line.
              Another policy can still give them.
            </small>
          </label>
          )}

          {resourceMode === "path" && (
          <label className="pm-field">
            <span>Only files ending in</span>
            <input
              value={endingsText}
              onChange={e => setEndingsText(e.target.value)}
              placeholder=".nii, .nii.gz"
              aria-describedby="pm-endings-help"
            />
            <small id="pm-endings-help" className="pm-muted">
              Optional, for a folder policy: it then covers only files whose names end in one of these (any
              case). Folders inside it can still be browsed.
            </small>
          </label>
          )}

          {resourceMode === "path" && (
          <label className="pm-field">
            <span>Only kinds of data</span>
            <input
              value={kindsText}
              onChange={e => setKindsText(e.target.value)}
              placeholder="anat, func"
              aria-describedby="pm-kinds-help"
            />
            <small id="pm-kinds-help" className="pm-muted">
              Optional, for a folder in a dataset that declares a standard: kinds as the standard names them
              (for BIDS: anat, func, dwi, fmap, ...). The policy then covers only those.
            </small>
          </label>
          )}

          <label className="pm-field">
            <span>Action *</span>
            <select value={action} onChange={e => setAction(e.target.value)}>
              <option value="read">read</option>
              <option value="write">write</option>
              <option value="delete">delete</option>
              <option value="admin">admin</option>
            </select>
          </label>

          <label className="pm-field">
            <span>Ends</span>
            <input
              type="date"
              value={ends}
              min={todayUtc()}
              onChange={e => setEnds(e.target.value)}
              aria-describedby="pm-ends-help"
            />
            <small id="pm-ends-help" className="pm-muted">
              Optional. The policy applies through this day and allows nothing after it. Leave empty
              for no end.
            </small>
          </label>

          {resourceMode === "path" && resource.trim() && (
            <section className="pm-rule-preview" aria-label="Policy to create">
              <p>{describeWho(username.trim(), action)}</p>
              <ul>
                <li>
                  <code>{describeRule({ resource: resource.trim(), excluded: typedExcluded })}</code>
                </li>
              </ul>
              {describeConditions({ endings: typedEndings, kinds: typedKinds, ends }).map((sentence) => (
                <p key={sentence} className="pm-muted">{sentence}</p>
              ))}
            </section>
          )}

          {broadWarnings.length > 0 && (
            <div role="status" className="pm-warn">
              {broadWarnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}

          <div className="pm-actions">
            <button className="pm-btn pm-btn-primary" type="submit" disabled={creating}>
              {creating ? <CircularProgress size={20} color="inherit" /> : createLabel}
            </button>
            {/* {err && <div className="pm-error">{err}</div>} */}
          </div>
        </form>
      </section>

      <CheckAccess http={http} instanceOptions={instanceOptions} />

      {/* Show policies and provide delete option */}
      <section className="pm-card">
        <h3>Policies</h3>
        {loading ? (
          <p>Loading policies…</p>
        ) : (policies?.length ?? 0) === 0 ? (
          <p className="pm-muted">No policies found.</p>
        ) : (
          <div className="pm-grid">
            <DataGrid
              rows={policyRows}
              columns={policyColumns}
              sx={{ width: "100%", '& .MuiDataGrid-columnHeaderTitle': { fontWeight: 700 }, '& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within': { outline: 'none' } }}
              showToolbar
              disableRowSelectionOnClick
              pageSizeOptions={[5, 10, 25]}
              disableColumnMenu
              disableColumnFilter
              disableColumnSelector 
              hideFooter
            />
          </div>
        )}
      </section>
    </div>
  );
}
