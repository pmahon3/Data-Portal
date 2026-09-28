export function formatError(err) {
  const d = err?.response?.data;

  if (!d) {
    // No response body: network failure, timeout, or a thrown client error.
    if (err?.code === "ECONNABORTED") return "The request timed out. Please try again.";
    if (err?.request) return "Could not reach the server. Check your connection and try again.";
    return String(err?.message || err);
  }

  // FastAPI validation errors arrive as a list of {loc, msg} objects.
  if (Array.isArray(d.detail)) {
    return d.detail
      .map((x) => {
        // Drop the leading "body"/"query" segment; it means nothing to a user.
        const field = (x.loc || []).filter((p) => p !== "body" && p !== "query").join(".");
        return field ? `${field}: ${x.msg}` : x.msg;
      })
      .join(" | ");
  }

  if (typeof d.detail === "string") return d.detail;
  // Guard against a non-string detail rendering as "[object Object]".
  if (d.detail) return JSON.stringify(d.detail);

  return typeof d === "string" ? d : JSON.stringify(d);
}