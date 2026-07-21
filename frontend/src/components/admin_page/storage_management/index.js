import React, { useEffect, useState } from "react";
import { useKeycloak } from "@react-keycloak/web";
import { CircularProgress, Dialog } from "@mui/material";
import { useStorageInstances } from "./useStorageInstances";
import StorageInstanceForm from "./StorageForm";
import StorageInstanceCard from "./StorageCard";
import "./StorageManagement.css";

export default function StorageManagement() {
  const { keycloak, initialized } = useKeycloak();
  const roles = keycloak?.tokenParsed?.realm_access?.roles || [];
  const isAdmin = roles.includes("admin");
  const [syncMessage, setSyncMessage] = useState("");

  // Pulls everything from useStorageInstances hook to keep
  // this component purely focused on layout
  const {
    instances,
    loading,
    creating,
    syncingIds,
    err,
    fetchInstances,
    createInstance,
    deleteInstance,
    updateInstance,
    syncInstance
  } = useStorageInstances();
  const isSyncing = Object.keys(syncingIds).length > 0;

  const handleSyncInstance = async (instanceId) => {
    setSyncMessage("");
    try {
      const data = await syncInstance(instanceId);
      const sync = data?.sync;
      setSyncMessage(
        sync
          ? `Synced ${sync.file_count} files across ${sync.bucket_count} buckets.`
          : "Sync completed."
      );
      return data;
    } catch (error) {
      setSyncMessage("");
      throw error;
    }
  };

  // We wait for Keycloak to be ready, then trigger the fetch.
  // fetchInstance uses useCallback so it won't trigger an infinite loop
  useEffect(() => {
    if (!initialized) return;
    fetchInstances();
  }, [initialized, fetchInstances]);

  return (
    <div className="im-root">
      <Dialog
        open={isSyncing || Boolean(syncMessage)}
        disableEscapeKeyDown={isSyncing}
        onClose={() => !isSyncing && setSyncMessage("")}
        aria-labelledby="storage-sync-title"
        aria-describedby="storage-sync-description"
        PaperProps={{ className: "im-sync-modal" }}
        sx={{ zIndex: 4000 }}
      >
        {isSyncing ? (
          <>
            <CircularProgress size={36} />
            <strong id="storage-sync-title">Syncing storage...</strong>
            <span id="storage-sync-description">Please wait until the sync finishes.</span>
          </>
        ) : (
          <>
            <strong id="storage-sync-title">Storage sync complete</strong>
            <div className="im-success" id="storage-sync-description">{syncMessage}</div>
            <button className="im-btn" onClick={() => setSyncMessage("")}>
              Close
            </button>
          </>
        )}
      </Dialog>

      <h1>Storage Instances</h1>

      <StorageInstanceForm onCreate={createInstance} creating={creating} initialized={initialized} />

      {err && <div className="im-error" style={{ marginBottom: "1rem" }}>{err}</div>}

      {/* Handles the three main states: Loading, Empty and Success */}
      <section className="im-grid">
        {loading ? (
          // State A: Data is still being fetched */
          <div className="im-card"><p>Loading instances…</p></div>
        ) : instances.length === 0 ? (
          // State B: No instances found
          <div className="im-card"><p className="im-muted">No instances found.</p></div>
        ) : (
          // State C: Data is ready to be mapped onto StorageInstanceCards
          instances.map(i => (
            <StorageInstanceCard 
              key={i.uuid} 
              instance={i} 
              onDelete={isAdmin ? deleteInstance : null}
              onUpdate={updateInstance} 
              onSync={handleSyncInstance}
              syncing={Boolean(syncingIds[i.uuid])}
            />
          ))
        )}
      </section>
    </div>
  );
}
