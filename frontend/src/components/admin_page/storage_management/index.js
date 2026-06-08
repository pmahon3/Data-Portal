import React, { useEffect } from "react";
import { useKeycloak } from "@react-keycloak/web";
import { useStorageInstances } from "./useStorageInstances";
import StorageInstanceForm from "./StorageForm";
import StorageInstanceCard from "./StorageCard";
import "./StorageManagement.css";

export default function StorageManagement() {
  const { keycloak, initialized } = useKeycloak();
  const roles = keycloak?.tokenParsed?.realm_access?.roles || [];
  const isAdmin = roles.includes("admin");

  // Pulls everything from useStorageInstances hook to keep
  // this component purely focused on layout
  const {
    instances,
    loading,
    creating,
    err,
    fetchInstances,
    createInstance,
    deleteInstance,
    updateInstance
  } = useStorageInstances();

  // We wait for Keycloak to be ready, then trigger the fetch.
  // fetchInstance uses useCallback so it won't trigger an infinite loop
  useEffect(() => {
    if (!initialized) return;
    fetchInstances();
  }, [initialized, fetchInstances]);

  return (
    <div className="im-root">
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
            />
          ))
        )}
      </section>
    </div>
  );
}
