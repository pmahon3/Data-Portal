// Asset Management Utilities
// This file contains asynchronous functions for download, upload and delete actions
import { getAuthHeaders } from '../../../utils/authUtils';

const BUNDLE_POLL_INTERVAL_MS = 2000;
const BUNDLE_MAX_POLL_ATTEMPTS = 1800; // 60 minutes for large folder bundles.

// Initiates an asynchronous server-side bundling process for specific assets,
// polls for completion, and opens the final object-storage URL once the ZIP is ready.
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

// Iterates through a selection of asset IDs and performs sequential delete requests.
// It distinguishes between files and folders based on ID prefixes and metadata.
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
