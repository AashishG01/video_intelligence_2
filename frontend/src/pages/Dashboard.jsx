import React, { useState, useEffect, useContext } from 'react';
import {
    MonitorPlay,
    UserSearch,
    BarChart3,
    Terminal,
    ShieldCheck,
    Users
} from 'lucide-react';
import { WS_URL } from '../config';
import { AuthContext } from '../context/AuthContext';

// --- View & Component Imports ---
import Sidebar from '../components/Sidebar';
import LiveMonitorView from '../views/LiveMonitorView';
import InvestigatorView from '../views/InvestigatorView';
import SystemStatusView from '../views/SystemStatusView';
import EventFeedView from '../views/EventFeedView';
import AdminPanel from '../views/AdminPanel';
import WatchlistManager from '../views/WatchlistManager';
import ThreatAlertModal from '../components/ThreatAlertModal'; // The Red Alert Interceptor

const Dashboard = () => {
    const { user } = useContext(AuthContext); // Identity Check

    // --- UI State ---
    const [currentView, setCurrentView] = useState('monitor');
    const [liveAlerts, setLiveAlerts] = useState([]);
    const [systemLogs, setSystemLogs] = useState([
        { time: new Date().toLocaleTimeString(), msg: "C.O.R.E. SYSTEM BOOT: ACCESS GRANTED", type: "system" }
    ]);

    // --- Threat Alert Interceptor State ---
    const [criticalAlert, setCriticalAlert] = useState(null);
    // Note: Ensure you have an 'alert.mp3' file inside your 'public' folder
    const [alarmAudio] = useState(new Audio('/alert.mp3'));

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
                        setCriticalAlert(data); // Trigger the Red Alert Modal

                        alarmAudio.loop = true;
                        // Browsers block autoplay without user interaction, 
                        // so we catch the promise rejection silently if it happens.
                        alarmAudio.play().catch(err => console.log("Audio autoplay blocked by browser."));
                    }

                    // 3. Generate System Log Entry
                    const statusText = data.status === "MATCH" ? "WATCHLIST MATCH" : "NEW SUBJECT";
                    const logType = data.status === "MATCH" ? "error" : "success"; // 'error' is red in our UI
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
                // Attempt to reconnect every 5 seconds
                setTimeout(connectWebSocket, 5000);
            };
        };

        connectWebSocket();

        // Cleanup: Sever connection and stop audio when component unmounts
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
        setCriticalAlert(null); // Hide the modal
        alarmAudio.pause();     // Silence the alarm
        alarmAudio.currentTime = 0; // Reset audio track
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

    // Only Admins get the keys to the kingdom
    const navItems = user?.role === 'admin'
        ? [...baseNavItems, { id: 'admin', label: 'Admin Control', icon: ShieldCheck }]
        : baseNavItems;

    // ==========================================
    // VIEW ROUTER
    // ==========================================
    const renderView = () => {
        switch (currentView) {
            case 'monitor':
                return <LiveMonitorView liveAlerts={liveAlerts} />;
            case 'investigator':
                return <InvestigatorView />;
            case 'watchlist':
                return <WatchlistManager />;
            case 'status':
                return <SystemStatusView />;
            case 'feed':
                return <EventFeedView systemLogs={systemLogs} />;
            case 'admin':
                return user?.role === 'admin' ? <AdminPanel /> : <InvestigatorView />;
            default:
                return <LiveMonitorView liveAlerts={liveAlerts} />;
        }
    };

    return (
        <div className="flex h-screen w-full font-sans bg-slate-950 overflow-hidden">

            {/* RED ALERT INTERCEPTOR MODAL */}
            <ThreatAlertModal
                alertData={criticalAlert}
                onAcknowledge={handleAcknowledgeAlert}
            />

            {/* Modular Sidebar */}
            <Sidebar
                navItems={navItems}
                currentView={currentView}
                onNavigate={setCurrentView}
            />

            {/* Main Content Area */}
            <main className="flex-1 h-screen overflow-hidden bg-slate-50 relative rounded-l-[32px] shadow-2xl border-l border-white/10">
                <div className="absolute inset-0 overflow-y-auto custom-scrollbar">
                    {renderView()}
                </div>
            </main>
        </div>
    );
};

export default Dashboard;