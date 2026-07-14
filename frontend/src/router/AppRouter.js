/* Handling App Routes and then export them to App.js
   The AuthenticatedApp function check if users have proper role to access admin page or normal user page
*/
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useKeycloak } from "@react-keycloak/web";
import Navbar from "../components/navbar/Navbar";
import LandingPage from "../components/landing_page/LandingPage";
import AdminPage from "../components/admin_page/AdminPage";
import NormalUserPage from "../components/normal_user_page/NormalUserPage";
import About from "../components/about/About";


// Check the role of user
function AuthenticatedApp({ keycloak }) {
  const roles = keycloak.tokenParsed?.realm_access?.roles || [];
  const projects = keycloak.tokenParsed?.projects || [];
  const isProjectManager = projects.some(path => String(path).replace(/\/$/, "").endsWith("/managers"));
  const token = keycloak.token;

  console.log("This is the token: "+ token)

  return roles.includes("admin") || isProjectManager ? <AdminPage token={token} /> : <NormalUserPage />;
}

//handle application routes
const AppRouter = () => {
  const { keycloak, initialized } = useKeycloak();
  const isAuthenticated = Boolean(keycloak.authenticated);

  return (
    <>
      <Navbar />
      <Routes>
        <Route
          path="/"
          element={
            initialized && isAuthenticated ? (
              <Navigate to="/app" replace />
            ) : (
              <LandingPage />
            )
          }
        />
        <Route
          path="/app/*"
          element={
            !initialized ? null : isAuthenticated ? (
              <AuthenticatedApp keycloak={keycloak} />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route path="/about" element={<About />} />
      </Routes>
    </>
  );
};

export default AppRouter;
