import React from "react";
import { Link } from "react-router-dom";
import { useKeycloak } from "@react-keycloak/web";
import PersonIcon from '@mui/icons-material/Person';
import "./Navbar.css";

function Navbar() {
  const { keycloak } = useKeycloak();
  const isLoggedIn = keycloak.authenticated;

  return (
    <nav className="navbar">
      <div className="navbar-left">INN Data Portal</div>
      <div className="navbar-right">
        <Link to={isLoggedIn ? "/app" : "/"} className="navbar-link">Home</Link>
        <Link to="/about" className="navbar-link">About</Link>
        {isLoggedIn && (
          <div className="navbar-user">
            <span>{keycloak.tokenParsed?.preferred_username}</span>
            <PersonIcon />
          </div>
        )}
        <button
          className={`navbar-button ${isLoggedIn ? "logout" : ""}`}
          onClick={() =>
            isLoggedIn
              ? keycloak.logout()
              : keycloak.login({ redirectUri: window.location.origin + "/app" })
          }
        >
          {isLoggedIn ? "Logout" : "Login"}
        </button>
      </div>
    </nav>
  );
}

export default Navbar;
