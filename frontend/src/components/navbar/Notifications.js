import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import Badge from "@mui/material/Badge";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemText from "@mui/material/ListItemText";
import NotificationsIcon from "@mui/icons-material/Notifications";
import { getAuthHeaders } from "../../utils/authUtils";

const http = axios.create({ baseURL: "/api" });
const REFRESH_MS = 30000;
// The newest notification the user has opened the list on, so the count shows only new ones.
// Kept in the browser: losing it only means old notifications count as new once.
const SEEN_KEY = "notificationsSeenUntil";

async function loadNotifications() {
  const { data } = await http.get("/notifications/", { headers: await getAuthHeaders() });
  return data;
}

function seenUntil() {
  try {
    return window.localStorage.getItem(SEEN_KEY) || "";
  } catch {
    return "";
  }
}

function Notifications({ load = loadNotifications }) {
  const [items, setItems] = useState([]);
  const [seen, setSeen] = useState(seenUntil);
  const [anchor, setAnchor] = useState(null);

  const refresh = useCallback(() => {
    // a failed refresh keeps the last list
    load().then(setItems).catch(() => {});
  }, [load]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const unseen = items.filter(n => n.created_at > seen).length;

  const open = event => {
    setAnchor(event.currentTarget);
    if (items.length) {
      const newest = items[0].created_at;
      setSeen(newest);
      try {
        window.localStorage.setItem(SEEN_KEY, newest);
      } catch {
        // storage blocked: the count just won't persist
      }
    }
  };

  return (
    <>
      <IconButton
        aria-label={unseen ? `notifications, ${unseen} new` : "notifications"}
        color="inherit"
        onClick={open}
        size="small"
      >
        <Badge badgeContent={unseen} color="error">
          <NotificationsIcon />
        </Badge>
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {items.length === 0 && <MenuItem disabled>No notifications</MenuItem>}
        {items.map(n => (
          <MenuItem key={n.id} onClick={() => setAnchor(null)}>
            <ListItemText primary={n.message} secondary={new Date(n.created_at).toLocaleString()} />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

export default Notifications;
