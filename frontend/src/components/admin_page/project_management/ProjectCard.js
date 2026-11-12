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

  // Manage and Delete act on the project itself, so they are rendered once and
  // simply move between the header (display mode) and a dedicated actions row
  // (edit mode), where the rename controls need the full width of the header.
  const projectActions = (
    <>
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
    </>
  );

  return (
    <div className="pm-card">
      {isEditing ? (
        /* --- EDIT MODE UI --- */
        <>
          <div className="pm-head">
            <div className="pm-title">
              <span className="pm-edit-label">Rename project</span>
            </div>
          </div>
          <div className="pm-edit-row">
            <input
              type="text"
              value={editingName}
              onChange={e => setEditingName(e.target.value)}
              placeholder="Project name"
            />
            <span className="pm-edit-spacer" />
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
        </>
      ) : (
        /* --- DISPLAY MODE UI --- */
        <div className="pm-head">
          <div className="pm-title">
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
          <div className="pm-actions-right">{projectActions}</div>
        </div>
      )}

      {isEditing && (
        <div className="pm-card-actions">{projectActions}</div>
      )}

      {project.uuid && (
        <div className="pm-meta">
          <span className="pm-key">UUID:</span>
          <code className="pm-code">{project.uuid}</code>
        </div>
      )}
    </div>
  );
}
