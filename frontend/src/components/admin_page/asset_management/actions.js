// Asset Management Utilities
// This file contains asynchronous functions for download, upload and delete actions
import { getAuthHeaders } from '../../../utils/authUtils';

const BUNDLE_POLL_INTERVAL_MS = 2000;
const BUNDLE_MAX_POLL_ATTEMPTS = 1800; // 60 minutes for large folder bundles.

// --- presigned upload helpers ---

function isSigV2(url) {
  try {
    const u = new URL(url);
    return u.searchParams.has("AWSAccessKeyId") && u.searchParams.has("Signature") && u.searchParams.has("Expires");
  } catch { return false; }
}

/**
 * Reads a File or Blob into an ArrayBuffer. Prefers the native .arrayBuffer()
 * method and falls back to FileReader for older environments.
 */
async function readFileAsArrayBuffer(file) {
  if (typeof file?.arrayBuffer === "function") return await file.arrayBuffer();
  return await new Promise((res, rej) => {
    const r = new FileReader();
    r.onerror = () => rej(r.error || new Error("FileReader error"));
    r.onload = () => res(r.result);
    r.readAsArrayBuffer(file);
  });
}

/**
 * Uploads a file to object storage using a presigned URL or a presigned POST
 * form.
 */
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
/**
 * Safely reads the response body as text. Returns an empty string if reading
 * fails.
 */
async function safeText(res) {
  try { return await res.text(); } catch { return ""; }
}

/**
 * Normalizes a presigned URL value into an array. Accepts a single URL
 * string, an object, or an existing array, always returning an array.
 */
function normalizePresigns(p) {
  return Array.isArray(p) ? p : (p ? [p] : []);
}

function isDirectoryPlaceholder(file) {
  return file.size === 0 && getRelativeFilePath(file).endsWith("/");
}

/**
 * Extracts the path of a file relative to the folder root that was picked
 * by the user. For webkitdirectory selections this is the full relative
 * path; for normal file picks it falls back to the plain file name.
 */
function getRelativeFilePath(file) {
  return String(file.webkitRelativePath || file.name || "").replace(/^\/+|\/+$/g, "");
}

/**
 * Given a relative file path, returns the parent directory portion. The
 * filename itself is uploaded through the existing single-file endpoints,
 * so only the directory chain needs to be created on the server.
 */
function getParentRelativePath(relativeFilePath) {
  const normalized = String(relativeFilePath || "").replace(/^\/+|\/+$/g, "");
  const lastSlash = normalized.lastIndexOf("/");
  return lastSlash === -1 ? "" : normalized.slice(0, lastSlash);
}

// --- upload orchestration ---

/**
 * Uploads a single file through the three-step flow: init (get presigned
 * URL), upload to object storage, and complete (notify the backend).
 */
async function uploadSingleFile(http, endpointName, bucket, folderId, file) {
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

/**
 * Uploads one or more files directly into the selected destination folder.
 */
export async function uploadFiles(http, endpointName, bucket, folderId, files, onProgress) {
  let completed = 0;
  onProgress(completed, files.length);

  for (const file of files) {
    await uploadSingleFile(http, endpointName, bucket, folderId, file);
    completed += 1;
    onProgress(completed, files.length);
  }

  return files.length;
}

/**
 * Uploads a local directory by recreating its relative folder paths on the
 * server first, then uploading each file through the standard presigned
 * upload flow.
 */
export async function uploadFolderFiles(http, endpointName, bucket, folderId, files, onProgress) {
  // flat list of File object returned by webkitdirectory
  const realFiles = files.filter(file => !isDirectoryPlaceholder(file));
  let completed = 0;
  onProgress(completed, realFiles.length);

  // Cache folder ids per relative path so repeated siblings do not keep
  // calling the backend for the same nested directory chain.
  const folderIdByRelativePath = new Map([["", Number(folderId)]]); // create a map and initilize it

  for (const file of realFiles) {
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

    await uploadSingleFile(http, endpointName, bucket, targetFolderId, file);
    completed += 1;
    onProgress(completed, realFiles.length);
  }

  return realFiles.length;
}

/**
 * Initiates an asynchronous server-side bundling process for the selected
 * assets, polls for completion, and opens the final object-storage URL
 * once the ZIP archive is ready. Single-file requests are served immediately
 * without polling.
 */
export const downloadAssetBundle = async (http, endpointName, fileIds, folderIds = []) => {
  let headers = await getAuthHeaders();
  
  // Call the backend endpoint to initiate the zip bundle creation
  const response = await http.post("/tree/bundle/zip", {
    instance_name: endpointName,
    file_ids: fileIds,
    folder_ids: folderIds
  }, {
    headers
  });

  const { bundle_id, status: initStatus, single_file_url } = response.data;

  // If a single file was requested, open it in a new tab
  if (initStatus === "completed" && single_file_url) {
    const a = document.createElement("a");
    a.href = single_file_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
    return;
  }

  if (!bundle_id) {
    throw new Error("Failed to initialize bundle: Missing bundle ID.");
  }

  // Poll for completion
  let status = "processing";

  for (let i = 0; i < BUNDLE_MAX_POLL_ATTEMPTS; i++) {
    await new Promise(resolve => setTimeout(resolve, BUNDLE_POLL_INTERVAL_MS));
    
    headers = await getAuthHeaders();
    const statusResp = await http.get(`/tree/bundle/${bundle_id}/status`, { headers });
    status = statusResp.data.status;
    
    if (status === "complete") {
      break;
    } else if (status === "failed") {
      throw new Error("Bundle generation failed on the server.");
    }
  }

  if (status !== "complete") {
    throw new Error("Bundle generation timed out after 60 minutes. Please try again.");
  }

  // Fetch the completed bundle's object-storage URL
  headers = await getAuthHeaders();
  const downloadUrlResponse = await http.get(`/tree/bundle/${bundle_id}/download`, { headers });
  const resultUrl = downloadUrlResponse.data?.result_url;
  if (!resultUrl) {
    throw new Error("Bundle generation completed but no download URL was returned.");
  }

  // Use current-tab navigation because async polling can make new-tab clicks look like popups.
  window.location.assign(resultUrl);
};

/**
 * Iterates through a selection of asset IDs and performs sequential delete
 * requests.
 */
export async function deleteAssets(http, endpointName, deleteTopSelected, deleteIndex, onProgress) {
  const total = deleteTopSelected.length;
  let done = 0;

  for (const id of deleteTopSelected) {
    const headers = await getAuthHeaders();
    const node = deleteIndex.get(String(id));

    if (String(id).startsWith("file-")) {
      const fileId = String(id).replace("file-", "");
      await http.delete(`/tree/files/${fileId}`, { params: { instance_name: endpointName }, headers });
    } else {
      const folderId = String(id);
      const bucket = node?.li_attr?.bucket;
      if (!bucket) throw new Error("Missing bucket for folder delete.");
      await http.delete(`/tree/folders/${folderId}`, { params: { instance_name: endpointName, bucket }, headers });
    }

    done += 1;
    if (onProgress) onProgress(done, total);
  }
}
