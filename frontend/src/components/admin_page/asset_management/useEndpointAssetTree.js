import { useEffect, useRef, useState } from "react";
import { getAuthHeaders } from "../../../utils/authUtils.js";
import { mergeAssetNodes, cascadeLoadedChildrenSelection } from "./EndpointCardUtils.js";

// Each access tab operates in one of two modes:
// - BROWSE: lazy-loaded tree, fetching children on expand (default)
// - SEARCH: full tree fetched once, then filtered locally by the Tree component
export const TREE_MODES = Object.freeze({
  BROWSE: "browse",
  SEARCH: "search",
});

export default function useEndpointAssetTree({
  endpointName,
  endpointUuid,
  activeAccess,
  selectedByAccess,
  onSelectedChange,
  http,
}) {
  const [treesByAccess, setTreesByAccess] = useState({});
  // Tracks whether each access tab is currently in browse or search mode
  const [treeModesByAccess, setTreeModesByAccess] = useState({});
  // Tracks access tabs whose tree data already came from the full dashboard endpoint.
  const [fullTreeLoadedByAccess, setFullTreeLoadedByAccess] = useState({});
  const [loadedFolderIdsByAccess, setLoadedFolderIdsByAccess] = useState({});
  const [loadingNodeIdsByAccess, setLoadingNodeIdsByAccess] = useState({});
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [assetError, setAssetError] = useState(null);
  const selectedByAccessRef = useRef(selectedByAccess);

  useEffect(() => {
    selectedByAccessRef.current = selectedByAccess;
  }, [selectedByAccess]);

  // Returns the current mode for an access tab, defaulting to BROWSE
  const getTreeMode = (accessKey) => treeModesByAccess[accessKey] || TREE_MODES.BROWSE;

  /**
   * Fetch only the root-level children for the given access tab (browse mode).
   * If the full tree is already cached locally, simply switches mode to BROWSE.
   */
  const fetchBrowseRoots = async (accessKey = activeAccess, forceRefresh = false) => {
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
   */
  const fetchSearchAssets = async (accessKey = activeAccess, forceRefresh = false, showLoading = true) => {
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

  // Fetch assets for this endpoint in the requested mode.
  const fetchAssets = async (
    accessKey = activeAccess,
    forceRefresh = false,
    mode = getTreeMode(accessKey),
  ) => {
    if (mode === TREE_MODES.SEARCH) {
      return fetchSearchAssets(accessKey, forceRefresh);
    }

    return fetchBrowseRoots(accessKey, forceRefresh);
  };

  /**
   * Lazy-load children of a folder node (browse mode only).
   */
  const fetchChildAssets = async (accessKey, node) => {
    const nodeId = String(node?.id || "");
    if (!nodeId || String(nodeId).startsWith("file-")) return;
    if (getTreeMode(accessKey) !== TREE_MODES.BROWSE) return;
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

  return {
    treesByAccess,
    loadingNodeIdsByAccess,
    loadingAssets,
    assetError,
    fetchAssets,
    fetchBrowseRoots,
    fetchSearchAssets,
    fetchChildAssets,
  };
}
