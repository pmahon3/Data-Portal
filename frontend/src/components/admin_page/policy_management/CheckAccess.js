import React, { useState } from "react";
import { formatError } from "../../../utils/errorUtils";
import { getAuthHeaders } from "../../../utils/authUtils";
import { describeCheck } from "./describeCheck.js";

/**
 * Check a person's access: may they do this action on this path, and which of their policies
 * allows it (DS-check-access; AC-1, AC-3). Answered by the backend exactly as a request would be.
 */

export default function CheckAccess({ http, instanceOptions }) {
  const [username, setUsername] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [path, setPath] = useState("");
  const [action, setAction] = useState("read");
  const [answer, setAnswer] = useState(null);
  const [err, setErr] = useState("");
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState(false);

  const handleCheck = async (e) => {
    e.preventDefault();
    setErr("");
    setAnswer(null);
    if (!username.trim() || !instanceName || !path.trim()) {
      setErr("Username, instance and path are required.");
      return;
    }
    setChecking(true);
    try {
      const { data } = await http.get("/policies/check", {
        headers: await getAuthHeaders(),
        params: {
          username: username.trim(),
          instance_name: instanceName,
          resource: path.trim(),
          action,
        },
      });
      setAnswer(describeCheck(data, username.trim(), action, path.trim()));
    } catch (e2) {
      setErr(formatError(e2));
    } finally {
      setChecking(false);
    }
  };

  return (
    <section className="pm-card" aria-label="Check access">
      <h3>Check Access</h3>
      {!open && (
        <button type="button" className="pm-btn" onClick={() => setOpen(true)}>
          Check someone's access
        </button>
      )}
      {open && (
        <form onSubmit={handleCheck} className="pm-form">
          <div className="pm-row">
            <label className="pm-field">
              <span>Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="who to check, e.g. bob"
              />
            </label>
            <label className="pm-field">
              <span>Instance</span>
              <select value={instanceName} onChange={(e) => setInstanceName(e.target.value)}>
                <option value="">— Select —</option>
                {instanceOptions.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="pm-row">
            <label className="pm-field">
              <span>Path</span>
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="bucket/path/file.ext or bucket/folder/"
              />
            </label>
            <label className="pm-field">
              <span>Action</span>
              <select value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="read">read</option>
                <option value="write">write</option>
                <option value="delete">delete</option>
              </select>
            </label>
          </div>
          <div className="pm-actions">
            <button className="pm-btn" type="submit" disabled={checking}>
              Check
            </button>
          </div>
        </form>
      )}
      {err && <div className="pm-error">{err}</div>}
      {answer && (
        <div role="status" className="pm-rule-preview">
          <p>{answer.sentence}</p>
          {answer.reasons.length > 0 && (
            <ul>
              {answer.reasons.map((reason) => (
                <li key={reason}>
                  <code>{reason}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
