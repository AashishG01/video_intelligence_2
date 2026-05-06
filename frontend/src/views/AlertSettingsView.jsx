import React, { useState, useRef, useEffect } from 'react';
import { 
    Settings, Mail, Phone, Volume2, Sliders, X, Plus, Save, AlertTriangle, 
    UploadCloud, PlayCircle, RefreshCw, VolumeX, Bell, Radio, FileAudio 
} from 'lucide-react';
import api from '../api'; // ✅ IMPORTED YOUR API CLIENT

const AlertSettingsView = () => {
    // State Management
    const [threshold, setThreshold] = useState(60); 
    
    // Custom Sound States
    const [sound, setSound] = useState('siren');
    const [customFileName, setCustomFileName] = useState('');
    const [customFileUrl, setCustomFileUrl] = useState(null);
    const audioPreviewRef = useRef(new Audio());
    const fileInputRef = useRef(null);
    
    // Comms Lists
    const [emails, setEmails] = useState(['admin@core-security.com']);
    const [newEmail, setNewEmail] = useState('');
    
    const [phones, setPhones] = useState(['+919876543210']);
    const [newPhone, setNewPhone] = useState('');

    const [isSaving, setIsSaving] = useState(false);

    // ==========================================
    // ✅ FETCH SETTINGS ON LOAD
    // ==========================================
    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const response = await api.get('/api/settings/alerts');
                if (response.data && !response.data.error) {
                    setThreshold(response.data.match_threshold * 100); // Convert 0.60 to 60 for the slider
                    setSound(response.data.alert_sound_type);
                    setEmails(response.data.notify_emails || []);
                    setPhones(response.data.notify_phones || []);
                }
            } catch (error) {
                console.error("Failed to fetch settings:", error);
            }
        };
        fetchSettings();
    }, []);

    // Handlers
    const handleAddEmail = (e) => {
        if (e.key === 'Enter' && newEmail.includes('@')) {
            if (!emails.includes(newEmail)) setEmails([...emails, newEmail.toLowerCase()]);
            setNewEmail('');
        }
    };

    const handleAddPhone = (e) => {
        if (e.key === 'Enter' && newPhone.length >= 10) {
            if (!phones.includes(newPhone)) setPhones([...phones, newPhone]);
            setNewPhone('');
        }
    };

    const removeEmail = (target) => setEmails(emails.filter(e => e !== target));
    const removePhone = (target) => setPhones(phones.filter(p => p !== target));

    // --- Audio Upload & Preview Logic ---
    const handleFileUpload = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        if (file.size > 2 * 1024 * 1024) {
            alert("File too large. Maximum size is 2MB to prevent memory bloat.");
            return;
        }

        const validTypes = ['audio/mpeg', 'audio/wav', 'audio/ogg'];
        if (!validTypes.includes(file.type)) {
            alert("Invalid format. Only MP3, WAV, or OGG allowed.");
            return;
        }

        setCustomFileName(file.name);
        setCustomFileUrl(URL.createObjectURL(file));
        setSound('custom');
    };

    const playPreview = (type) => {
        audioPreviewRef.current.pause(); 
        audioPreviewRef.current.currentTime = 0;

        if (type === 'silent') return;

        if (type === 'custom') {
            if (customFileUrl) {
                audioPreviewRef.current.src = customFileUrl;
                audioPreviewRef.current.play();
            } else {
                alert("Please upload a custom sound first.");
            }
        } else {
            audioPreviewRef.current.src = `/${type}.mp3`;
            audioPreviewRef.current.play().catch(e => console.log("Missing standard audio file in public folder."));
        }
    };

    // ==========================================
    // ✅ SAVE SETTINGS TO BACKEND (Upgraded for Audio)
    // ==========================================
    const handleSave = async () => {
        setIsSaving(true);
        
        try {
            // 1. FIRST, UPLOAD AUDIO IF CUSTOM IS SELECTED
            if (sound === 'custom' && fileInputRef.current && fileInputRef.current.files.length > 0) {
                const file = fileInputRef.current.files[0];
                const formData = new FormData();
                formData.append('file', file);
                
                await api.post('/api/settings/upload_audio', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                });
                console.log("Custom Audio Uploaded Successfully");
            }

            // 2. THEN, SAVE ALL SETTINGS
            const config = {
                match_threshold: threshold / 100, 
                alert_sound_type: sound,
                notify_emails: emails,
                notify_phones: phones
            };

            const response = await api.post('/api/settings/alerts', config);
            if (response.data.status === 'success') {
                console.log("Configuration Deployed Successfully");
                // Reset file input so it doesn't upload again unless changed
                if (fileInputRef.current) fileInputRef.current.value = "";
            }
        } catch (error) {
            console.error("Failed to save configuration:", error);
            alert("Failed to deploy settings to the AI Core.");
        } finally {
            setIsSaving(false);
        }
    };

    // Sound Profile Configuration
    const soundOptions = [
        { id: 'silent', label: 'Silent Mode', icon: VolumeX, desc: 'Visual UI alerts only. No audio.' },
        { id: 'subtle', label: 'Subtle Beep', icon: Bell, desc: 'Low-profile notification for stealth monitoring.' },
        { id: 'siren', label: 'Tactical Siren', icon: Radio, desc: 'High-decibel warning for critical threats.' },
        { id: 'custom', label: 'Custom Audio', icon: FileAudio, desc: 'Upload your own specialized alert file.' }
    ];

    return (
        <div className="flex-1 p-8 bg-slate-50 h-full overflow-y-auto custom-scrollbar">
            
            {/* HEADER */}
            <div className="flex justify-between items-end mb-8">
                <div>
                    <h2 className="text-3xl font-black text-slate-900 tracking-tight flex items-center">
                        <Settings className="w-8 h-8 mr-3 text-blue-600" />
                        Live Alert Settings
                    </h2>
                    <p className="text-slate-500 font-medium mt-2">Configure AI sensitivities and automated escalation protocols.</p>
                </div>
                <button 
                    onClick={handleSave}
                    disabled={isSaving}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl font-bold flex items-center shadow-lg shadow-blue-600/20 transition-all disabled:opacity-50"
                >
                    {isSaving ? <RefreshCw className="w-5 h-5 mr-2 animate-spin" /> : <Save className="w-5 h-5 mr-2" />}
                    {isSaving ? 'Deploying...' : 'Save Configuration'}
                </button>
            </div>

            <div className="max-w-4xl space-y-6 pb-12">

                {/* AI ENGINE SETTINGS */}
                <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <h3 className="text-lg font-black uppercase tracking-widest text-slate-800 flex items-center mb-6">
                        <Sliders className="w-5 h-5 mr-2 text-indigo-500" />
                        AI Recognition Engine
                    </h3>
                    
                    <div className="space-y-4">
                        <div className="flex justify-between items-end">
                            <div>
                                <label className="block text-sm font-bold text-slate-700">Cosine Distance Threshold</label>
                                <p className="text-xs font-medium text-slate-500 mt-1">Lower value = stricter matching. Higher value = more false positives.</p>
                            </div>
                            <span className="text-2xl font-black text-indigo-600">{threshold}%</span>
                        </div>
                        
                        <input 
                            type="range" 
                            min="30" 
                            max="85" 
                            value={threshold} 
                            onChange={(e) => setThreshold(e.target.value)}
                            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                        />
                        
                        {threshold > 75 && (
                            <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg flex items-start text-amber-800 text-sm font-medium mt-4">
                                <AlertTriangle className="w-5 h-5 mr-2 shrink-0 text-amber-500" />
                                Warning: A threshold above 75% will cause the AI to hallucinate matches. Expect severe false positives.
                            </div>
                        )}
                    </div>
                </div>

                {/* 🚨 REDESIGNED DASHBOARD NOTIFICATIONS UI (Sleek Vertical List) 🚨 */}
                <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <h3 className="text-lg font-black uppercase tracking-widest text-slate-800 flex items-center mb-6">
                        <Volume2 className="w-5 h-5 mr-2 text-emerald-500" />
                        Dashboard Notifications
                    </h3>
                    
                    <div className="flex flex-col space-y-3">
                        {soundOptions.map(option => {
                            const Icon = option.icon;
                            const isActive = sound === option.id;
                            return (
                                <div
                                    key={option.id}
                                    onClick={() => setSound(option.id)}
                                    className={`group flex items-center justify-between p-4 rounded-xl cursor-pointer transition-all duration-300 border-2 ${
                                        isActive
                                            ? 'bg-emerald-50 border-emerald-500 shadow-[0_4px_20px_-4px_rgba(16,185,129,0.15)]'
                                            : 'bg-white border-slate-200 hover:border-emerald-300 hover:bg-slate-50'
                                    }`}
                                >
                                    <div className="flex items-center gap-4">
                                        {/* Custom Radio Button */}
                                        <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                                            isActive ? 'border-emerald-500' : 'border-slate-300 group-hover:border-emerald-400'
                                        }`}>
                                            {isActive && <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-in zoom-in duration-200" />}
                                        </div>

                                        {/* Icon Container */}
                                        <div className={`p-2.5 rounded-xl transition-colors ${isActive ? 'bg-emerald-200 text-emerald-700' : 'bg-slate-100 text-slate-500 group-hover:bg-emerald-100/50 group-hover:text-emerald-600'}`}>
                                            <Icon className="w-5 h-5" />
                                        </div>

                                        {/* Text Info */}
                                        <div>
                                            <h4 className={`font-black uppercase tracking-widest text-sm transition-colors ${isActive ? 'text-emerald-800' : 'text-slate-700'}`}>
                                                {option.label}
                                            </h4>
                                            <p className={`text-[11px] font-bold mt-0.5 transition-colors ${isActive ? 'text-emerald-600/80' : 'text-slate-400'}`}>
                                                {option.desc}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Action Area (Play Button) */}
                                    {option.id !== 'silent' && (
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation(); 
                                                playPreview(option.id);
                                            }}
                                            className={`p-2 rounded-full transition-all ${
                                                isActive 
                                                ? 'text-emerald-600 hover:bg-emerald-200 hover:scale-110' 
                                                : 'text-slate-400 hover:bg-slate-200 hover:text-slate-700 opacity-0 group-hover:opacity-100'
                                            }`}
                                            title="Preview Sound"
                                        >
                                            <PlayCircle className="w-7 h-7" />
                                        </button>
                                    )}
                                </div>
                            )
                        })}
                    </div>

                    {/* Premium Custom Upload Dropzone - Attached seamlessly if Custom is active */}
                    {sound === 'custom' && (
                        <div className="mt-3 p-5 border-2 border-dashed border-emerald-300 bg-emerald-50/50 rounded-xl flex items-center justify-between animate-in fade-in slide-in-from-top-2 duration-300">
                            {customFileName ? (
                                <div className="flex items-center w-full">
                                    <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 mr-4 shrink-0 shadow-sm border border-emerald-200">
                                        <FileAudio className="w-6 h-6" />
                                    </div>
                                    <div className="flex-1 overflow-hidden">
                                        <p className="text-sm font-black text-slate-800 truncate">{customFileName}</p>
                                        <p className="text-[10px] uppercase tracking-widest font-bold text-emerald-600 mt-0.5">Custom Audio Ready</p>
                                    </div>
                                    <button
                                        onClick={() => fileInputRef.current.click()}
                                        className="ml-4 px-4 py-2 bg-white border border-emerald-200 hover:bg-emerald-100 text-emerald-700 text-xs font-bold uppercase tracking-widest rounded-lg transition-colors shadow-sm"
                                    >
                                        Change File
                                    </button>
                                </div>
                            ) : (
                                <div className="flex items-center justify-between w-full">
                                    <div className="flex items-center">
                                         <div className="w-12 h-12 bg-white border border-emerald-200 shadow-sm text-emerald-500 rounded-full flex items-center justify-center mr-4">
                                            <UploadCloud className="w-6 h-6" />
                                        </div>
                                        <div>
                                            <h4 className="text-sm font-black text-slate-700 uppercase tracking-widest">Upload Custom Audio</h4>
                                            <p className="text-[11px] font-bold text-slate-400 mt-0.5">MP3, WAV, or OGG • Max 2MB</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => fileInputRef.current.click()}
                                        className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-black uppercase tracking-widest rounded-xl transition-all shadow-md shadow-emerald-600/20"
                                    >
                                        Browse
                                    </button>
                                </div>
                            )}
                            <input
                                type="file"
                                accept=".mp3,.wav,.ogg"
                                className="hidden"
                                ref={fileInputRef}
                                onChange={handleFileUpload}
                            />
                        </div>
                    )}
                </div>

                {/* AUTOMATED ESCALATION (EMAILS) */}
                <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <h3 className="text-lg font-black uppercase tracking-widest text-slate-800 flex items-center mb-6">
                        <Mail className="w-5 h-5 mr-2 text-rose-500" />
                        Email Escalation Protocol
                    </h3>
                    
                    <div className="space-y-4">
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Plus className="h-5 w-5 text-slate-400" />
                            </div>
                            <input
                                type="email"
                                value={newEmail}
                                onChange={(e) => setNewEmail(e.target.value)}
                                onKeyDown={handleAddEmail}
                                className="block w-full pl-10 pr-3 py-3 border border-slate-300 rounded-xl leading-5 bg-slate-50 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-rose-500 focus:ring-1 focus:ring-rose-500 font-medium sm:text-sm transition-all"
                                placeholder="Type email address and press Enter..."
                            />
                        </div>

                        <div className="flex flex-wrap gap-2">
                            {emails.map((email, idx) => (
                                <span key={idx} className="inline-flex items-center px-3 py-1 rounded-lg text-sm font-bold bg-rose-50 text-rose-700 border border-rose-200">
                                    {email}
                                    <button onClick={() => removeEmail(email)} className="ml-2 hover:text-rose-900"><X className="w-4 h-4"/></button>
                                </span>
                            ))}
                            {emails.length === 0 && <span className="text-sm font-medium text-slate-400">No email addresses configured.</span>}
                        </div>
                    </div>
                </div>

                {/* AUTOMATED ESCALATION (SMS) */}
                <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <h3 className="text-lg font-black uppercase tracking-widest text-slate-800 flex items-center mb-6">
                        <Phone className="w-5 h-5 mr-2 text-teal-500" />
                        SMS Alert Protocol
                    </h3>
                    
                    <div className="space-y-4">
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Plus className="h-5 w-5 text-slate-400" />
                            </div>
                            <input
                                type="tel"
                                value={newPhone}
                                onChange={(e) => setNewPhone(e.target.value)}
                                onKeyDown={handleAddPhone}
                                className="block w-full pl-10 pr-3 py-3 border border-slate-300 rounded-xl leading-5 bg-slate-50 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500 font-medium sm:text-sm transition-all"
                                placeholder="Type phone number (+91...) and press Enter..."
                            />
                        </div>

                        <div className="flex flex-wrap gap-2">
                            {phones.map((phone, idx) => (
                                <span key={idx} className="inline-flex items-center px-3 py-1 rounded-lg text-sm font-bold bg-teal-50 text-teal-700 border border-teal-200">
                                    {phone}
                                    <button onClick={() => removePhone(phone)} className="ml-2 hover:text-teal-900"><X className="w-4 h-4"/></button>
                                </span>
                            ))}
                            {phones.length === 0 && <span className="text-sm font-medium text-slate-400">No phone numbers configured.</span>}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
};

export default AlertSettingsView;