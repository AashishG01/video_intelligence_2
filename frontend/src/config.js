// ==========================================
// SHARED CONFIGURATION & UTILITIES
// ==========================================
export const BACKEND_URL = "http://localhost:8000";
export const WS_URL = "ws://localhost:8000/ws/live_alerts";
export const MEDIAMTX_URL = "http://localhost:8889";

// Helper to fix image paths coming from backend
export const getImageUrl = (path) => {
    if (!path) return 'https://via.placeholder.com/150/f1f5f9/94a3b8?text=NO+IMG';
    if (path.startsWith('http')) return path;
    // If path from WS is /captured_faces/..., convert to /images/... as mounted in FastAPI
    const cleanPath = path.replace('/captured_faces/', '/images/');
    return `${BACKEND_URL}${cleanPath}`;
};
