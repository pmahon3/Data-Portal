// Asset Management Utilities
// This file contains asynchronous functions for download, upload and delete actions
import { getAuthHeaders } from '../../../utils/authUtils';

const BUNDLE_POLL_INTERVAL_MS = 2000;
const BUNDLE_MAX_POLL_ATTEMPTS = 1800; // 60 minutes for large folder bundles.
// Upload at most 6 folder files at the same time.
const FOLDER_UPLOAD_CONCURRENCY = 6;
const IGNORED_FOLDER_UPLOAD_NAMES = new Set([
  ".DS_Store",
  "Thumbs.db",
  "desktop.ini",
]);
const IGNORED_FOLDER_UPLOAD_DIRS = new Set([
  "__MACOSX",
]);

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
 * Uploads a file to object storage using a presigned PUT URL.
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

function shouldSkipFolderUploadFile(file) {
  const relativePath = getRelativeFilePath(file);
  const parts = relativePath.split("/").filter(Boolean);
  const filename = parts[parts.length - 1];

  if (isDirectoryPlaceholder(file)) return true;
  if (IGNORED_FOLDER_UPLOAD_NAMES.has(filename)) return true;
  return parts.some(part => IGNORED_FOLDER_UPLOAD_DIRS.has(part));
}

/**
 * Extracts the path of a file relative to the folder root that was picked
 * by the user. For webkitdirectory selections this is the full relative
 * path; for normal file picks it falls back to the plain file name.
 */
function getRelativeFilePath(file) {
  return String(file.webkitRelativePath || file.name || "").replace(/^\/+|\/+$/g, "");
}

async function runWithConcurrency(items, concurrency, worker) {
  let nextIndex = 0;
  const workerCount = Math.min(concurrency, items.length);

  // Example: with 20 files and concurrency 6, only 6 uploads run at once.
  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      await worker(items[currentIndex], currentIndex);
    }
  }));
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
 * Uploads a local directory by preparing metadata once, then using the
 * returned PUT URLs to upload files directly to object storage.
 */
export async function uploadFolderFiles(http, endpointName, bucket, folderId, files, onProgress) {
  // Keep real user files only. Example: skip ".DS_Store" from macOS.
  const realFiles = files.filter(file => !shouldSkipFolderUploadFile(file));
  let completed = 0;
  onProgress(completed, realFiles.length);

  const fileByRelativePath = new Map();
  const manifest = realFiles.map(file => {
    const relativePath = getRelativeFilePath(file);
    // Keep the browser File object so we can find it after backend returns the plan.
    fileByRelativePath.set(relativePath, file);
    return {
      // Example: "StudyA/a.txt".
      relative_path: relativePath,
      content_type: file.type || "application/octet-stream",
      size: file.size,
    };
  });

  let authHeaders = await getAuthHeaders();
  const { data } = await http.post("/tree/folders/upload/init", {
    instance_name: endpointName,
    bucket,
    parent_id: Number(folderId),
    // For now, do not overwrite existing files from the frontend.
    on_conflict: "error",
    files: manifest,
  }, { headers: authHeaders });

  await runWithConcurrency(data.files || [], FOLDER_UPLOAD_CONCURRENCY, async filePlan => {
    const file = fileByRelativePath.get(filePlan.relative_path);
    if (!file) throw new Error(`Missing selected file for ${filePlan.relative_path}`);
    if (!filePlan.url) throw new Error(`Missing upload URL for ${filePlan.relative_path}`);

    // Example: filePlan.url is already signed for "bc/sub/a.txt".
    await uploadViaPresigned(filePlan.url, file);

    completed += 1;
    onProgress(completed, realFiles.length);
  });

  // Tell the backend to verify all uploaded files in one request.
  // Example: file_ids = [691, 692].
  const completeHeaders = await getAuthHeaders();
  const completeResp = await http.post("/tree/folders/upload/complete", {
    instance_name: endpointName,
    file_ids: (data.files || []).map(filePlan => filePlan.file_id),
  }, { headers: completeHeaders });

  if (completeResp.data?.failed?.length) {
    throw new Error(`Folder upload complete failed for ${completeResp.data.failed.length} file(s).`);
  }

  // Return the backend-confirmed completed count; `?.` reads safely and `??` keeps the old fallback.
  return completeResp.data?.completed ?? realFiles.length;
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
