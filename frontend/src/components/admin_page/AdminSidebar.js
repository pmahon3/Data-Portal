import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import "./AdminSidebar.css";

export default function AdminSidebar() {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);

  const navItems = [

    { path: "/app/user-management", label: "User Management" },
    { path: "/app/project-management", label: "Project Management" },
    { path: "/app/policy-management", label: "Policy Management" },
    { path: "/app/asset-management", label: "Asset Management" },
    { path: "/app/storage-management", label: "Connection Management" }
  ];

  return (
    <>
      {/* Mobile Toggle Button */}
      <button className="sidebar-toggle" onClick={() => setIsOpen(!isOpen)}>
        ☰
      </button>

      {/* Sidebar */}
      <div className={`admin-sidebar ${isOpen ? "open" : ""}`}>
        <h2 className="sidebar-title">Admin Panel</h2>
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`sidebar-link ${location.pathname === item.path ? "active" : ""}`}
            onClick={() => setIsOpen(false)} // close menu on mobile after click
          >
            {item.label}
          </Link>
        ))}
      </div>
    </>
  );
}
