import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import UserManagement from "./user_management";
import ProjectManagement from "./project_management";
import AssetManagement from "./asset_management";
import StorageManagement from "./storage_management";
import AdminSidebar from "./AdminSidebar";
import "./AdminPage.css";
import PolicyManagement from "./policy_management";


export default function AdminPage({ token }) {
  return (
    <div className="admin-layout">

      <AdminSidebar/>
      <div className="admin-content">

        {/* Router handling for the subcomponents of the admin page */}
        <Routes>
          {/* <Route path="/" element={<AdminHome />} /> */}
          <Route path="user-management" element={<UserManagement />} />
          <Route path="project-management" element={<ProjectManagement />} />
          <Route path="policy-management" element={<PolicyManagement />} />
          <Route
            path="asset-management"
            element={
              <AssetManagement
                emptyDescription={
                  "No storage endpoints have been set up yet, so there is " +
                  "nothing to browse here."
                }
                emptyAction={
                  "Create a storage instance under Connection Management, then " +
                  "grant access to it under Policy Management."
                }
              />
            }
          />
          <Route path="storage-management" element={<StorageManagement />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </div>
    </div>
  );
}
