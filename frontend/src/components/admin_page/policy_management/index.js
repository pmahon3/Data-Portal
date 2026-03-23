import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useKeycloak } from "@react-keycloak/web";
import "./PolicyManagement.css";
// Constants and the component states
// const http = axios.create({ baseURL: "http://localhost:8000" });
const http = axios.create({ baseURL: "/api" });
// const INSTANCES_BASE = "/api/instances";   
// const POLICIES_BASE  = "/api/policies";    
const INSTANCES_BASE = "/instances";   
const POLICIES_BASE  = "/policies";    

export default function PolicyManagement() {
  const { keycloak, initialized } = useKeycloak();

  const [policies, setPolicies] = useState([]);
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState("");

  const [username, setUsername] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [resource, setResource] = useState("");
  const [action, setAction] = useState("read");

  /////////////////////////////////////////////

  // keycloack token handling
  const authHeaders = async () => {
    if (!initialized) return {};
    try { await keycloak.updateToken(30); } catch {}
    return keycloak?.token ? { Authorization: `Bearer ${keycloak.token}` } : {};
  };

  // Load instances to be displayed in a deop down list
  async function loadInstances() {
    const headers = await authHeaders();
    const { data } = await http.get(`${INSTANCES_BASE}/`, { headers });
    setInstances(Array.isArray(data?.instances) ? data.instances : []);
  }

  // Load polices to be displayed
  // TODO ----> policies are returned based user_uuid and instance_uuid , which are not human readable. This needs to be changed to return username and instance names. These changes impact th ebody request of create/delete policies.  
  async function loadPolicies() {
    const headers = await authHeaders();
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

    if (!u) { setCreating(false); return setErr("Username is required."); }
    if (!i) { setCreating(false); return setErr("Instance name is required."); }
    if (!r) { setCreating(false); return setErr("Resource is required."); }
    if (!a) { setCreating(false); return setErr("Action is required."); }

    try {
      const headers = await authHeaders();
      await http.post(
        `${POLICIES_BASE}/`,
        { username: u, instance_name: i, resource: r, action: a },
        { headers }
      );
      await loadPolicies();
      setResource("");
      setAction("read");
      alert("Policy created.");
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

    const headers = await authHeaders();
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
  }

  // sorted list of instances for the drop down 
  const instanceOptions = instances
    .map(i => i?.name)
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));

    // HTML part
  return (
    <div className="pm-root">
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

          <label className="pm-field">
            <span>Resource *</span>
            <input
              value={resource}
              onChange={e => setResource(e.target.value)}
              placeholder="/bucket/prefix/.* or exact path"
            />
          </label>

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
              {creating ? "Creating…" : "Create Policy"}
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
          <table className="pm-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Instance Name</th>
                <th>Resource</th>
                <th>Action</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p, idx) => (
                <tr key={idx}>
                  <td><code className="pm-mono">{String(p.username || "")}</code></td>
                  <td><code className="pm-mono">{String(p.instance_name || "")}</code></td>
                  <td>{p.resource || "—"}</td>
                  <td>{p.action || "—"}</td>
                  <td className="pm-actions-right">
                    <button className="pm-btn pm-btn-danger" onClick={() => handleDelete(p)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
// standard way to formatting errors
function formatError(err) {
  const d = err?.response?.data;
  if (!d) return String(err?.message || err);
  if (Array.isArray(d.detail)) return d.detail.map(x => `${(x.loc || []).join(".")} → ${x.msg}`).join(" | ");
  return d.detail || JSON.stringify(d);
}
