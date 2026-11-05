import React from "react";

/* Shown when a user's account exists but nothing has been shared with it yet.
   Both "My Assets" and "My Policies" reach this state, and an empty result
   there is a normal pending-access state rather than a failure, so it is
   presented as guidance instead of an error.

   `action` overrides the closing line for callers whose audience cannot act
   on the default advice, such as an administrator viewing the same screen. */
export default function NoAccessNotice({ title, description, action }) {
  return (
    <div
      role="status"
      style={{
        background: "#f8fafc",
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        display: "grid",
        gap: 6,
        maxWidth: 720,
      }}
    >
      <strong style={{ color: "#111827" }}>{title}</strong>
      <p style={{ margin: 0, color: "#4b5563", lineHeight: 1.5 }}>{description}</p>
      <p style={{ margin: 0, color: "#4b5563", lineHeight: 1.5 }}>
        {action ||
          "Access is granted per storage instance by an administrator. Contact " +
            "your project administrator to request access to the data you need."}
      </p>
    </div>
  );
}
