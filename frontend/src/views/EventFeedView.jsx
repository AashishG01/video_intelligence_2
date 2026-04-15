import React from 'react';

const EventFeedView = ({ systemLogs }) => {
    const getTypeStyle = (type) => {
        switch (type) {
            case 'success': return 'text-emerald-400';
            case 'warning': return 'text-amber-400';
            case 'system': return 'text-blue-400';
            default: return 'text-slate-400';
        }
    };

    const getTypeBadge = (type) => {
        switch (type) {
            case 'success': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
            case 'warning': return 'bg-amber-500/20  text-amber-400  border-amber-500/30';
            case 'system': return 'bg-blue-500/20   text-blue-400   border-blue-500/30';
            default: return 'bg-slate-500/20  text-slate-400  border-slate-500/30';
        }
    };

    return (
        <div className="max-w-4xl mx-auto py-8 px-6">
            <div className="mb-8 flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-slate-800 mb-2">Live Event Feed</h2>
                    <p className="text-slate-500">Real-time WebSocket stream from Redis & Milvus.</p>
                </div>
                <span className="flex items-center text-sm font-medium text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-full border border-emerald-200">
                    <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse mr-2"></span> Live
                </span>
            </div>

            <div className="bg-slate-900 rounded-2xl border border-slate-700 overflow-hidden shadow-xl">
                <div className="flex items-center px-4 py-3 bg-slate-800 border-b border-slate-700">
                    <div className="flex space-x-2 mr-4">
                        <div className="w-3 h-3 rounded-full bg-red-500"></div>
                        <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                        <div className="w-3 h-3 rounded-full bg-green-500"></div>
                    </div>
                    <span className="text-xs text-slate-400 font-mono">C.O.R.E. — AI Worker Stream</span>
                </div>

                <div className="p-4 h-[600px] overflow-y-auto space-y-1 font-mono text-sm flex flex-col-reverse">
                    {systemLogs.map((log, index) => (
                        <div key={index} className={`flex items-start py-1.5 px-2 rounded transition-all hover:bg-slate-800/40`}>
                            <span className="text-slate-600 mr-3 flex-shrink-0 text-xs mt-0.5">[{log.time}]</span>
                            <span className={`border text-xs px-1.5 py-0.5 rounded mr-3 flex-shrink-0 uppercase ${getTypeBadge(log.type)}`}>
                                {log.type}
                            </span>
                            <span className={getTypeStyle(log.type)}>{log.msg}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default EventFeedView;
