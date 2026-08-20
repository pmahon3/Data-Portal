import { useState, useCallback } from 'react';
import axios from 'axios';
import { getAuthHeaders } from '../../../utils/authUtils';
import { formatError } from '../../../utils/errorUtils';

const http = axios.create({ baseURL: "/api" });
const INSTANCES_BASE = "/instances";

// Custom hook to manage storage instance logic.
// Encapsulates CRUD operations and state management (loading, errors, data).
export function useStorageInstances() {
  const [instances, setInstances] = useState([]);   // List of storage instances
  const [loading, setLoading] = useState(true);     // Global loading state for instances
  const [creating, setCreating] = useState(false);  // Submission state
  const [syncingIds, setSyncingIds] = useState({});  // Per-instance sync state
  const [deletingIds, setDeletingIds] = useState({});  // Per-instance delete state
  const [err, setErr] = useState("");               // Error display message

  // Fetches the full list of instances from the server.
  // Wrapped in useCallback to prevent unnecessary re-renders in parent components
  // that might include this function in a useEffect dependency array.
  const fetchInstances = useCallback(async () => {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const { data } = await http.get(`${INSTANCES_BASE}/`, { headers });

      // Ensure data is an array before setting state
      setInstances(Array.isArray(data?.instances) ? data.instances : []);
      setErr("");
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setLoading(false);
    }
  }, []);


  // Creates a new storage instance
  const createInstance = async (payload, selectedProjects = []) => {
    setCreating(true);
    setErr("");
    try {
      const headers = await getAuthHeaders();
      // Project attachment must happen in the create request for manager-scoped access.
      await http.post(
        `${INSTANCES_BASE}/`,
        { ...payload, project_names: selectedProjects },
        { headers }
      );

      // Re-fetch the entire list to ensure the UI is in sync with the server
      await fetchInstances();
      return true; // Success
    } catch (e) {
      setErr(formatError(e));
      throw e; // Let the caller handle the error if needed
    } finally {
      setCreating(false);
    }
  };

  // Delete a storage instance by ID
  const deleteInstance = async (instance) => {
    if (!window.confirm(`Delete instance "${instance.name}"? Please note this process takes some time.`)) return false;
    setErr("");
    setDeletingIds(prev => ({ ...prev, [instance.uuid]: true }));
    try {
      const headers = await getAuthHeaders();
      await http.delete(`${INSTANCES_BASE}/${encodeURIComponent(instance.uuid)}`, { headers });
      setInstances(prev => prev.filter(x => x.uuid !== instance.uuid));
      return true;
    } catch (e) {
      setErr(formatError(e));
      return false;
    } finally {
      setDeletingIds(prev => {
        const next = { ...prev };
        delete next[instance.uuid];
        return next;
      });
    }
  };

  // Update the name of a storage instance
  const updateInstance = async (instanceId, newName) => {
    try {
      const headers = await getAuthHeaders();
      await http.patch(`${INSTANCES_BASE}/${encodeURIComponent(instanceId)}`, 
        { instance_name: newName.trim() }, 
        { headers }
      );
      setInstances(prev => prev.map(x => x.uuid === instanceId ? { ...x, name: newName.trim() } : x));
      return true;
    } catch (e) {
      throw e;
    }
  };

  // Sync object storage contents into the database for one instance
  const syncInstance = async (instanceId) => {
    setSyncingIds(prev => ({ ...prev, [instanceId]: true }));
    try {
      const headers = await getAuthHeaders();
      const { data } = await http.post(`${INSTANCES_BASE}/${encodeURIComponent(instanceId)}/sync`, null, { headers });
      return data;
    } catch (e) {
      throw e;
    } finally {
      setSyncingIds(prev => {
        const next = { ...prev };
        delete next[instanceId];
        return next;
      });
    }
  };

  // Expose state and methods to the consuming component
  return {
    instances,
    loading,
    creating,
    syncingIds,
    deletingIds,
    err,
    setErr,
    fetchInstances,
    createInstance,
    deleteInstance,
    updateInstance,
    syncInstance
  };
}
