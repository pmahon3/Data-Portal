import React, { useState } from "react";
import { CircularProgress } from "@mui/material";

export default function ProjectForm({ onCreate, creating = false }) {
  const [projectName, setProjectName] = useState("");
  const [localErr, setLocalErr] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setLocalErr("");

    const name = projectName.trim();
    if (!name) return setLocalErr("Project name is required.");

    try {
      if (onCreate) {
        await onCreate({ name });
      }
      setProjectName("");
    } catch (err) {
      // Keep the entered value so the parent can show the API error.
    }
  }

  return (
    <section className="pm-card">
      <h3>Create Project</h3>
      <form onSubmit={handleSubmit} className="pm-form">
        <label className="pm-field">
          <span>Project Name *</span>
          <input
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
            placeholder="inn-project"
          />
          <small className="pm-muted">Shown in the UI and used to identify the project</small>
        </label>

        <div className="pm-actions">
          <button className="pm-btn pm-btn-primary" type="submit" disabled={creating}>
            {creating ? <CircularProgress size={20} color="inherit" /> : "Create Project"}
          </button>
          {localErr && <div className="pm-error">{localErr}</div>}
        </div>
      </form>
    </section>
  );
}
