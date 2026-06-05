import React, { useContext } from 'react';
import { LogOut, ShieldAlert } from 'lucide-react';
import { AuthContext } from '../context/AuthContext';

const Sidebar = ({ navItems, currentView, onNavigate }) => {
    const { logout, user } = useContext(AuthContext);

    return (
        <div className="w-20 bg-slate-950 border-r border-slate-800 flex flex-col h-full text-slate-300 shadow-2xl z-50 shrink-0 items-center py-6">
            
            {/* --- Logo Area --- */}
            <div className="mb-10 flex flex-col items-center">
                <div className="w-12 h-12 bg-blue-600/10 rounded-full flex items-center justify-center border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.15)] mb-2">
                    <ShieldAlert className="w-6 h-6 text-blue-500" />
                </div>
                <div className="text-[9px] font-black tracking-widest text-slate-500 uppercase">CORE</div>
            </div>

            {/* --- Navigation Links --- */}
            <nav className="flex-1 space-y-5 flex flex-col items-center w-full">
                {navItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = currentView === item.id;
                    return (
                        <button
                            key={item.id}
                            onClick={() => onNavigate(item.id)}
                            title={item.label} // Native tooltip on hover
                            className={`group relative w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 ${
                                isActive 
                                ? 'bg-blue-600 text-white shadow-[0_0_20px_rgba(59,130,246,0.4)]' 
                                : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-slate-700/50 hover:border-slate-600'
                            }`}
                        >
                            <Icon className={`w-5 h-5 transition-transform duration-300 ${isActive ? 'scale-110' : 'group-hover:scale-110'}`} />
                            
                            {/* Optional: Add a custom tooltip if desired, or rely on native 'title' attribute. Native is used here for simplicity. */}
                        </button>
                    );
                })}
            </nav>

            {/* --- User Profile & Logout Area --- */}
            <div className="mt-auto flex flex-col items-center space-y-4 pt-6 border-t border-slate-800/50 w-full">
                {/* Avatar */}
                <div 
                    title={`Logged in as ${user?.username} (${user?.role})`}
                    className="w-10 h-10 bg-slate-800 rounded-full flex items-center justify-center text-blue-500 font-bold border border-slate-700 cursor-help"
                >
                    {user?.username?.charAt(0).toUpperCase() || 'U'}
                </div>
                
                {/* Secure Logout Button */}
                <button 
                    onClick={logout}
                    title="Disconnect"
                    className="w-10 h-10 rounded-full flex items-center justify-center bg-red-500/10 hover:bg-red-500 text-red-500 hover:text-white transition-all duration-300 border border-red-500/20 hover:border-red-500 shadow-lg hover:shadow-red-500/20"
                >
                    <LogOut className="w-4 h-4 ml-1" /> {/* ml-1 to visually center the LogOut icon */}
                </button>
            </div>
        </div>
    );
};

export default Sidebar;