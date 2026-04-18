import React, { useEffect } from 'react';
import { AlertTriangle, MapPin, Crosshair, ShieldAlert, X } from 'lucide-react';
import { BACKEND_URL } from '../config';

const ThreatAlertModal = ({ alertData, onAcknowledge }) => {
    if (!alertData) return null;

    // Optional: Flash the screen red using a CSS animation class
    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Pulsing Red Backdrop */}
            <div className="absolute inset-0 bg-red-950/90 backdrop-blur-md animate-pulse" style={{ animationDuration: '2s' }}></div>

            <div className="bg-slate-950 border-2 border-red-600 rounded-3xl shadow-[0_0_100px_rgba(220,38,38,0.4)] w-full max-w-4xl relative z-10 overflow-hidden flex flex-col animate-in zoom-in duration-200">

                {/* Header - Flashing Red */}
                <div className="bg-red-600 p-4 flex justify-between items-center">
                    <div className="flex items-center text-white">
                        <AlertTriangle className="w-8 h-8 mr-3 animate-bounce" />
                        <div>
                            <h2 className="text-2xl font-black tracking-widest uppercase">Critical Watchlist Match</h2>
                            <p className="text-red-200 text-xs font-bold tracking-widest">Protocol Override: Immediate Action Required</p>
                        </div>
                    </div>
                    <button onClick={onAcknowledge} className="text-white/70 hover:text-white p-2">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <div className="p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
                    {/* Left: Intelligence Data */}
                    <div className="space-y-6">
                        <div>
                            <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Identified Target</h3>
                            <p className="text-4xl font-black text-white">{alertData.full_name}</p>
                            <div className="inline-block mt-2 px-3 py-1 bg-red-950 border border-red-500 text-red-500 text-xs font-bold uppercase rounded-md">
                                Risk Level: {alertData.risk_level || 'UNKNOWN'}
                            </div>
                        </div>

                        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
                            <div className="flex items-start">
                                <MapPin className="w-5 h-5 text-blue-500 mr-3 mt-0.5" />
                                <div>
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Location / Camera Feed</h4>
                                    <p className="text-lg font-bold text-white">{alertData.camera_id}</p>
                                </div>
                            </div>
                            <div className="flex items-start">
                                <Crosshair className="w-5 h-5 text-amber-500 mr-3 mt-0.5" />
                                <div>
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">AI Confidence Score</h4>
                                    <p className="text-lg font-bold text-white">{(alertData.confidence * 100).toFixed(2)}% Match</p>
                                </div>
                            </div>
                        </div>

                        <button
                            onClick={onAcknowledge}
                            className="w-full py-4 bg-red-600 hover:bg-red-700 text-white font-black uppercase tracking-widest rounded-xl transition-all shadow-lg shadow-red-600/20"
                        >
                            Acknowledge & Disarm Alarm
                        </button>
                    </div>

                    {/* Right: Side-by-side Visual Verification */}
                    <div className="flex gap-4">
                        {/* Reference Image (Database) */}
                        <div className="flex-1 flex flex-col">
                            <div className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden relative">
                                <img
                                    src={`${BACKEND_URL}${alertData.reference_image}`}
                                    className="w-full h-full object-cover"
                                    alt="Reference"
                                    onError={(e) => { e.target.onerror = null; e.target.src = "https://placehold.co/300x400/1e293b/ffffff?text=NO+REFERENCE"; }}
                                />
                                <div className="absolute top-2 left-2 bg-black/80 px-2 py-1 rounded text-[9px] font-bold text-slate-300 uppercase">File Photo</div>
                            </div>
                        </div>

                        {/* Live Sighting Image */}
                        <div className="flex-1 flex flex-col">
                            <div className="flex-1 bg-slate-900 border-2 border-red-500 rounded-2xl overflow-hidden relative">
                                <img
                                    src={`${BACKEND_URL}${alertData.live_image}`}
                                    className="w-full h-full object-cover"
                                    alt="Live Match"
                                    onError={(e) => { e.target.onerror = null; e.target.src = "https://placehold.co/300x400/1e293b/ffffff?text=NO+LIVE+FEED"; }}
                                />
                                <div className="absolute top-2 left-2 bg-red-600 px-2 py-1 rounded text-[9px] font-bold text-white uppercase flex items-center">
                                    <div className="w-1.5 h-1.5 bg-white rounded-full animate-ping mr-1.5"></div>
                                    Live Capture
                                </div>
                                {/* Crosshair overlay effect */}
                                <div className="absolute inset-0 border border-red-500/30 bg-[radial-gradient(circle_at_center,transparent_50%,rgba(220,38,38,0.1)_100%)] pointer-events-none"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ThreatAlertModal;