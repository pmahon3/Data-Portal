export function formatError(err) {
  const d = err?.response?.data;
  if (!d) return String(err?.message || err);
  if (Array.isArray(d.detail)) {
    return d.detail.map((x) => `${(x.loc || []).join(".")} → ${x.msg}`).join(" | ");
  }
  return d.detail || JSON.stringify(d);
}