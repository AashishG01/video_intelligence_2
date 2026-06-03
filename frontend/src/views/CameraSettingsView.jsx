import React, { useState, useEffect } from 'react';
import { Video, Trash2, Edit, Plus, MapPin, Activity, Tag, Link as LinkIcon, Loader2 } from 'lucide-react';
import api from '../api';

const CameraSettingsView = () => {
    const [cameras, setCameras] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isEditing, setIsEditing] = useState(false);

    // Form State
    const [formData, setFormData] = useState({
        camera_id: '',
        camera_name: '',
        place: '',
        rtsp_url: '',
        fps_limit: 1
    });

    const fetchCameras = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/cameras');
            setCameras(response.data || []);
        } catch (error) {
            console.error("Failed to fetch cameras:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCameras();
    }, []);

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            if (isEditing) {
                await api.put(`/api/cameras/edit/${formData.camera_id}`, formData);
            } else {
                await api.post('/api/cameras/add', formData);
            }
            // Reset form
            setFormData({
                camera_id: '',
                camera_name: '',
                place: '',
                rtsp_url: '',
                fps_limit: 1
            });
            setIsEditing(false);
            fetchCameras();
        } catch (error) {
            console.error("Failed to save camera:", error);
            alert(error.response?.data?.detail || "Failed to save camera");
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleEditClick = (cam) => {
        setFormData({
            camera_id: cam.camera_id,
            camera_name: cam.camera_name,
            place: cam.place || '',
            rtsp_url: cam.rtsp_url,
            fps_limit: cam.fps_limit
        });
        setIsEditing(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleCancelEdit = () => {
        setFormData({ camera_id: '', camera_name: '', place: '', rtsp_url: '', fps_limit: 1 });
        setIsEditing(false);
    };

    const handleDeleteCamera = async (cameraId) => {
        if (!window.confirm(`Are you sure you want to permanently delete camera ${cameraId}?`)) {
            return;
        }
        
        try {
            await api.delete(`/api/cameras/remove/${cameraId}`);
            fetchCameras();
        } catch (error) {
            console.error("Failed to delete camera:", error);
            alert("Failed to delete camera");
        }
    };

    return (
        <div className="p-8 pb-32 max-w-7xl mx-auto space-y-8 animate-in fade-in zoom-in-95 duration-500">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-4xl font-black text-slate-900 tracking-tight flex items-center">
                        <Video className="w-10 h-10 mr-4 text-blue-600" />
                        Camera Management
                    </h1>
                    <p className="text-slate-500 mt-2 text-lg">
                        Dynamically enroll or remove RTSP streams from the surveillance network.
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Add Camera Form */}
                <div className="lg:col-span-1">
                    <div className="bg-white p-6 rounded-[24px] shadow-xl border border-slate-100">
                        <h2 className="text-xl font-bold text-slate-800 flex items-center mb-6">
                            {isEditing ? <Edit className="w-5 h-5 mr-2 text-blue-600" /> : <Plus className="w-5 h-5 mr-2 text-green-600" />}
                            {isEditing ? 'Edit Camera Stream' : 'Enroll New Stream'}
                        </h2>
                        
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Camera ID (Unique)</label>
                                <div className="relative">
                                    <Tag className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                                    <input 
                                        type="text" name="camera_id" required
                                        value={formData.camera_id} onChange={handleInputChange}
                                        disabled={isEditing}
                                        placeholder="e.g. cam_south_01"
                                        className={`w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all ${isEditing ? 'opacity-50 cursor-not-allowed' : ''}`}
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Friendly Name</label>
                                <div className="relative">
                                    <Video className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                                    <input 
                                        type="text" name="camera_name" required
                                        value={formData.camera_name} onChange={handleInputChange}
                                        placeholder="e.g. South Gate Main Entrance"
                                        className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Place / Location</label>
                                <div className="relative">
                                    <MapPin className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                                    <input 
                                        type="text" name="place"
                                        value={formData.place} onChange={handleInputChange}
                                        placeholder="e.g. Sector 54 Warehouse"
                                        className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">RTSP Stream URL</label>
                                <div className="relative">
                                    <LinkIcon className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                                    <input 
                                        type="text" name="rtsp_url" required
                                        value={formData.rtsp_url} onChange={handleInputChange}
                                        placeholder="rtsp://admin:pass@ip:554/live"
                                        className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">AI Processing FPS Limit</label>
                                <div className="relative">
                                    <Activity className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                                    <input 
                                        type="number" name="fps_limit" min="1" max="30" required
                                        value={formData.fps_limit} onChange={handleInputChange}
                                        className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                                    />
                                </div>
                                <p className="text-xs text-slate-400 mt-1">Lower FPS saves AI resources. Recommended: 1</p>
                            </div>

                            <div className="flex gap-2 pt-2">
                                <button 
                                    type="submit" 
                                    disabled={isSubmitting}
                                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl shadow-lg shadow-blue-500/30 transition-all flex justify-center items-center"
                                >
                                    {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : (isEditing ? 'Update Camera' : 'Enroll Camera')}
                                </button>
                                {isEditing && (
                                    <button 
                                        type="button" 
                                        onClick={handleCancelEdit}
                                        className="px-4 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl transition-all"
                                    >
                                        Cancel
                                    </button>
                                )}
                            </div>
                        </form>
                    </div>
                </div>

                {/* Active Cameras Grid */}
                <div className="lg:col-span-2">
                    <h2 className="text-2xl font-bold text-slate-800 flex items-center mb-6">
                        <Activity className="w-6 h-6 mr-3 text-blue-500" />
                        Active Camera Nodes ({cameras.length})
                    </h2>
                    
                    {loading ? (
                        <div className="flex justify-center items-center h-64 bg-slate-100 rounded-3xl border border-slate-200 border-dashed">
                            <Loader2 className="w-10 h-10 text-slate-300 animate-spin" />
                        </div>
                    ) : cameras.length === 0 ? (
                        <div className="flex flex-col justify-center items-center h-64 bg-slate-100 rounded-3xl border border-slate-200 border-dashed text-slate-400">
                            <Video className="w-16 h-16 mb-4 opacity-50" />
                            <p className="font-semibold text-lg">No Active Cameras</p>
                            <p className="text-sm">Enroll a new stream to begin surveillance.</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {cameras.map((cam) => (
                                <div key={cam.id} className="bg-white rounded-2xl p-5 border border-slate-200 shadow-md hover:shadow-xl transition-all group relative overflow-hidden">
                                    <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
                                    <div className="flex justify-between items-start">
                                        <div>
                                            <h3 className="text-lg font-bold text-slate-800 line-clamp-1">{cam.camera_name}</h3>
                                            <div className="flex items-center text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-1 rounded-md mt-1 w-max">
                                                {cam.camera_id}
                                            </div>
                                        </div>
                                        <div className="flex gap-1">
                                            <button 
                                                onClick={() => handleEditClick(cam)}
                                                className="text-slate-400 hover:text-blue-600 hover:bg-blue-50 p-2 rounded-lg transition-colors"
                                                title="Edit Camera"
                                            >
                                                <Edit className="w-5 h-5" />
                                            </button>
                                            <button 
                                                onClick={() => handleDeleteCamera(cam.camera_id)}
                                                className="text-slate-400 hover:text-red-600 hover:bg-red-50 p-2 rounded-lg transition-colors"
                                                title="Delete Camera"
                                            >
                                                <Trash2 className="w-5 h-5" />
                                            </button>
                                        </div>
                                    </div>

                                    <div className="mt-4 space-y-2 text-sm text-slate-600">
                                        {cam.place && (
                                            <div className="flex items-center">
                                                <MapPin className="w-4 h-4 mr-2 text-slate-400 shrink-0" />
                                                <span className="truncate" title={cam.place}>{cam.place}</span>
                                            </div>
                                        )}
                                        <div className="flex items-center">
                                            <LinkIcon className="w-4 h-4 mr-2 text-slate-400 shrink-0" />
                                            <span className="truncate font-mono text-xs" title={cam.rtsp_url}>{cam.rtsp_url}</span>
                                        </div>
                                        <div className="flex items-center">
                                            <Activity className="w-4 h-4 mr-2 text-slate-400 shrink-0" />
                                            <span>Processing at <strong>{cam.fps_limit} FPS</strong></span>
                                        </div>
                                    </div>
                                    
                                    {cam.is_active ? (
                                        <div className="absolute bottom-4 right-4 flex items-center text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-full border border-emerald-100">
                                            <div className="w-2 h-2 bg-emerald-500 rounded-full mr-1 animate-pulse"></div>
                                            ONLINE
                                        </div>
                                    ) : (
                                        <div className="absolute bottom-4 right-4 flex items-center text-xs font-bold text-red-600 bg-red-50 px-2 py-1 rounded-full border border-red-100">
                                            <div className="w-2 h-2 bg-red-500 rounded-full mr-1"></div>
                                            OFFLINE
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CameraSettingsView;
