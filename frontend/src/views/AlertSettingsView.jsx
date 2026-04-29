import React, { useState, useRef } from 'react';
import { Settings, Bell, Mail, Phone, Volume2, Sliders, X, Plus, Save, AlertTriangle, Upload, Play } from 'lucide-react';

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

        // Security Lock: 2MB Limit
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
        audioPreviewRef.current.pause(); // Stop any currently playing sound
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
            // Assumes subtle.mp3 and siren.mp3 exist in your React public folder
            audioPreviewRef.current.src = `/${type}.mp3`;
            audioPreviewRef.current.play().catch(e => console.log("Missing standard audio file in public folder."));
        }
    };

    const handleSave = () => {
        setIsSaving(true);
        
        // Prepare data for backend
        const config = {
            match_threshold: threshold / 100, 
            alert_sound_type: sound,
            notify_emails: emails,
            notify_phones: phones
        };

        // Note: Sending files requires a different approach (FormData) than JSON.
        // We will build that when we connect the backend.
        console.log("Saving Configuration:", config);
        if (sound === 'custom' && customFileName) {
            console.log("Custom File Ready for Upload:", customFileName);
        }
        
        setTimeout(() => {
            setIsSaving(false);
        }, 1000);
    };

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

                {/* LOCAL DASHBOARD NOTIFICATIONS */}
                <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <h3 className="text-lg font-black uppercase tracking-widest text-slate-800 flex items-center mb-6">
                        <Volume2 className="w-5 h-5 mr-2 text-emerald-500" />
                        Dashboard Notifications
                    </h3>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                        {['silent', 'subtle', 'siren', 'custom'].map(type => (
                            <div 
                                key={type}
                                onClick={() => setSound(type)}
                                className={`border-2 p-4 rounded-xl cursor-pointer text-center flex flex-col items-center justify-center transition-all ${sound === type ? 'border-emerald-500 bg-emerald-50 text-emerald-700 shadow-sm' : 'border-slate-200 text-slate-500 hover:border-slate-300'}`}
                            >
                                <span className="font-bold uppercase tracking-wider mb-2">{type}</span>
                                <button 
                                    onClick={(e) => {
                                        e.stopPropagation(); // Prevent triggering the outer div click
                                        playPreview(type);
                                    }}
                                    className={`p-2 rounded-full ${sound === type ? 'bg-emerald-200 text-emerald-800' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'}`}
                                    title="Preview Sound"
                                >
                                    {type === 'silent' ? <X className="w-4 h-4" /> : <Play className="w-4 h-4 fill-current" />}
                                </button>
                            </div>
                        ))}
                    </div>

                    {/* Custom Upload Section (Only visible if 'custom' is selected) */}
                    {sound === 'custom' && (
                        <div className="mt-4 p-4 border border-emerald-200 bg-emerald-50/50 rounded-xl flex items-center justify-between animate-in fade-in slide-in-from-top-2">
                            <div className="flex items-center">
                                <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-600 mr-4">
                                    <Volume2 className="w-5 h-5" />
                                </div>
                                <div>
                                    <p className="text-sm font-bold text-slate-800">
                                        {customFileName ? customFileName : 'No file uploaded'}
                                    </p>
                                    <p className="text-xs font-medium text-slate-500">MP3, WAV, OGG (Max 2MB)</p>
                                </div>
                            </div>
                            
                            <input 
                                type="file" 
                                accept=".mp3,.wav,.ogg" 
                                className="hidden" 
                                ref={fileInputRef}
                                onChange={handleFileUpload}
                            />
                            
                            <button 
                                onClick={() => fileInputRef.current.click()}
                                className="px-4 py-2 bg-white border border-emerald-300 text-emerald-700 text-sm font-bold rounded-lg hover:bg-emerald-50 transition-colors flex items-center"
                            >
                                <Upload className="w-4 h-4 mr-2" />
                                {customFileName ? 'Change File' : 'Upload Audio'}
                            </button>
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