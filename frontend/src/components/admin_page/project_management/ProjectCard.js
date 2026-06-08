import { CircularProgress } from "@mui/material";

export default function ProjectCard({ project, onManage, onDelete, deleting = false }) {
  return (
    <div className="pm-card">
      <div className="pm-head">
        <div className="pm-title">
          <strong>{project.name}</strong>
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
