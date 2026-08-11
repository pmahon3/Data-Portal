import React, { useEffect, useRef, useState } from "react";
import Tree from "./tree/index.js";
import { CircularProgress, LinearProgress, Tab, Tabs } from "@mui/material";
import { formatError } from "../../../utils/errorUtils";
import { downloadAssetBundle, deleteAssets, uploadFiles, uploadFolderFiles } from "./actions.js";
import { formatTime, normalizeAccess, getSelectedDownloadIds, getSelectTopLevel } from "./EndpointCardUtils.js";
import useEndpointAssetTree, { TREE_MODES } from "./useEndpointAssetTree.js";

/* ---------------- local sub-components ---------------- */

function ActionButton({ variant, label, busyLabel, onClick, isBusy, disabled }) {
  return (
    <button
      type="button"
      className={`ec-btn ec-btn-${variant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {isBusy && <CircularProgress size={14} sx={{ color: "#fff" }} />}
      {isBusy ? busyLabel : label}
    </button>
  );
}

function ProgressBar({ type, label, barColor, trackColor, progressValue, children }) {
  return (
    <div className={`ec-progress ec-progress-${type}`}>
      <div className="ec-progress-stats">
        <span className={`ec-progress-label ec-progress-label-${type}`}>{label}</span>
        <span className={`ec-progress-numbers ec-progress-numbers-${type}`}>{children}</span>
      </div>
      <LinearProgress
        variant="determinate"
        value={progressValue}
        sx={{
          height: 8,
          borderRadius: 4,
          backgroundColor: trackColor,
          "& .MuiLinearProgress-bar": {
            borderRadius: 4,
            backgroundColor: barColor,
          },
        }}
      />
    </div>
  );
}

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
  const [progress, setProgress] = useState({ mode: null, done: 0, total: 0 });
  const [elapsedSec, setElapsedSec] = useState(0);
  const startTimeRef = useRef(null);

  const {
    treesByAccess,
    loadingNodeIdsByAccess,
    loadingAssets,
    assetError,
    fetchAssets,
    fetchBrowseRoots,
    fetchSearchAssets,
    fetchChildAssets,
  } = useEndpointAssetTree({
    endpointName,
    endpointUuid,
    activeAccess,
    selectedByAccess,
    onSelectedChange,
    http,
  });

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
        await uploadFiles(http, endpointName, bucket, folderId, files, (done, total) => {
          setProgress({ mode: "up", done, total });
        });

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
        const files = Array.from(input.files);
        const count = await uploadFolderFiles(http, endpointName, bucket, folderId, files, (done, total) => {
          setProgress({ mode: "up", done, total });
        });

        if (onMutate) onMutate(); // refresh dashboard with ?refresh=1 upstream  ------> TODO: need to further investigate refresh dashboard after upload or cerated new policy
        console.log(`[Upload] Successfully uploaded ${count} file(s) in endpoint "${endpointName}"`);
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

    const numFilesToDelete = Array.from(selectedByAccess.delete).filter(
      id => String(id).startsWith("file-") && deleteIndex.has(String(id))
    ).length;

    if (!window.confirm(`Delete ${numFilesToDelete} file(s)? This cannot be undone.`)) return;

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
    <ActionButton
      variant="download"
      label="Download"
      busyLabel={`Preparing download… ${formatTime(elapsedSec)}`}
      onClick={handleDownload}
      isBusy={busy === "down" && busyID === endpointUuid}
      disabled={!!busy}
    />
  );

  const uploadActions = (
    <>
      <ActionButton
        variant="upload"
        label="Upload File"
        busyLabel="Uploading..."
        onClick={handleFileUpload}
        isBusy={busy === "up" && busyID === endpointUuid}
        disabled={!!busy}
      />
      <ActionButton
        variant="upload-folder"
        label="Upload Folder"
        busyLabel="Uploading..."
        onClick={handleFolderUpload}
        isBusy={busy === "up" && busyID === endpointUuid}
        disabled={!!busy}
      />
    </>
  );

  const deleteAction = (
    <ActionButton
      variant="delete"
      label="Delete"
      busyLabel="Deleting..."
      onClick={handleDelete}
      isBusy={busy === "del" && busyID === endpointUuid}
      disabled={!!busy}
    />
  );

  // ------------------------------- HTML  --------------------------------
  return (
    <div className="ec-card">
      <div
        onClick={handleToggle}
        className="ec-header"
      >
        <div>
          <strong>{endpointName}</strong>
        </div>
        <div className="ec-header-toggle">{open ? "▼" : "▶"}</div>
      </div>

      {open && (
        <div className="ec-body">
          <div className="ec-body-grid">
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
              <div className="ec-loading">
                <CircularProgress size={16} />
                Loading assets...
              </div>
            )}
            {!loadingAssets && assetError && (
              <div className="ec-error">Error: {assetError}</div>
            )}
            {!loadingAssets && !assetError && activeTab === "read" && !hasRead && (
              <div className="ec-empty">No tree data.</div>
            )}
            {!loadingAssets && !assetError && hasRead && activeTab === "read" && (
              <div>
                <div className="ec-tree-header">
                  <div className="ec-tree-header-label">Download</div>
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
              <div className="ec-empty">No tree data.</div>
            )}
            {!loadingAssets && !assetError && hasWrite && activeTab === "write" && (
              <div>
                <div className="ec-tree-header">
                  <div className="ec-tree-header-label">Upload</div>
                </div>
                {showUploadProgress && (
                  <ProgressBar
                    type="upload"
                    label={`Uploading… ${formatTime(elapsedSec)}`}
                    barColor="#10b981"
                    trackColor="#d1fae5"
                    progressValue={progressValue}
                  >
                    {progress.done} / {progress.total} ({Math.round(progressValue)}%)
                  </ProgressBar>
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
              <div className="ec-empty">No tree data.</div>
            )}
            {!loadingAssets && !assetError && hasDelete && activeTab === "delete" && (
              <div>
                <div className="ec-tree-header-between">
                  <div className="ec-tree-header-label">Delete</div>
                </div>
                {showDeleteProgress && (
                  <ProgressBar
                    type="delete"
                    label={`Deleting… ${formatTime(elapsedSec)}`}
                    barColor="#ef4444"
                    trackColor="#fee2e2"
                    progressValue={progressValue}
                  >
                    {progress.done} / {progress.total}  —  {Math.round(progressValue)}%
                  </ProgressBar>
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
