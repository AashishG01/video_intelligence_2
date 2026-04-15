import React, { useState, useEffect, useRef } from 'react';
import { MonitorPlay, AlertCircle, RefreshCw } from 'lucide-react';
import { MEDIAMTX_URL, getImageUrl } from '../config';

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

                const offer = await pc.createOffer();
                if (!isActive) return;
                await pc.setLocalDescription(offer);

                // Send offer to MediaMTX WebRTC endpoint
                const response = await fetch(`${MEDIAMTX_URL}/${camId}/whep`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: pc.localDescription.sdp,
                });

                if (!isActive) return;
                if (!response.ok) {
                    throw new Error(`MediaMTX WHEP failed with HTTP ${response.status}`);
                }

                const answerSdp = await response.text();
                if (!isActive) return;

                await pc.setRemoteDescription(new RTCSessionDescription({
                    type: 'answer',
                    sdp: answerSdp
                }));

            } catch (err) {
                console.error(`[WebRTC] Error streaming ${camId}:`, err);
                if (isActive) {
                    setIsPlaying(false);
                    onError(camId);
                    // Try to reconnect every 5 seconds if connection fails
                    setTimeout(() => setRetryCount(rc => rc + 1), 5000);
                }
            }
        };

        startStream();

        return () => {
            isActive = false;
            if (pc) pc.close();
        };
    }, [camId, retryCount, onError]);

    return (
        <div className="w-full aspect-video relative bg-slate-900 overflow-hidden">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className={`w-full h-full object-cover transition-opacity duration-500 ${isPlaying ? 'opacity-100' : 'opacity-0'}`}
            />
            {!isPlaying && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500">
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

    const handleStreamError = (camId) => {
        setCamStatus(prev => ({ ...prev, [camId]: false }));
    };

    return (
        <div className="flex h-full">
            <div className="flex-1 p-6 overflow-auto">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-2xl font-bold text-slate-800">Live Monitor</h2>
                    <div className="flex items-center gap-3">
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

            {/* REAL-TIME Activity Sidebar */}
            <div className="w-80 bg-white border-l border-slate-200 flex flex-col h-full">
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
                                        <p className="text-sm font-bold text-slate-800">{alert.camera_id}</p>
                                        <p className="text-xs font-medium text-slate-500 mb-0.5">{alert.person_id.substring(0, 10)}...</p>
                                        <p className="text-[10px] text-slate-400">{new Date(alert.timestamp * 1000).toLocaleTimeString()}</p>
                                    </div>
                                </div>
                                {alert.status === "MATCH" && (
                                    <AlertCircle className="w-4 h-4 text-amber-500" />
                                )}
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
};

export default LiveMonitorView;
