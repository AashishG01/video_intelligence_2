import React, { useState, useEffect, useRef } from 'react';
import { MonitorPlay, AlertCircle, RefreshCw, User, Video, X } from 'lucide-react';
import { BACKEND_URL, MEDIAMTX_URL, getImageUrl } from '../config';

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

    const [cameras, setCameras] = useState([]);
    const [camStatus, setCamStatus] = useState({});
    
    // Dynamic array of active camera IDs
    const [activeCameras, setActiveCameras] = useState([]);

    // Fetch dynamic cameras from PostgreSQL backend
    useEffect(() => {
        const fetchCameras = async () => {
            try {
                const res = await fetch(`${BACKEND_URL}/api/cameras`);
                if (res.ok) {
                    const data = await res.json();
                    const activeCams = data.filter(c => c.is_active || true).map(c => ({
                        id: c.camera_id,
                        label: c.camera_name,
                        is_active: c.is_active
                    }));
                    setCameras(activeCams);
                    
                    const statusObj = {};
                    activeCams.forEach(c => statusObj[c.id] = c.is_active);
                    setCamStatus(statusObj);
                }
            } catch (err) {
                console.error("Failed to load dynamic cameras:", err);
            }
        };
        fetchCameras();
    }, []);

    const [selectedCam, setSelectedCam] = useState(null);


    // ESC key to close fullscreen camera view
    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === "Escape") setSelectedCam(null);
        };
        window.addEventListener("keydown", handleEsc);
        return () => window.removeEventListener("keydown", handleEsc);
    }, []);

    const handleStreamError = (camId) => {
        setCamStatus(prev => ({ ...prev, [camId]: false }));
    };

    // Derived State for Active Target Panel
    const activeTarget = liveAlerts.length > 0 ? liveAlerts[0] : null;
    const isWatchlist = activeTarget && activeTarget.status === "WATCHLIST_MATCH";

    // --- Drag and Drop Handlers ---
    const handleDragStart = (e, camId) => {
        e.dataTransfer.setData('cameraId', camId);
    };

    const handleDragOver = (e) => {
        e.preventDefault();
    };

    const handleDrop = (e) => {
        e.preventDefault();
        const camId = e.dataTransfer.getData('cameraId');
        if (!camId) return;

        setActiveCameras(prev => {
            if (prev.includes(camId)) return prev; // Prevent duplicate feeds
            return [...prev, camId];
        });
    };

    const clearCamera = (camId) => {
        setActiveCameras(prev => prev.filter(id => id !== camId));
    };

    const clearAllCameras = () => {
        setActiveCameras([]);
    };

    return (
        <div className="flex h-full relative bg-slate-50 overflow-hidden">
            {/* LEFT SIDEBAR: Camera Roster */}
            <div className="w-[280px] bg-slate-900 border-r border-slate-800 flex flex-col z-10 shrink-0 text-white shadow-2xl">
                <div className="p-5 border-b border-slate-800 flex justify-between items-center">
                    <h3 className="font-black uppercase tracking-widest text-sm flex items-center">
                        <Video className="w-4 h-4 mr-2 text-blue-500" />
                        Roster
                    </h3>
                    <span className="bg-slate-800 text-slate-300 px-2 py-1 rounded text-xs font-bold">
                        {cameras.length} Cams
                    </span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar bg-slate-900">
                    {cameras.length === 0 ? (
                        <div className="text-center text-slate-500 mt-10 text-xs font-bold uppercase tracking-widest">No Cameras</div>
                    ) : (
                        cameras.map(cam => (
                            <div 
                                key={cam.id} 
                                draggable 
                                onDragStart={(e) => handleDragStart(e, cam.id)} 
                                className="bg-slate-800 p-3 rounded-xl cursor-grab active:cursor-grabbing hover:bg-slate-700 transition-colors border border-slate-700 shadow-sm"
                            >
                                <div className="flex justify-between items-start">
                                    <span className="font-bold text-sm truncate pr-2">{cam.label}</span>
                                    <span className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${camStatus[cam.id] ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]' : 'bg-red-500'}`}></span>
                                </div>
                                <div className="text-[10px] text-slate-400 mt-1 font-mono">{cam.id}</div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* MAIN CONTENT AREA */}
            <div className="flex-1 p-6 overflow-auto">

                {/* HEADER */}
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center">
                            <MonitorPlay className="w-7 h-7 mr-3 text-blue-600" />
                            Command Center
                        </h2>
                        <p className="text-slate-500 font-medium mt-1">Real-time HD streams and AI tracking.</p>
                    </div>

                    <div className="flex items-center gap-3">
                        {activeCameras.length > 0 && (
                            <button 
                                onClick={clearAllCameras}
                                className="text-slate-500 hover:text-red-500 hover:bg-red-50 px-3 py-1.5 rounded-lg text-sm font-bold transition-colors"
                            >
                                Clear Board
                            </button>
                        )}
                        <span className="text-blue-600 bg-blue-50 border border-blue-200 px-4 py-1.5 rounded-full text-sm font-bold flex items-center shadow-sm">
                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2"></span>
                            Live Feed Active
                        </span>
                    </div>
                </div>

                {/* CAMERA GRID: Dynamic Auto-Scaling Grid */}
                <div 
                    className={`grid gap-4 h-[calc(100%-60px)] overflow-y-auto custom-scrollbar content-start ${
                        activeCameras.length === 0 ? 'flex items-center justify-center' :
                        activeCameras.length === 1 ? 'grid-cols-1' :
                        activeCameras.length === 2 ? 'grid-cols-2' :
                        activeCameras.length <= 4 ? 'grid-cols-2 grid-rows-2' :
                        activeCameras.length <= 9 ? 'grid-cols-3' :
                        'grid-cols-4'
                    }`}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                >
                    {activeCameras.length === 0 ? (
                        <div className="text-slate-400 flex flex-col items-center pointer-events-none w-full max-w-md mx-auto p-12 border-2 border-dashed border-slate-200 rounded-3xl bg-slate-50">
                            <MonitorPlay className="w-16 h-16 mb-4 text-slate-300" />
                            <h3 className="text-lg font-black uppercase tracking-widest text-slate-500 mb-2">Awaiting Feeds</h3>
                            <p className="text-sm font-medium text-center">Drag and drop cameras from the roster on the left into this area to build your Command Center.</p>
                        </div>
                    ) : (
                        activeCameras.map((camId) => {
                            const cam = cameras.find(c => c.id === camId);
                            if (!cam) return null;
                            
                            return (
                                <div 
                                    key={camId}
                                    className="rounded-2xl overflow-hidden relative transition-all bg-slate-900 shadow-lg border border-slate-800 min-h-[300px] max-h-[80vh] flex flex-col"
                                >
                                    {/* Overlay Header */}
                                    <div className="absolute top-3 left-3 z-10 text-white text-xs font-bold tracking-widest uppercase bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 cursor-pointer hover:bg-blue-600/80 transition-colors" onClick={() => setSelectedCam(cam)}>
                                        {cam.label}
                                    </div>
                                    
                                    {/* Close Button */}
                                    <button 
                                        onClick={() => clearCamera(camId)}
                                        className="absolute top-3 right-3 z-10 text-white/70 hover:text-white bg-black/40 hover:bg-red-500/90 p-1.5 rounded-lg transition-colors"
                                        title="Close Stream"
                                    >
                                        <X className="w-4 h-4" />
                                    </button>

                                    {/* Video Feed */}
                                    <div className="flex-1 w-full relative">
                                        {camStatus[cam.id] ? (
                                            <div className="absolute inset-0" onDoubleClick={() => setSelectedCam(cam)}>
                                                <WebRTCPlayer camId={cam.id} onError={handleStreamError} />
                                            </div>
                                        ) : (
                                            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 bg-slate-950">
                                                <AlertCircle className="w-8 h-8 mb-2 opacity-50" />
                                                <span className="text-sm font-medium uppercase tracking-widest">Offline</span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* RIGHT SIDEBAR: Recent Detections Queue & Active Target */}
            <div className="w-[340px] bg-white border-l border-slate-200 flex flex-col shadow-2xl z-10 shrink-0">
                <div className="p-5 border-b border-slate-100 bg-slate-50">
                    <h3 className="font-black text-slate-800 uppercase tracking-widest text-sm flex items-center">
                        <AlertCircle className="w-4 h-4 mr-2 text-blue-600" />
                        Live Intelligence
                    </h3>
                </div>

                {/* ACTIVE TARGET PANEL (liveAlerts[0]) */}
                {activeTarget ? (
                    <div className="p-4 border-b border-slate-200 bg-slate-50/50">
                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Active Target</h4>
                        <div className={`p-4 rounded-2xl border-2 shadow-sm ${isWatchlist ? 'bg-red-50 border-red-200' : 'bg-white border-blue-200'}`}>
                            <div className="flex gap-2 mb-3">
                                <div className="w-1/2 aspect-square rounded-xl overflow-hidden bg-slate-100 border border-slate-200 relative">
                                    <span className="absolute bottom-1 right-1 bg-black/60 text-white text-[10px] px-1.5 rounded uppercase font-bold z-10">LIVE</span>
                                    {activeTarget.live_image ? (
                                        <img src={getImageUrl(activeTarget.live_image)} className="w-full h-full object-cover" alt="Live" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center"><User className="w-6 h-6 text-slate-300" /></div>
                                    )}
                                </div>
                                <div className="w-1/2 aspect-square rounded-xl overflow-hidden bg-slate-100 border border-slate-200 relative">
                                    <span className="absolute bottom-1 right-1 bg-black/60 text-white text-[10px] px-1.5 rounded uppercase font-bold z-10">DB</span>
                                    {isWatchlist && activeTarget.reference_image ? (
                                        <img src={getImageUrl(activeTarget.reference_image)} className="w-full h-full object-cover" alt="Reference" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center"><User className="w-6 h-6 text-slate-300" /></div>
                                    )}
                                </div>
                            </div>
                            <div>
                                <h5 className={`font-black text-lg ${isWatchlist ? 'text-red-700' : 'text-slate-900'} leading-tight truncate`}>
                                    {isWatchlist ? activeTarget.full_name : activeTarget.person_id}
                                </h5>
                                {isWatchlist && (
                                    <div className="mt-1 flex items-center">
                                        <span className="px-2 py-0.5 bg-red-600 text-white text-[10px] font-bold uppercase rounded-md tracking-widest">{activeTarget.risk_level} Risk</span>
                                    </div>
                                )}
                                <div className="mt-2 text-xs font-medium text-slate-500 space-y-1">
                                    <div className="flex justify-between">
                                        <span>Camera:</span>
                                        <span className="font-bold text-slate-700">{activeTarget.camera_id}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>Time:</span>
                                        <span className="font-bold text-slate-700">{new Date(activeTarget.timestamp * 1000).toLocaleTimeString()}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="p-8 text-center text-slate-400 border-b border-slate-100">
                        <User className="w-8 h-8 mx-auto mb-2 opacity-30" />
                        <p className="text-xs font-bold uppercase tracking-widest">No Detections</p>
                    </div>
                )}

                {/* QUEUE (liveAlerts 1 through 9) */}
                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-slate-50/30">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Recent Detections Queue</h4>
                    {liveAlerts.length <= 1 ? (
                        <div className="text-center text-slate-400 mt-6">
                            <p className="text-xs font-medium">Queue is empty</p>
                        </div>
                    ) : (
                        liveAlerts.slice(1).map((alert, idx) => {
                            const isWl = alert.status === 'WATCHLIST_MATCH';
                            return (
                                <div key={idx} className={`flex items-start gap-3 mb-3 p-2.5 rounded-xl border transition-all ${isWl ? 'bg-red-50 border-red-200 hover:border-red-300' : 'bg-white border-slate-200 hover:border-blue-300'}`}>
                                    <div className="w-10 h-10 rounded-lg overflow-hidden bg-slate-100 shrink-0 border border-slate-200 relative">
                                        {alert.live_image ? (
                                            <img src={getImageUrl(alert.live_image)} className="w-full h-full object-cover" alt="Sighting" />
                                        ) : (
                                            <div className="absolute inset-0 flex items-center justify-center"><User className="w-4 h-4 text-slate-300"/></div>
                                        )}
                                    </div>
                                    <div className="flex-1 overflow-hidden">
                                        <p className={`text-[13px] font-bold truncate ${isWl ? 'text-red-700' : 'text-slate-800'}`}>
                                            {isWl ? (alert.full_name || 'Unknown Suspect') : alert.person_id}
                                        </p>
                                        <div className="flex justify-between items-center mt-0.5">
                                            <span className="text-[10px] font-bold text-slate-400">{alert.camera_id}</span>
                                            <span className="text-[10px] font-bold text-slate-400">{new Date(alert.timestamp * 1000).toLocaleTimeString()}</span>
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