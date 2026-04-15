import React from 'react';
import { Camera, Clock } from 'lucide-react';
import { getImageUrl } from '../config';

const TimelineCard = ({ data }) => {
    const fullImageUrl = getImageUrl(data.image_url);
    return (
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center shadow-sm hover:shadow-md transition-shadow">
            <img
                src={fullImageUrl}
                alt="Capture"
                className="w-16 h-16 rounded-lg object-cover mr-4 border border-slate-100"
                onError={(e) => e.target.src = 'https://via.placeholder.com/150/f1f5f9/94a3b8?text=NO+IMG'}
            />
            <div className="flex-1">
                <div className="flex items-center text-sm text-slate-500 space-x-4">
                    <div className="flex items-center font-medium text-slate-700">
                        <Camera className="w-3.5 h-3.5 mr-1.5 text-blue-500" /> {data.camera}
                    </div>
                    <div className="flex items-center">
                        <Clock className="w-3.5 h-3.5 mr-1.5" /> {data.timestamp}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default TimelineCard;
