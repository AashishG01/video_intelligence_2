import React, { useState } from 'react';
import { ShieldCheck, UserPlus, ShieldAlert, Loader2, KeyRound, User, Eye, EyeOff } from 'lucide-react';
import api from '../api'; // Your custom axios instance

const AdminPanel = () => {
    const [newUsername, setNewUsername] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [newRole, setNewRole] = useState('user'); // Default to standard user
    
    // NEW: State to handle password visibility
    const [showPassword, setShowPassword] = useState(false);
    
    const [status, setStatus] = useState({ type: '', message: '' });
    const [isLoading, setIsLoading] = useState(false);

    const handleCreateOperator = async (e) => {
        e.preventDefault();
        setStatus({ type: '', message: '' });
        setIsLoading(true);

        try {
            const payload = {
                username: newUsername,
                password: newPassword,
                role: newRole
            };

            const response = await api.post('/api/auth/register_operator', payload);
            
            setStatus({ type: 'success', message: response.data.message });
            setNewUsername('');
            setNewPassword('');
            setNewRole('user');
            setShowPassword(false); // Reset visibility on success
        } catch (err) {
            setStatus({ 
                type: 'error', 
                message: err.response?.data?.detail || "Failed to create operator." 
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="p-8 max-w-4xl mx-auto">
            <div className="mb-8 border-b border-slate-200 pb-5">
                <h2 className="text-2xl font-bold text-slate-800 flex items-center">
                    <ShieldCheck className="w-6 h-6 mr-3 text-blue-600" />
                    Command Center: Operator Management
                </h2>
                <p className="text-slate-500 mt-2">Provision access credentials for new surveillance personnel.</p>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="bg-slate-50 border-b border-slate-200 p-5">
                    <h3 className="font-semibold text-slate-800 flex items-center">
                        <UserPlus className="w-5 h-5 mr-2 text-slate-500" />
                        Provision New Operator
                    </h3>
                </div>

                <div className="p-6">
                    {status.message && (
                        <div className={`mb-6 p-4 rounded-lg flex items-center text-sm font-medium ${status.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
                            {status.type === 'error' && <ShieldAlert className="w-5 h-5 mr-2 flex-shrink-0" />}
                            {status.type === 'success' && <ShieldCheck className="w-5 h-5 mr-2 flex-shrink-0" />}
                            {status.message}
                        </div>
                    )}

                    <form onSubmit={handleCreateOperator} className="space-y-5 max-w-md">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">Assigned Username</label>
                            <div className="relative">
                                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input 
                                    type="text" 
                                    value={newUsername}
                                    onChange={(e) => setNewUsername(e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-lg pl-10 pr-4 py-2.5 outline-none focus:border-blue-500 transition-all"
                                    placeholder="e.g. Operator_Alpha"
                                    required
                                    minLength={4}
                                />
                            </div>
                        </div>

                        {/* UPDATED: Password field with visibility toggle */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">Initial Password</label>
                            <div className="relative">
                                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input 
                                    type={showPassword ? "text" : "password"} 
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-lg pl-10 pr-10 py-2.5 outline-none focus:border-blue-500 transition-all"
                                    placeholder="Minimum 8 characters"
                                    required
                                    minLength={8}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors"
                                >
                                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </button>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">Clearance Level</label>
                            <select 
                                value={newRole} 
                                onChange={(e) => setNewRole(e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-lg px-4 py-2.5 outline-none focus:border-blue-500 transition-all"
                            >
                                <option value="user">Standard User (View & Investigate)</option>
                                <option value="admin">Administrator (Full System Control)</option>
                            </select>
                        </div>

                        <button 
                            type="submit" 
                            disabled={isLoading}
                            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg mt-6 transition-colors flex items-center justify-center disabled:opacity-50 shadow-md shadow-blue-600/20"
                        >
                            {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Provision Account'}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
};

export default AdminPanel;