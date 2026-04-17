import React, { useState, useEffect } from 'react';
import { X, Upload, Loader2, Check, User, AlertTriangle } from 'lucide-react';
import api from '../api';
import { BACKEND_URL } from '../config';

const EnrollSubjectModal = ({ isOpen, onClose, categories, onRefresh, editData = null }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [preview, setPreview] = useState(null);
    const [formData, setFormData] = useState({
        full_name: '', age: '', gender: 'Male',
        category_ids: [], risk_level: 'Low',
        description: '', occupation: '', notes: '', file: null
    });

    const isEditMode = !!editData; // Checks if we are editing

    useEffect(() => {
        if (!isOpen) {
            setFormData({ full_name: '', age: '', gender: 'Male', category_ids: [], risk_level: 'Low', description: '', occupation: '', notes: '', file: null });
            setPreview(null);
        } else if (editData) {
            // Auto-fill existing data if in edit mode
            
            // Map the category names back to IDs for the form
            const existingCatIds = editData.categories
                ?.map(catObj => categories.find(c => c.name === catObj.name)?.id)
                .filter(id => id !== undefined) || [];

            setFormData({
                full_name: editData.full_name || '',
                age: editData.age || '',
                gender: editData.gender || 'Male',
                category_ids: existingCatIds,
                risk_level: editData.risk_level || 'Low',
                description: editData.description || '',
                occupation: editData.occupation || '',
                notes: '', // Notes are usually appended, keeping blank for safety
                file: null // Don't enforce file upload on edit
            });
            setPreview(`${BACKEND_URL}${editData.image_url}`);
        }
    }, [isOpen, editData, categories]);

    if (!isOpen) return null;

    const toggleCategory = (id) => {
        setFormData(prev => ({
            ...prev,
            category_ids: prev.category_ids.includes(id)
                ? prev.category_ids.filter(catId => catId !== id)
                : [...prev.category_ids, id]
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        
        // In Edit Mode, file is optional. In Add Mode, file is required.
        if (!isEditMode && !formData.file) return alert("Security Protocol: Biometric reference image required.");
        if (formData.category_ids.length === 0) return alert("Protocol Error: Select at least one watchlist.");
        if (!formData.full_name.trim()) return alert("Protocol Error: Legal name required.");

        setIsLoading(true);
        const data = new FormData();
        
        data.append('full_name', formData.full_name);
        data.append('risk_level', formData.risk_level);
        data.append('gender', formData.gender);
        if (formData.age) data.append('age', formData.age);
        if (formData.description) data.append('description', formData.description);
        if (formData.occupation) data.append('occupation', formData.occupation);
        if (formData.notes) data.append('notes', formData.notes);
        if (formData.file) data.append('file', formData.file); // Only append if new file exists

        formData.category_ids.forEach(id => data.append('category_ids', id));

        try {
            if (isEditMode) {
                await api.put(`/api/subjects/update/${editData.subject_uuid}`, data, { headers: { 'Content-Type': 'multipart/form-data' } });
            } else {
                await api.post('/api/subjects/enroll', data, { headers: { 'Content-Type': 'multipart/form-data' } });
            }
            onRefresh();
            onClose();
        } catch (err) {
            const errorDetail = err.response?.data?.detail;
            alert("System Error:\n" + (typeof errorDetail === 'object' ? JSON.stringify(errorDetail) : errorDetail));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] bg-slate-950/90 backdrop-blur-md flex items-center justify-center p-4">
            <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
                <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                    <div className="flex items-center">
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-lg mr-4 ${isEditMode ? 'bg-amber-500 shadow-amber-500/20' : 'bg-blue-600 shadow-blue-600/20'}`}>
                            <User className="text-white w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-slate-900">{isEditMode ? "Update Subject Dossier" : "Subject Identity Enrollment"}</h3>
                            <p className="text-xs text-slate-500 font-medium">{isEditMode ? "Modify existing intelligence records" : "Create forensic dossier and assign watchlists"}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full"><X className="w-5 h-5 text-slate-500" /></button>
                </div>

                <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                    <div className="grid grid-cols-12 gap-8">
                        {/* LEFT COLUMN */}
                        <div className="col-span-12 lg:col-span-4 space-y-6">
                            <div>
                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Biometric Reference</label>
                                <div className="aspect-[3/4] border-2 border-dashed border-slate-200 rounded-[24px] flex flex-col items-center justify-center relative overflow-hidden bg-slate-50 hover:bg-slate-100 cursor-pointer group" onClick={() => document.getElementById('subjectFile').click()}>
                                    {preview ? (
                                        <>
                                            <img src={preview} className="w-full h-full object-cover" alt="Preview" />
                                            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center transition-all">
                                                <Upload className="text-white w-8 h-8 mb-2" />
                                                <span className="text-white text-xs font-bold">Update Photo</span>
                                            </div>
                                        </>
                                    ) : (
                                        <div className="text-center p-6"><Upload className="w-8 h-8 text-blue-600 mx-auto mb-2" /><p className="text-xs text-slate-500 font-bold">Upload Photo</p></div>
                                    )}
                                    <input id="subjectFile" type="file" hidden accept="image/*" onChange={(e) => {
                                        const file = e.target.files[0];
                                        if (file) { setFormData({...formData, file}); setPreview(URL.createObjectURL(file)); }
                                    }}/>
                                </div>
                                {isEditMode && <p className="text-[10px] text-amber-600 font-bold mt-2 text-center">Leave blank to keep existing photo.</p>}
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Threat Assessment</label>
                                    <div className="grid grid-cols-2 gap-2">
                                        {['Low', 'Medium', 'High', 'Extreme'].map(level => (
                                            <button key={level} type="button" onClick={() => setFormData({...formData, risk_level: level})}
                                                className={`py-2 rounded-lg text-xs font-bold border transition-all flex items-center justify-center ${formData.risk_level === level ? (level === 'Extreme' ? 'bg-red-600 text-white border-red-600' : 'bg-slate-900 text-white border-slate-900') : 'bg-white text-slate-500 border-slate-200 hover:border-slate-300'}`}>
                                                {level === 'Extreme' && formData.risk_level === level && <AlertTriangle className="w-3 h-3 mr-1" />} {level}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* RIGHT COLUMN */}
                        <div className="col-span-12 lg:col-span-8 space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="col-span-2 sm:col-span-1"><label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Full Name</label><input type="text" required className="w-full mt-1.5 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-blue-500 text-sm font-semibold" value={formData.full_name} onChange={(e) => setFormData({...formData, full_name: e.target.value})} /></div>
                                <div className="col-span-2 sm:col-span-1"><label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Occupation</label><input type="text" className="w-full mt-1.5 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-blue-500 text-sm font-semibold" value={formData.occupation} onChange={(e) => setFormData({...formData, occupation: e.target.value})} /></div>
                                <div><label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Age</label><input type="number" className="w-full mt-1.5 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl outline-none text-sm font-semibold" value={formData.age} onChange={(e) => setFormData({...formData, age: e.target.value})} /></div>
                                <div><label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Gender</label><select className="w-full mt-1.5 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-semibold outline-none" value={formData.gender} onChange={(e) => setFormData({...formData, gender: e.target.value})}><option value="Male">Male</option><option value="Female">Female</option><option value="Non-Binary">Non-Binary</option><option value="Unknown">Unknown</option></select></div>
                            </div>

                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3 block">Watchlist Assignment</label>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {categories.map(cat => (
                                        <button key={cat.id} type="button" onClick={() => toggleCategory(cat.id)} className={`flex items-center p-3 rounded-2xl border text-left ${formData.category_ids.includes(cat.id) ? 'bg-blue-50 border-blue-500 shadow-sm' : 'bg-white border-slate-200'}`}>
                                            <div className={`w-5 h-5 rounded-lg border mr-3 flex items-center justify-center ${formData.category_ids.includes(cat.id) ? 'bg-blue-600 border-blue-600' : 'bg-slate-50'}`}>{formData.category_ids.includes(cat.id) && <Check className="w-3 h-3 text-white" strokeWidth={4} />}</div>
                                            <div className="overflow-hidden"><p className="text-xs font-bold text-slate-800 truncate">{cat.name}</p></div>
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div><label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Description</label><textarea className="w-full mt-1.5 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-blue-500 text-sm font-medium min-h-[100px]" value={formData.description} onChange={(e) => setFormData({...formData, description: e.target.value})} /></div>
                        </div>
                    </div>
                </form>

                <div className="p-6 border-t border-slate-100 bg-slate-50/50 flex gap-4">
                    <button type="button" onClick={onClose} className="flex-1 py-3 border border-slate-200 rounded-2xl font-bold text-slate-600 hover:bg-white">Cancel</button>
                    <button onClick={handleSubmit} disabled={isLoading} className={`flex-[2] py-3 text-white rounded-2xl font-bold disabled:opacity-50 flex items-center justify-center shadow-xl transition-all ${isEditMode ? 'bg-amber-600 hover:bg-amber-700 shadow-amber-600/20' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-600/20'}`}>
                        {isLoading ? <><Loader2 className="w-5 h-5 animate-spin mr-2" /> Processing...</> : (isEditMode ? "Save Changes" : "Finalize Enrollment")}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default EnrollSubjectModal;