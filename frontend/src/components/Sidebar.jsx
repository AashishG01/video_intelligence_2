import React, { useContext } from 'react';
import { LogOut, ShieldAlert } from 'lucide-react';
import { AuthContext } from '../context/AuthContext'; // Import the brain

const Sidebar = ({ navItems, currentView, onNavigate }) => {
    // Pull the logout function and current user data from the global state
    const { logout, user } = useContext(AuthContext);

    return (
        <div className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col h-full text-slate-300">
            {/* --- Logo Area --- */}
            <div className="p-6 border-b border-slate-800 flex items-center">
                <ShieldAlert className="w-8 h-8 text-blue-500 mr-3" />
                <div>
                    <h1 className="text-xl font-bold text-white tracking-widest">C.O.R.E.</h1>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Surveillance Matrix</p>
                </div>
            </div>

            {/* --- Navigation Links --- */}
            <nav className="flex-1 px-4 py-6 space-y-2 overflow-y-auto">
                {navItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = currentView === item.id;
                    return (
                        <button
                            key={item.id}
                            onClick={() => onNavigate(item.id)}
                            className={`w-full flex items-center px-4 py-3 rounded-lg transition-all font-medium text-sm ${
                                isActive 
                                ? 'bg-blue-600 text-white shadow-md shadow-blue-900/20' 
                                : 'hover:bg-slate-900 hover:text-white'
                            }`}
                        >
                            <Icon className={`w-5 h-5 mr-3 ${isActive ? 'text-white' : 'text-slate-500'}`} />
                            {item.label}
                        </button>
                    );
                })}
            </nav>

            {/* --- User Profile & Logout Area --- */}
            <div className="p-4 border-t border-slate-800">
                <div className="bg-slate-900 rounded-xl p-4 flex flex-col items-center">
                    {/* Display who is currently logged in */}
                    <div className="w-10 h-10 bg-slate-800 rounded-full flex items-center justify-center text-blue-500 font-bold mb-2 border border-slate-700">
                        {user?.username?.charAt(0).toUpperCase()}
                    </div>
                    <p className="text-sm font-bold text-white">{user?.username}</p>
                    <p className="text-xs text-slate-500 uppercase tracking-wider mb-4">
                        Clearance: {user?.role}
                    </p>
                    
                    {/* Secure Logout Button */}
                    <button 
                        onClick={logout}
                        className="w-full flex items-center justify-center px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-500 rounded-lg text-sm font-semibold transition-colors border border-red-500/20"
                    >
                        <LogOut className="w-4 h-4 mr-2" />
                        Disconnect
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Sidebar;