import React, { useEffect, useState } from "react";
import axios from "axios";
import { useKeycloak } from "@react-keycloak/web";
import { CircularProgress } from '@mui/material';
import "./StorageManagement.css";
import { formatError } from "../../../utils/errorUtils";
import { getAuthHeaders } from '../../../utils/authUtils';

const http = axios.create({ baseURL: "/api" });
const INSTANCES_BASE = "/instances";
const FLAVOURS = ["s3"];

export default function StorageManagement() {
  const { keycloak, initialized } = useKeycloak();

  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState("");

  // form state
  const [instanceName, setInstanceName] = useState("my-instance-id");
  const [flavour, setFlavour] = useState("");
  // S3 fields
  const [s3Url, setS3Url] = useState("http://localhost:9000");
  const [s3Key, setS3Key] = useState("");
  const [s3Secret, setS3Secret] = useState("");

  async function loadInstances() {
    const headers = await getAuthHeaders();
    const { data } = await http.get(`${INSTANCES_BASE}/`, { headers });
    setInstances(Array.isArray(data?.instances) ? data.instances : []);
  }

  useEffect(() => {
    (async () => {
      if (!initialized) return;
      try {
        await loadInstances();
      } catch (e) {
        setErr(formatError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [initialized]);

  async function handleCreate(e) {
    e.preventDefault();
    setErr("");

    if (!instanceName.trim()) return setErr("Instance name is required.");
    if (!flavour) return setErr("Flavour is required.");

    let payload;
    if (flavour === "s3") {
      if (!s3Url.trim() || !s3Key.trim() || !s3Secret.trim()) {
        return setErr("For S3, please fill endpoint URL, access key, and secret.");
      }
      payload = {
        flavour: "s3",
        instance_name: instanceName.trim(),
        instance_url: s3Url.trim(),
        aws_access_key_id: s3Key.trim(),
        aws_secret_access_key: s3Secret.trim(),
      };
    } else {
      return setErr(`Unsupported flavour: ${flavour}`);
    }

    try {
      setCreating(true);
      const headers = { ...(await getAuthHeaders()) };
      await http.post(`${INSTANCES_BASE}/`, payload, { headers });
      await loadInstances();
      // light reset of sensitive fields
      setS3Key(""); setS3Secret("");
      setFlavour("");
      alert("Instance created.");
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(i) {
    if (!window.confirm(`Delete instance "${i.name}" (${i.uuid})?`)) return;
    setErr("");
    try {
      const headers = await getAuthHeaders();
      await http.delete(`${INSTANCES_BASE}/${encodeURIComponent(i.uuid)}`, { headers });
      setInstances(prev => prev.filter(x => x.uuid !== i.uuid));
    } catch (e) {
      setErr(formatError(e));
    }
  }

  return (
    <div className="im-root">
      <h1>Storage Instances</h1>

      <section className="im-card">
        <h3>Create Instance</h3>
        <form onSubmit={handleCreate} className="im-form">
          <label className="im-field">
            <span>Instance Name *</span>
            <input value={instanceName} onChange={e => setInstanceName(e.target.value)} placeholder="my-instance-id" />
            <small className="im-muted">Used to derive a stable UUID and shown in the UI</small>
          </label>

          <label className="im-field">
            <span>Flavour *</span>
            <select value={flavour} onChange={e => setFlavour(e.target.value)}>
              <option value="">— Select flavour —</option>
              {FLAVOURS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>

          {flavour === "s3" && (
            <div className="im-row">
              <label className="im-field">
                <span>S3 Endpoint URL *</span>
                <input value={s3Url} onChange={e => setS3Url(e.target.value)} placeholder="http://localhost:9000" />
              </label>
              <label className="im-field">
                <span>Access Key *</span>
                <input value={s3Key} onChange={e => setS3Key(e.target.value)} />
              </label>
              <label className="im-field">
                <span>Secret Key *</span>
                <input type="password" value={s3Secret} onChange={e => setS3Secret(e.target.value)} />
              </label>
            </div>
          )}

          <div className="im-actions">
            <button className="im-btn im-btn-primary" type="submit" disabled={!flavour || creating}>
              {creating ? <CircularProgress size={20} color="inherit" /> : "Create"}
            </button>
            {err && <div className="im-error">{err}</div>}
          </div>
        </form>
      </section>

      <section className="im-grid">
        {loading ? (
          <div className="im-card"><p>Loading instances…</p></div>
        ) : instances.length === 0 ? (
          <div className="im-card"><p className="im-muted">No instances found.</p></div>
        ) : (
          instances.map(i => (
            <div key={i.uuid} className="im-card">
              <div className="im-head">
                <div className="im-title">
                  <strong>{i.name}</strong>
                  <span className="im-chip">{i.flavour}</span>
                </div>
                <div className="im-actions-right">
                  <button className="im-btn im-btn-danger" onClick={() => handleDelete(i)}>Delete</button>
                </div>
              </div>
              {i.config && (
                <details className="im-details">
                  <summary>Config</summary>
                  {/* Display config without UUID field */}
                  <pre className="im-pre">{JSON.stringify(i.config, (key, value) => key === 'uuid' ? undefined : value, 2)}</pre>
                </details>
              )}
            </div>
          ))
        )}
      </section>
    </div>
  );
}

