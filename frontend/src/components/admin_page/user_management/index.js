import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useKeycloak } from '@react-keycloak/web';
import { CircularProgress } from '@mui/material';
import { DataGrid } from "@mui/x-data-grid";
import './User_Management.css';
import { formatError } from '../../../utils/errorUtils';
import { getAuthHeaders } from '../../../utils/authUtils';

const http = axios.create({ baseURL: "/api" });

const apiDeleteUser = async (uname) => {
  const headers = await getAuthHeaders();
  await http.delete(`/users/${encodeURIComponent(uname)}`, { headers });
};

export default function UserManagement() {
  const { keycloak, initialized } = useKeycloak();
  const roles = keycloak?.tokenParsed?.realm_access?.roles || [];
  const isAdmin = roles.includes("admin");

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState('');

  // form state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [rolesText, setRolesText] = useState('');

  // API calls (use the hook-provided token each time)
  const apiListUsers = async () => {
    const headers = await getAuthHeaders();
    const { data } = await http.get('/users/', { headers });
    return data;
  };

  const apiCreateUser = async (payload) => {
    const headers = await getAuthHeaders();
    const res= await http.post('/users/', payload, { headers });
    console.log("This is user created: ");
    console.dir(res.data)
  };

  useEffect(() => {
    (async () => {
      if (!initialized) return; // wait until keycloak is ready
      try {
        const data = await apiListUsers();
        if (Array.isArray(data)) setUsers(data);
      } catch (e) {
        setErr(formatError(e));
      } finally {
        setLoading(false);
      }
    })();
    // re-run if auth state flips from uninitialized to initialized
  }, [initialized]); 

  const rolesArray = useMemo(
    () => rolesText.split(',').map(r => r.trim()).filter(Boolean),
    [rolesText]
  );

  async function handleCreate(e) {
    e.preventDefault();
    setErr('');
    if (!username) return setErr('Username is required.');
    if (!email) return setErr('Email is required');
    if (!password) return setErr('Password is required.');
    setCreating(true);
    try {
      await apiCreateUser({
        username,
        password,
        full_name: fullName,
        email,
        roles: rolesArray,
      });

      // update (or re-fetch with apiListUsers())
      setUsers(prev => {
        const next = { username, full_name: fullName, email, roles: rolesArray };
        const exists = prev.some(u => u.username === username);
        return exists ? prev.map(u => (u.username === username ? next : u)) : [next, ...prev];
      });

      setUsername(''); setPassword(''); setFullName(''); setEmail(''); setRolesText('');
      alert(`User ${username} created/updated.`);
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setCreating(false);
    }
  }

  const handleDelete = useCallback(async (u) => {
    if (!window.confirm(`Delete user "${u.username}"?`)) return;
    setErr('');
    try {
      await apiDeleteUser(u.username);
      setUsers(prev => prev.filter(x => x.username !== u.username));
      alert(`Deleted ${u.username}`);
    } catch (e) {
      setErr(formatError(e));
    }
  }, []);

  // Creates a saved list of users with a unique id for MUI data grid
  const userRows = useMemo(
    () => users.map((u) => ({
      id: u.username,
      ...u,
    })),
    [users]
  );

  // Configurations for the user table to be rendered with MUI data grid
  const userColumns = useMemo(() => {
    const cols = [
      { field: "username", headerName: "Username", flex: 1, minWidth: 140 },
      { field: "email", headerName: "Email", flex: 1.5, minWidth: 220, renderCell: (params) => String(params.value || "") },
      { field: "roles", headerName: "Roles", flex: 1, minWidth: 180, renderCell: (params) => {
          // Safely formats an array of roles into a comma-separated string and filter out invalid entries
          const roles = Array.isArray(params.value)
            ? params.value.filter(Boolean).map(r => String(r).trim()).filter(r => r.toLowerCase() !== 'default-roles-ams-portal')
            : [];
          return roles.join(", ");
        }
      },
    ];
    if (isAdmin) {
      cols.push({
        field: "delete",
        headerName: "",
        width: 120,
        sortable: false,
        filterable: false,
        renderCell: (params) => (
          <button className="um-btn um-btn-danger" onClick={() => handleDelete(params.row)}>Delete</button>
        ),
      });
    }
    return cols;
  }, [isAdmin, handleDelete]);

  return (
    <div className="um-root">
      <h1>User Management</h1>

      <section className="um-card">
        <h3>Create / Update User</h3>
        <form onSubmit={handleCreate} className="um-form">
          <label className="um-field">
            <span>Username *</span>
            <input value={username} onChange={e => setUsername(e.target.value)} placeholder="jane.doe" />
          </label>

          <label className="um-field">
            <span>Password *</span>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" required />
          </label>

          <label className="um-field">
            <span>Full name</span>
            <input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Jane Doe" />
          </label>

          <label className="um-field">
            <span>Email *</span>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="jane@example.com" />
          </label>

          <label className="um-field">
            <span>Roles (comma-separated)</span>
            <input value={rolesText} onChange={e => setRolesText(e.target.value)} placeholder="admin, user" />
          </label>

          <div className="um-actions">
            <button className="um-btn um-btn-primary" type="submit" disabled={creating}>
              {creating ? <CircularProgress size={20} color="inherit" /> : "Create User"}
            </button>
            {err && <div className="um-error">{err}</div>}
          </div>
        </form>
      </section>

      <section className="um-card">
        <h3>Users</h3>
        {loading ? (
          <p>Loading users…</p>
        ) : users.length === 0 ? (
          <p className="um-muted">No users to show.</p>
        ) : (
          <div className="um-grid">
            <DataGrid
              rows={userRows}
              columns={userColumns}
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
