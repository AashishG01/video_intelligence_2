import React, { useState, useRef } from 'react';
import {
    UserSearch,
    UploadCloud,
    Search,
    Clock,
    AlertCircle,
    Loader2,
    X,
    Hash
} from 'lucide-react';
import { BACKEND_URL } from '../config';
import SightingCard from '../components/SightingCard';
import TimelineCard from '../components/TimelineCard';

const InvestigatorView = () => {
    const [activeTab, setActiveTab] = useState('IMG_SEARCH');
    const [isSearching, setIsSearching] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);
    const [searchResults, setSearchResults] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [errorMsg, setErrorMsg] = useState(null);
    const fileInputRef = useRef(null);

    const [searchThreshold, setSearchThreshold] = useState(0.60);

    const [searchId, setSearchId] = useState("");
    const [isIdSearching, setIsIdSearching] = useState(false);
    const [idSearchResults, setIdSearchResults] = useState(null);
    const [idSearchError, setIdSearchError] = useState(null);
    const [personDossier, setPersonDossier] = useState(null);

    const handleFileSelect = (e) => {
        const file = e.target.files[0];
        if (file) {
            setSelectedFile(file);
            setPreviewUrl(URL.createObjectURL(file));
            setHasSearched(false);
            setSearchResults([]);
            setErrorMsg(null);
        }
    };

    const clearSelection = (e) => {
        e.stopPropagation();
        setSelectedFile(null);
        setPreviewUrl(null);
        setHasSearched(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleSearch = async () => {
        if (!selectedFile) { setErrorMsg("Please upload a suspect photo first."); return; }
        setIsSearching(true);
        setErrorMsg(null);
        const formData = new FormData();
        formData.append("file", selectedFile);

        try {
            const response = await fetch(`${BACKEND_URL}/api/investigate/search_by_image?threshold=${searchThreshold}`, {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Database search failed.");
            }
            const data = await response.json();
            setSearchResults(data.sightings || []);
            setHasSearched(true);
        } catch (err) {
            setErrorMsg(err.message);
        } finally {
            setIsSearching(false);
        }
    };

    const handleIdSearch = async () => {
        if (!searchId.trim()) { setIdSearchError("Please enter a person ID."); return; }
        setIsIdSearching(true);
        setIdSearchError(null);
        setIdSearchResults(null);
        setPersonDossier(null);
        try {
            const res = await fetch(`${BACKEND_URL}/api/investigate/person/${searchId.trim()}`);
            if (!res.ok) {
                if (res.status === 404) throw new Error("Person ID not found in database.");
                throw new Error("Search failed.");
            }
            const data = await res.json();
            setPersonDossier(data);
            setIdSearchResults(data.timeline || []);
        } catch (err) {
            setIdSearchError(err.message);
        } finally {
            setIsIdSearching(false);
        }
    };

    const switchTab = (tab) => {
        setActiveTab(tab);
        setErrorMsg(null);
        setIdSearchError(null);
    };

    return (
        <div className="max-w-4xl mx-auto py-8 px-6">
            <div className="mb-8">
                <h2 className="text-2xl font-bold text-slate-800 mb-2">Subject Investigation</h2>
                <p className="text-slate-500">Search the surveillance database by image or person ID.</p>
            </div>

            <div className="flex space-x-1 bg-slate-100 rounded-xl p-1 mb-8">
                <button
                    onClick={() => switchTab('IMG_SEARCH')}
                    className={`flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg font-medium text-sm transition-all ${activeTab === 'IMG_SEARCH' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                        }`}
                >
                    <UploadCloud className="w-4 h-4 mr-2" /> Image Search
                </button>
                <button
                    onClick={() => switchTab('ID_SEARCH')}
                    className={`flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg font-medium text-sm transition-all ${activeTab === 'ID_SEARCH' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                        }`}
                >
                    <Hash className="w-4 h-4 mr-2" /> ID Search
                </button>
            </div>

            {activeTab === 'IMG_SEARCH' && (
                <>
                    <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileSelect} />
                    <div
                        onClick={() => fileInputRef.current?.click()}
                        className={`relative border-2 border-dashed rounded-2xl bg-white p-10 flex flex-col items-center justify-center text-center cursor-pointer mb-6 transition-all ${previewUrl ? 'border-blue-400 bg-blue-50/30' : 'border-slate-300 hover:bg-slate-50'
                            }`}
                    >
                        {previewUrl ? (
                            <div className="flex flex-col items-center">
                                <div className="relative">
                                    <img src={previewUrl} alt="Preview" className="w-32 h-32 object-cover rounded-xl shadow-md border border-slate-200 mb-4" />
                                    <button onClick={clearSelection} className="absolute -top-3 -right-3 bg-red-100 text-red-600 rounded-full p-1.5 hover:bg-red-200 transition-colors shadow-sm">
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                                <p className="text-sm font-medium text-slate-700">{selectedFile.name}</p>
                            </div>
                        ) : (
                            <>
                                <UploadCloud className="w-12 h-12 text-blue-500 mb-4" />
                                <h3 className="text-lg font-semibold text-slate-700 mb-1">Drag suspect photo here</h3>
                                <p className="text-sm text-slate-400">or click to browse (JPG, PNG)</p>
                            </>
                        )}
                    </div>

                    {errorMsg && (
                        <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center">
                            <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
                            <span className="font-medium text-sm">{errorMsg}</span>
                        </div>
                    )}

                    {/* AI Strictness Level (Threshold) Slider */}
                    <div className="mb-6 p-5 bg-white border border-slate-200 rounded-xl shadow-sm">
                        <div className="flex justify-between items-center mb-3">
                            <label className="text-sm font-semibold text-slate-700 flex items-center">
                                <AlertCircle className="w-4 h-4 mr-2 text-blue-500" />
                                AI Strictness Level (Threshold)
                            </label>
                            <span className="text-sm font-bold bg-blue-50 text-blue-700 px-3 py-1 rounded-md">
                                {searchThreshold.toFixed(2)}
                            </span>
                        </div>

                        <input
                            type="range"
                            min="0.30"
                            max="0.90"
                            step="0.05"
                            value={searchThreshold}
                            onChange={(e) => setSearchThreshold(parseFloat(e.target.value))}
                            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                        />

                        <div className="mt-3 text-xs font-medium text-center">
                            {searchThreshold < 0.55 ? (
                                <span className="text-amber-600">⚠️ Loose: Might match similar looking innocent people</span>
                            ) : searchThreshold > 0.65 ? (
                                <span className="text-rose-500">⚠️ Strict: Might miss valid faces if lighting is poor</span>
                            ) : (
                                <span className="text-emerald-600">✅ Optimal "Sweet Spot" for accurate results</span>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center gap-4 mb-8">
                        <button
                            onClick={handleSearch}
                            disabled={isSearching || !selectedFile}
                            className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-2.5 rounded-lg flex items-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed w-full justify-center"
                        >
                            {isSearching ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : <Search className="w-5 h-5 mr-2" />}
                            {isSearching ? 'Analyzing Milvus Vectors...' : 'Search Surveillance Database'}
                        </button>
                    </div>

                    {isSearching && (
                        <div className="text-center py-12">
                            <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
                            <p className="text-slate-500 font-medium">Scanning 512-d vector database...</p>
                        </div>
                    )}

                    {!isSearching && hasSearched && (
                        <div className="space-y-4">
                            {searchResults.length > 0 ? (
                                <>
                                    <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center">
                                        <AlertCircle className="w-5 h-5 mr-2 text-blue-500" />
                                        Found {searchResults.length} possible sightings
                                    </h3>
                                    {searchResults.map((res, idx) => <SightingCard key={idx} data={res} />)}
                                </>
                            ) : (
                                <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
                                    <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <h3 className="text-lg font-medium text-slate-800">No Matches Found</h3>
                                    <p className="text-slate-500">The system could not locate this individual in the database.</p>
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}

            {activeTab === 'ID_SEARCH' && (
                <>
                    <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 shadow-sm">
                        <label className="block text-sm font-medium text-slate-700 mb-2">Enter Target Identification</label>
                        <div className="flex items-center gap-4">
                            <div className="flex-1 relative">
                                <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input
                                    type="text"
                                    className="w-full bg-slate-50 border border-slate-200 text-slate-700 rounded-lg pl-10 pr-4 py-2.5 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
                                    placeholder="e.g. P_17000000"
                                    value={searchId}
                                    onChange={(e) => setSearchId(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleIdSearch()}
                                />
                            </div>
                            <button
                                onClick={handleIdSearch}
                                disabled={isIdSearching || !searchId.trim()}
                                className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-2.5 rounded-lg flex items-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isIdSearching ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : <Search className="w-5 h-5 mr-2" />}
                                {isIdSearching ? 'Searching...' : 'Pull Dossier'}
                            </button>
                        </div>
                    </div>

                    {idSearchError && (
                        <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center">
                            <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
                            <span className="font-medium text-sm">{idSearchError}</span>
                        </div>
                    )}

                    {isIdSearching && (
                        <div className="text-center py-12">
                            <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
                            <p className="text-slate-500 font-medium">Pulling dossier from PostgreSQL...</p>
                        </div>
                    )}

                    {!isIdSearching && idSearchResults !== null && (
                        <div>
                            {idSearchResults.length > 0 ? (
                                <>
                                    {personDossier && (
                                        <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 shadow-sm">
                                            <h3 className="font-semibold text-slate-800 mb-4 flex items-center">
                                                <UserSearch className="w-5 h-5 mr-2 text-blue-500" />
                                                Dossier: {personDossier.person_id}
                                            </h3>
                                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                                                <div className="bg-slate-50 rounded-lg p-3">
                                                    <p className="text-xs text-slate-500 uppercase font-medium">Total Sightings</p>
                                                    <p className="text-lg font-bold text-slate-800">{personDossier.total_sightings}</p>
                                                </div>
                                                <div className="bg-slate-50 rounded-lg p-3">
                                                    <p className="text-xs text-slate-500 uppercase font-medium">First Seen</p>
                                                    <p className="text-sm font-semibold text-slate-800">{personDossier.first_seen.split(' ')[1]}</p>
                                                </div>
                                                <div className="bg-slate-50 rounded-lg p-3">
                                                    <p className="text-xs text-slate-500 uppercase font-medium">Last Seen</p>
                                                    <p className="text-sm font-semibold text-slate-800">{personDossier.last_seen.split(' ')[1]}</p>
                                                </div>
                                                <div className="bg-slate-50 rounded-lg p-3">
                                                    <p className="text-xs text-slate-500 uppercase font-medium">Locations</p>
                                                    <p className="text-sm font-semibold text-slate-800">{personDossier.locations?.length || 0} Cameras</p>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                    <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center">
                                        <Clock className="w-5 h-5 mr-2 text-blue-500" />
                                        Tracking Timeline ({idSearchResults.length} entries)
                                    </h3>
                                    <div className="space-y-3">
                                        {idSearchResults.map((entry, idx) => <TimelineCard key={idx} data={entry} />)}
                                    </div>
                                </>
                            ) : (
                                <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
                                    <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <h3 className="text-lg font-medium text-slate-800">No Records Found</h3>
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default InvestigatorView;
