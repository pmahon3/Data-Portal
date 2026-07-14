import React, { useState } from "react";
import { Box, Tab, Tabs } from "@mui/material";
import AssetManagement from "../admin_page/asset_management";
import MyPolicies from "./MyPolicies";

function NormalUser() {
  const [activeTab, setActiveTab] = useState("assets");

  return (
    <Box sx={{ minWidth: 0 }}>
      <Tabs
        value={activeTab}
        onChange={(_, nextTab) => setActiveTab(nextTab)}
        sx={{ borderBottom: 1, borderColor: "divider", px: 2 }}
      >
        <Tab label="My Assets" value="assets" />
        <Tab label="My Policies" value="policies" />
      </Tabs>

      {activeTab === "assets" ? (
        <AssetManagement title="My Assets" />
      ) : (
        <MyPolicies />
      )}
    </Box>
  );
}

export default NormalUser;
