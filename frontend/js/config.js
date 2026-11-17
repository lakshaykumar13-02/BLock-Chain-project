// =============================================================================
// ChainVault Runtime Staging & Production Configuration
// =============================================================================
// This file is loaded before api.js.
// In custom domains or separate Render static site deployments, you can set the
// backend API URL here if not using Render domain auto-detection or query params.
//
// Example for Render Staging:
// window.__CHAINVAULT_API_URL__ = "https://chainvault-api.onrender.com/api";
//
// Leave empty ("") for automatic local and staging discovery:
window.__CHAINVAULT_API_URL__ = window.__CHAINVAULT_API_URL__ || "";
