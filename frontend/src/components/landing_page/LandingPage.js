import React from "react";

function LandingPage() {
  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1>Welcome to the INN Data Portal Application</h1>
        <p>Please login to continue.</p>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    backgroundImage: "url(/inn.jpg)", // from public/
    backgroundSize: "cover",
    backgroundPosition: "center",
    backgroundRepeat: "no-repeat",
    display: "grid",
    placeItems: "center",
    padding: "2rem",
  },
  card: {
    background: "rgba(255,255,255,0.85)", 
    padding: "2rem",
    borderRadius: "12px",
    textAlign: "center",
  },
};

export default LandingPage;