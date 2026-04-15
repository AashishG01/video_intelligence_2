import React from 'react';

const StatCard = ({ icon: Icon, label, value, color }) => (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow">
        <div className="flex items-center justify-between mb-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
                <Icon className="w-5 h-5 text-white" />
            </div>
        </div>
        <p className="text-2xl font-bold text-slate-800">{value}</p>
        <p className="text-sm text-slate-500 mt-1">{label}</p>
    </div>
);

export default StatCard;
