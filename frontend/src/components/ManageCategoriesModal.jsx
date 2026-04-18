import React, { useState } from 'react';
import { X, Plus, Trash2, ShieldAlert, Loader2, Settings2 } from 'lucide-react';
import api from '../api';

const ManageCategoriesModal = ({ isOpen, onClose, categories, onRefresh }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [newCat, setNewCat] = useState({ name: '', color_code: '#ef4444', description: '' });

    if (!isOpen) return null;

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!newCat.name.trim()) return alert("Protocol Error: Category name required.");

        setIsLoading(true);
        try {
            await api.post('/api/watchlist/categories/add', newCat);
            setNewCat({ name: '', color_code: '#ef4444', description: '' }); // Reset form
            onRefresh(); // Refresh the parent view
        } catch (err) {
            alert("System Error: " + (err.response?.data?.detail || "Failed to create list."));
        } finally {
            setIsLoading(false);
        }
    };

    const handleDelete = async (id, name) => {
        if (window.confirm(`CRITICAL: Deleting '${name}' will remove this tag from ALL assigned subjects. Proceed?`)) {
            try {
                await api.delete(`/api/watchlist/categories/remove/${id}`);
                onRefresh();
            } catch (err) {
                alert("System Error: " + (err.response?.data?.detail || "Failed to delete list."));
            }
        }
    };

    return (
        <div className="fixed inset-0 z-[70] bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white rounded-[24px] shadow-2xl w-full max-w-lg overflow-hidden flex flex-col">

                {/* Header */}
                <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                    <div className="flex items-center">
                        <div className="w-10 h-10 bg-slate-900 rounded-xl flex items-center justify-center shadow-lg mr-4">
                            <Settings2 className="text-white w-5 h-5" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-slate-900">Manage Watchlists</h3>
                            <p className="text-xs text-slate-500 font-medium">Create or remove intelligence categories</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
                        <X className="w-5 h-5 text-slate-500" />
                    </button>
                </div>

                {/* Create New Category Form */}
                <div className="p-6 border-b border-slate-100 bg-white">
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Provision New Category</h4>
                    <form onSubmit={handleCreate} className="space-y-4">
                        <div className="flex gap-4">
                            <div className="flex-1">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">List Name</label>
                                <input
                                    type="text" required placeholder="e.g. Interpol Red Notice"
                                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-slate-900 text-sm font-semibold"
                                    value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })}
                                />
                            </div>
                            <div className="w-24">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">Tag Color</label>
                                <input
                                    type="color" required
                                    className="w-full h-[42px] p-1 bg-slate-50 border border-slate-200 rounded-xl cursor-pointer"
                                    value={newCat.color_code} onChange={(e) => setNewCat({ ...newCat, color_code: e.target.value })}
                                />
                            </div>
                        </div>
                        <div>
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1">Protocol / Rules of Engagement</label>
                            <input
                                type="text" placeholder="e.g. Detain immediately on sight."
                                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-slate-900 text-sm font-semibold"
                                value={newCat.description} onChange={(e) => setNewCat({ ...newCat, description: e.target.value })}
                            />
                        </div>
                        <button type="submit" disabled={isLoading} className="w-full py-3 bg-slate-900 text-white rounded-xl font-bold flex items-center justify-center shadow-lg hover:bg-slate-800 transition-all text-sm disabled:opacity-50">
                            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Plus className="w-4 h-4 mr-2" /> Provision Custom Watchlist</>}
                        </button>
                    </form>
                </div>

                {/* Existing Categories List */}
                <div className="p-6 bg-slate-50 overflow-y-auto max-h-[300px] custom-scrollbar">
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Active Deployments</h4>
                    <div className="space-y-3">
                        {categories.map(cat => (
                            <div key={cat.id} className="flex items-center justify-between p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
                                <div className="flex items-center">
                                    <div className="w-4 h-4 rounded-full mr-3 shadow-inner border border-black/10" style={{ backgroundColor: cat.color_code }}></div>
                                    <div>
                                        <p className="text-sm font-bold text-slate-800">{cat.name}</p>
                                        <p className="text-[10px] text-slate-500 font-medium truncate max-w-[200px]">{cat.description || "No description"}</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => handleDelete(cat.id, cat.name)}
                                    className="p-2 text-rose-500 hover:bg-rose-50 rounded-lg transition-colors border border-transparent hover:border-rose-100"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>

            </div>
        </div>
    );
};

export default ManageCategoriesModal;