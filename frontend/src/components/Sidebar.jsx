import React from 'react';
import { MonitorPlay } from 'lucide-react';

const Sidebar = ({ navItems, currentView, onNavigate }) => {
    return (
        <nav className="w-64 bg-white border-r border-slate-200 flex flex-col z-10 shadow-sm">
            <div className="p-6 border-b border-slate-100">
                <div className="flex items-center text-blue-600 font-bold text-2xl tracking-tight">
                    <MonitorPlay className="w-7 h-7 mr-2" />
                    C.O.R.E.
                </div>
                <div className="text-xs text-slate-400 mt-1 uppercase font-semibold tracking-wider">Surveillance Engine</div>
            </div>

            <div className="flex-1 py-4 px-3 space-y-1 bg-white">
                {navItems.map((item) => (
                    <button
                        key={item.id}
                        onClick={() => onNavigate(item.id)}
                        className={`w-full flex items-center px-3 py-3 rounded-lg font-medium transition-colors ${currentView === item.id
                                ? 'bg-blue-50 text-blue-700'
                                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                            }`}
                    >
                        <item.icon className="w-5 h-5 mr-3" />
                        {item.label}
                    </button>
                ))}
            </div>
        </nav>
    );
};

export default Sidebar;
