import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// Security Context & Guards
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Entrance */}
          <Route path="/login" element={<Login />} />

          {/* Protected Vault (The entire Dashboard is locked inside here) */}
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } 
          />

          {/* Catch-all: Send unknown URLs back to the vault */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}