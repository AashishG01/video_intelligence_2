import React, { useContext } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

const ProtectedRoute = ({ children, requireAdmin = false }) => {
    const { user } = useContext(AuthContext);
    const location = useLocation();

    if (!user) {
        // Not logged in? Kick them to the login screen.
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    if (requireAdmin && user.role !== 'admin') {
        // Logged in, but not an admin? Kick them to the main dashboard.
        return <Navigate to="/" replace />;
    }

    return children;
};

export default ProtectedRoute;