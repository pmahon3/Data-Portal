import React, { useState } from "react";
import Tree from "./Tree.js";
import { CircularProgress } from "@mui/material";
import { formatError } from "../../../utils/errorUtils";
import { downloadAssetBundle, deleteAssets } from "./actions.js";
import { getAuthHeaders } from '../../../utils/authUtils';

export default function EndpointCard({
  endpointName,
  endpointUuid,
  selectedByAccess,       // { read: Set<string>, write: Set<string>, delete: Set<string> }
  onSelectedChange,       // (access: 'read'|'write'|'delete', nextSet: Set<string>) => void
  http,
  busy,
  setBusy,
  busyID,
  setBusyID,
}) {
  const [open, setOpen] = useState(false);
  const [treesByAccess, setTreesByAccess] = useState({});
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [assetError, setAssetError] = useState(null);

  // Fetch assets for this endpoint
  const fetchAssets = async (forceRefresh = false) => {
    try {
      setLoadingAssets(true);
      setAssetError(null);
      const authHeaders = await getAuthHeaders();
      //const { data } = await http.get(`/assets/dashboard/${encodeURIComponent(endpointUuid)}`, {
      const { data } = await http.get(`/tree/dashboard/${encodeURIComponent(endpointUuid)}`, {
 
      headers: authHeaders,
        params: { _t: Date.now(), ...(forceRefresh ? { refresh: 1 } : {}) },
      });
      setTreesByAccess(data.assets[endpointUuid] || {});
    } catch (e) {
      console.error(`[EndpointCard] Failed to fetch assets for ${endpointName}:`, e);
      setAssetError(e?.response?.data?.detail || e?.message || "Failed to load assets");
    } finally {
      setLoadingAssets(false);
    }
  };

  // Toggle card open/closed - fetch assets on first open
  const handleToggle = () => {
    const willOpen = !open;
    setOpen(willOpen);
    // Fetch assets when opening if not already loaded
    if (willOpen && Object.keys(treesByAccess).length === 0 && !loadingAssets) {
      fetchAssets(false);
    }
  };

  // onMutate callback to refresh assets after upload/delete
  const onMutate = () => fetchAssets(true);

  // Normalize to explicit read/write arrays
  const access = normalizeAccess(treesByAccess);
  const readArray = access.read;
  const writeArray = access.write;
  const deleteArray = access.delete;

  // turning array to a hashmap with file id as  key for faster look up
  const readIndex = new Map(readArray.map(n => [String(n.id), n]));
  const writeIndex = new Map(writeArray.map(n => [String(n.id), n]));
  const deleteIndex = new Map(deleteArray.map(n => [String(n.id), n]));

  const hasRead = readArray.length > 0;
  const hasWrite = writeArray.length > 0;
  const hasDelete = deleteArray.length > 0;

  // Compute selections we need
  const readLeaves = getSelectedLeaves(readArray, selectedByAccess.read || new Set());
  const writeTopFolders = getSelectTopLevel(writeArray, selectedByAccess.write || new Set(), false);
  const deleteTopSelected = getSelectTopLevel(deleteArray, selectedByAccess.delete || new Set(), true);

  // This one allows multiple items to be selected at the same time. We may need to get back to this
  const onTreeChange = (accessKey) => (nextSet) =>
    onSelectedChange(accessKey, new Set(nextSet));

  // --------------------- Download (from READ selection) ---------------------

const handleDownload = async () => {
  if (!hasRead) return alert("No read permission.");
  if (readLeaves.length === 0) return alert("Select files or folders in READ.");

  setBusy("down");
  setBusyID(endpointUuid);
  try {
    const fileIds = readLeaves
      .filter((id) => String(id).startsWith("file-"))
      .map((id) => parseInt(String(id).replace("file-", ""), 10));

    if (fileIds.length === 0) {
      alert("No valid files selected for download.");
      setBusy(null);
      setBusyID(null);
      return;
    }

    await downloadAssetBundle(http, endpointName, fileIds);
    console.log(`[Download] Triggered downloads for ${fileIds.length} file(s) from "${endpointName}"`);
  } catch (e) {
    console.error(`[Download] Download failed for endpoint "${endpointName}":`, e);
    let errMsg = formatError(e);
    if (e.response && e.response.data instanceof Blob) {
      try {
        const text = await e.response.data.text();
        const json = JSON.parse(text);
        errMsg = json.detail || json.message || text;
      } catch (err) {
        // use default errMsg
      }
    }
    alert(`Download failed: ${errMsg}`);
  } finally {
    setBusy(null);
    setBusyID(null);
  }
};

  // This validation/lookup used to live inline in the single-file upload flow.
  // It is now shared by both file upload and folder upload.
  // Validate the write-tree selection and return the selected destination
  // folder's DB id plus its bucket. Both upload modes start from this target.
  // It reads the current selection and tree data directly from this component's existing state/props.
  async function getWriteUploadTarget() {
    // Check if user has write permission at all for this endpoint
    if (!hasWrite) {
      alert("No write permission for this endpoint.");
      return null;
    }

    // Ensure a folder is selected in the UI
    if (!selectedByAccess.write || selectedByAccess.write.size === 0) {
      alert("Select a folder to upload to.");
      return null;
    }

    // Verify writeTopFolders is not empty after filtering
    if (writeTopFolders.length === 0) {
      alert("No valid folder selected for upload.");
      return null;
    }

    // Ensure exactly one folder is selected
    if (writeTopFolders.length > 1) {
      alert("Please select exactly ONE folder to upload to.");
      return null;
    }
    //That part extracts the upload destination information from the folder the user selected in the write tree.
    const folderId = String(writeTopFolders[0]);
    const folderNode = writeIndex.get(folderId);
    const bucket = folderNode?.li_attr?.bucket;
    if (!bucket) {
      alert("No bucket found for selected folder.");
      return null;
    }

    return { folderId, bucket };
  }

  // Upload one or more files directly into the selected destination folder.
  const handleFileUpload = async () => {
    const target = await getWriteUploadTarget();
    if (!target) return;

    const { folderId, bucket } = target;
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.style.position = "fixed";
    input.style.left = "-9999px";
    document.body.appendChild(input);

    input.onchange = async () => {
      if (!input.files || input.files.length === 0) {
        document.body.removeChild(input);
        return;
      }
      setBusy("up");
      setBusyID(endpointUuid)
      try {
        const files = Array.from(input.files);

        for (const file of files) {
          let authHeaders = await getAuthHeaders();
          const { data } = await http.post("/tree/files/upload/init", {
            instance_name: endpointName,
            bucket,
            folder_id: Number(folderId),
            filename: file.name,
            content_type: file.type || "application/octet-stream",
          }, { headers: authHeaders });

          // Start with `data.url`. If it is missing, the first `if` tries
          // `data.presigned_urls`. If that is also missing, the second `if`
          // tries `data.urls`.
          // Optional chaining: `data?.url` means "use data.url if data exists;
          // otherwise return undefined instead of throwing an error".
          let presignSource = data?.url;
          
          
          if (presignSource === null || presignSource === undefined) {
            presignSource = data?.presigned_urls;
          }
          if (presignSource === null || presignSource === undefined) {
            presignSource = data?.urls;
          }
          const presigns = normalizePresigns(presignSource);
          for (const entry of presigns) {
            await uploadViaPresigned(entry, file);
          }

          // Refresh auth headers in case they expired between init and complete
          authHeaders = await getAuthHeaders();
          await http.post("/tree/files/upload/complete", {
            instance_name: endpointName,
            file_id: data.file_id,
          }, { headers: authHeaders });
        }

        if (onMutate) onMutate(); // refresh dashboard with ?refresh=1 upstream  ------> TODO: need to further investigate refresh dashboard after upload or cerated new policy
        console.log(`[Upload] Successfully uploaded ${files.length} file(s) in endpoint "${endpointName}"`);
        alert("File upload complete.");
      } catch (e) {
        console.error(`[Upload] Upload failed for endpoint "${endpointName}":`, e);
        if (e?.response?.status === 409) {
          alert(`Upload failed! A file with the same name already exists in this folder.`);
        } else {
          alert(`Upload failed: ${formatError(e)}`);
        }
      } finally {
        setBusy(null);
        setBusyID(null);
        try { document.body.removeChild(input); } catch {}
      }
    };

    input.click();
  };

  // Upload a local directory by recreating its relative paths in Postgres first,
  // then reusing the existing per-file presigned upload flow for each file.
  const handleFolderUpload = async () => {
    const target = await getWriteUploadTarget();
    if (!target) return;

    const { folderId, bucket } = target;
    const input = document.createElement("input");
    input.type = "file";
    input.webkitdirectory = true;
    input.multiple = true;
    input.style.position = "fixed";
    input.style.left = "-9999px";
    document.body.appendChild(input);

    input.onchange = async () => {
      if (!input.files || input.files.length === 0) {
        document.body.removeChild(input);
        return;
      }
      setBusy("up");
      setBusyID(endpointUuid)
      try {
        // flat list of File object returned by webkitdirectory
        const files = Array.from(input.files).filter(file => !isDirectoryPlaceholder(file));

        // Cache folder ids per relative path so repeated siblings do not keep
        // calling the backend for the same nested directory chain.
        const folderIdByRelativePath = new Map([["", Number(folderId)]]); // create a map and initilize it

        for (const file of files) {
          let authHeaders = await getAuthHeaders();
          // Example:
          // webkitRelativePath = "StudyA/session1/image.nii.gz"
          // parentRelativePath = "StudyA/session1"
          const relativeFilePath = getRelativeFilePath(file);
          const parentRelativePath = getParentRelativePath(relativeFilePath);
          let targetFolderId = folderIdByRelativePath.get(parentRelativePath);

          if (!targetFolderId) {
            const { data: folderData } = await http.post("/tree/folders/ensure-path", {
              instance_name: endpointName,
              bucket,
              parent_id: Number(folderId),
              relative_path: parentRelativePath,
            }, { headers: authHeaders });
            targetFolderId = Number(folderData.id);
            folderIdByRelativePath.set(parentRelativePath, targetFolderId);
          }

          const { data } = await http.post("/tree/files/upload/init", {
            instance_name: endpointName,
            bucket,
            folder_id: targetFolderId,
            filename: file.name,
            content_type: file.type || "application/octet-stream",
          }, { headers: authHeaders });

          // Optional chaining: `data?.url` means "use data.url if data exists;
          // otherwise return undefined instead of throwing an error".
          let presignSource = data?.url;
          if (presignSource === null || presignSource === undefined) {
            presignSource = data?.presigned_urls;
          }
          if (presignSource === null || presignSource === undefined) {
            presignSource = data?.urls;
          }
          const presigns = normalizePresigns(presignSource);
          for (const entry of presigns) {
            await uploadViaPresigned(entry, file);
          }

          // Refresh auth headers in case they expired between init and complete
          authHeaders = await getAuthHeaders();
          await http.post("/tree/files/upload/complete", {
            instance_name: endpointName,
            file_id: data.file_id,
          }, { headers: authHeaders });
        }

        if (onMutate) onMutate(); // refresh dashboard with ?refresh=1 upstream  ------> TODO: need to further investigate refresh dashboard after upload or cerated new policy
        console.log(`[Upload] Successfully uploaded ${files.length} file(s) in endpoint "${endpointName}"`);
        alert("Folder upload complete.");
      } catch (e) {
        console.error(`[Upload] Upload failed for endpoint "${endpointName}":`, e);
        if (e?.response?.status === 409) {
          alert(`Upload failed! A file with the same name already exists in this folder.`);
        } else {
          alert(`Upload failed: ${formatError(e)}`);
        }
      } finally {
        setBusy(null);
        setBusyID(null);
        try { document.body.removeChild(input); } catch {}
      }
    };

    input.click();
  };

  // ---------------------- Delete (from DELETE selection) ----------------------
  const handleDelete = async () => {
    // Check if user has delete permission at all for this endpoint
    if (!hasDelete) return alert("No delete permission for this endpoint.");

    // Ensure files are selected in the UI
    if (!selectedByAccess.delete || selectedByAccess.delete.size === 0) {
      return alert("Select files or folders to delete.");
    }

    // Verify deleteTopSelected is not empty
    if (deleteTopSelected.length === 0) {
      return alert("No valid items selected for deletion.");
    }

    const numFilesToDelete = Array.from(selectedByAccess.delete).filter(
      id => String(id).startsWith("file-") && deleteIndex.has(String(id))
    ).length;

    if (!window.confirm(`Delete ${numFilesToDelete} file(s)? This cannot be undone.`)) return;

    setBusy("del");
    setBusyID(endpointUuid)
    try {
      await deleteAssets(http, endpointName, deleteTopSelected, deleteIndex);
      
      console.log(`[Delete] Successfully deleted selected item(s) from endpoint "${endpointName}"`);
      if (onMutate) onMutate(); // refresh dashboard
      onSelectedChange("delete", new Set());
      alert("Delete complete.");
    } catch (e) {
      console.error(`[Delete] Delete failed for endpoint "${endpointName}" while attempting to delete item(s):`, e);
      alert(`Delete failed: ${formatError(e)}`);
    } finally {
      setBusy(null);
      setBusyID(null);
    }
  };

  // ------------------------------- HTML  --------------------------------
  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <div
        onClick={handleToggle}
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: 12,
          cursor: "pointer",
          background: "#f9fafb",
        }}
      >
        <div>
          <strong>{endpointName}</strong>
        </div>
        <div style={{ fontSize: 14, color: "#6b7280" }}>{open ? "▼" : "▶"}</div>
      </div>

      {open && (
        <div style={{ padding: 12 }}>
          {loadingAssets ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#6b7280" }}>
              <CircularProgress size={16} />
              Loading assets…
            </div>
          ) : assetError ? (
            <div style={{ color: "#ef4444" }}>Error: {assetError}</div>
          ) : !hasRead && !hasWrite && !hasDelete ? (
            <div style={{ color: "#6b7280" }}>No tree data.</div>
          ) : (
            <div style={{ display: "grid", gap: 16 }}>
              {hasRead && (
                <div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>Read</div>
                    <button
                      onClick={handleDownload}
                      disabled={!!busy}
                      style={{
                        background: busy ? "#9ca3af" : "#3b82f6",
                        cursor: busy ? "not-allowed" : "pointer",
                        color: "#fff",
                        border: 0,
                        borderRadius: 8,
                        padding: "6px 10px",
                        fontSize: 13,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      {busy === "down" && busyID == endpointUuid && (
                        <CircularProgress size={14} sx={{ color: "#fff" }} />
                      )}
                      {busy === "down" && busyID == endpointUuid
                        ? "Downloading…"
                        : "Download"}
                    </button>
                  </div>
                  <Tree
                    nodes={readArray}
                    selected={selectedByAccess.read || new Set()}
                    onChange={onTreeChange("read")}
                  />
                </div>
              )}
              {hasWrite && (
                <div
                  style={{
                    borderTop: hasRead ? "2px dashed #c9c9c9" : "none",
                    paddingTop: hasRead ? 8 : 0,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>Write</div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        onClick={handleFileUpload}
                        disabled={!!busy}
                        style={{
                          background: busy ? "#9ca3af" : "#10b981",
                          cursor: busy ? "not-allowed" : "pointer",
                          color: "#fff",
                          border: 0,
                          borderRadius: 8,
                          padding: "6px 10px",
                          fontSize: 13,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        {busy === "up" && busyID == endpointUuid && (
                          <CircularProgress size={14} sx={{ color: "#fff" }} />
                        )}
                        {busy === "up" && busyID == endpointUuid
                          ? "Uploading…"
                          : "Upload File"}
                      </button>
                      <button
                        onClick={handleFolderUpload}
                        disabled={!!busy}
                        style={{
                          background: busy ? "#9ca3af" : "#059669",
                          cursor: busy ? "not-allowed" : "pointer",
                          color: "#fff",
                          border: 0,
                          borderRadius: 8,
                          padding: "6px 10px",
                          fontSize: 13,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        {busy === "up" && busyID == endpointUuid && (
                          <CircularProgress size={14} sx={{ color: "#fff" }} />
                        )}
                        {busy === "up" && busyID == endpointUuid
                          ? "Uploading…"
                          : "Upload Folder"}
                      </button>
                    </div>
                  </div>
                  <Tree
                    nodes={writeArray}
                    selected={selectedByAccess.write || new Set()}
                    onChange={onTreeChange("write")}
                    disableFileSelection={true}
                    disableCascade={true}
                  />
                </div>
              )}
              {hasDelete && (
                <div
                  style={{
                    borderTop: hasRead || hasWrite ? "2px dashed #c9c9c9" : "none",
                    paddingTop: hasRead ? 8 : 0,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>Delete</div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        onClick={handleDelete}
                        disabled={!!busy}
                        style={{
                          background: busy ? "#9ca3af" : "#ef4444",
                          cursor: busy ? "not-allowed" : "pointer",
                          color: "#fff",
                          border: 0,
                          borderRadius: 8,
                          padding: "6px 10px",
                          fontSize: 13,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        {busy === "del" && busyID == endpointUuid && (
                          <CircularProgress size={14} sx={{ color: "#fff" }} />
                        )}
                        {busy === "del" && busyID == endpointUuid
                          ? "Deleting…"
                          : "Delete"}
                      </button>
                    </div>
                  </div>
                  <Tree
                    nodes={deleteArray}
                    selected={selectedByAccess.delete || new Set()}
                    onChange={onTreeChange("delete")}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- helpers ---------------- */

function normalizeAccess(input) {
  if (!input) return { read: [], write: [], delete: [] };
  if (Array.isArray(input)) return { read: input, write: [], delete: [] };
  if (typeof input === "object") {
    return {
      read: Array.isArray(input.read) ? input.read : [],
      write: Array.isArray(input.write) ? input.write : [],
      delete: Array.isArray(input.delete) ? input.delete : [],
    };
  }
  return { read: [], write: [], delete: [] };
}

// selected leaf files for READ (ids that are not any node's parent)
function getSelectedLeaves(list, sel) {
  const parents = new Set(list.filter(n => n.parent !== "#").map(n => String(n.parent)));
  const ids = new Set(list.map(n => String(n.id)));
  const out = [];
  sel.forEach((id) => {
    const s = String(id);
    if (ids.has(s) && !parents.has(s)) out.push(s);
  });
  return out;
}

// Get selected top level nodes (files and folders) for WRITE and DELETE
// If a folder and its child are both selected, only the folder is returned.
// File selection is disabled for WRITE elsewhere
function getSelectTopLevel(list, sel, excludeRoot) {
  // Create of a map of Node Id -> Parent Id
  const parentMap = new Map();
  for (const node of list) {
    parentMap.set(String(node.id), String(node.parent));
  }

  const result = [];

  // Iterate through selections
  for (const id of sel) {
    // Skip if the ID isn't in our list
    if (!parentMap.has(id)) continue;

    // Do not include root nodes if excludeRoot is true
    if (excludeRoot && parentMap.get(id) === "#") continue;

    let currentParent = parentMap.get(id);
    let isTopLevel = true;

    // Climb the tree until we reach the top most selected node
    while (currentParent && currentParent !== "#") {
      // If this node's parent is in the selection it is not a top level node
      if (sel.has(currentParent)) {

        // We only mark as not top level if we aren't excluding roots 
        // OR if the parent isn't actually a root.
        if (!excludeRoot || parentMap.get(currentParent) !== "#") {
          isTopLevel = false;
          break;
        }
      }
      currentParent = parentMap.get(currentParent);
    }

    if (isTopLevel) {
      result.push(id);
    }
  }

  return result;
}

function isDirectoryPlaceholder(file) {
  return file.size === 0 && getRelativeFilePath(file).endsWith("/");
}

// Files selected via `webkitdirectory` preserve the path relative to the picked
// folder root. Normal file picks fall back to the plain file name here.
function getRelativeFilePath(file) {
  return String(file.webkitRelativePath || file.name || "").replace(/^\/+|\/+$/g, "");
}

// We only need the parent directory chain because the filename itself is still
// uploaded through the existing single-file init/complete endpoints.
function getParentRelativePath(relativeFilePath) {
  const normalized = String(relativeFilePath || "").replace(/^\/+|\/+$/g, "");
  const lastSlash = normalized.lastIndexOf("/");
  return lastSlash === -1 ? "" : normalized.slice(0, lastSlash);
}

// --- presigned upload helpers ---

function isSigV2(url) {
  try {
    const u = new URL(url);
    return u.searchParams.has("AWSAccessKeyId") && u.searchParams.has("Signature") && u.searchParams.has("Expires");
  } catch { return false; }
}

async function readFileAsArrayBuffer(file) {
  if (typeof file?.arrayBuffer === "function") return await file.arrayBuffer();
  return await new Promise((res, rej) => {
    const r = new FileReader();
    r.onerror = () => rej(r.error || new Error("FileReader error"));
    r.onload = () => res(r.result);
    r.readAsArrayBuffer(file);
  });
}

async function uploadViaPresigned(entry, file) {
  if (typeof entry === "string") {
    if (isSigV2(entry)) {
      const buf = await readFileAsArrayBuffer(file);
      const r = await fetch(entry, { method: "PUT", body: buf, credentials: "omit", cache: "no-store", mode: "cors" });
      if (!r.ok) throw new Error(`Storage PUT failed (${r.status}): ${await safeText(r)}`);
      return;
    }
    let r = await fetch(entry, { method: "PUT", body: file, credentials: "omit", cache: "no-store", mode: "cors" });
    if (r.ok) return;
    r = await fetch(entry, { method: "PUT", headers: { "Content-Type": "application/octet-stream" }, body: file, credentials: "omit", cache: "no-store", mode: "cors" });
    if (r.ok) return;
    if (file.type) {
      r = await fetch(entry, { method: "PUT", headers: { "Content-Type": file.type }, body: file, credentials: "omit", cache: "no-store", mode: "cors" });
      if (r.ok) return;
    }
    throw new Error(`Storage PUT failed (${r.status}): ${await safeText(r)}`);
  }

  if (entry && typeof entry === "object") {
    const url = entry.url || entry.href;
    if (!url) throw new Error("Presigned entry missing url.");
    if (entry.fields && typeof entry.fields === "object") {
      const fd = new FormData();
      for (const [k, v] of Object.entries(entry.fields)) fd.append(k, v);
      fd.append("file", file);
      const r = await fetch(url, { method: "POST", body: fd, credentials: "omit", cache: "no-store", mode: "cors" });
      if (!r.ok) throw new Error(`Storage POST failed (${r.status}): ${await safeText(r)}`);
      return;
    }
    const method = (entry.method || "PUT").toUpperCase();
    const headers = entry.headers || undefined;
    const r = await fetch(url, { method, headers, body: file, credentials: "omit", cache: "no-store", mode: "cors" });
    if (!r.ok) throw new Error(`Storage ${method} failed (${r.status}): ${await safeText(r)}`);
    return;
  }

  throw new Error("Unknown presigned URL format.");
}
//Return response text; if reading fails, return empty string
async function safeText(res) {
  try { return await res.text(); } catch { return ""; }
}

// cehck if presigned URLs are always from an array ([], [p], or p if already array)
function normalizePresigns(p) {
  return Array.isArray(p) ? p : (p ? [p] : []);
}
