import React, { useState, useEffect, useRef } from 'react';
import { MonitorPlay, AlertCircle, RefreshCw, User } from 'lucide-react';
import { MEDIAMTX_URL, getImageUrl } from '../config';
import ThreatAlertModal from '../components/ThreatAlertModal';

// ================================
// WebRTC Player Component
// ================================
const WebRTCPlayer = ({ camId, label, onError }) => {
    const videoRef = useRef(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [retryCount, setRetryCount] = useState(0);

    useEffect(() => {
        let pc = null;
        let isActive = true;

        const startStream = async () => {
            try {
                pc = new RTCPeerConnection();
                pc.addTransceiver('video', { direction: 'recvonly' });

                pc.ontrack = (event) => {
                    if (isActive && videoRef.current) {
                        videoRef.current.srcObject = event.streams[0];
                        setIsPlaying(true);
                    }
                };

                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                const whepUrl = `${MEDIAMTX_URL}/${camId}/whep`;

                const response = await fetch(whepUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: pc.localDescription.sdp,
                });

                if (!response.ok) throw new Error(`WHEP ${response.status}`);

                const answerSdp = await response.text();

                if (isActive && pc.signalingState !== 'closed') {
                    await pc.setRemoteDescription({
                        type: 'answer',
                        sdp: answerSdp,
                    });
                }
            } catch (err) {
                if (retryCount < 3) {
                    setTimeout(() => setRetryCount(prev => prev + 1), 5000);
                } else {
                    onError(camId);
                }
            }
        };

        startStream();

        return () => {
            isActive = false;
            if (pc) pc.close();
        };
    }, [camId, retryCount]);

    return (
        <div className="relative w-full h-full bg-black">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className={`w-full h-full object-contain transition-opacity duration-300 ${isPlaying ? 'opacity-100' : 'opacity-0'}`}
            />
            {!isPlaying && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                    <RefreshCw className="w-8 h-8 animate-spin opacity-50 mb-2" />
                    <p className="text-xs opacity-50 font-medium">Connecting...</p>
                </div>
            )}
        </div>
    );
};

// ================================
// MAIN COMPONENT
// ================================
const LiveMonitorView = ({ liveAlerts }) => {

    const cameras = [
        { id: "cam1", label: "Lab cam 1" },
        { id: "cam2", label: "Lab cam 2" },
        { id: "cam3", label: "Lab cam 3" },
        { id: "cam4", label: "Dept gate Cam" },
    ];

    const [camStatus, setCamStatus] = useState({
        cam1: true, cam2: true, cam3: true, cam4: true
    });

    const [watchlistAlert, setWatchlistAlert] = useState(null);
    const [selectedCam, setSelectedCam] = useState(null);

    // ESC key close for fullscreen
    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === "Escape") setSelectedCam(null);
        };
        window.addEventListener("keydown", handleEsc);
        return () => window.removeEventListener("keydown", handleEsc);
    }, []);

    // Monitor incoming alerts from WebSocket
    useEffect(() => {
        if (liveAlerts.length > 0) {
            const latest = liveAlerts[0];
            // 🚨 FORCED TRIGGER: Listens for BOTH Watchlist hits and General DB hits to ensure the modal pops
            if (latest.status === "WATCHLIST_MATCH" || latest.status === "MATCH") {
                setWatchlistAlert(latest);
            }
        }
    }, [liveAlerts]);

    const handleStreamError = (camId) => {
        setCamStatus(prev => ({ ...prev, [camId]: false }));
    };

    return (
        <div className="flex h-full relative bg-slate-50 overflow-hidden">

            {/* ========================= */}
            {/* 🚨 THE FULLSCREEN RED ALERT MODAL 🚨 */}
            {/* ========================= */}
            {watchlistAlert && (
                <div className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-md flex items-center justify-center">
                    <ThreatAlertModal 
                        isOpen={true} 
                        alert={{
                            ...watchlistAlert,
                            // Fallbacks applied to prevent React crashes on normal MATCHes
                            full_name: watchlistAlert.full_name || watchlistAlert.person_id || "UNKNOWN SUBJECT",
                            risk_level: watchlistAlert.risk_level || "UNKNOWN",
                            reference_image: watchlistAlert.reference_image || null
                        }}
                        onDismiss={() => setWatchlistAlert(null)} 
                    />
                </div>
            )}

            {/* MAIN CONTENT AREA */}
            <div className="flex-1 p-6 overflow-auto">

                {/* HEADER */}
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center">
                            <MonitorPlay className="w-7 h-7 mr-3 text-blue-600" />
                            Command Center
                        </h2>
                        <p className="text-slate-500 font-medium mt-1">Real-time WebRTC streams and AI tracking.</p>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="text-blue-600 bg-blue-50 border border-blue-200 px-4 py-1.5 rounded-full text-sm font-bold flex items-center shadow-sm">
                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2"></span>
                            WebRTC Active
                        </span>
                    </div>
                </div>

                {/* CAMERA GRID */}
                <div className="grid grid-cols-2 gap-4">
                    {cameras.map((cam) => (
                        <div
                            key={cam.id}
                            onClick={() => setSelectedCam(cam)}
                            className="bg-slate-900 rounded-2xl overflow-hidden relative cursor-pointer hover:ring-4 ring-blue-500/30 transition-all shadow-lg border border-slate-800"
                        >
                            <div className="absolute top-3 left-3 z-10 text-white text-xs font-bold tracking-widest uppercase bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10">
                                {cam.label}
                            </div>

                            {camStatus[cam.id] ? (
                                <div className="w-full aspect-video">
                                    <WebRTCPlayer camId={cam.id} onError={handleStreamError} />
                                </div>
                            ) : (
                                <div className="w-full aspect-video flex flex-col items-center justify-center text-slate-500 bg-slate-950">
                                    <AlertCircle className="w-8 h-8 mb-2 opacity-50" />
                                    <span className="text-sm font-medium uppercase tracking-widest">Offline</span>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* SIDEBAR: Live Intel Feed */}
            <div className="w-[350px] bg-white border-l border-slate-200 flex flex-col shadow-2xl z-10 shrink-0">
                <div className="p-5 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                    <h3 className="font-black text-slate-800 uppercase tracking-widest text-sm flex items-center">
                        <AlertCircle className="w-4 h-4 mr-2 text-blue-600" />
                        Live Intel Feed
                    </h3>
                    <span className="bg-slate-200 text-slate-600 px-2 py-1 rounded text-xs font-bold">
                        {liveAlerts.length} Events
                    </span>
                </div>

                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-slate-50/50">
                    {liveAlerts.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-slate-400">
                            <MonitorPlay className="w-12 h-12 mb-3 opacity-20" />
                            <p className="text-xs font-bold uppercase tracking-widest">No Active Events</p>
                        </div>
                    ) : (
                        liveAlerts.map((alert, idx) => {
                            const isMatch = alert.status === 'WATCHLIST_MATCH' || alert.status === 'MATCH';
                            return (
                                <div key={idx} className={`flex items-start gap-3 mb-3 p-3 rounded-2xl border transition-all ${isMatch ? 'bg-red-50 border-red-200 shadow-sm' : 'bg-white border-slate-200 hover:border-blue-300'}`}>
                                    
                                    {/* Thumbnail with Error Fallback */}
                                    <div className="w-12 h-12 rounded-xl overflow-hidden bg-slate-100 shrink-0 border border-slate-200 relative">
                                        {alert.live_image ? (
                                            <img 
                                                src={getImageUrl(alert.live_image)} 
                                                onError={(e) => {
                                                    e.target.style.display = 'none';
                                                    e.target.nextSibling.style.display = 'flex';
                                                }}
                                                className="w-full h-full object-cover relative z-10" 
                                                alt="Sighting" 
                                            />
                                        ) : null}
                                        {/* Fallback icon if image fails or doesn't exist */}
                                        <div className="absolute inset-0 w-full h-full flex items-center justify-center bg-slate-100 z-0" style={{ display: alert.live_image ? 'none' : 'flex' }}>
                                            <User className="w-5 h-5 text-slate-400"/>
                                        </div>
                                    </div>
                                    
                                    <div className="flex-1 overflow-hidden">
                                        <div className="flex justify-between items-start">
                                            <p className={`text-sm font-black truncate ${isMatch ? 'text-red-700' : 'text-slate-900'}`}>
                                                {alert.full_name || alert.person_id || 'Unknown Subject'}
                                            </p>
                                        </div>
                                        <div className="flex items-center mt-1 text-[11px] font-medium text-slate-500">
                                            <span>{alert.camera_id}</span>
                                            <span className="mx-1.5">•</span>
                                            <span>{new Date(alert.timestamp * 1000).toLocaleTimeString()}</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* ========================= */}
            {/* 🔥 FULLSCREEN CAMERA VIEW */}
            {/* ========================= */}
            {selectedCam && (
                <div className="fixed inset-0 z-[100] bg-black/95 flex items-center justify-center backdrop-blur-sm">
                    
                    {/* CLOSE */}
                    <button
                        onClick={() => setSelectedCam(null)}
                        className="absolute top-6 right-6 text-white hover:text-red-500 bg-white/10 hover:bg-white/20 px-6 py-2.5 rounded-xl font-bold tracking-widest uppercase text-sm transition-all"
                    >
                        ✕ Close
                    </button>

                    {/* LABEL */}
                    <div className="absolute top-6 left-6 text-white bg-blue-600/80 backdrop-blur-md border border-blue-400/30 px-4 py-2 rounded-xl font-black tracking-widest uppercase text-sm">
                        {selectedCam.label}
                    </div>

                    {/* VIDEO */}
                    <div className="w-[90vw] h-[85vh] rounded-2xl overflow-hidden border border-white/10 shadow-2xl bg-black">
                        {camStatus[selectedCam.id] ? (
                            <WebRTCPlayer camId={selectedCam.id} onError={handleStreamError} />
                        ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center text-slate-500">
                                <AlertCircle className="w-16 h-16 mb-4 opacity-50" />
                                <span className="text-xl font-bold uppercase tracking-widest">Camera Offline</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default LiveMonitorView;