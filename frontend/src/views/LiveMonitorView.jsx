import React, { useState, useEffect, useRef } from 'react';
import { MonitorPlay, AlertCircle, RefreshCw } from 'lucide-react';
import { MEDIAMTX_URL, BACKEND_URL, getImageUrl } from '../config';
import WatchlistPanel from '../components/WatchlistPanel';
import LiveAlertBar from '../components/LiveAlertBar';

// WebRTC Player Component
const WebRTCPlayer = ({ camId, label, onError }) => {
    const videoRef = useRef(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [retryCount, setRetryCount] = useState(0);

    useEffect(() => {
        let pc = null;
        let isActive = true;

        const startStream = async () => {
            try {
                console.log(`[WebRTC] Connecting to ${camId}...`);
                pc = new RTCPeerConnection();

                // Add a transceiver to receive video
                pc.addTransceiver('video', { direction: 'recvonly' });

                pc.ontrack = (event) => {
                    if (isActive && videoRef.current) {
                        videoRef.current.srcObject = event.streams[0];
                        setIsPlaying(true);
                    }
                };

                // Create and set local description (SDP Offer)
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                // Send the offer to MediaMTX's WHEP endpoint
                const whepUrl = `${MEDIAMTX_URL}/${camId}/whep`;
                console.log(`[WebRTC] Sending offer to ${whepUrl}`);

                const response = await fetch(whepUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: pc.localDescription.sdp,
                });

                if (!response.ok) {
                    throw new Error(`WHEP response: ${response.status}`);
                }

                // Set the remote description (SDP Answer from MediaMTX)
                const answerSdp = await response.text();
                if (isActive && pc.signalingState !== 'closed') {
                    await pc.setRemoteDescription(new RTCSessionDescription({
                        type: 'answer',
                        sdp: answerSdp,
                    }));
                    console.log(`[WebRTC] ✅ ${camId} connected!`);
                }
            } catch (err) {
                console.error(`[WebRTC] ❌ ${camId} failed:`, err.message);
                if (isActive) {
                    if (retryCount < 3) {
                        setTimeout(() => setRetryCount(prev => prev + 1), 5000);
                    } else {
                        onError(camId);
                    }
                }
            }
        };

        startStream();

        return () => {
            isActive = false;
            if (pc) {
                pc.close();
            }
        };
    }, [camId, retryCount]);

    return (
        <div className="relative w-full aspect-video bg-black">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className={`w-full h-full object-contain ${isPlaying ? 'opacity-100' : 'opacity-0'}`}
            />
            {!isPlaying && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                    <RefreshCw className="w-8 h-8 animate-spin opacity-50 mb-2" />
                    <p className="text-xs opacity-50 font-medium">Connecting WebRTC...</p>
                </div>
            )}
        </div>
    );
};


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
    const [isSearchActive, setIsSearchActive] = useState(false);

    // Watch for WATCHLIST_MATCH events
    useEffect(() => {
        if (liveAlerts.length > 0) {
            const latest = liveAlerts[0];
            if (latest.status === "WATCHLIST_MATCH") {
                setWatchlistAlert(latest);
            }
        }
    }, [liveAlerts]);

    const handleStreamError = (camId) => {
        setCamStatus(prev => ({ ...prev, [camId]: false }));
    };

    const handleSearchStateChange = (active, ids) => {
        setIsSearchActive(active);
    };

    return (
        <div className="flex h-full relative">
            {/* Top Alert Bar */}
            <LiveAlertBar alert={watchlistAlert} onDismiss={() => setWatchlistAlert(null)} />

            <div className="flex-1 p-6 overflow-auto">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-2xl font-bold text-slate-800">Live Monitor</h2>
                    <div className="flex items-center gap-3">
                        {isSearchActive && (
                            <span className="flex items-center text-sm font-medium text-red-600 bg-red-50 px-3 py-1 rounded-full border border-red-200 animate-pulse">
                                <span className="w-2 h-2 bg-red-500 rounded-full mr-2"></span>
                                Watchlist Scanning
                            </span>
                        )}
                        <span className="flex items-center text-sm font-medium text-blue-600 bg-blue-50 px-3 py-1 rounded-full border border-blue-200">
                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2"></span>
                            WebRTC Active
                        </span>
                        <span className="flex items-center text-sm font-medium text-green-600 bg-green-50 px-3 py-1 rounded-full border border-green-200">
                            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2"></span>
                            System Active
                        </span>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    {cameras.map((cam) => (
                        <div key={cam.id} className="bg-slate-800 rounded-xl overflow-hidden relative group shadow-sm border border-slate-700">
                            <div className="absolute top-3 left-3 z-10 text-white text-xs font-medium bg-black/60 px-3 py-1 rounded-md backdrop-blur-sm flex items-center">
                                <span className={`w-2 h-2 rounded-full mr-2 ${camStatus[cam.id] ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}></span>
                                {cam.label}
                            </div>

                            {camStatus[cam.id] ? (
                                <WebRTCPlayer camId={cam.id} label={cam.label} onError={handleStreamError} />
                            ) : (
                                <div className="w-full aspect-video flex flex-col items-center justify-center text-slate-500 bg-slate-900">
                                    <MonitorPlay className="w-12 h-12 opacity-30 mb-2" />
                                    <p className="text-xs opacity-50 font-medium">Camera Offline / Waiting</p>
                                    <p className="text-xs opacity-30 mt-1">{cam.label}</p>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* RIGHT SIDEBAR: Watchlist + Live Captures */}
            <div className="w-80 bg-white border-l border-slate-200 flex flex-col h-full">
                {/* Watchlist Panel */}
                <WatchlistPanel onSearchStateChange={handleSearchStateChange} />

                {/* Live Captures Feed */}
                <div className="flex-1 flex flex-col min-h-0 border-t border-slate-200">
                    <div className="p-4 border-b border-slate-100 flex justify-between items-center">
                        <h3 className="font-semibold text-slate-800">Live Captures</h3>
                        <span className="bg-blue-100 text-blue-700 text-xs px-2 py-1 rounded-full font-bold">{liveAlerts.length}</span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {liveAlerts.length === 0 ? (
                            <div className="text-center text-slate-400 text-sm mt-10">Waiting for AI detections...</div>
                        ) : (
                            liveAlerts.map((alert, idx) => (
                                <div key={idx} className="flex items-center justify-between p-2 hover:bg-slate-50 rounded-lg border border-transparent hover:border-slate-100 transition-colors">
                                    <div className="flex items-center space-x-3">
                                        <img src={getImageUrl(alert.image_path)} alt="Capture" className="w-12 h-12 rounded-full border border-slate-200 object-cover" />
                                        <div>
                                            <p className="text-sm font-bold text-slate-800">{alert.suspect_name || alert.camera_id}</p>
                                            <p className="text-xs font-medium text-slate-500 mb-0.5">{alert.person_id?.substring(0, 12)}...</p>
                                            <p className="text-[10px] text-slate-400">{new Date(alert.timestamp * 1000).toLocaleTimeString()}</p>
                                        </div>
                                    </div>
                                    {alert.status === "MATCH" && (
                                        <AlertCircle className="w-4 h-4 text-amber-500" />
                                    )}
                                    {alert.status === "WATCHLIST_MATCH" && (
                                        <span className="bg-red-500 text-white text-[10px] font-bold px-2 py-1 rounded-full animate-pulse">WANTED</span>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LiveMonitorView;
