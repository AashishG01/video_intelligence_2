import React, { useState, useEffect } from 'react';
import { Loader2, Wifi, WifiOff, ScanFace, Users, Camera, Timer } from 'lucide-react';
import { BACKEND_URL } from '../config';
import StatCard from '../components/StatCard';

const SystemStatusView = () => {
    const [stats, setStats] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const response = await fetch(`${BACKEND_URL}/api/system/stats`);
                if (!response.ok) throw new Error("Failed to fetch stats");
                const data = await response.json();
                setStats(data);
                setError(null);
            } catch (err) {
                setError("Could not connect to backend. Is the server running?");
            } finally {
                setIsLoading(false);
            }
        };
        fetchStats();
        const interval = setInterval(fetchStats, 5000); // Auto refresh every 5s
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="max-w-4xl mx-auto py-8 px-6">
            <div className="mb-8">
                <h2 className="text-2xl font-bold text-slate-800 mb-2">System Status</h2>
                <p className="text-slate-500">Live statistics from the surveillance PostgreSQL backend.</p>
            </div>

            {isLoading && (
                <div className="text-center py-16">
                    <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">Connecting to surveillance database...</p>
                </div>
            )}

            {error && !isLoading && (
                <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center">
                    <WifiOff className="w-5 h-5 mr-3 flex-shrink-0" />
                    <span className="font-medium text-sm">{error}</span>
                </div>
            )}

            {stats && !isLoading && (
                <>
                    <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between ${stats.status === 'ONLINE' ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'
                        }`}>
                        <div className="flex items-center">
                            {stats.status === 'ONLINE' ? <Wifi className="w-5 h-5 text-emerald-600 mr-3" /> : <WifiOff className="w-5 h-5 text-red-600 mr-3" />}
                            <div>
                                <p className={`font-semibold text-sm ${stats.status === 'ONLINE' ? 'text-emerald-800' : 'text-red-800'}`}>
                                    Network: {stats.status || 'OFFLINE'}
                                </p>
                                <p className="text-xs text-slate-500 mt-0.5">AI Core: ANTELOPE-V2 Active</p>
                            </div>
                        </div>
                        <span className={`flex items-center text-xs font-medium px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-700`}>
                            <span className="w-2 h-2 rounded-full mr-2 bg-emerald-500 animate-pulse"></span>
                            Connected
                        </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                        <StatCard icon={ScanFace} label="Total Captures" value={stats.total_faces_captured || 0} color="bg-blue-500" />
                        <StatCard icon={Users} label="Unique Suspects" value={stats.unique_suspects || 0} color="bg-violet-500" />
                        <StatCard icon={Camera} label="Active Cameras" value={stats.active_cameras || 0} color="bg-amber-500" />
                        <StatCard icon={Timer} label="System Start" value={stats.system_start_time || 'N/A'} color="bg-emerald-500" />
                    </div>
                </>
            )}
        </div>
    );
};

export default SystemStatusView;
