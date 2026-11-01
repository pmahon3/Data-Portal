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
    const resources = fromTree ? treeRules : [r];
    const failed = [];
    try {
      const headers = await getAuthHeaders();
      for (const res of resources) {
        try {
          await http.post(
            `${POLICIES_BASE}/`,
            { username: u, instance_name: i, resource: res, action: a },
            { headers }
          );
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
            <button type="button" className="pm-btn" aria-pressed={resourceMode === "path"} onClick={() => setResourceMode("path")}>
              Type a path
            </button>
            <button type="button" className="pm-btn" aria-pressed={resourceMode === "tree"} onClick={() => setResourceMode("tree")}>
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
                  onSearch={() => { setTreeSelection(new Set()); return fetchSearchAssets("read", false, false); }}
                  onClearSearch={() => { setTreeSelection(new Set()); return fetchBrowseRoots("read", false); }}
                  onLoadChildren={(node) => fetchChildAssets("read", node)}
                  loadingNodeIds={loadingNodeIdsByAccess.read || new Set()}
                />
              )}
              <small className="pm-muted">
                A ticked folder covers everything in it, including files added later. Ticked files are
                granted one by one, and under a filter only the files it shows are granted.
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

          <label className="pm-field">
            <span>Action *</span>
            <select value={action} onChange={e => setAction(e.target.value)}>
              <option value="read">read</option>
              <option value="write">write</option>
              <option value="delete">delete</option>
              <option value="admin">admin</option>
            </select>
          </label>

          <div className="pm-actions">
            <button className="pm-btn pm-btn-primary" type="submit" disabled={creating}>
              {creating ? <CircularProgress size={20} color="inherit" />
                : resourceMode === "tree" && treeRules.length > 1 ? `Create ${treeRules.length} Policies` : "Create Policy"}
            </button>
            {/* {err && <div className="pm-error">{err}</div>} */}
          </div>
        </form>
      </section>

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
