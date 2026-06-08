import React, { useState } from 'react';
import { Search, Loader2, X, CheckSquare, AlertTriangle, ShieldCheck, RefreshCw } from 'lucide-react';
import api from '../api';

const NvrDiscoveryModal = ({ isOpen, onClose, onImportSuccess }) => {
    const [step, setStep] = useState(1); // 1: Input, 2: Scanning, 3: Results, 4: Importing
    const [credentials, setCredentials] = useState({ ip: '', port: 80, user: 'admin', password: '' });
    const [discoveredCameras, setDiscoveredCameras] = useState([]);
    const [selectedCameras, setSelectedCameras] = useState(new Set());
    const [importResult, setImportResult] = useState(null);

    if (!isOpen) return null;

    const handleScan = async () => {
        setStep(2);
        try {
            const res = await api.post('/api/nvr/discover', credentials);
            setDiscoveredCameras(res.data.cameras || []);
            // Auto-select all by default
            setSelectedCameras(new Set(res.data.cameras.map(c => c.camera_id)));
            setStep(3);
        } catch (error) {
            console.error(error);
            alert("Scan Failed: " + (error.response?.data?.detail || error.message));
            setStep(1);
        }
    };

    const toggleSelection = (id) => {
        const newSet = new Set(selectedCameras);
        if (newSet.has(id)) newSet.delete(id);
        else newSet.add(id);
        setSelectedCameras(newSet);
    };

    const handleImport = async () => {
        setStep(4);
        setImportResult(null);
        const camerasToImport = discoveredCameras.filter(c => selectedCameras.has(c.camera_id));
        try {
            const res = await api.post('/api/nvr/bulk_import', camerasToImport);
            setImportResult(res.data);
            onImportSuccess();
        } catch (error) {
            console.error(error);
            alert("Bulk Import Failed: " + (error.response?.data?.detail || error.message));
            setStep(3);
        }
    };

    const handleRetry = () => {
        setImportResult(null);
        setStep(3);
    };

    return (
        <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-50 flex justify-center items-center p-4">
            <div className="bg-white rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
                
                {/* Header */}
                <div className="bg-indigo-600 p-6 flex justify-between items-center text-white shrink-0">
                    <div>
                        <h2 className="text-2xl font-black flex items-center">
                            <Search className="w-6 h-6 mr-3" />
                            ONVIF Auto-Discovery
                        </h2>
                        <p className="text-indigo-200 text-sm mt-1">Scan NVRs and bulk-import active cameras.</p>
                    </div>
                    <button onClick={onClose} className="hover:bg-indigo-700 p-2 rounded-lg transition-colors">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 overflow-y-auto flex-1 custom-scrollbar">
                    {step === 1 && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 uppercase">NVR IP Address</label>
                                    <input type="text" className="mt-1 w-full border border-slate-200 rounded-lg p-3 bg-slate-50" placeholder="192.168.1.100" value={credentials.ip} onChange={e => setCredentials({...credentials, ip: e.target.value})} />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 uppercase">ONVIF Port</label>
                                    <input type="number" className="mt-1 w-full border border-slate-200 rounded-lg p-3 bg-slate-50" value={credentials.port} onChange={e => setCredentials({...credentials, port: parseInt(e.target.value)})} />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 uppercase">Username</label>
                                    <input type="text" className="mt-1 w-full border border-slate-200 rounded-lg p-3 bg-slate-50" value={credentials.user} onChange={e => setCredentials({...credentials, user: e.target.value})} />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 uppercase">Password</label>
                                    <input type="password" className="mt-1 w-full border border-slate-200 rounded-lg p-3 bg-slate-50" value={credentials.password} onChange={e => setCredentials({...credentials, password: e.target.value})} />
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="py-12 flex flex-col items-center justify-center">
                            <Loader2 className="w-12 h-12 text-indigo-500 animate-spin mb-4" />
                            <h3 className="text-lg font-bold text-slate-700">Executing SOAP Handshake...</h3>
                            <p className="text-slate-500 text-sm text-center max-w-sm mt-2">Connecting to NVR and extracting media profiles. This may take up to 15 seconds depending on the network.</p>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-4">
                            <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl flex items-start">
                                <AlertTriangle className="w-6 h-6 text-amber-500 mr-3 shrink-0" />
                                <div>
                                    <h4 className="font-bold text-amber-800">Verify Ghost Channels</h4>
                                    <p className="text-amber-700 text-sm mt-1">ONVIF returns all channels, even if no physical camera is plugged in. Please uncheck dead streams before importing.</p>
                                </div>
                            </div>
                            
                            <div className="border border-slate-200 rounded-xl overflow-hidden divide-y divide-slate-100">
                                {discoveredCameras.length === 0 ? (
                                    <div className="p-6 text-center text-slate-500 font-medium">No ONVIF profiles found.</div>
                                ) : (
                                    discoveredCameras.map((cam, idx) => (
                                        <label key={idx} className="flex items-center p-4 hover:bg-slate-50 cursor-pointer transition-colors">
                                            <input 
                                                type="checkbox" 
                                                className="w-5 h-5 text-indigo-600 rounded mr-4"
                                                checked={selectedCameras.has(cam.camera_id)}
                                                onChange={() => toggleSelection(cam.camera_id)}
                                            />
                                            <div className="flex-1 min-w-0">
                                                <p className="font-bold text-slate-800 truncate">{cam.name}</p>
                                                <p className="text-xs text-slate-400 font-mono truncate mt-1">{cam.rtsp_url}</p>
                                            </div>
                                        </label>
                                    ))
                                )}
                            </div>
                        </div>
                    )}

                    {step === 4 && (
                        <div className="py-12 flex flex-col items-center justify-center">
                            {importResult ? (
                                <>
                                    <ShieldCheck className="w-16 h-16 text-teal-500 mb-4" />
                                    <h3 className="text-2xl font-black text-slate-800">Verification Complete</h3>
                                    <div className="mt-4 bg-slate-50 p-4 rounded-xl border border-slate-200 text-center w-full max-w-sm">
                                        <p className="text-sm font-bold text-slate-500 uppercase">Attempted</p>
                                        <p className="text-xl font-black text-slate-800">{importResult.attempted}</p>
                                        <div className="h-px bg-slate-200 my-2"></div>
                                        <p className="text-sm font-bold text-teal-600 uppercase">Successfully Imported</p>
                                        <p className="text-2xl font-black text-teal-600">{importResult.imported}</p>
                                    </div>
                                    <p className="text-slate-500 text-sm mt-4">Dead ghost streams were actively rejected.</p>
                                    <button 
                                        onClick={handleRetry}
                                        className="mt-5 flex items-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm shadow-lg shadow-indigo-600/20 transition-all"
                                    >
                                        <RefreshCw className="w-4 h-4" /> Retry Verification
                                    </button>
                                </>
                            ) : (
                                <>
                                    <Loader2 className="w-12 h-12 text-teal-500 animate-spin mb-4" />
                                    <h3 className="text-lg font-bold text-slate-700">Pinging OpenCV Streams...</h3>
                                    <p className="text-slate-500 text-sm text-center max-w-sm mt-2">Executing concurrent asyncio.gather validation to filter out ghost channels. (Timeout: 8s)</p>
                                </>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-slate-50 p-6 border-t border-slate-200 flex justify-end shrink-0">
                    <button onClick={onClose} className="px-6 py-3 font-bold text-slate-500 hover:text-slate-800 transition-colors mr-2">Cancel</button>
                    {step === 1 && (
                        <button onClick={handleScan} disabled={!credentials.ip} className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-3 rounded-xl font-bold flex items-center shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50">
                            <Search className="w-5 h-5 mr-2" /> Start Discovery Scan
                        </button>
                    )}
                    {step === 3 && (
                        <button onClick={handleImport} disabled={selectedCameras.size === 0} className="bg-teal-600 hover:bg-teal-700 text-white px-8 py-3 rounded-xl font-bold flex items-center shadow-lg shadow-teal-600/20 transition-all disabled:opacity-50">
                            <CheckSquare className="w-5 h-5 mr-2" /> Verify & Import Selected
                        </button>
                    )}
                </div>

            </div>
        </div>
    );
};

export default NvrDiscoveryModal;
