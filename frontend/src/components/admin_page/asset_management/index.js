import React, { useEffect, useState } from "react";
import axios from "axios";
import { useKeycloak } from "@react-keycloak/web";
import EndpointCard from "./EndpointCard.js";
import { formatError } from "../../../utils/errorUtils";
import { getAuthHeaders } from '../../../utils/authUtils';
import "./AssetManagement.css";

// const http = axios.create({ baseURL: "http://localhost:8000" });
const http = axios.create({ baseURL: "/api" });

function Spinner() {
  return <div style={{ padding: 16 }}>Loading…</div>;
}

function ErrorNote({ children }) {
  return (
    <div style={{
      background: "#fdecea",
      color: "#611a15",
      border: "1px solid #f5c6cb",
      borderRadius: 8,
      padding: 12,
      margin: 12,
    }}>
      {children}
    </div>
  );
}

export default function AssetManagement({ bootstrap, title = "Storage Endpoints" }) {
  const { keycloak, initialized } = useKeycloak();
  const username = keycloak?.tokenParsed?.preferred_username;

  const [boot, setBoot] = useState(bootstrap || null);
  const [loading, setLoading] = useState(!bootstrap);
  const [error, setError] = useState(null);
  // { [endpointUuid]: { read: Set, write: Set, delete: Set } }
  const [selected, setSelected] = useState({});
  const [busy, setBusy] = useState(null); // "down" | "up" | "del" | null
  const [busyID, setBusyID] = useState(null); // UUID of the endpoint that is busy | null

  const getSel = (uuid) => {
    const ent = selected[uuid];
    return { 
      read: (ent && ent.read) || new Set(), 
      write: (ent && ent.write) || new Set(),
      delete: (ent && ent.delete) || new Set()
    };
  };

  // Fetch the current user's storage endpoint dashboard
  useEffect(() => {
    const loadStorageEndpoints = async () => {
      try {
        setLoading(true);
        setError(null);
        const headers = await getAuthHeaders();
        if (!username) {
          throw new Error("Username not found in token");
        }
        const { data } = await http.get(`users/${encodeURIComponent(username)}/instances`, {
          headers,
          params: { _t: Date.now() },
        });
        setBoot(data);
      } catch (e) {
        setError(formatError(e));
      } finally {
        setLoading(false);
      }
    };

    if (!boot) loadStorageEndpoints();
  }, [boot, username]);

  if (loading) return <Spinner />;
  if (error) return <ErrorNote>{String(error)}</ErrorNote>;
  if (!boot) return <ErrorNote>No data.</ErrorNote>;

  const handleSelectedChange = (endpointUuid, access, nextSet) => {
    setSelected((prev) => ({
      ...prev,
      [endpointUuid]: { ...(prev[endpointUuid] || {}), [access]: new Set(nextSet) },
    }));
  };

  const instances = boot.instances || {};

  return (
    <div style={{ padding: 16, fontFamily: "Inter, system-ui, Arial" }}>
      <h2 style={{ margin: "0 0 12px" }}>{title}</h2>

      {Object.entries(instances).length === 0 ? (
        <ErrorNote>No endpoints available.</ErrorNote>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          {Object.entries(instances).map(
            ([endpointName, endpointUuid]) => (
              <EndpointCard
                key={endpointUuid}
                endpointName={endpointName}
                endpointUuid={endpointUuid}
                selectedByAccess={getSel(endpointUuid)}
                onSelectedChange={(access, nextSet) =>
                  handleSelectedChange(endpointUuid, access, nextSet)
                }
                http={http}
                busy={busy}
                setBusy={setBusy}
                busyID={busyID}
                setBusyID={setBusyID}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}
