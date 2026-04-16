import React, { useState, useEffect, useRef } from 'react';
import { UserPlus, Search, X, Shield, ShieldAlert, ShieldCheck, Trash2, Loader2 } from 'lucide-react';
import { BACKEND_URL } from '../config';

const WatchlistPanel = ({ onSearchStateChange }) => {
    const [suspects, setSuspects] = useState([]);
    const [selectedIds, setSelectedIds] = useState([]);
    const [isSearching, setIsSearching] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadName, setUploadName] = useState('');
    const [showUploadForm, setShowUploadForm] = useState(false);
    const fileInputRef = useRef(null);

    // Fetch enrolled suspects on mount
    useEffect(() => {
        fetchSuspects();
    }, []);

    const fetchSuspects = async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/api/watchlist/list`);
            const data = await res.json();
            setSuspects(data.suspects || []);
        } catch (err) {
            console.error("Failed to fetch watchlist:", err);
        }
    };

    const handleUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setIsUploading(true);
        const formData = new FormData();
        formData.append("file", file);

        const name = uploadName.trim() || "Unknown Suspect";
        const url = `${BACKEND_URL}/api/watchlist/add?name=${encodeURIComponent(name)}`;

        try {
            const res = await fetch(url, { method: 'POST', body: formData });
            const data = await res.json();
            if (res.ok) {
                await fetchSuspects();
                setShowUploadForm(false);
                setUploadName('');
            } else {
                alert("Error: " + (data.detail || "Upload failed"));
            }
        } catch (err) {
            alert("Upload failed: " + err.message);
        }
        setIsUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleRemove = async (watchlistId) => {
        try {
            await fetch(`${BACKEND_URL}/api/watchlist/remove/${watchlistId}`, { method: 'DELETE' });
            setSelectedIds(prev => prev.filter(id => id !== watchlistId));
            await fetchSuspects();
        } catch (err) {
            console.error("Remove failed:", err);
        }
    };

    const toggleSelection = (id) => {
        setSelectedIds(prev =>
            prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
        );
    };

    const startSearch = async () => {
        if (selectedIds.length === 0) return;
        try {
            await fetch(`${BACKEND_URL}/api/watchlist/activate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(selectedIds)
            });
            setIsSearching(true);
            onSearchStateChange?.(true, selectedIds);
        } catch (err) {
            console.error("Activate failed:", err);
        }
    };

    const stopSearch = async () => {
        try {
            await fetch(`${BACKEND_URL}/api/watchlist/deactivate`, { method: 'DELETE' });
            setIsSearching(false);
            onSearchStateChange?.(false, []);
        } catch (err) {
            console.error("Deactivate failed:", err);
        }
    };

    return (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="p-4 border-b border-slate-100 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <Shield className="w-5 h-5 text-red-500" />
                    <h3 className="font-bold text-slate-800">Watchlist</h3>
                    <span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full font-bold">{suspects.length}</span>
                </div>
                <button
                    onClick={() => setShowUploadForm(!showUploadForm)}
                    className="p-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg transition-colors"
                >
                    {showUploadForm ? <X className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
                </button>
            </div>

            {/* Upload Form */}
            {showUploadForm && (
                <div className="p-4 bg-red-50/50 border-b border-red-100 space-y-3">
                    <input
                        type="text"
                        placeholder="Suspect Name..."
                        value={uploadName}
                        onChange={(e) => setUploadName(e.target.value)}
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/30 bg-white"
                    />
                    <input type="file" accept="image/*" ref={fileInputRef} onChange={handleUpload} className="hidden" />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploading}
                        className="w-full py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                    >
                        {isUploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing...</> : <><UserPlus className="w-4 h-4" /> Upload & Enroll</>}
                    </button>
                </div>
            )}

            {/* Suspects Grid */}
            <div className="p-3 max-h-[300px] overflow-y-auto">
                {suspects.length === 0 ? (
                    <div className="text-center text-slate-400 text-sm py-8">No suspects enrolled yet.</div>
                ) : (
                    <div className="grid grid-cols-2 gap-2">
                        {suspects.map((s) => {
                            const isSelected = selectedIds.includes(s.watchlist_id);
                            return (
                                <div
                                    key={s.watchlist_id}
                                    onClick={() => toggleSelection(s.watchlist_id)}
                                    className={`relative cursor-pointer rounded-lg overflow-hidden border-2 transition-all duration-200 group ${isSelected
                                        ? `border-red-500 scale-[1.02] shadow-lg ring-4 ring-red-500/40`
                                        : 'border-transparent opacity-70 hover:opacity-100 hover:border-slate-200'
                                        }`}
                                >
                                    <img
                                        src={BACKEND_URL + s.image_url}
                                        alt={s.name}
                                        className="w-full h-20 object-cover"
                                    />
                                    {/* Selection indicator */}
                                    {isSelected && (
                                        <div className="absolute top-1 right-1 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center">
                                            <ShieldCheck className="w-3 h-3 text-white" />
                                        </div>
                                    )}
                                    {/* Delete button */}
                                    <button
                                        onClick={(e) => { e.stopPropagation(); handleRemove(s.watchlist_id); }}
                                        className="absolute top-1 left-1 w-5 h-5 bg-black/50 hover:bg-red-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                    >
                                        <Trash2 className="w-3 h-3 text-white" />
                                    </button>
                                    <div className="bg-slate-900 text-center py-1 px-1">
                                        <p className="text-[10px] text-white font-medium truncate">{s.name}</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Action Bar */}
            {suspects.length > 0 && (
                <div className="p-3 border-t border-slate-100 space-y-2">
                    {!isSearching ? (
                        <button
                            onClick={startSearch}
                            disabled={selectedIds.length === 0}
                            className={`w-full py-2.5 text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-2 ${selectedIds.length > 0
                                ? 'bg-red-600 hover:bg-red-700 text-white shadow-md hover:shadow-red-500/25 active:scale-[0.98]'
                                : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                                }`}
                        >
                            <Search className="w-4 h-4" />
                            {selectedIds.length > 0
                                ? `Start Live Search (${selectedIds.length} Target${selectedIds.length > 1 ? 's' : ''})`
                                : 'Select Targets First'}
                        </button>
                    ) : (
                        <button
                            onClick={stopSearch}
                            className="w-full py-2.5 bg-slate-800 hover:bg-slate-900 text-white text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-2 animate-pulse"
                        >
                            <ShieldAlert className="w-4 h-4" />
                            Stop Search ({selectedIds.length} Active)
                        </button>
                    )}
                </div>
            )}
        </div>
    );
};

export default WatchlistPanel;
