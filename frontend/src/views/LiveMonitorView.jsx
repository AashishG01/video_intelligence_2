import React, { useState, useEffect, useRef } from 'react';
import { MonitorPlay, AlertCircle, RefreshCw } from 'lucide-react';
import { MEDIAMTX_URL, BACKEND_URL, getImageUrl } from '../config';
import WatchlistPanel from '../components/WatchlistPanel';
import LiveAlertBar from '../components/LiveAlertBar';

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
                className={`w-full h-full object-contain ${isPlaying ? 'opacity-100' : 'opacity-0'}`}
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
    const [isSearchActive, setIsSearchActive] = useState(false);

    // 🔥 NEW STATE (fullscreen)
    const [selectedCam, setSelectedCam] = useState(null);

    // ESC key close
    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === "Escape") setSelectedCam(null);
        };
        window.addEventListener("keydown", handleEsc);
        return () => window.removeEventListener("keydown", handleEsc);
    }, []);

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

    const handleSearchStateChange = (active) => {
        setIsSearchActive(active);
    };

    return (
        <div className="flex h-full relative">

            <LiveAlertBar alert={watchlistAlert} onDismiss={() => setWatchlistAlert(null)} />

            <div className="flex-1 p-6 overflow-auto">

                {/* HEADER */}
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-2xl font-bold text-slate-800">Live Monitor</h2>

                    <div className="flex items-center gap-3">
                        {isSearchActive && (
                            <span className="text-red-600 bg-red-50 px-3 py-1 rounded-full animate-pulse">
                                Watchlist Active
                            </span>
                        )}
                        <span className="text-blue-600 bg-blue-50 px-3 py-1 rounded-full">
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
                            className="bg-slate-800 rounded-xl overflow-hidden relative cursor-pointer hover:scale-[1.02] transition"
                        >
                            <div className="absolute top-3 left-3 z-10 text-white text-xs bg-black/60 px-3 py-1 rounded-md">
                                {cam.label}
                            </div>

                            {camStatus[cam.id] ? (
                                <WebRTCPlayer camId={cam.id} onError={handleStreamError} />
                            ) : (
                                <div className="w-full aspect-video flex items-center justify-center text-slate-400">
                                    Offline
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* SIDEBAR */}
            <div className="w-80 bg-white border-l flex flex-col">
                <WatchlistPanel onSearchStateChange={handleSearchStateChange} />

                <div className="flex-1 overflow-y-auto p-4">
                    {liveAlerts.map((alert, idx) => (
                        <div key={idx} className="flex items-center gap-3 mb-3">
                            <img
                                src={getImageUrl(alert.image_path)}
                                className="w-10 h-10 rounded-full"
                            />
                            <div>
                                <p className="text-sm font-bold">
                                    {alert.suspect_name || alert.camera_id}
                                </p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ========================= */}
            {/* 🔥 FULLSCREEN MODAL */}
            {/* ========================= */}
            {selectedCam && (
                <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center">

                    {/* CLOSE */}
                    <button
                        onClick={() => setSelectedCam(null)}
                        className="absolute top-5 right-5 text-white bg-black/60 px-4 py-2 rounded-lg"
                    >
                        ✕ Close
                    </button>

                    {/* LABEL */}
                    <div className="absolute top-5 left-5 text-white bg-black/60 px-4 py-2 rounded-lg">
                        {selectedCam.label}
                    </div>

                    {/* VIDEO */}
                    <div className="w-[90%] h-[90%]">
                        {camStatus[selectedCam.id] ? (
                            <WebRTCPlayer
                                camId={selectedCam.id}
                                onError={handleStreamError}
                            />
                        ) : (
                            <div className="text-white">Camera Offline</div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default LiveMonitorView;