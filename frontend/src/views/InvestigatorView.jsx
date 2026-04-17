import React, { useState, useRef, useEffect } from 'react';
import {
    UserSearch, UploadCloud, Search, Clock, AlertCircle, Loader2, X, Hash,
    Settings2, Crop as CropIcon, SlidersHorizontal, Image as ImageIcon
} from 'lucide-react';
import ReactCrop, { centerCrop, makeAspectCrop } from 'react-image-crop';
import 'react-image-crop/dist/ReactCrop.css';
import { BACKEND_URL } from '../config';
import SightingCard from '../components/SightingCard';
import TimelineCard from '../components/TimelineCard';

// ============================================================
// 🎨 Forensic Studio Modal (Cropping + Sharpness SVG Math)
// ============================================================
const ImageEditorModal = ({ file, onCancel, onSave }) => {
    const [previewUrl, setPreviewUrl] = useState(null);
    const imgRef = useRef(null);
    
    // Crop State
    const [crop, setCrop] = useState();
    const [completedCrop, setCompletedCrop] = useState(null);
    
    // Tuning State
    const [settings, setSettings] = useState({
        brightness: 100,
        contrast: 100,
        smoothness: 100, // 100 = Original. Lower = blur
        sharpness: 0,    // NEW: 0 = Original. 100 = Max Sharp
    });

    useEffect(() => {
        if (file) setPreviewUrl(URL.createObjectURL(file));
        return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }
    }, [file]);

    const onImageLoad = (e) => {
        const { naturalWidth: width, naturalHeight: height } = e.currentTarget;
        const initialCrop = centerCrop(
            makeAspectCrop({ unit: '%', width: 50 }, 1, width, height),
            width,
            height
        );
        setCrop(initialCrop);
    };

    const handleChange = (key, value) => {
        setSettings(prev => ({ ...prev, [key]: value }));
    };

    const handleInputBlur = (key, value, min, max) => {
        let numValue = parseInt(value, 10);
        if (isNaN(numValue)) numValue = parseInt(settings[key], 10);
        numValue = Math.max(min, Math.min(max, numValue));
        handleChange(key, numValue);
    };

    // 🚀 THE MAGIC: Bake the crop, SVG Sharpen Matrix, and filters into a NEW Image
    const getBaledImage = async () => {
        const image = imgRef.current;
        if (!image || !completedCrop?.width || !completedCrop?.height) return null;

        const canvas = document.createElement('canvas');
        const scaleX = image.naturalWidth / image.width;
        const scaleY = image.naturalHeight / image.height;

        canvas.width = completedCrop.width * scaleX;
        canvas.height = completedCrop.height * scaleY;
        const ctx = canvas.getContext('2d');

        // Apply filters including the custom SVG Sharpen URL
        const blur = (100 - settings.smoothness) / 10;
        ctx.filter = `url(#dynamic-sharpen) brightness(${settings.brightness}%) contrast(${settings.contrast}%) blur(${blur}px)`;

        // Draw ONLY the cropped area
        ctx.drawImage(
            image,
            completedCrop.x * scaleX,
            completedCrop.y * scaleY,
            completedCrop.width * scaleX,
            completedCrop.height * scaleY,
            0,
            0,
            canvas.width,
            canvas.height
        );

        return new Promise((resolve) => {
            canvas.toBlob((blob) => {
                if (!blob) { resolve(null); return; }
                const croppedFile = new File([blob], "forensic_target.jpg", { type: "image/jpeg" });
                resolve({ file: croppedFile, url: URL.createObjectURL(blob) });
            }, 'image/jpeg', 0.95);
        });
    };

    const handleApply = async () => {
        const bakedData = await getBaledImage();
        if (bakedData) {
            onSave(bakedData.file, bakedData.url);
        } else {
            alert("Please draw a crop box first.");
        }
    };

    // Calculate dynamic values for the Convolution Matrix (Sharpen Math)
    // s = sharpness intensity (0 to 1)
    const s = settings.sharpness / 100;
    const centerMatrix = 1 + (4 * s);
    const edgeMatrix = -s;

    return (
        <div className="fixed inset-0 z-50 bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4">
            
            {/* 🧠 INVISIBLE SVG FILTER FOR REAL-TIME SHARPNESS */}
            <svg style={{ position: 'absolute', width: 0, height: 0 }}>
                <filter id="dynamic-sharpen">
                    <feConvolveMatrix 
                        order="3 3" 
                        preserveAlpha="true" 
                        kernelMatrix={`0 ${edgeMatrix} 0 ${edgeMatrix} ${centerMatrix} ${edgeMatrix} 0 ${edgeMatrix} 0`} 
                    />
                </filter>
            </svg>

            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl flex overflow-hidden h-[90vh]">
                
                {/* Left Side: React Crop Canvas */}
                <div className="flex-1 bg-slate-900 flex items-center justify-center relative overflow-hidden border-r border-slate-200 p-4">
                    <div className="absolute top-4 left-4 z-10 bg-white/90 px-3 py-1.5 rounded-lg text-xs font-bold text-slate-700 shadow-sm flex items-center">
                        <CropIcon className="w-4 h-4 mr-2 text-blue-500"/>
                        Draw box to isolate face
                    </div>

                    {previewUrl && (
                        <ReactCrop
                            crop={crop}
                            onChange={(c) => setCrop(c)}
                            onComplete={(c) => setCompletedCrop(c)}
                            className="max-h-full shadow-2xl"
                        >
                            <img
                                ref={imgRef}
                                src={previewUrl}
                                onLoad={onImageLoad}
                                alt="Crop Preview"
                                style={{
                                    maxHeight: '80vh',
                                    // Applying the SVG math filter alongside standard filters!
                                    filter: `url(#dynamic-sharpen) brightness(${settings.brightness}%) contrast(${settings.contrast}%) blur(${(100 - settings.smoothness)/10}px)`,
                                }}
                            />
                        </ReactCrop>
                    )}
                </div>

                {/* Right Side: Tuning Control Panel */}
                <div className="w-96 bg-white flex flex-col h-full">
                    <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                        <h3 className="font-bold text-slate-800 flex items-center">
                            <Settings2 className="w-5 h-5 mr-2 text-blue-600" />
                            Image Tuning
                        </h3>
                        <button onClick={onCancel} className="p-1 hover:bg-slate-200 rounded-md transition-colors text-slate-500">
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-5 space-y-6">
                        
                        {/* Brightness */}
                        <div>
                            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                                <span className="flex items-center"><SlidersHorizontal className="w-4 h-4 mr-1"/> Brightness</span>
                                <input type="text" value={settings.brightness} onChange={(e) => handleChange('brightness', e.target.value)} onBlur={(e) => handleInputBlur('brightness', e.target.value, 50, 200)}
                                    className="w-16 h-7 text-center text-sm font-bold bg-slate-50 border border-slate-200 rounded outline-none focus:border-blue-500"
                                />
                            </label>
                            <input type="range" min="50" max="200" step="1" value={settings.brightness} onChange={(e) => handleChange('brightness', parseInt(e.target.value))} className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600" />
                        </div>

                        {/* Contrast */}
                        <div>
                            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                                <span className="flex items-center"><SlidersHorizontal className="w-4 h-4 mr-1"/> Contrast</span>
                                <input type="text" value={settings.contrast} onChange={(e) => handleChange('contrast', e.target.value)} onBlur={(e) => handleInputBlur('contrast', e.target.value, 50, 200)}
                                    className="w-16 h-7 text-center text-sm font-bold bg-slate-50 border border-slate-200 rounded outline-none focus:border-blue-500"
                                />
                            </label>
                            <input type="range" min="50" max="200" step="1" value={settings.contrast} onChange={(e) => handleChange('contrast', parseInt(e.target.value))} className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600" />
                        </div>

                        {/* NEW: Sharpness Control */}
                        <div>
                            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                                <span className="flex items-center"><SlidersHorizontal className="w-4 h-4 mr-1 text-indigo-500"/> Sharpness</span>
                                <input type="text" value={settings.sharpness} onChange={(e) => handleChange('sharpness', e.target.value)} onBlur={(e) => handleInputBlur('sharpness', e.target.value, 0, 100)}
                                    className="w-16 h-7 text-center text-sm font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 rounded outline-none focus:border-indigo-500"
                                />
                            </label>
                            <input type="range" min="0" max="100" step="1" value={settings.sharpness} onChange={(e) => handleChange('sharpness', parseInt(e.target.value))} className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600" />
                            <div className="flex justify-between text-xs font-medium mt-1">
                                <span className="text-slate-400">Original</span>
                                <span className="text-indigo-600">Max Crisp</span>
                            </div>
                        </div>

                        {/* Smoothness */}
                        <div>
                            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                                <span className="flex items-center"><SlidersHorizontal className="w-4 h-4 mr-1 text-emerald-500"/> Smoothness (Denoise)</span>
                                <input type="text" value={settings.smoothness} onChange={(e) => handleChange('smoothness', e.target.value)} onBlur={(e) => handleInputBlur('smoothness', e.target.value, 0, 100)}
                                    className="w-16 h-7 text-center text-sm font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 rounded outline-none focus:border-emerald-500"
                                />
                            </label>
                            <input type="range" min="0" max="100" step="1" value={settings.smoothness} onChange={(e) => handleChange('smoothness', parseInt(e.target.value))} className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-600" />
                            <div className="flex justify-between text-xs font-medium mt-1">
                                <span className="text-emerald-600">Max Blur</span>
                                <span className="text-slate-400">Original</span>
                            </div>
                        </div>

                    </div>

                    <div className="p-4 border-t border-slate-100 bg-slate-50 grid grid-cols-2 gap-3">
                        <button onClick={onCancel} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg font-medium hover:bg-slate-50 transition-colors">
                            Cancel
                        </button>
                        <button onClick={handleApply} className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors shadow-sm shadow-blue-600/30">
                            Crop & Apply
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

// ============================================================
// MAIN INVESTIGATOR VIEW
// ============================================================
const InvestigatorView = () => {
    const [activeTab, setActiveTab] = useState('IMG_SEARCH');
    const [isSearching, setIsSearching] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);
    const [searchResults, setSearchResults] = useState([]);
    
    // File handling
    const [originalFile, setOriginalFile] = useState(null); 
    const [processedFile, setProcessedFile] = useState(null); 
    const [previewUrl, setPreviewUrl] = useState(null);
    const [errorMsg, setErrorMsg] = useState(null);
    const fileInputRef = useRef(null);

    const [isEditorOpen, setIsEditorOpen] = useState(false);
    const [searchThreshold, setSearchThreshold] = useState(0.60);

    const [searchId, setSearchId] = useState("");
    const [isIdSearching, setIsIdSearching] = useState(false);
    const [idSearchResults, setIdSearchResults] = useState(null);
    const [idSearchError, setIdSearchError] = useState(null);
    const [personDossier, setPersonDossier] = useState(null);

    const handleFileSelect = (e) => {
        const file = e.target.files[0];
        if (file) {
            setOriginalFile(file);
            setHasSearched(false);
            setSearchResults([]);
            setErrorMsg(null);
            setIsEditorOpen(true);
        }
    };

    const handleEditorSave = (newCroppedFile, newPreviewUrl) => {
        setProcessedFile(newCroppedFile); 
        setPreviewUrl(newPreviewUrl);
        setIsEditorOpen(false);
    };

    const clearSelection = (e) => {
        if (e && e.stopPropagation) e.stopPropagation();
        setOriginalFile(null);
        setProcessedFile(null);
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
        setHasSearched(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleSearch = async () => {
        if (!processedFile) { setErrorMsg("Please enhance and crop a photo first."); return; }
        setIsSearching(true);
        setErrorMsg(null);
        
        const formData = new FormData();
        formData.append("file", processedFile); 

        try {
            const response = await fetch(`${BACKEND_URL}/api/investigate/search_by_image?threshold=${searchThreshold}`, {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) throw new Error("Database search failed.");
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
            if (!res.ok) throw new Error("Person ID not found.");
            const data = await res.json();
            setPersonDossier(data);
            setIdSearchResults(data.timeline || []);
        } catch (err) {
            setIdSearchError(err.message);
        } finally {
            setIsIdSearching(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto py-8 px-6">
            
            {isEditorOpen && originalFile && (
                <ImageEditorModal 
                    file={originalFile} 
                    onCancel={() => { setIsEditorOpen(false); if (!previewUrl) clearSelection(); }} 
                    onSave={handleEditorSave} 
                />
            )}

            <div className="mb-8">
                <h2 className="text-2xl font-bold text-slate-800 mb-2">Subject Investigation</h2>
                <p className="text-slate-500">Search the database using cropped forensic images.</p>
            </div>

            <div className="flex space-x-1 bg-slate-100 rounded-xl p-1 mb-8">
                <button onClick={() => setActiveTab('IMG_SEARCH')} className={`flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg font-medium text-sm transition-all ${activeTab === 'IMG_SEARCH' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500'}`}>
                    <UploadCloud className="w-4 h-4 mr-2" /> Forensic Image Search
                </button>
                <button onClick={() => setActiveTab('ID_SEARCH')} className={`flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg font-medium text-sm transition-all ${activeTab === 'ID_SEARCH' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500'}`}>
                    <Hash className="w-4 h-4 mr-2" /> Dossier Search
                </button>
            </div>

            {activeTab === 'IMG_SEARCH' && (
                <>
                    <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileSelect} />
                    <div onClick={() => !previewUrl && fileInputRef.current?.click()} className={`relative border-2 border-dashed rounded-2xl bg-white p-10 flex flex-col items-center justify-center text-center mb-6 transition-all shadow-inner ${previewUrl ? 'border-blue-400 bg-blue-50/30' : 'border-slate-300 hover:bg-slate-50 cursor-pointer'}`}>
                        {previewUrl ? (
                            <div className="flex flex-col items-center w-full">
                                <div className="relative flex justify-center w-48 h-48 bg-slate-900 p-2 rounded-xl shadow border border-slate-700 mb-3 overflow-hidden">
                                    <img src={previewUrl} alt="Cropped Output" className="max-w-full max-h-full object-contain" />
                                    <button onClick={clearSelection} className="absolute top-1 right-1 bg-red-600 text-white rounded-full p-1.5 hover:bg-red-700 transition-colors z-10">
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                                <div className="flex gap-2 text-xs">
                                    <button onClick={() => setIsEditorOpen(true)} className="font-bold text-blue-600 bg-blue-50 px-3 py-1.5 rounded hover:bg-blue-100 transition-colors flex items-center">
                                        <Settings2 className="w-3.5 h-3.5 mr-1.5"/> Re-Crop / Tune
                                    </button>
                                    <span className="font-medium text-slate-500 bg-slate-100 px-3 py-1.5 rounded border border-slate-200">
                                        {(processedFile.size / 1024).toFixed(1)} KB (Cropped)
                                    </span>
                                </div>
                            </div>
                        ) : (
                            <>
                                <UploadCloud className="w-12 h-12 text-blue-500 mb-4" />
                                <h3 className="text-lg font-semibold text-slate-700 mb-1">Upload & Crop Suspect Photo</h3>
                                <p className="text-sm text-slate-400">Drops into Forensic Studio to isolate the face</p>
                            </>
                        )}
                    </div>

                    {errorMsg && (
                        <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center shadow-sm">
                            <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
                            <span className="font-medium text-sm">{errorMsg}</span>
                        </div>
                    )}

                    <div className="mb-6 p-5 bg-white border border-slate-200 rounded-xl shadow-sm">
                        <div className="flex justify-between items-center mb-3 gap-3">
                            <label className="text-sm font-semibold text-slate-700 flex items-center">
                                <AlertCircle className="w-4 h-4 mr-2 text-blue-500" />
                                AI Strictness Level
                            </label>
                            <input 
                                type="text" 
                                value={searchThreshold.toFixed(2)} 
                                onChange={(e) => setSearchThreshold(isNaN(parseFloat(e.target.value)) ? e.target.value : parseFloat(e.target.value))}
                                onBlur={(e) => setSearchThreshold(Math.max(0.30, Math.min(0.90, isNaN(parseFloat(e.target.value)) ? 0.60 : parseFloat(e.target.value))))}
                                className="w-16 h-8 text-center text-sm font-bold bg-blue-50 text-blue-700 border border-blue-200 rounded-md outline-none"
                            />
                        </div>
                        <input type="range" min="0.30" max="0.90" step="0.05" value={searchThreshold} onChange={(e) => setSearchThreshold(parseFloat(e.target.value))} className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600" />
                    </div>

                    <button onClick={handleSearch} disabled={isSearching || !processedFile} className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-3 rounded-xl flex items-center justify-center transition-colors disabled:opacity-50 w-full shadow-lg active:scale-[0.98]">
                        {isSearching ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : <Search className="w-5 h-5 mr-2" />}
                        {isSearching ? 'Analyzing Milvus Vectors...' : 'Search Surveillance Database'}
                    </button>

                    {!isSearching && hasSearched && (
                        <div className="mt-8 space-y-4">
                            {searchResults.length > 0 ? (
                                <>
                                    <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center">
                                        <AlertCircle className="w-5 h-5 mr-2 text-blue-500" /> Found {searchResults.length} sightings
                                    </h3>
                                    {searchResults.map((res, idx) => <SightingCard key={idx} data={res} />)}
                                </>
                            ) : (
                                <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
                                    <h3 className="text-lg font-medium text-slate-800">No Matches Found</h3>
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}

            {activeTab === 'ID_SEARCH' && (
                <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 shadow-sm">
                    <label className="block text-sm font-medium text-slate-700 mb-2">Enter Target Identification</label>
                    <div className="flex gap-4">
                        <input type="text" className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-4 outline-none focus:border-blue-500" placeholder="e.g. P_17000000" value={searchId} onChange={(e) => setSearchId(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleIdSearch()}/>
                        <button onClick={handleIdSearch} disabled={isIdSearching || !searchId.trim()} className="bg-blue-600 text-white px-8 py-2.5 rounded-lg disabled:opacity-50">
                            {isIdSearching ? 'Searching...' : 'Pull Dossier'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default InvestigatorView;