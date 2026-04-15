import React, { useState, useEffect } from 'react';
import { MonitorPlay, UserSearch, BarChart3, Terminal } from 'lucide-react';
import { WS_URL } from './config';
import Sidebar from './components/Sidebar';
import LiveMonitorView from './views/LiveMonitorView';
import InvestigatorView from './views/InvestigatorView';
import SystemStatusView from './views/SystemStatusView';
import EventFeedView from './views/EventFeedView';

// ==========================================
// MAIN APP COMPONENT (Global State & WebSocket)
// ==========================================
export default function App() {
  const [currentView, setCurrentView] = useState('investigator');
  const [liveAlerts, setLiveAlerts] = useState([]);
  const [systemLogs, setSystemLogs] = useState([
    { time: new Date().toLocaleTimeString(), msg: "INITIALIZING C.O.R.E. SYSTEMS...", type: "system" }
  ]);

  // Global WebSocket Connection
  useEffect(() => {
    let ws;
    let isConnected = false;

    const connectWebSocket = () => {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        isConnected = true;
        setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg: "Connected to AI Redis Stream via WebSocket.", type: "success" }, ...prev]);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // 1. Update Sidebar
          setLiveAlerts(prev => [data, ...prev].slice(0, 50));

          // 2. Update Event Feed Logs
          const statusText = data.status === "MATCH" ? "MATCH FOUND" : "NEW SUBJECT";
          const logType = data.status === "MATCH" ? "warning" : "success";
          const logMsg = `[${data.camera_id}] ${statusText}: ${data.person_id} (Conf: ${(data.confidence * 100).toFixed(1)}%)`;

          setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg: logMsg, type: logType }, ...prev].slice(0, 100));
        } catch (err) {
          console.error("Failed to parse WS message", err);
        }
      };

      ws.onclose = () => {
        if (isConnected) {
          setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg: "WebSocket disconnected. Reconnecting in 5s...", type: "system" }, ...prev]);
          isConnected = false;
        }
        setTimeout(connectWebSocket, 5000);
      };
    };

    connectWebSocket();
    return () => { if (ws) ws.close(); };
  }, []);

  const navItems = [
    { id: 'monitor', label: 'Live Monitor', icon: MonitorPlay },
    { id: 'investigator', label: 'Investigator', icon: UserSearch },
    { id: 'status', label: 'System Status', icon: BarChart3 },
    { id: 'feed', label: 'Event Feed', icon: Terminal },
  ];

  const renderView = () => {
    switch (currentView) {
      case 'monitor': return <LiveMonitorView liveAlerts={liveAlerts} />;
      case 'investigator': return <InvestigatorView />;
      case 'status': return <SystemStatusView />;
      case 'feed': return <EventFeedView systemLogs={systemLogs} />;
      default: return <InvestigatorView />;
    }
  };

  return (
    <div className="flex h-screen w-full font-sans">
      <Sidebar navItems={navItems} currentView={currentView} onNavigate={setCurrentView} />

      <main className="flex-1 h-screen overflow-hidden bg-slate-50 relative">
        <div className="absolute inset-0 overflow-y-auto">
          {renderView()}
        </div>
      </main>
    </div>
  );
}