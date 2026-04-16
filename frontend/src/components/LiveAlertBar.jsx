import React from 'react';
import { ShieldAlert, X, MapPin, Clock } from 'lucide-react';
import { getImageUrl } from '../config';

const LiveAlertBar = ({ alert, onDismiss }) => {
    if (!alert) return null;

    return (
        <div className="fixed top-0 left-0 right-0 z-[60] animate-slideDown">
            <div className="bg-gradient-to-r from-red-700 via-red-600 to-red-700 text-white shadow-2xl border-b-4 border-red-900">
                <div className="max-w-screen-xl mx-auto px-6 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="relative">
                            <div className="absolute -inset-1 bg-white/20 rounded-full blur animate-pulse"></div>
                            <ShieldAlert className="relative w-8 h-8 animate-bounce" />
                        </div>

                        <div className="flex items-center gap-4">
                            <img
                                src={getImageUrl(alert.image_path)}
                                alt="Match"
                                className="w-12 h-12 rounded-full object-cover border-2 border-white/50 shadow-lg"
                            />
                            <div>
                                <p className="font-black text-lg tracking-wide uppercase">
                                    🚨 {alert.suspect_name || alert.person_id} Detected!
                                </p>
                                <div className="flex items-center gap-4 text-sm text-red-100">
                                    <span className="flex items-center gap-1">
                                        <MapPin className="w-3 h-3" /> {alert.camera_id}
                                    </span>
                                    <span className="flex items-center gap-1">
                                        <Clock className="w-3 h-3" /> {new Date(alert.timestamp * 1000).toLocaleTimeString()}
                                    </span>
                                    <span>Confidence: {(alert.confidence * 100).toFixed(1)}%</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <button
                        onClick={onDismiss}
                        className="p-2 bg-black/20 hover:bg-black/40 rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
            </div>
        </div>
    );
};

export default LiveAlertBar;
