import React from 'react';
import { MapPin, Clock } from 'lucide-react';
import { getImageUrl } from '../config';

const SightingCard = ({ data }) => {
    const confidencePercent = (data.match_score * 100).toFixed(1);
    const isHighConf = data.match_score >= 0.50;
    const fullImageUrl = getImageUrl(data.image_url);

    return (
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center shadow-sm hover:shadow-md transition-shadow">
            <img
                src={fullImageUrl}
                alt="Subject Sighting"
                className="w-16 h-16 rounded-lg object-cover mr-4 border border-slate-100"
                onError={(e) => e.target.src = 'https://via.placeholder.com/150/f1f5f9/94a3b8?text=NO+IMG'}
            />
            <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                    <h4 className="font-semibold text-slate-800">Subject #{data.person_id.substring(0, 8)}</h4>
                    <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${isHighConf ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                        }`}>
                        {isHighConf ? `High Match (${confidencePercent}%)` : `Possible (${confidencePercent}%)`}
                    </span>
                </div>
                <div className="flex items-center text-sm text-slate-500 space-x-4">
                    <div className="flex items-center"><MapPin className="w-3.5 h-3.5 mr-1" /> {data.camera}</div>
                    <div className="flex items-center"><Clock className="w-3.5 h-3.5 mr-1" /> {data.timestamp}</div>
                </div>
            </div>
            <button className="ml-6 px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors">
                Full Timeline
            </button>
        </div>
    );
};

export default SightingCard;
