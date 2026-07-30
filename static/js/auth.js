/**
 * auth.js - OAI Authentication Helper
 */

document.addEventListener("DOMContentLoaded", () => {
    updateAuthUI();
});

function updateAuthUI() {
    const token = localStorage.getItem("auth_token");
    const guestSec = document.getElementById("sidebar-guest-section");
    const authSec = document.getElementById("sidebar-auth-section");
    const nicknameEl = document.getElementById("dashboardNickname");

    if (token) {
        if (guestSec) guestSec.style.display = "none";
        if (authSec) authSec.style.display = "block";
        const nick = localStorage.getItem("user_nickname") || "Learner";
        if (nicknameEl) nicknameEl.textContent = nick;
    } else {
        if (guestSec) guestSec.style.display = "block";
        if (authSec) authSec.style.display = "none";
    }
}

// Function to handle logout
function handleLogout() {
    localStorage.clear();
    location.href = "/";
}

// Attach logout to button if it exists
document.addEventListener("click", (e) => {
    if (e.target && e.target.id === "logout-btn") {
        handleLogout();
    }
});
