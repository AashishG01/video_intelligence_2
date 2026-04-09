import React, { useState, useRef, useEffect } from 'react';
import { 
  MonitorPlay, 
  UserSearch, 
  UploadCloud, 
  Search, 
  MapPin, 
  Clock, 
  AlertCircle,
  Loader2,
  X,
  BarChart3,
  Terminal,
  Hash,
  Wifi,
  WifiOff,
  Camera,
  Users,
  ScanFace,
  Timer
} from 'lucide-react';

// ==========================================
// CONFIGURATION
// ==========================================
const BACKEND_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/live_alerts";

// Helper to fix image paths coming from backend
const getImageUrl = (path) => {
  if (!path) return 'https://via.placeholder.com/150/f1f5f9/94a3b8?text=NO+IMG';
  if (path.startsWith('http')) return path;
  // If path from WS is /captured_faces/..., convert to /images/... as mounted in FastAPI
  const cleanPath = path.replace('/captured_faces/', '/images/');
  return `${BACKEND_URL}${cleanPath}`;
};

// ==========================================
// COMPONENT: Sighting Card
// ==========================================
const SightingCard = ({ data }) => {
  const confidencePercent = (data.match_score * 100).toFixed(1);
  const isHighConf        = data.match_score >= 0.50;
  const fullImageUrl      = getImageUrl(data.image_url);

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
          <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${
            isHighConf ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
          }`}>
            {isHighConf ? `High Match (${confidencePercent}%)` : `Possible (${confidencePercent}%)`}
          </span>
        </div>
        <div className="flex items-center text-sm text-slate-500 space-x-4">
          <div className="flex items-center"><MapPin className="w-3.5 h-3.5 mr-1" /> {data.camera}</div>
          <div className="flex items-center"><Clock  className="w-3.5 h-3.5 mr-1" /> {data.timestamp}</div>
        </div>
      </div>
      <button className="ml-6 px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors">
        Full Timeline
      </button>
    </div>
  );
};

// ==========================================
// COMPONENT: Timeline Card
// ==========================================
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

// ==========================================
// COMPONENT: Stat Card
// ==========================================
const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow">
    <div className="flex items-center justify-between mb-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
        <Icon className="w-5 h-5 text-white" />
      </div>
    </div>
    <p className="text-2xl font-bold text-slate-800">{value}</p>
    <p className="text-sm text-slate-500 mt-1">{label}</p>
  </div>
);

// ==========================================
// COMPONENT: System Status View
// ==========================================
const SystemStatusView = () => {
  const [stats, setStats]       = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError]       = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/system/stats`);
        if (!response.ok) throw new Error("Failed to fetch stats");
        const data = await response.json();
        setStats(data);
        setError(null);
      } catch (err) {
        setError("Could not connect to backend. Is the server running?");
      } finally {
        setIsLoading(false);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000); // Auto refresh every 5s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="max-w-4xl mx-auto py-8 px-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-800 mb-2">System Status</h2>
        <p className="text-slate-500">Live statistics from the surveillance PostgreSQL backend.</p>
      </div>

      {isLoading && (
        <div className="text-center py-16">
          <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
          <p className="text-slate-500 font-medium">Connecting to surveillance database...</p>
        </div>
      )}

      {error && !isLoading && (
        <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center">
          <WifiOff className="w-5 h-5 mr-3 flex-shrink-0" />
          <span className="font-medium text-sm">{error}</span>
        </div>
      )}

      {stats && !isLoading && (
        <>
          <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between ${
            stats.status === 'ONLINE' ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'
          }`}>
            <div className="flex items-center">
              {stats.status === 'ONLINE' ? <Wifi className="w-5 h-5 text-emerald-600 mr-3" /> : <WifiOff className="w-5 h-5 text-red-600 mr-3" />}
              <div>
                <p className={`font-semibold text-sm ${stats.status === 'ONLINE' ? 'text-emerald-800' : 'text-red-800'}`}>
                  Network: {stats.status || 'OFFLINE'}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">AI Core: ANTELOPE-V2 Active</p>
              </div>
            </div>
            <span className={`flex items-center text-xs font-medium px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-700`}>
              <span className="w-2 h-2 rounded-full mr-2 bg-emerald-500 animate-pulse"></span>
              Connected
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard icon={ScanFace} label="Total Captures"   value={stats.total_faces_captured || 0} color="bg-blue-500"    />
            <StatCard icon={Users}    label="Unique Suspects"  value={stats.unique_suspects || 0}      color="bg-violet-500"  />
            <StatCard icon={Camera}   label="Active Cameras"   value={stats.active_cameras || 0}       color="bg-amber-500"   />
            <StatCard icon={Timer}    label="System Start"     value={stats.system_start_time || 'N/A'} color="bg-emerald-500" />
          </div>
        </>
      )}
    </div>
  );
};

// ==========================================
// COMPONENT: Event Feed View (Real WebSocket Data)
// ==========================================
const EventFeedView = ({ systemLogs }) => {
  const getTypeStyle = (type) => {
    switch (type) {
      case 'success': return 'text-emerald-400';
      case 'warning': return 'text-amber-400';
      case 'system':  return 'text-blue-400';
      default:        return 'text-slate-400';
    }
  };

  const getTypeBadge = (type) => {
    switch (type) {
      case 'success': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'warning': return 'bg-amber-500/20  text-amber-400  border-amber-500/30';
      case 'system':  return 'bg-blue-500/20   text-blue-400   border-blue-500/30';
      default:        return 'bg-slate-500/20  text-slate-400  border-slate-500/30';
    }
  };

  return (
    <div className="max-w-4xl mx-auto py-8 px-6">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 mb-2">Live Event Feed</h2>
          <p className="text-slate-500">Real-time WebSocket stream from Redis & Milvus.</p>
        </div>
        <span className="flex items-center text-sm font-medium text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-full border border-emerald-200">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse mr-2"></span> Live
        </span>
      </div>

      <div className="bg-slate-900 rounded-2xl border border-slate-700 overflow-hidden shadow-xl">
        <div className="flex items-center px-4 py-3 bg-slate-800 border-b border-slate-700">
          <div className="flex space-x-2 mr-4">
            <div className="w-3 h-3 rounded-full bg-red-500"></div>
            <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
          </div>
          <span className="text-xs text-slate-400 font-mono">C.O.R.E. — AI Worker Stream</span>
        </div>

        <div className="p-4 h-[600px] overflow-y-auto space-y-1 font-mono text-sm flex flex-col-reverse">
          {systemLogs.map((log, index) => (
            <div key={index} className={`flex items-start py-1.5 px-2 rounded transition-all hover:bg-slate-800/40`}>
              <span className="text-slate-600 mr-3 flex-shrink-0 text-xs mt-0.5">[{log.time}]</span>
              <span className={`border text-xs px-1.5 py-0.5 rounded mr-3 flex-shrink-0 uppercase ${getTypeBadge(log.type)}`}>
                {log.type}
              </span>
              <span className={getTypeStyle(log.type)}>{log.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ==========================================
// COMPONENT: Investigator View
// ==========================================
const InvestigatorView = () => {
  const [activeTab, setActiveTab]         = useState('IMG_SEARCH');
  const [isSearching, setIsSearching]     = useState(false);
  const [hasSearched, setHasSearched]     = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [selectedFile, setSelectedFile]   = useState(null);
  const [previewUrl, setPreviewUrl]       = useState(null);
  const [errorMsg, setErrorMsg]           = useState(null);
  const fileInputRef                      = useRef(null);

  // 👉 1. STATE FIX: Slider ka state add kiya (Default 0.60)
  const [searchThreshold, setSearchThreshold] = useState(0.60);

  const [searchId, setSearchId]               = useState("");
  const [isIdSearching, setIsIdSearching]     = useState(false);
  const [idSearchResults, setIdSearchResults] = useState(null);
  const [idSearchError, setIdSearchError]     = useState(null);
  const [personDossier, setPersonDossier]     = useState(null);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setHasSearched(false);
      setSearchResults([]);
      setErrorMsg(null);
    }
  };

  const clearSelection = (e) => {
    e.stopPropagation();
    setSelectedFile(null);
    setPreviewUrl(null);
    setHasSearched(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSearch = async () => {
    if (!selectedFile) { setErrorMsg("Please upload a suspect photo first."); return; }
    setIsSearching(true);
    setErrorMsg(null);
    const formData = new FormData();
    formData.append("file", selectedFile);
    
    try {
      // 👉 2. DYNAMIC URL FIX: Yahan hardcoded 0.60 ko hata ke variable lagaya
      const response = await fetch(`${BACKEND_URL}/api/investigate/search_by_image?threshold=${searchThreshold}`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Database search failed.");
      }
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
      if (!res.ok) {
        if (res.status === 404) throw new Error("Person ID not found in database.");
        throw new Error("Search failed.");
      }
      const data = await res.json();
      setPersonDossier(data);
      setIdSearchResults(data.timeline || []);
    } catch (err) {
      setIdSearchError(err.message);
    } finally {
      setIsIdSearching(false);
    }
  };

  const switchTab = (tab) => {
    setActiveTab(tab);
    setErrorMsg(null);
    setIdSearchError(null);
  };

  return (
    <div className="max-w-4xl mx-auto py-8 px-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-800 mb-2">Subject Investigation</h2>
        <p className="text-slate-500">Search the surveillance database by image or person ID.</p>
      </div>

      <div className="flex space-x-1 bg-slate-100 rounded-xl p-1 mb-8">
        <button
          onClick={() => switchTab('IMG_SEARCH')}
          className={`flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg font-medium text-sm transition-all ${
            activeTab === 'IMG_SEARCH' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <UploadCloud className="w-4 h-4 mr-2" /> Image Search
        </button>
        <button
          onClick={() => switchTab('ID_SEARCH')}
          className={`flex-1 flex items-center justify-center px-4 py-2.5 rounded-lg font-medium text-sm transition-all ${
            activeTab === 'ID_SEARCH' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <Hash className="w-4 h-4 mr-2" /> ID Search
        </button>
      </div>

      {activeTab === 'IMG_SEARCH' && (
        <>
          <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileSelect} />
          <div
            onClick={() => fileInputRef.current?.click()}
            className={`relative border-2 border-dashed rounded-2xl bg-white p-10 flex flex-col items-center justify-center text-center cursor-pointer mb-6 transition-all ${
              previewUrl ? 'border-blue-400 bg-blue-50/30' : 'border-slate-300 hover:bg-slate-50'
            }`}
          >
            {previewUrl ? (
              <div className="flex flex-col items-center">
                <div className="relative">
                  <img src={previewUrl} alt="Preview" className="w-32 h-32 object-cover rounded-xl shadow-md border border-slate-200 mb-4" />
                  <button onClick={clearSelection} className="absolute -top-3 -right-3 bg-red-100 text-red-600 rounded-full p-1.5 hover:bg-red-200 transition-colors shadow-sm">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-sm font-medium text-slate-700">{selectedFile.name}</p>
              </div>
            ) : (
              <>
                <UploadCloud className="w-12 h-12 text-blue-500 mb-4" />
                <h3 className="text-lg font-semibold text-slate-700 mb-1">Drag suspect photo here</h3>
                <p className="text-sm text-slate-400">or click to browse (JPG, PNG)</p>
              </>
            )}
          </div>

          {errorMsg && (
            <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center">
              <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
              <span className="font-medium text-sm">{errorMsg}</span>
            </div>
          )}

          {/* 👉 3. UI FIX: Tailwind Slider */}
          <div className="mb-6 p-5 bg-white border border-slate-200 rounded-xl shadow-sm">
            <div className="flex justify-between items-center mb-3">
              <label className="text-sm font-semibold text-slate-700 flex items-center">
                <AlertCircle className="w-4 h-4 mr-2 text-blue-500" />
                AI Strictness Level (Threshold)
              </label>
              <span className="text-sm font-bold bg-blue-50 text-blue-700 px-3 py-1 rounded-md">
                {searchThreshold.toFixed(2)}
              </span>
            </div>
            
            <input 
              type="range" 
              min="0.30" 
              max="0.90" 
              step="0.05" 
              value={searchThreshold} 
              onChange={(e) => setSearchThreshold(parseFloat(e.target.value))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
            
            <div className="mt-3 text-xs font-medium text-center">
              {searchThreshold < 0.55 ? (
                <span className="text-amber-600">⚠️ Loose: Might match similar looking innocent people</span>
              ) : searchThreshold > 0.65 ? (
                <span className="text-rose-500">⚠️ Strict: Might miss valid faces if lighting is poor</span>
              ) : (
                <span className="text-emerald-600">✅ Optimal "Sweet Spot" for accurate results</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 mb-8">
            <button
              onClick={handleSearch}
              disabled={isSearching || !selectedFile}
              className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-2.5 rounded-lg flex items-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed w-full justify-center"
            >
              {isSearching ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : <Search className="w-5 h-5 mr-2" />}
              {isSearching ? 'Analyzing Milvus Vectors...' : 'Search Surveillance Database'}
            </button>
          </div>

          {isSearching && (
            <div className="text-center py-12">
              <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
              <p className="text-slate-500 font-medium">Scanning 512-d vector database...</p>
            </div>
          )}

          {!isSearching && hasSearched && (
            <div className="space-y-4">
              {searchResults.length > 0 ? (
                <>
                  <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center">
                    <AlertCircle className="w-5 h-5 mr-2 text-blue-500" />
                    Found {searchResults.length} possible sightings
                  </h3>
                  {searchResults.map((res, idx) => <SightingCard key={idx} data={res} />)}
                </>
              ) : (
                <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
                  <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-800">No Matches Found</h3>
                  <p className="text-slate-500">The system could not locate this individual in the database.</p>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {activeTab === 'ID_SEARCH' && (
        <>
          <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 shadow-sm">
            <label className="block text-sm font-medium text-slate-700 mb-2">Enter Target Identification</label>
            <div className="flex items-center gap-4">
              <div className="flex-1 relative">
                <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  className="w-full bg-slate-50 border border-slate-200 text-slate-700 rounded-lg pl-10 pr-4 py-2.5 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
                  placeholder="e.g. P_17000000"
                  value={searchId}
                  onChange={(e) => setSearchId(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleIdSearch()}
                />
              </div>
              <button
                onClick={handleIdSearch}
                disabled={isIdSearching || !searchId.trim()}
                className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-2.5 rounded-lg flex items-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isIdSearching ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : <Search className="w-5 h-5 mr-2" />}
                {isIdSearching ? 'Searching...' : 'Pull Dossier'}
              </button>
            </div>
          </div>

          {idSearchError && (
            <div className="mb-6 p-4 bg-red-50 text-red-700 border border-red-200 rounded-lg flex items-center">
              <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
              <span className="font-medium text-sm">{idSearchError}</span>
            </div>
          )}

          {isIdSearching && (
            <div className="text-center py-12">
              <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
              <p className="text-slate-500 font-medium">Pulling dossier from PostgreSQL...</p>
            </div>
          )}

          {!isIdSearching && idSearchResults !== null && (
            <div>
              {idSearchResults.length > 0 ? (
                <>
                  {personDossier && (
                    <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 shadow-sm">
                      <h3 className="font-semibold text-slate-800 mb-4 flex items-center">
                        <UserSearch className="w-5 h-5 mr-2 text-blue-500" />
                        Dossier: {personDossier.person_id}
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500 uppercase font-medium">Total Sightings</p>
                          <p className="text-lg font-bold text-slate-800">{personDossier.total_sightings}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500 uppercase font-medium">First Seen</p>
                          <p className="text-sm font-semibold text-slate-800">{personDossier.first_seen.split(' ')[1]}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500 uppercase font-medium">Last Seen</p>
                          <p className="text-sm font-semibold text-slate-800">{personDossier.last_seen.split(' ')[1]}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500 uppercase font-medium">Locations</p>
                          <p className="text-sm font-semibold text-slate-800">{personDossier.locations?.length || 0} Cameras</p>
                        </div>
                      </div>
                    </div>
                  )}
                  <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center">
                    <Clock className="w-5 h-5 mr-2 text-blue-500" />
                    Tracking Timeline ({idSearchResults.length} entries)
                  </h3>
                  <div className="space-y-3">
                    {idSearchResults.map((entry, idx) => <TimelineCard key={idx} data={entry} />)}
                  </div>
                </>
              ) : (
                <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
                  <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-800">No Records Found</h3>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

// ==========================================
// COMPONENT: Live Monitor View (With Real Sidebar)
// ==========================================
const LiveMonitorView = ({ liveAlerts }) => {
  const cameras = [
    { id: "cam1", label: "Lab cam 1"},
    { id: "cam2", label: "Lab cam 2"},
    { id: "cam3", label: "Lab cam 3"},
    { id: "cam4", label: "Dept gate Cam"},
  ];

  const [camStatus, setCamStatus] = useState({
    cam1: true, cam2: true, cam3: true, cam4: true
  });

  const handleStreamError = (camId) => {
    setCamStatus(prev => ({ ...prev, [camId]: false }));
  };

  return (
    <div className="flex h-full">
      <div className="flex-1 p-6 overflow-auto">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-slate-800">Live Monitor</h2>
          <span className="flex items-center text-sm font-medium text-green-600 bg-green-50 px-3 py-1 rounded-full border border-green-200">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2"></span>
            System Active
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {cameras.map((cam) => (
            <div key={cam.id} className="bg-slate-800 rounded-xl overflow-hidden relative group">
              <div className="absolute top-3 left-3 z-10 text-white text-xs font-medium bg-black/60 px-3 py-1 rounded-md backdrop-blur-sm flex items-center">
                <span className={`w-2 h-2 rounded-full mr-2 ${camStatus[cam.id] ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}></span>
                {cam.label}
              </div>

              {camStatus[cam.id] ? (
                <img
                  src={`${BACKEND_URL}/api/stream/${cam.id}`}
                  alt={cam.label}
                  className="w-full aspect-video object-cover"
                  onError={() => handleStreamError(cam.id)}
                />
              ) : (
                <div className="w-full aspect-video flex flex-col items-center justify-center text-slate-500 bg-slate-900">
                  <MonitorPlay className="w-12 h-12 opacity-30 mb-2" />
                  <p className="text-xs opacity-50 font-medium">Camera Offline / Waiting</p>
                  <p className="text-xs opacity-30 mt-1">{cam.label}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* REAL-TIME Activity Sidebar */}
      <div className="w-80 bg-white border-l border-slate-200 flex flex-col h-full">
        <div className="p-4 border-b border-slate-100 flex justify-between items-center">
          <h3 className="font-semibold text-slate-800">Live Captures</h3>
          <span className="bg-blue-100 text-blue-700 text-xs px-2 py-1 rounded-full font-bold">{liveAlerts.length}</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {liveAlerts.length === 0 ? (
            <div className="text-center text-slate-400 text-sm mt-10">Waiting for AI detections...</div>
          ) : (
            liveAlerts.map((alert, idx) => (
              <div key={idx} className="flex items-center justify-between p-2 hover:bg-slate-50 rounded-lg border border-transparent hover:border-slate-100 transition-colors">
                <div className="flex items-center space-x-3">
                  <img src={getImageUrl(alert.image_path)} alt="Capture" className="w-12 h-12 rounded-full border border-slate-200 object-cover" />
                  <div>
                    <p className="text-sm font-bold text-slate-800">{alert.camera_id}</p>
                    <p className="text-xs font-medium text-slate-500 mb-0.5">{alert.person_id.substring(0, 10)}...</p>
                    <p className="text-[10px] text-slate-400">{new Date(alert.timestamp * 1000).toLocaleTimeString()}</p>
                  </div>
                </div>
                {alert.status === "MATCH" && (
                  <AlertCircle className="w-4 h-4 text-amber-500" />
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

// ==========================================
// MAIN APP COMPONENT (Global State & WebSocket)
// ==========================================
export default function App() {
  const [currentView, setCurrentView] = useState('investigator');
  const [liveAlerts, setLiveAlerts] = useState([]);
  const [systemLogs, setSystemLogs] = useState([
    { time: new Date().toLocaleTimeString(), msg: "INITIALIZING C.O.R.E. SYSTEMS...", type: "system" }
  ]);

  // Global WebSocket Connection
  useEffect(() => {
    let ws;
    let isConnected = false;

    const connectWebSocket = () => {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        isConnected = true;
        setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg: "Connected to AI Redis Stream via WebSocket.", type: "success" }, ...prev]);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // 1. Update Sidebar
          setLiveAlerts(prev => [data, ...prev].slice(0, 50));

          // 2. Update Event Feed Logs
          const statusText = data.status === "MATCH" ? "MATCH FOUND" : "NEW SUBJECT";
          const logType = data.status === "MATCH" ? "warning" : "success";
          const logMsg = `[${data.camera_id}] ${statusText}: ${data.person_id} (Conf: ${(data.confidence * 100).toFixed(1)}%)`;
          
          setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg: logMsg, type: logType }, ...prev].slice(0, 100));
        } catch (err) {
          console.error("Failed to parse WS message", err);
        }
      };

      ws.onclose = () => {
        if (isConnected) {
          setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg: "WebSocket disconnected. Reconnecting in 5s...", type: "system" }, ...prev]);
          isConnected = false;
        }
        setTimeout(connectWebSocket, 5000);
      };
    };

    connectWebSocket();
    return () => { if (ws) ws.close(); };
  }, []);

  const navItems = [
    { id: 'monitor',      label: 'Live Monitor',   icon: MonitorPlay },
    { id: 'investigator', label: 'Investigator',   icon: UserSearch  },
    { id: 'status',       label: 'System Status',  icon: BarChart3   },
    { id: 'feed',         label: 'Event Feed',     icon: Terminal    },
  ];

  const renderView = () => {
    switch (currentView) {
      case 'monitor':      return <LiveMonitorView liveAlerts={liveAlerts} />;
      case 'investigator': return <InvestigatorView />;
      case 'status':       return <SystemStatusView />;
      case 'feed':         return <EventFeedView systemLogs={systemLogs} />;
      default:             return <InvestigatorView />;
    }
  };

  return (
    <div className="flex h-screen w-full font-sans">
      <nav className="w-64 bg-white border-r border-slate-200 flex flex-col z-10 shadow-sm">
        <div className="p-6 border-b border-slate-100">
          <div className="flex items-center text-blue-600 font-bold text-2xl tracking-tight">
            <MonitorPlay className="w-7 h-7 mr-2" />
            C.O.R.E.
          </div>
          <div className="text-xs text-slate-400 mt-1 uppercase font-semibold tracking-wider">Surveillance Engine</div>
        </div>

        <div className="flex-1 py-4 px-3 space-y-1 bg-white">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={`w-full flex items-center px-3 py-3 rounded-lg font-medium transition-colors ${
                currentView === item.id
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <item.icon className="w-5 h-5 mr-3" />
              {item.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="flex-1 h-screen overflow-hidden bg-slate-50 relative">
        <div className="absolute inset-0 overflow-y-auto">
          {renderView()}
        </div>
      </main>
    </div>
  );
}