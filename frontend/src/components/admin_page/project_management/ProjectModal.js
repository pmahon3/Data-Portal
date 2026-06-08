import React, { useState } from "react";
import { Dialog, IconButton, Tooltip } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";

export default function ProjectModal({ project, onClose, onUpdate, isAdmin }) {
  const [userName, setUserName] = useState("");
  const [managerName, setManagerName] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [localErr, setLocalErr] = useState("");

  const users = project.users || [];
  const managers = project.managers || [];
  const storageInstances = project.storageInstances || [];

  async function addUser(e) {
    e.preventDefault();
    setLocalErr("");

    const name = userName.trim();
    if (!name) return setLocalErr("User name is required.");
    if (users.includes(name)) return setLocalErr("User is already added.");

    try {
      await onUpdate({ ...project, users: [...users, name] });
      setUserName("");
    } catch (err) {
      setLocalErr(err.message);
    }
  }

  async function deleteUser(name) {
    if (!window.confirm(`Remove user "${name}" from project "${project.name}"?`)) return;
    setLocalErr("");
    try {
      await onUpdate({ ...project, users: users.filter(user => user !== name) });
    } catch (err) {
      setLocalErr(err.message);
    }
  }

  async function addManager(e) {
    e.preventDefault();
    setLocalErr("");

    const name = managerName.trim();
    if (!name) return setLocalErr("Manager name is required.");
    if (managers.includes(name)) return setLocalErr("Manager is already added.");

    try {
      await onUpdate({ ...project, managers: [...managers, name] });
      setManagerName("");
    } catch (err) {
      setLocalErr(err.message);
    }
  }

  async function deleteManager(name) {
    if (!window.confirm(`Remove manager "${name}" from project "${project.name}"?`)) return;
    setLocalErr("");
    try {
      await onUpdate({ ...project, managers: managers.filter(manager => manager !== name) });
    } catch (err) {
      setLocalErr(err.message);
    }
  }

  async function addStorageInstance(e) {
    e.preventDefault();
    setLocalErr("");

    const name = instanceName.trim();
    if (!name) return setLocalErr("Storage instance name is required.");
    if (storageInstances.includes(name)) {
      return setLocalErr("Storage instance is already added.");
    }

    try {
      await onUpdate({ ...project, storageInstances: [...storageInstances, name] });
      setInstanceName("");
    } catch (err) {
      setLocalErr(err.message);
    }
  }

  async function deleteStorageInstance(name) {
    if (!window.confirm(`Remove storage instance "${name}" from project "${project.name}"?`)) return;
    setLocalErr("");
    try {
      await onUpdate({
        ...project,
        storageInstances: storageInstances.filter(instance => instance !== name),
      });
    } catch (err) {
      setLocalErr(err.message);
    }
  }

  return (
    <Dialog 
      open={true} 
      onClose={onClose}
      aria-labelledby="project-management-title"
      classes={{ paper: 'pm-modal' }}
      maxWidth="lg" /* Just to allow width expansion */
      style={{ zIndex: 4000 }}
    >
        <div className="pm-modal-head">
          <div>
            <h3 id="project-management-title">Manage Project</h3>
            <p className="pm-muted">{project.name}</p>
          </div>
          <button className="pm-btn" onClick={onClose}>Close</button>
        </div>

        <div className="pm-error" style={{ minHeight: '1.5rem', marginBottom: '8px' }}>
          {localErr}
        </div>

        <div className="pm-modal-grid">
          <section className="pm-panel">
            <h4 style={{ fontSize: '1.25rem' }}>Users</h4>
            <form className="pm-inline-form" onSubmit={addUser}>
              <input
                value={userName}
                onChange={e => setUserName(e.target.value)}
                placeholder="username"
              />
              <Tooltip title="Add User">
                <IconButton color="primary" type="submit" size="small">
                  <AddIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </form>

            {/* List of users */}
            <ProjectItemList
              emptyText="No users added."
              items={users}
              onDelete={deleteUser}
            />
          </section>

          <section className="pm-panel">
            <h4 style={{ fontSize: '1.25rem' }}>Managers</h4>
            {isAdmin && (
              <form className="pm-inline-form" onSubmit={addManager}>
                <input
                  value={managerName}
                  onChange={e => setManagerName(e.target.value)}
                  placeholder="manager name"
                />
                <Tooltip title="Add Manager">
                  <IconButton color="primary" type="submit" size="small">
                    <AddIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </form>
            )}

            {/* List of managers */}
            <ProjectItemList
              emptyText="No managers added."
              items={managers}
              onDelete={deleteManager}
              hideDelete={!isAdmin}
            />
          </section>

          <section className="pm-panel">
            <h4 style={{ fontSize: '1.25rem' }}>Storage Instances</h4>
            {isAdmin && (
              <form className="pm-inline-form" onSubmit={addStorageInstance}>
                <input
                  value={instanceName}
                  onChange={e => setInstanceName(e.target.value)}
                  placeholder="instance name"
                />
                <Tooltip title="Add Storage Instance">
                  <IconButton color="primary" type="submit" size="small">
                    <AddIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </form>
            )}

            {/* List of storage instances */}
            <ProjectItemList
              emptyText="No storage instances added."
              items={storageInstances}
              onDelete={deleteStorageInstance}
              hideDelete={!isAdmin}
            />
          </section>
        </div>
    </Dialog>
  );
}

function ProjectItemList({ emptyText, items, onDelete, hideDelete }) {
  if (items.length === 0) {
    return <p className="pm-muted">{emptyText}</p>;
  }

  return (
    <div className="pm-list">
      {items.map(item => (
        <div className="pm-list-item" key={item}>
          <span>{item}</span>
          {!hideDelete && (
            <Tooltip title="Delete">
              <IconButton color="error" onClick={() => onDelete(item)} size="small" style={{ padding: '4px' }}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </div>
      ))}
    </div>
  );
}
