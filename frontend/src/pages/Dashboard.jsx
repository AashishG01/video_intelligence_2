import React, { useState, useEffect, useContext } from 'react';
import {
    MonitorPlay,
    UserSearch,
    BarChart3,
    Terminal,
    ShieldCheck,
    Users,
    Power
} from 'lucide-react';
import { WS_URL } from '../config';
import api from '../api'; // Ensure your axios instance is imported
import { AuthContext } from '../context/AuthContext';

// --- View & Component Imports ---
import Sidebar from '../components/Sidebar';
import LiveMonitorView from '../views/LiveMonitorView';
import InvestigatorView from '../views/InvestigatorView';
import SystemStatusView from '../views/SystemStatusView';
import EventFeedView from '../views/EventFeedView';
import AdminPanel from '../views/AdminPanel';
import WatchlistManager from '../views/WatchlistManager';
import ThreatAlertModal from '../components/ThreatAlertModal';

const Dashboard = () => {
    const { user } = useContext(AuthContext);

    // --- UI & Routing State ---
    const [currentView, setCurrentView] = useState('monitor');
    const [liveAlerts, setLiveAlerts] = useState([]);
    const [systemLogs, setSystemLogs] = useState([
        { time: new Date().toLocaleTimeString(), msg: "C.O.R.E. SYSTEM BOOT: ACCESS GRANTED", type: "system" }
    ]);

    // --- Threat Alert Interceptor State ---
    const [criticalAlert, setCriticalAlert] = useState(null);
    const [alarmAudio] = useState(new Audio('/alert.mp3'));

    // --- System Kill Switch State ---
    const [isArmed, setIsArmed] = useState(true);
    const [isToggling, setIsToggling] = useState(false);

    // ==========================================
    // INITIAL BOOT: Check System Status
    // ==========================================
    useEffect(() => {
        const checkStatus = async () => {
            try {
                const res = await api.get('/api/system/status');
                setIsArmed(res.data.is_armed);
            } catch (err) {
                console.error("Failed to fetch initial system status.");
            }
        };
        checkStatus();
    }, []);

    // ==========================================
    // GLOBAL WEBSOCKET (Live Intelligence Stream)
    // ==========================================
    useEffect(() => {
        let ws;
        let isConnected = false;

        const connectWebSocket = () => {
            console.log("📡 Initializing Secure WebSocket Connection...");
            ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                isConnected = true;
                setSystemLogs(prev => [{
                    time: new Date().toLocaleTimeString(),
                    msg: "CONNECTED: Real-time AI stream active.",
                    type: "success"
                }, ...prev]);
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    // 1. Inject into standard Live Alerts (Sidebar/Monitor)
                    setLiveAlerts(prev => [data, ...prev].slice(0, 50));

                    // 2. THE RED ALERT INTERCEPTOR (Overrides the UI)
                    if (data.status === "MATCH") {
                        setCriticalAlert(data);
                        alarmAudio.loop = true;
                        alarmAudio.play().catch(err => console.log("Audio autoplay blocked by browser."));
                    }

                    // 3. Generate System Log Entry
                    const statusText = data.status === "MATCH" ? "WATCHLIST MATCH" : "NEW SUBJECT";
                    const logType = data.status === "MATCH" ? "error" : "success";
                    const logMsg = `[CAM-${data.camera_id}] ${statusText}: ${data.person_id || data.full_name} (${(data.confidence * 100).toFixed(1)}%)`;

                    setSystemLogs(prev => [{
                        time: new Date().toLocaleTimeString(),
                        msg: logMsg,
                        type: logType
                    }, ...prev].slice(0, 100));

                } catch (err) {
                    console.error("Intelligence Packet Error:", err);
                }
            };

            ws.onclose = () => {
                if (isConnected) {
                    setSystemLogs(prev => [{
                        time: new Date().toLocaleTimeString(),
                        msg: "CRITICAL: Connection lost. Re-establishing...",
                        type: "system"
                    }, ...prev]);
                    isConnected = false;
                }
                setTimeout(connectWebSocket, 5000);
            };
        };

        connectWebSocket();

        return () => {
            if (ws) ws.close();
            alarmAudio.pause();
            alarmAudio.currentTime = 0;
        };
    }, [alarmAudio]);

    // ==========================================
    // ALERT ACKNOWLEDGEMENT
    // ==========================================
    const handleAcknowledgeAlert = () => {
        setCriticalAlert(null);
        alarmAudio.pause();
        alarmAudio.currentTime = 0;
    };

    // ==========================================
    // KILL SWITCH HANDLER
    // ==========================================
    const handleToggleSystem = async () => {
        if (!user || user.role !== 'admin') {
            return alert("Access Denied: Only Admins can modify global security state.");
        }

        setIsToggling(true);
        const newState = !isArmed;
        try {
            await api.post('/api/system/toggle', { is_armed: newState });
            setIsArmed(newState);

            setSystemLogs(prev => [{
                time: new Date().toLocaleTimeString(),
                msg: `GLOBAL SYSTEM OVERRIDE: AI Surveillance ${newState ? 'ARMED' : 'DISARMED'} by ${user.username}`,
                type: newState ? "success" : "warning"
            }, ...prev].slice(0, 100));

        } catch (err) {
            alert("Failed to toggle system state.");
        } finally {
            setIsToggling(false);
        }
    };

    // ==========================================
    // DYNAMIC NAVIGATION (RBAC Aware)
    // ==========================================
    const baseNavItems = [
        { id: 'monitor', label: 'Live Monitor', icon: MonitorPlay },
        { id: 'investigator', label: 'Investigator', icon: UserSearch },
        { id: 'watchlist', label: 'Watchlist', icon: Users },
        { id: 'status', label: 'System Status', icon: BarChart3 },
        { id: 'feed', label: 'Event Feed', icon: Terminal },
    ];

    const navItems = user?.role === 'admin'
        ? [...baseNavItems, { id: 'admin', label: 'Admin Control', icon: ShieldCheck }]
        : baseNavItems;

    // ==========================================
    // VIEW ROUTER
    // ==========================================
    const renderView = () => {
        switch (currentView) {
            case 'monitor': return <LiveMonitorView liveAlerts={liveAlerts} />;
            case 'investigator': return <InvestigatorView />;
            case 'watchlist': return <WatchlistManager />;
            case 'status': return <SystemStatusView />;
            case 'feed': return <EventFeedView systemLogs={systemLogs} />;
            case 'admin': return user?.role === 'admin' ? <AdminPanel /> : <InvestigatorView />;
            default: return <LiveMonitorView liveAlerts={liveAlerts} />;
        }
    };

    return (
        <div className="flex h-screen w-full font-sans bg-slate-950 overflow-hidden">

            {/* --- RED ALERT INTERCEPTOR MODAL --- */}
            <ThreatAlertModal
                alertData={criticalAlert}
                onAcknowledge={handleAcknowledgeAlert}
            />

            {/* --- MODULAR SIDEBAR --- */}
            <Sidebar
                navItems={navItems}
                currentView={currentView}
                onNavigate={setCurrentView}
            />

            {/* --- MAIN CONTENT AREA --- */}
            <main className="flex-1 h-screen overflow-hidden bg-slate-50 relative rounded-l-[32px] shadow-2xl border-l border-white/10 flex flex-col">

                {/* GLOBAL TOP BAR (The Kill Switch) */}
                <div className="h-16 bg-white border-b border-slate-200 flex justify-end items-center px-8 z-10 shadow-sm shrink-0">
                    <button
                        onClick={handleToggleSystem}
                        disabled={isToggling}
                        className={`flex items-center px-4 py-2 rounded-xl text-sm font-black tracking-widest uppercase transition-all shadow-md border ${isArmed
                                ? 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100 shadow-red-500/10'
                                : 'bg-slate-800 text-slate-300 border-slate-900 hover:bg-slate-700'
                            }`}
                    >
                        <Power className={`w-4 h-4 mr-2 ${isArmed ? 'animate-pulse' : ''}`} />
                        {isArmed ? 'System Armed' : 'System Disarmed'}
                    </button>
                </div>

                {/* SCROLLABLE VIEW CONTAINER */}
                <div className="flex-1 overflow-y-auto custom-scrollbar relative">
                    {renderView()}
                </div>
            </main>
        </div>
    );
};

export default Dashboard;