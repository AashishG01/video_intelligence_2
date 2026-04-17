import React, { useState, useEffect, useContext } from 'react';
import { UserPlus, Trash2, AlertTriangle, User, CheckSquare, Square, X, Loader2 } from 'lucide-react';
import api from '../api';
import { BACKEND_URL } from '../config'; 
import EnrollSubjectModal from '../components/EnrollSubjectModal';
import { AuthContext } from '../context/AuthContext';

const WatchlistManager = () => {
    const { user } = useContext(AuthContext);
    
    // Core Data States
    const [categories, setCategories] = useState([]);
    const [subjects, setSubjects] = useState([]);
    const [selectedCategory, setSelectedCategory] = useState('All');
    const [loading, setLoading] = useState(true);

    // Modal & Action States
    const [isEnrollModalOpen, setIsEnrollModalOpen] = useState(false);
    const [subjectToEdit, setSubjectToEdit] = useState(null); // Tracks subject being edited
    const [activeDossier, setActiveDossier] = useState(null); // Tracks subject for view pop-up
    
    // Bulk Select States
    const [isSelectMode, setIsSelectMode] = useState(false);
    const [selectedSubjects, setSelectedSubjects] = useState([]);

    const loadData = async () => {
        try {
            setLoading(true);
            const [catRes, subRes] = await Promise.all([
                api.get('/api/watchlist/categories'),
                api.get('/api/subjects/list')
            ]);
            
            // SECURITY CHECK: Ensure arrays are set to prevent "map of undefined" crashes
            setCategories(Array.isArray(catRes.data) ? catRes.data : []);
            setSubjects(Array.isArray(subRes.data) ? subRes.data : []);
            
        } catch (err) { 
            console.error("Data fetch failed:", err); 
            setCategories([]);
            setSubjects([]);
        } finally { 
            setLoading(false); 
        }
    };

    useEffect(() => { loadData(); }, []);

    // Handle toggling selection for bulk delete
    const toggleSelection = (uuid) => {
        setSelectedSubjects(prev => 
            prev.includes(uuid) ? prev.filter(id => id !== uuid) : [...prev, uuid]
        );
    };

    // Bulk Delete Execution
    const handleBulkDelete = async () => {
        if (selectedSubjects.length === 0) return;
        if (window.confirm(`CRITICAL WARNING: You are about to permanently delete ${selectedSubjects.length} intelligence records. Proceed?`)) {
            try {
                // Delete concurrently for speed
                await Promise.all(selectedSubjects.map(uuid => api.delete(`/api/subjects/remove/${uuid}`)));
                setSelectedSubjects([]);
                setIsSelectMode(false);
                loadData();
            } catch (err) {
                alert("Bulk deletion encountered an error: " + err.message);
            }
        }
    };

    // Filter logic for multi-category arrays
    const filteredSubjects = subjects.filter(s => {
        if (selectedCategory === 'All') return true;
        return s.categories && s.categories.some(c => c.name === selectedCategory);
    });

    return (
        <div className="p-8 bg-slate-50 min-h-screen relative">
            
            {/* --- SMART MODAL (Handles both Enroll and Edit) --- */}
            <EnrollSubjectModal 
                isOpen={isEnrollModalOpen || !!subjectToEdit} 
                onClose={() => { setIsEnrollModalOpen(false); setSubjectToEdit(null); }} 
                categories={categories} 
                onRefresh={loadData}
                editData={subjectToEdit} 
            />

            {/* --- DOSSIER POP-UP MODAL --- */}
            {activeDossier && (
                <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
                    <div className="bg-white rounded-[24px] shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col md:flex-row relative">
                        
                        <div className="w-full md:w-2/5 h-64 md:h-auto bg-slate-200 relative">
                            <img 
                                src={`${BACKEND_URL}${activeDossier.image_url}`} 
                                className="w-full h-full object-cover" 
                                alt={activeDossier.full_name} 
                                onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/300x400?text=NO+IMAGE"; }}
                            />
                            <div className="absolute top-4 left-4 flex flex-col gap-1">
                                {activeDossier.categories?.map((cat, idx) => (
                                    <span key={idx} className="px-2 py-1 rounded text-[9px] font-black uppercase text-white shadow-md" style={{ backgroundColor: cat.color }}>
                                        {cat.name}
                                    </span>
                                ))}
                            </div>
                        </div>
                        
                        <div className="w-full md:w-3/5 p-8 flex flex-col relative">
                            {/* Close Button */}
                            <button onClick={() => setActiveDossier(null)} className="absolute top-4 right-4 p-2 text-slate-400 hover:bg-slate-100 rounded-full transition-colors">
                                <X className="w-5 h-5"/>
                            </button>
                            
                            {/* Admin Edit Button */}
                            {user?.role === 'admin' && (
                                <button 
                                    onClick={() => { setSubjectToEdit(activeDossier); setActiveDossier(null); }} 
                                    className="absolute top-4 right-14 px-3 py-1.5 text-xs font-bold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors border border-amber-200"
                                >
                                    Edit Dossier
                                </button>
                            )}
                            
                            <h2 className="text-2xl font-black text-slate-900 pr-24">{activeDossier.full_name}</h2>
                            <p className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">
                                {activeDossier.gender} • {activeDossier.age ? `${activeDossier.age} YRS` : 'UNKNOWN AGE'}
                            </p>
                            
                            <div className={`inline-flex items-center self-start px-3 py-1 rounded-md text-xs font-black uppercase mb-6 ${
                                activeDossier.risk_level === 'Extreme' ? 'bg-red-100 text-red-700' : 
                                activeDossier.risk_level === 'High' ? 'bg-orange-100 text-orange-700' : 'bg-slate-100 text-slate-700'
                            }`}>
                                <AlertTriangle className="w-3 h-3 mr-2" strokeWidth={3} /> {activeDossier.risk_level} RISK
                            </div>

                            <div className="flex-1">
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Occupation / Alias</h4>
                                <p className="text-sm text-slate-800 font-medium mb-4">{activeDossier.occupation || 'Unknown'}</p>

                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Tactical Notes</h4>
                                <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-100 min-h-[80px] max-h-[150px] overflow-y-auto custom-scrollbar">
                                    {activeDossier.description || "No tactical notes provided."}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* --- HEADER CONTROLS --- */}
            <div className="flex justify-between items-end mb-8">
                <div>
                    <h2 className="text-3xl font-black text-slate-900 tracking-tight flex items-center">
                        <User className="w-8 h-8 mr-3 text-blue-600" />
                        INTEL WATCHLIST
                    </h2>
                    <p className="text-slate-500 font-medium mt-1">Categorized threat management and identity tracking.</p>
                </div>
                
                {/* Admin Actions */}
                {user?.role === 'admin' && (
                    <div className="flex items-center gap-3">
                        {isSelectMode ? (
                            <>
                                <button 
                                    onClick={() => { setIsSelectMode(false); setSelectedSubjects([]); }} 
                                    className="bg-slate-200 text-slate-700 px-4 py-2.5 rounded-xl font-bold hover:bg-slate-300 transition-all text-sm"
                                >
                                    Cancel
                                </button>
                                <button 
                                    onClick={handleBulkDelete}
                                    disabled={selectedSubjects.length === 0}
                                    className="bg-red-600 text-white px-5 py-2.5 rounded-xl flex items-center font-bold shadow-lg shadow-red-600/20 hover:bg-red-700 disabled:opacity-50 transition-all text-sm"
                                >
                                    <Trash2 className="w-4 h-4 mr-2" /> 
                                    Delete Selected ({selectedSubjects.length})
                                </button>
                            </>
                        ) : (
                            <button 
                                onClick={() => setIsSelectMode(true)} 
                                className="bg-slate-800 text-white px-5 py-2.5 rounded-xl flex items-center font-bold shadow-lg hover:bg-slate-900 transition-all text-sm"
                            >
                                <CheckSquare className="w-4 h-4 mr-2" /> 
                                Select Targets
                            </button>
                        )}

                        <div className="w-px h-8 bg-slate-300 mx-1"></div>

                        <button 
                            onClick={() => setIsEnrollModalOpen(true)} 
                            className="bg-blue-600 text-white px-5 py-2.5 rounded-xl flex items-center font-bold shadow-lg shadow-blue-600/20 hover:bg-blue-700 transition-all text-sm"
                        >
                            <UserPlus className="w-4 h-4 mr-2" /> 
                            Enroll Target
                        </button>
                    </div>
                )}
            </div>

            {/* --- CATEGORY FILTER PILLS --- */}
            <div className="flex space-x-2 mb-8 overflow-x-auto pb-2 custom-scrollbar">
                <button 
                    onClick={() => setSelectedCategory('All')} 
                    className={`px-5 py-2 rounded-lg text-sm font-bold transition-all whitespace-nowrap ${
                        selectedCategory === 'All' ? 'bg-slate-900 text-white' : 'bg-white text-slate-500 border border-slate-200 hover:bg-slate-50'
                    }`}
                >
                    All ({subjects.length})
                </button>
                {categories.map(cat => {
                    const count = subjects.filter(s => s.categories?.some(c => c.name === cat.name)).length;
                    const isSelected = selectedCategory === cat.name;
                    return (
                        <button 
                            key={cat.id} 
                            onClick={() => setSelectedCategory(cat.name)}
                            className={`px-5 py-2 rounded-lg text-sm font-bold border transition-all whitespace-nowrap ${
                                isSelected ? 'shadow-md text-white' : 'bg-white text-slate-500 hover:bg-slate-50'
                            }`}
                            style={{ backgroundColor: isSelected ? cat.color_code : 'white', borderColor: cat.color_code }}
                        >
                            {cat.name} ({count})
                        </button>
                    );
                })}
            </div>

            {/* --- COMPACT SUBJECTS GRID --- */}
            {loading ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                    <Loader2 className="w-8 h-8 animate-spin mb-4 text-blue-600" />
                    <span className="font-bold uppercase tracking-widest text-xs">Decrypting Database...</span>
                </div>
            ) : filteredSubjects.length === 0 ? (
                <div className="text-center py-20 bg-white border border-slate-200 rounded-3xl shadow-sm">
                    <User className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                    <h3 className="text-lg font-bold text-slate-700">No Subjects Found</h3>
                    <p className="text-sm text-slate-500">The current category filter returned zero results.</p>
                </div>
            ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-5">
                    {filteredSubjects.map(subject => {
                        const isSelected = selectedSubjects.includes(subject.subject_uuid);
                        
                        return (
                            <div 
                                key={subject.id} 
                                onClick={() => {
                                    if (isSelectMode) toggleSelection(subject.subject_uuid);
                                    else setActiveDossier(subject);
                                }}
                                className={`group cursor-pointer bg-white border rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-all ${
                                    isSelected ? 'border-blue-500 ring-2 ring-blue-500/50 scale-[0.98]' : 'border-slate-200 hover:border-slate-300'
                                }`}
                            >
                                {/* Small Square Image Container */}
                                <div className="relative aspect-square bg-slate-200">
                                    <img 
                                        src={`${BACKEND_URL}${subject.image_url}`} 
                                        className={`w-full h-full object-cover transition-all duration-300 ${isSelectMode && !isSelected ? 'grayscale opacity-60' : 'group-hover:scale-105'}`} 
                                        alt={subject.full_name} 
                                        onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/200x200?text=NO+IMAGE"; }}
                                    />
                                    
                                    {/* Selection Overlay */}
                                    {isSelectMode && (
                                        <div className="absolute top-2 right-2 z-10">
                                            {isSelected ? (
                                                <div className="bg-blue-600 rounded-md p-1 shadow-md"><CheckSquare className="w-5 h-5 text-white" /></div>
                                            ) : (
                                                <div className="bg-white/90 rounded-md p-1 shadow-sm"><Square className="w-5 h-5 text-slate-400" /></div>
                                            )}
                                        </div>
                                    )}

                                    {/* Risk Indicator Dot */}
                                    {!isSelectMode && subject.risk_level === 'Extreme' && (
                                        <div className="absolute bottom-2 right-2 w-3 h-3 bg-red-500 rounded-full border-2 border-white shadow-sm animate-pulse z-10"></div>
                                    )}
                                </div>
                                
                                {/* Compact ID Plate */}
                                <div className="p-3 text-center bg-white z-20 relative">
                                    <h3 className="font-bold text-slate-800 text-sm truncate">{subject.full_name}</h3>
                                    <p className="text-[10px] text-slate-400 font-bold uppercase truncate mt-0.5">
                                        {subject.categories && subject.categories.length > 0 ? subject.categories[0].name : 'Uncategorized'}
                                        {subject.categories && subject.categories.length > 1 && ' +'}
                                    </p>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default WatchlistManager;