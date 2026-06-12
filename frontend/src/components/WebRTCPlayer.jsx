import React, { useState, useEffect, useRef } from 'react';
import { RefreshCw } from 'lucide-react';
import { MEDIAMTX_URL } from '../config';

const WebRTCPlayer = ({ camId, label, onError }) => {
    const videoRef = useRef(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [retryCount, setRetryCount] = useState(0);

    useEffect(() => {
        let pc = null;
        let isActive = true;
        let timeoutId = null;

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
                    timeoutId = setTimeout(() => {
                        if (isActive) setRetryCount(prev => prev + 1);
                    }, 5000);
                } else {
                    if (onError) onError(camId);
                }
            }
        };

        startStream();

        return () => {
            isActive = false;
            if (timeoutId) clearTimeout(timeoutId);
            if (pc) pc.close();
        };
    }, [camId, retryCount, onError]);

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

export default WebRTCPlayer;
