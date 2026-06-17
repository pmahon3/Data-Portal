import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useKeycloak } from "@react-keycloak/web";
import { CircularProgress } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import { formatError } from "../../utils/errorUtils";
import { getAuthHeaders } from "../../utils/authUtils";

const http = axios.create({ baseURL: "/api" });

export default function MyPolicies() {
  const { initialized } = useKeycloak();
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  async function loadPolicies() {
    const headers = await getAuthHeaders();
    const { data } = await http.get("/policies/me", { headers });
    setPolicies(Array.isArray(data?.details) ? data.details : []);
  }

  useEffect(() => {
    (async () => {
      if (!initialized) return;
      try {
        await loadPolicies();
      } catch (e) {
        setErr(formatError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [initialized]);

  const policyRows = useMemo(
    () => policies.map((policy, index) => ({
      id: `${policy.instance_uuid || "instance"}-${policy.resource || "resource"}-${policy.action || "action"}-${index}`,
      instance_name: policy.instance_name || "",
      resource: policy.resource || "",
      action: policy.action || "",
    })),
    [policies]
  );

  const policyColumns = useMemo(() => [
    { field: "instance_name", headerName: "Instance Name", flex: 1, minWidth: 180 },
    { field: "resource", headerName: "Resource", flex: 1.5, minWidth: 220 },
    { field: "action", headerName: "Action", width: 120 },
  ], []);

  return (
    <div style={{ display: "grid", gap: 16, padding: 16, minWidth: 0 }}>
      <h2 style={{ margin: 0 }}>My Policies</h2>

      {err && (
        <div style={{
          background: "#fdecea",
          color: "#611a15",
          border: "1px solid #f5c6cb",
          borderRadius: 8,
          padding: 12,
        }}>
          {err}
        </div>
      )}

      <section style={{
        background: "#fff",
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        minWidth: 0,
      }}>
        {loading ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <CircularProgress size={20} />
            <span>Loading policies...</span>
          </div>
        ) : policyRows.length === 0 ? (
          <p style={{ color: "#6b7280", margin: 0 }}>No policies found.</p>
        ) : (
          <div style={{ height: 520, width: "100%", minWidth: 0 }}>
            <DataGrid
              rows={policyRows}
              columns={policyColumns}
              sx={{
                width: "100%",
                "& .MuiDataGrid-columnHeaderTitle": { fontWeight: 700 },
                "& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within": { outline: "none" },
              }}
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
