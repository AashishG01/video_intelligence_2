import React, { useState, useEffect, useContext, useRef } from 'react';
import {
    MonitorPlay,
    UserSearch,
    BarChart3,
    Terminal,
    ShieldCheck,
    Users,
    Power,
    Settings
} from 'lucide-react';
import { WS_URL } from '../config';
import api from '../api'; 
import { AuthContext } from '../context/AuthContext';

// --- View & Component Imports ---
import Sidebar from '../components/Sidebar';
import LiveMonitorView from '../views/LiveMonitorView';
import InvestigatorView from '../views/InvestigatorView';
import SystemStatusView from '../views/SystemStatusView';
import EventFeedView from '../views/EventFeedView';
import AdminPanel from '../views/AdminPanel';
import WatchlistManager from '../views/WatchlistManager';
import AlertSettingsView from '../views/AlertSettingsView';
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
    
    // ✅ UPGRADED: Using useRef for Audio prevents React from constantly re-rendering the WebSocket
    const alarmAudioRef = useRef(new Audio('/siren.mp3'));

    // --- System Kill Switch State ---
    const [isArmed, setIsArmed] = useState(true);
    const [isToggling, setIsToggling] = useState(false);

    // ==========================================
    // INITIAL BOOT: Check System Status & Audio Settings
    // ==========================================
    useEffect(() => {
        const bootSystem = async () => {
            // 1. Fetch Armed Status
            try {
                const resStatus = await api.get('/api/system/status');
                setIsArmed(resStatus.data.is_armed);
            } catch (err) {
                console.error("Failed to fetch initial system status.");
            }

            // 2. ✅ FETCH DYNAMIC AUDIO SETTINGS (Upgraded for Custom Audio)
            try {
                const resAudio = await api.get('/api/settings/alerts');
                if (resAudio.data) {
                    const soundType = resAudio.data.alert_sound_type;
                    
                    if (soundType === 'silent') {
                        alarmAudioRef.current = null; // No sound
                    } else if (soundType === 'custom') {
                        // 👈 FETCH CUSTOM AUDIO DIRECTLY FROM FASTAPI MOUNT
                        const customUrl = resAudio.data.custom_audio_url;
                        // Pointing to FastAPI backend port 8000
                        alarmAudioRef.current = new Audio(`http://localhost:8000${customUrl}`);
                    } else {
                        // Default built-in sounds (siren, subtle)
                        alarmAudioRef.current = new Audio(`/${soundType}.mp3`);
                    }
                }
            } catch (err) {
                console.error("Audio Config Error:", err);
            }
        };
        bootSystem();
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
                    if (data.status === "WATCHLIST_MATCH" || data.status === "MATCH") {
                        setCriticalAlert(data);
                        
                        // ✅ DYNAMIC AUDIO PLAYBACK
                        if (alarmAudioRef.current) {
                            alarmAudioRef.current.loop = true;
                            alarmAudioRef.current.play().catch(err => console.log("Audio autoplay blocked by browser."));
                        }
                    }

                    // 3. Generate System Log Entry
                    const statusText = data.status.includes("MATCH") ? "WATCHLIST MATCH" : "NEW SUBJECT";
                    const logType = data.status.includes("MATCH") ? "error" : "success";
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
            if (alarmAudioRef.current) {
                alarmAudioRef.current.pause();
                alarmAudioRef.current.currentTime = 0;
            }
        };
    }, []); 

    // ==========================================
    // ALERT ACKNOWLEDGEMENT
    // ==========================================
    const handleAcknowledgeAlert = () => {
        setCriticalAlert(null);
        if (alarmAudioRef.current) {
            alarmAudioRef.current.pause();
            alarmAudioRef.current.currentTime = 0;
        }
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
        { id: 'alert_settings', label: 'Alert Settings', icon: Settings }, 
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
            case 'alert_settings': return <AlertSettingsView />; 
            case 'admin': return user?.role === 'admin' ? <AdminPanel /> : <InvestigatorView />;
            default: return <LiveMonitorView liveAlerts={liveAlerts} />;
        }
    };

    return (
        <div className="flex h-screen w-full font-sans bg-slate-950 overflow-hidden">

            {/* --- RED ALERT INTERCEPTOR MODAL --- */}
            <ThreatAlertModal
                alert={criticalAlert} 
                onDismiss={handleAcknowledgeAlert} 
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