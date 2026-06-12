import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import api from '../api';
import { BACKEND_URL } from '../config';
import { X, Video } from 'lucide-react';
import WebRTCPlayer from '../components/WebRTCPlayer';
import { useMap } from 'react-leaflet';

const MapResizer = () => {
    const map = useMap();
    useEffect(() => {
        // Delay to allow DOM layout to finish before invalidating
        setTimeout(() => {
            map.invalidateSize();
        }, 100);
    }, [map]);
    return null;
};
// Fix for default Leaflet markers in React
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    tooltipAnchor: [16, -28],
    shadowSize: [41, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

const SURAT_CENTER = [21.1702, 72.8311];

export default function MapView() {
    const [cameras, setCameras] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedCam, setSelectedCam] = useState(null);

    useEffect(() => {
        const fetchCameras = async () => {
            try {
                const res = await api.get('/api/cameras');
                // Filter only cameras with latitude and longitude
                const mappedCams = res.data.filter(c => c.latitude && c.longitude);
                setCameras(mappedCams);
            } catch (error) {
                console.error("Error fetching cameras:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchCameras();
    }, []);

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center">
                <div className="text-slate-500 animate-pulse font-medium">Loading Map...</div>
            </div>
        );
    }

    return (
        <div className="h-full w-full relative bg-slate-100 flex flex-col">
            <div className="p-6 pb-0 flex items-center shrink-0">
                <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center mr-4">
                    <Video className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">City Map</h1>
                    <p className="text-sm text-slate-500">Live surveillance geographical overview (Surat)</p>
                </div>
            </div>

            <div className="flex-1 p-6 relative">
                <div className="w-full h-full min-h-[400px] rounded-2xl overflow-hidden shadow-sm border border-slate-200">
                    <MapContainer center={SURAT_CENTER} zoom={13} style={{ height: '100%', width: '100%' }}>
                        <MapResizer />
                        <TileLayer
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                        />
                        {cameras.map(cam => (
                            <Marker 
                                key={cam.id} 
                                position={[cam.latitude, cam.longitude]}
                                eventHandlers={{
                                    click: () => {
                                        setSelectedCam(cam);
                                    },
                                }}
                            >
                                <Popup>
                                    <div className="text-center font-semibold text-slate-800">
                                        {cam.camera_name}
                                    </div>
                                    <div className="text-xs text-slate-500 mt-1">
                                        {cam.place}
                                    </div>
                                    <button 
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setSelectedCam(cam);
                                        }}
                                        className="mt-2 w-full py-1 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700 transition-colors"
                                    >
                                        View Feed
                                    </button>
                                </Popup>
                            </Marker>
                        ))}
                    </MapContainer>
                </div>
            </div>

            {/* Video Feed Modal */}
            {selectedCam && (
                <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
                    <div className="bg-slate-900 w-full max-w-5xl rounded-2xl shadow-2xl border border-slate-700 overflow-hidden flex flex-col">
                        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-950">
                            <div>
                                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                    {selectedCam.camera_name} (LIVE)
                                </h3>
                                <p className="text-sm text-slate-400">{selectedCam.place} | ID: {selectedCam.camera_id}</p>
                            </div>
                            <button 
                                onClick={() => setSelectedCam(null)}
                                className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="relative aspect-video bg-black flex items-center justify-center">
                            <WebRTCPlayer camId={selectedCam.camera_id} />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
