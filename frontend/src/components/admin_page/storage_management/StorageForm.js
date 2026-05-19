import React, { useState } from 'react';
import { CircularProgress } from '@mui/material';

const FLAVOURS = ["s3"];

export default function StorageInstanceForm({ onCreate, creating }) {
  const [instanceName, setInstanceName] = useState("");
  const [flavour, setFlavour] = useState("");
  const [s3Url, setS3Url] = useState("http://localhost:9000");
  const [s3Key, setS3Key] = useState("");
  const [s3Secret, setS3Secret] = useState("");
  const [s3Region, setS3Region] = useState("");
  const [localErr, setLocalErr] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setLocalErr("");

    if (!instanceName.trim()) return setLocalErr("Instance name is required.");
    if (!flavour) return setLocalErr("Flavour is required.");

    let payload;
    if (flavour === "s3") {
      if (!s3Url.trim() || !s3Key.trim() || !s3Secret.trim()) {
        return setLocalErr("For S3, please fill endpoint URL, access key, and secret.");
      }
      payload = {
        flavour: "s3",
        instance_name: instanceName.trim(),
        instance_url: s3Url.trim(),
        aws_access_key_id: s3Key.trim(),
        aws_secret_access_key: s3Secret.trim(),
      };
      if (s3Region.trim()) {
        payload.region_name = s3Region.trim();
      }
    } else {
      return setLocalErr(`Unsupported flavour: ${flavour}`);
    }

    try {
      await onCreate(payload);
      // Light reset of sensitive fields
      setS3Key(""); 
      setS3Secret("");
      alert("Instance created.");
    } catch (err) {
      // Errors are handled by the hook/parent, but we catch so we don't clear the form
    }
  }

  return (
    <section className="im-card">
      <h3>Create Instance</h3>
      <form onSubmit={handleSubmit} className="im-form">
        <label className="im-field">
          <span>Instance Name *</span>
          <input value={instanceName} onChange={e => setInstanceName(e.target.value)} placeholder="my-instance-name" />
          <small className="im-muted">Used to derive a stable UUID and shown in the UI</small>
        </label>

        <label className="im-field">
          <span>Flavour *</span>
          <select value={flavour} onChange={e => setFlavour(e.target.value)}>
            <option value="">— Select flavour —</option>
            {FLAVOURS.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>

        {/* S3 Specific Fields: Only visible if "s3" is selected */}
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
            <label className="im-field">
              <span>Region Name</span>
              <input value={s3Region} onChange={e => setS3Region(e.target.value)} placeholder="us-east-2" />
            </label>
          </div>
        )}

        {/* Form Actions */}
        <div className="im-actions">
          <button className="im-btn im-btn-primary" type="submit" disabled={!flavour || creating}>
            {creating ? <CircularProgress size={20} color="inherit" /> : "Create"}
          </button>
          {localErr && <div className="im-error">{localErr}</div>}
        </div>
      </form>
    </section>
  );
}
