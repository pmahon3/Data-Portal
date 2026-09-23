import { useState } from "react";
import { CircularProgress } from "@mui/material";

export default function ProjectCard({ project, onManage, onDelete, onRename, deleting = false }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editingName, setEditingName] = useState(project.name);

  async function handleSave() {
    await onRename(project, editingName);
    setIsEditing(false);
  }

  function handleCancel() {
    setEditingName(project.name);
    setIsEditing(false);
  }

  return (
    <div className="pm-card">
      <div className="pm-head">
        <div className="pm-title">
          {isEditing ? (
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <input
                type="text"
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                placeholder="Project name"
                style={{ padding: "4px 6px", border: "1px solid #ccc", borderRadius: "4px" }}
              />
              <button
                className="pm-btn pm-btn-primary"
                style={{ padding: "4px 8px", fontSize: "12px" }}
                onClick={handleSave}
              >
                Save
              </button>
              <button
                className="pm-btn"
                style={{ padding: "4px 8px", fontSize: "12px" }}
                onClick={handleCancel}
              >
                Cancel
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <strong>{project.name}</strong>
              {onRename && (
                <button
                  className="pm-btn"
                  style={{ padding: "2px 6px", fontSize: "12px" }}
                  onClick={() => setIsEditing(true)}
                  title="Rename project"
                >
                  ✎
                </button>
              )}
            </div>
          )}
        </div>
        <div className="pm-actions-right">
          <button className="pm-btn pm-btn-primary" onClick={onManage}>
            Manage
          </button>
          {onDelete && (
            <button
              className="pm-btn pm-btn-danger"
              onClick={onDelete}
              disabled={deleting}
            >
              {deleting ? <CircularProgress size={18} color="inherit" /> : "Delete"}
            </button>
          )}
        </div>
      </div>

      {project.uuid && (
        <div className="pm-meta">
          <span className="pm-key">UUID:</span>
          <code className="pm-code">{project.uuid}</code>
        </div>
      )}
    </div>
  );
}
