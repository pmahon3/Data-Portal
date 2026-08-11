import React, { useEffect, useRef, useState } from "react";
import Tree from "./tree/index.js";
import { CircularProgress, LinearProgress, Tab, Tabs } from "@mui/material";
import { formatError } from "../../../utils/errorUtils";
import { downloadAssetBundle, deleteAssets } from "./actions.js";
import { getAuthHeaders } from '../../../utils/authUtils';

// Each access tab operates in one of two modes:
// - BROWSE: lazy-loaded tree, fetching children on expand (default)
// - SEARCH: full tree fetched once, then filtered locally by the Tree component
const TREE_MODES = Object.freeze({
  BROWSE: "browse",
  SEARCH: "search",
});

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
  const [activeAccess, setActiveAccess] = useState("read");
  const [treesByAccess, setTreesByAccess] = useState({});
  // Tracks whether each access tab is currently in browse or search mode
  const [treeModesByAccess, setTreeModesByAccess] = useState({});
  // Tracks access tabs whose tree data already came from the full dashboard endpoint.
  // Once true, search and browse can reuse the local tree instead of refetching.
  const [fullTreeLoadedByAccess, setFullTreeLoadedByAccess] = useState({});
  const [loadedFolderIdsByAccess, setLoadedFolderIdsByAccess] = useState({});
  const [loadingNodeIdsByAccess, setLoadingNodeIdsByAccess] = useState({});
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [assetError, setAssetError] = useState(null);
  const [progress, setProgress] = useState({ mode: null, done: 0, total: 0 });
  const [elapsedSec, setElapsedSec] = useState(0);
  const startTimeRef = useRef(null);
  const selectedByAccessRef = useRef(selectedByAccess);

  useEffect(() => {
    selectedByAccessRef.current = selectedByAccess;
  }, [selectedByAccess]);

  // Tick elapsed timer while any operation is busy
  useEffect(() => {
    if (!busy) {
      setElapsedSec(0);
      startTimeRef.current = null;
      return;
    }
    startTimeRef.current = startTimeRef.current || Date.now();
    const id = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 200);
    return () => clearInterval(id);
  }, [busy]);

  // Returns the current mode for an access tab, defaulting to BROWSE
  const getTreeMode = (accessKey) => treeModesByAccess[accessKey] || TREE_MODES.BROWSE;

  // Fetch assets for this endpoint
  const fetchAssets = async (accessKey = activeAccess, forceRefresh = false, mode = getTreeMode(accessKey)) => {
    if (mode === TREE_MODES.SEARCH) {
      return fetchSearchAssets(accessKey, forceRefresh);
    }

    return fetchBrowseRoots(accessKey, forceRefresh);
  };

  /**
   * Fetch only the root-level children for the given access tab (browse mode).
   * If the full tree is already cached locally, simply switches mode to BROWSE
   * without a network call. Otherwise hits the /children endpoint.
   */
  const fetchBrowseRoots = async (accessKey = activeAccess, forceRefresh = false) => {
    // Clearing search should only switch modes when the full tree is already local.
    if (fullTreeLoadedByAccess[accessKey] && !forceRefresh) {
      setAssetError(null);
      setTreeModesByAccess((prev) => ({
        ...prev,
        [accessKey]: TREE_MODES.BROWSE,
      }));
      return;
    }

    try {
      setLoadingAssets(true);
      setAssetError(null);
      const authHeaders = await getAuthHeaders();
      const { data } = await http.get(`/tree/dashboard/${encodeURIComponent(endpointUuid)}/children`, {
        headers: authHeaders,
        params: { access: accessKey, _t: Date.now(), ...(forceRefresh ? { refresh: 1 } : {}) },
      });
      setTreesByAccess((prev) => ({
        ...prev,
        [accessKey]: data.assets || [],
      }));
      setLoadedFolderIdsByAccess((prev) => ({
        ...prev,
        [accessKey]: new Set(),
      }));
      setFullTreeLoadedByAccess((prev) => ({
        ...prev,
        [accessKey]: false,
      }));
      setTreeModesByAccess((prev) => ({
        ...prev,
        [accessKey]: TREE_MODES.BROWSE,
      }));
    } catch (e) {
      console.error(`[EndpointCard] Failed to fetch assets for ${endpointName}:`, e);
      setAssetError(e?.response?.data?.detail || e?.message || "Failed to load assets");
    } finally {
      setLoadingAssets(false);
    }
  };

  /**
   * Fetch the entire tree for the given access tab (search mode).
   * Once fetched, the Tree component filters the full dataset locally.
   * If already cached, simply switches mode to SEARCH without a network call.
   */
  const fetchSearchAssets = async (accessKey = activeAccess, forceRefresh = false, showLoading = true) => {
    // The Tree component applies the actual filter locally; this fetch is only
    // needed until the access tab has a complete tree to search against.
    if (fullTreeLoadedByAccess[accessKey] && !forceRefresh) {
      setAssetError(null);
      setTreeModesByAccess((prev) => ({
        ...prev,
        [accessKey]: TREE_MODES.SEARCH,
      }));
      return;
    }

    try {
      if (showLoading) {
        setLoadingAssets(true);
      }
      setAssetError(null);
      const authHeaders = await getAuthHeaders();
      const { data } = await http.get(`/tree/dashboard/${encodeURIComponent(endpointUuid)}`, {
        headers: authHeaders,
        params: { access: accessKey, _t: Date.now(), ...(forceRefresh ? { refresh: 1 } : {}) },
      });
      setTreesByAccess((prev) => ({
        ...prev,
        [accessKey]: data.assets || [],
      }));
      setFullTreeLoadedByAccess((prev) => ({
        ...prev,
        [accessKey]: true,
      }));
      setTreeModesByAccess((prev) => ({
        ...prev,
        [accessKey]: TREE_MODES.SEARCH,
      }));
    } catch (e) {
      console.error(`[EndpointCard] Failed to fetch search assets for ${endpointName}:`, e);
      setAssetError(e?.response?.data?.detail || e?.message || "Failed to load assets");
    } finally {
      if (showLoading) {
        setLoadingAssets(false);
      }
    }
  };

  /**
   * Lazy-load children of a folder node (browse mode only).
   * Skipped if: node is a file, not in browse mode, full tree already cached,
   * or children were already loaded for this folder.
   */
  const fetchChildAssets = async (accessKey, node) => {
    const nodeId = String(node?.id || "");
    if (!nodeId || String(nodeId).startsWith("file-")) return;
    if (getTreeMode(accessKey) !== TREE_MODES.BROWSE) return;
    // Full tree data already includes descendants, so lazy /children calls are redundant.
    if (fullTreeLoadedByAccess[accessKey]) return;
    if (loadedFolderIdsByAccess[accessKey]?.has(nodeId)) return;

    try {
      setAssetError(null);
      setLoadingNodeIdsByAccess((prev) => ({
        ...prev,
        [accessKey]: new Set([...(prev[accessKey] || []), nodeId]),
      }));
      const authHeaders = await getAuthHeaders();
      const { data } = await http.get(`/tree/dashboard/${encodeURIComponent(endpointUuid)}/children`, {
        headers: authHeaders,
        params: { access: accessKey, parent_id: Number(nodeId), _t: Date.now() },
      });

      const incomingAssets = data.assets || [];
      setTreesByAccess((prev) => ({
        ...prev,
        [accessKey]: mergeAssetNodes(prev[accessKey] || [], incomingAssets, nodeId),
      }));
      if (accessKey !== "write") {
        cascadeLoadedChildrenSelection(
          selectedByAccessRef.current[accessKey] || new Set(),
          incomingAssets,
          nodeId,
          (nextSet) => onSelectedChange(accessKey, nextSet),
        );
      }
      setLoadedFolderIdsByAccess((prev) => ({
        ...prev,
        [accessKey]: new Set([...(prev[accessKey] || []), nodeId]),
      }));
    } catch (e) {
      console.error(`[EndpointCard] Failed to fetch child assets for ${endpointName}:`, e);
      setAssetError(e?.response?.data?.detail || e?.message || "Failed to load assets");
    } finally {
      setLoadingNodeIdsByAccess((prev) => {
        const nextForAccess = new Set(prev[accessKey] || []);
        nextForAccess.delete(nodeId);
        return { ...prev, [accessKey]: nextForAccess };
      });
    }
  };

  // Toggle card open/closed - fetch assets on first open
  const handleToggle = () => {
    const willOpen = !open;
    setOpen(willOpen);
    // Fetch assets when opening if not already loaded
    if (willOpen && Object.keys(treesByAccess).length === 0 && !loadingAssets) {
      fetchAssets("read", false, TREE_MODES.BROWSE);
    }
  };

  // onMutate callback to refresh assets after upload/delete
  const onMutate = () => fetchAssets(activeAccess, true);

  // Normalize to explicit read/write arrays
  const access = normalizeAccess(treesByAccess);
  const readArray = access.read;
  const writeArray = access.write;
  const deleteArray = access.delete;

  // turning array to a hashmap with file id as  key for faster look up
  const writeIndex = new Map(writeArray.map(n => [String(n.id), n]));
  const deleteIndex = new Map(deleteArray.map(n => [String(n.id), n]));

  const hasRead = readArray.length > 0;
  const hasWrite = writeArray.length > 0;
  const hasDelete = deleteArray.length > 0;
  const availableAccessTabs = [
    { value: "read", label: "Download", color: "#2563eb" },
    { value: "write", label: "Upload", color: "#059669" },
    { value: "delete", label: "Delete", color: "#dc2626" },
  ];
  const activeTab = availableAccessTabs.some(tab => tab.value === activeAccess)
    ? activeAccess
    : "read";
  const activeTabColor = availableAccessTabs.find(tab => tab.value === activeTab)?.color || "#2563eb";
  const showUploadProgress = busy === "up" && busyID === endpointUuid && progress.mode === "up" && progress.total > 0;
  const showDeleteProgress = busy === "del" && busyID === endpointUuid && progress.mode === "del" && progress.total > 0;
  const progressValue = progress.total > 0 ? (progress.done / progress.total) * 100 : 0;

  // Compute selections we need
  const writeTopFolders = getSelectTopLevel(writeArray, selectedByAccess.write || new Set(), false);
  const deleteTopSelected = getSelectTopLevel(deleteArray, selectedByAccess.delete || new Set(), true);

  // This one allows multiple items to be selected at the same time. We may need to get back to this
  const onTreeChange = (accessKey) => (nextSet) =>
    onSelectedChange(accessKey, new Set(nextSet));

  const clearAccessSelection = (accessKey) => {
    onSelectedChange(accessKey, new Set());
  };

  const clearAllSelections = () => {
    availableAccessTabs.forEach((tab) => clearAccessSelection(tab.value));
  };

  // Switch to search mode: fetch the full tree so the Tree component can filter locally.
  // Clears the current selection first to avoid stale selections across mode switches.
  const searchAssets = (accessKey) => {
    clearAccessSelection(accessKey);
    return fetchSearchAssets(accessKey, false, false);
  };

  // Switch back to browse mode: reload lazy children and clear any active search filter.
  const clearSearch = (accessKey) => {
    clearAccessSelection(accessKey);
    return fetchBrowseRoots(accessKey, false);
  };

  // --------------------- Download (from READ selection) ---------------------

  const handleDownload = async () => {
    if (!hasRead) return alert("No download permission.");
    const readSelection = selectedByAccess.read || new Set();
    if (readSelection.size === 0) return alert("Select files or folders to download.");

    setBusy("down");
    setBusyID(endpointUuid);
    try {
      const { fileIds, folderIds } = getSelectedDownloadIds(readSelection);

      if (fileIds.length === 0 && folderIds.length === 0) {
        alert("No valid files selected for download.");
        setBusy(null);
        setBusyID(null);
        return;
      }

      await downloadAssetBundle(http, endpointName, fileIds, folderIds);
      console.log(
        `[Download] Triggered downloads for ${fileIds.length} file(s) and ${folderIds.length} folder(s) from "${endpointName}"`
      );
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
      alert("No upload permission for this endpoint.");
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
    if (selectedByAccess.write.size > 1) {
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
        let completed = 0;
        setProgress({ mode: "up", done: completed, total: files.length });

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

          completed += 1;
          setProgress({ mode: "up", done: completed, total: files.length });
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
        setProgress({ mode: null, done: 0, total: 0 });
        try { document.body.removeChild(input); } catch { }
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
        let completed = 0;
        setProgress({ mode: "up", done: completed, total: files.length });

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

          completed += 1;
          setProgress({ mode: "up", done: completed, total: files.length });
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
        setProgress({ mode: null, done: 0, total: 0 });
        try { document.body.removeChild(input); } catch { }
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

    // TODO: Fetch number of files from backend to display accurately
    const numFilesToDelete = deleteTopSelected.filter(
      id => String(id).startsWith("file-")
    ).length;
    const numFoldersToDelete = deleteTopSelected.length - numFilesToDelete;

    if (!window.confirm(
      `Delete ${numFoldersToDelete} folder(s) and ${numFilesToDelete} file(s)? This cannot be undone.`
    )) return;

    setBusy("del");
    setBusyID(endpointUuid)
    setProgress({ mode: "del", done: 0, total: deleteTopSelected.length });
    try {
      await deleteAssets(http, endpointName, deleteTopSelected, deleteIndex, (done, total) => {
        setProgress({ mode: "del", done, total });
      });

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
      setProgress({ mode: null, done: 0, total: 0 });
    }
  };

  const downloadAction = (
    <button
      type="button"
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
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        whiteSpace: "nowrap",
      }}
    >
      {busy === "down" && busyID === endpointUuid && (
        <CircularProgress size={14} sx={{ color: "#fff" }} />
      )}
      {busy === "down" && busyID === endpointUuid
        ? `Preparing download… ${formatTime(elapsedSec)}`
        : "Download"}
    </button>
  );

  const uploadActions = (
    <>
      <button
        type="button"
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
          whiteSpace: "nowrap",
        }}
      >
        {busy === "up" && busyID === endpointUuid && (
          <CircularProgress size={14} sx={{ color: "#fff" }} />
        )}
        {busy === "up" && busyID === endpointUuid
          ? "Uploading..."
          : "Upload File"}
      </button>
      <button
        type="button"
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
          whiteSpace: "nowrap",
        }}
      >
        {busy === "up" && busyID === endpointUuid && (
          <CircularProgress size={14} sx={{ color: "#fff" }} />
        )}
        {busy === "up" && busyID === endpointUuid
          ? "Uploading..."
          : "Upload Folder"}
      </button>
    </>
  );

  const deleteAction = (
    <button
      type="button"
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
        whiteSpace: "nowrap",
      }}
    >
      {busy === "del" && busyID === endpointUuid && (
        <CircularProgress size={14} sx={{ color: "#fff" }} />
      )}
      {busy === "del" && busyID === endpointUuid
        ? "Deleting..."
        : "Delete"}
    </button>
  );

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
          <div style={{ display: "grid", gap: 16 }}>
            <Tabs
              value={activeTab}
              onChange={(_, nextAccess) => {
                if (nextAccess !== activeAccess) {
                  clearAllSelections();
                }
                setActiveAccess(nextAccess);
                // Switching tabs resets to browse mode so the user always sees
                // the lazy-loaded tree first (reuses full tree if already cached).
                fetchAssets(nextAccess, false, TREE_MODES.BROWSE);
              }}
              aria-label="Asset access tabs"
              sx={{
                borderBottom: "1px solid #e5e7eb",
                minHeight: 40,
                "& .MuiTabs-indicator": {
                  backgroundColor: activeTabColor,
                  height: 3,
                },
              }}
            >
              {availableAccessTabs.map(tab => (
                <Tab
                  key={tab.value}
                  value={tab.value}
                  label={tab.label}
                  sx={{
                    color: "#6b7280",
                    fontWeight: 600,
                    minHeight: 40,
                    textTransform: "none",
                    "&.Mui-selected": {
                      color: tab.color,
                    },
                  }}
                />
              ))}
            </Tabs>
            {loadingAssets && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#6b7280" }}>
                <CircularProgress size={16} />
                Loading assets...
              </div>
            )}
            {!loadingAssets && assetError && (
              <div style={{ color: "#ef4444" }}>Error: {assetError}</div>
            )}
            {!loadingAssets && !assetError && activeTab === "read" && !hasRead && (
              <div style={{ color: "#6b7280" }}>No tree data.</div>
            )}
            {!loadingAssets && !assetError && hasRead && activeTab === "read" && (
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    marginBottom: 6,
                  }}
                >
                  <div style={{ fontWeight: 600 }}>Download</div>
                </div>
                <Tree
                  nodes={readArray}
                  selected={selectedByAccess.read || new Set()}
                  onChange={onTreeChange("read")}
                  enableSearch={true}
                  onSearch={() => searchAssets("read")}
                  onClearSearch={() => clearSearch("read")}
                  onLoadChildren={(node) => fetchChildAssets("read", node)}
                  loadingNodeIds={loadingNodeIdsByAccess.read || new Set()}
                  actions={downloadAction}
                />
              </div>
            )}
            {!loadingAssets && !assetError && activeTab === "write" && !hasWrite && (
              <div style={{ color: "#6b7280" }}>No tree data.</div>
            )}
            {!loadingAssets && !assetError && hasWrite && activeTab === "write" && (
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    marginBottom: 6,
                  }}
                >
                  <div style={{ fontWeight: 600 }}>Upload</div>
                </div>
                {showUploadProgress && (
                  <div
                    style={{
                      marginBottom: 12,
                      padding: "10px 14px",
                      background: "#f0fdf4",
                      border: "1px solid #bbf7d0",
                      borderRadius: 10,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        marginBottom: 6,
                      }}
                    >
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#065f46" }}>
                        Uploading… {formatTime(elapsedSec)}
                      </span>
                      <span style={{ fontSize: 12, color: "#047857", fontVariantNumeric: "tabular-nums" }}>
                        {progress.done} / {progress.total} ({Math.round(progressValue)}%)
                      </span>
                    </div>
                    <LinearProgress
                      variant="determinate"
                      value={progressValue}
                      sx={{
                        height: 8,
                        borderRadius: 4,
                        backgroundColor: "#d1fae5",
                        "& .MuiLinearProgress-bar": {
                          borderRadius: 4,
                          backgroundColor: "#10b981",
                        },
                      }}
                    />
                  </div>
                )}
                <Tree
                  nodes={writeArray}
                  selected={selectedByAccess.write || new Set()}
                  onChange={onTreeChange("write")}
                  disableFileSelection={true}
                  disableCascade={true}
                  enableSearch={true}
                  onSearch={() => searchAssets("write")}
                  onClearSearch={() => clearSearch("write")}
                  onLoadChildren={(node) => fetchChildAssets("write", node)}
                  loadingNodeIds={loadingNodeIdsByAccess.write || new Set()}
                  actions={uploadActions}
                />
              </div>
            )}
            {!loadingAssets && !assetError && activeTab === "delete" && !hasDelete && (
              <div style={{ color: "#6b7280" }}>No tree data.</div>
            )}
            {!loadingAssets && !assetError && hasDelete && activeTab === "delete" && (
              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 6,
                  }}
                >
                  <div style={{ fontWeight: 600 }}>Delete</div>
                </div>
                {showDeleteProgress && (
                  <div
                    style={{
                      marginBottom: 12,
                      padding: "10px 14px",
                      background: "#fef2f2",
                      border: "1px solid #fecaca",
                      borderRadius: 10,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        marginBottom: 6,
                      }}
                    >
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#991b1b" }}>
                        Deleting… {formatTime(elapsedSec)}
                      </span>
                      <span style={{ fontSize: 12, color: "#b91c1c", fontVariantNumeric: "tabular-nums" }}>
                        {progress.done} / {progress.total}  —  {Math.round(progressValue)}%
                      </span>
                    </div>
                    <LinearProgress
                      variant="determinate"
                      value={progressValue}
                      sx={{
                        height: 8,
                        borderRadius: 4,
                        backgroundColor: "#fee2e2",
                        "& .MuiLinearProgress-bar": {
                          borderRadius: 4,
                          backgroundColor: "#ef4444",
                        },
                      }}
                    />
                  </div>
                )}
                <Tree
                  nodes={deleteArray}
                  selected={selectedByAccess.delete || new Set()}
                  onChange={onTreeChange("delete")}
                  enableSearch={true}
                  onSearch={() => searchAssets("delete")}
                  onClearSearch={() => clearSearch("delete")}
                  onLoadChildren={(node) => fetchChildAssets("delete", node)}
                  loadingNodeIds={loadingNodeIdsByAccess.delete || new Set()}
                  actions={deleteAction}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- helpers ---------------- */

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

/**
 * Normalize tree data into { read, write, delete } arrays.
 * Accepts an array (treated as read-only) or an object with optional keys.
 *
 * @param {Array|Object} input - Raw tree data from state
 * @returns {{ read: Array, write: Array, delete: Array }}
 */
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

/**
 * Merge newly fetched child nodes into the existing tree, deduplicating by id.
 * When a parentId is given, updates that parent's has_children flag.
 */
function mergeAssetNodes(existing, incoming, parentId = null) {
  const byId = new Map();
  for (const node of existing) {
    if (parentId !== null && String(node.id) === String(parentId)) {
      byId.set(String(node.id), {
        ...node,
        li_attr: {
          ...(node.li_attr || {}),
          has_children: incoming.length > 0,
        },
      });
    } else {
      byId.set(String(node.id), node);
    }
  }
  for (const node of incoming) {
    byId.set(String(node.id), node);
  }
  return Array.from(byId.values());
}

/**
 * When a parent folder is selected and its children are lazy-loaded, auto-select
 * those newly loaded children so the selection stays consistent.
 */
function cascadeLoadedChildrenSelection(currentSelection, loadedNodes, parentId, onChange) {
  if (!currentSelection.has(String(parentId)) || loadedNodes.length === 0) return;

  const next = new Set(currentSelection);
  let changed = false;

  for (const node of loadedNodes) {
    const id = String(node.id);
    if (!next.has(id)) {
      next.add(id);
      changed = true;
    }
  }

  if (changed) onChange(next);
}

/**
 * Split tree selection IDs into DB file IDs and folder IDs.
 * File nodes use "file-{id}" while folder nodes are plain numeric IDs.
 */
function getSelectedDownloadIds(sel) {
  const fileIds = new Set();
  const folderIds = new Set();

  sel.forEach((id) => {
    const selectedId = String(id);
    const numericId = Number.parseInt(selectedId.replace("file-", ""), 10);
    if (Number.isNaN(numericId)) return;

    if (selectedId.startsWith("file-")) {
      fileIds.add(numericId);
    } else {
      folderIds.add(numericId);
    }
  });

  return {
    fileIds: Array.from(fileIds),
    folderIds: Array.from(folderIds),
  };
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
