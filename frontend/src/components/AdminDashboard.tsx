'use client';
import { useAuth } from '@clerk/nextjs';

import React, { useState, useEffect } from 'react';
import { Shield, Users, Activity, Settings, Save, AlertCircle, Eye, EyeOff, Clock, List, MessageSquare, X } from 'lucide-react';
import { driver } from "driver.js";
import "driver.js/dist/driver.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type StatCount = { name: string; count: number };
type StatsResponse = { total_requests: number; actions: StatCount[]; detected_types: StatCount[]; top_sequences: StatCount[] };
type TierConfigResponse = { user_id: string; tier_block: string[]; tier_redact: string[]; tier_audit: string[] };
type UserLog = { id: number; action: string; detected_types: string[]; flagged_sequences: string[]; original_message?: string; created_at: string };

const TIME_WINDOWS = [
  { label: 'Last 6 Hours', hours: 6 },
  { label: 'Last 12 Hours', hours: 12 },
  { label: 'Last 24 Hours', hours: 24 },
  { label: 'Last 7 Days', hours: 24 * 7 },
  { label: 'Last 14 Days', hours: 24 * 14 },
  { label: 'Last 30 Days', hours: 24 * 30 },
  { label: 'All Time', hours: 0 }
];

type CustomLabel = { id: number; name: string; description: string; tier: string; created_at: string };

export default function AdminDashboard() {
  const { getToken, orgId, isLoaded } = useAuth();
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [userStats, setUserStats] = useState<StatsResponse | null>(null);
  const [configUserId, setConfigUserId] = useState('default_user');
  const [userConfig, setUserConfig] = useState<TierConfigResponse | null>(null);
  const [userLogs, setUserLogs] = useState<UserLog[]>([]);
  const [customLabels, setCustomLabels] = useState<CustomLabel[]>([]);
  const [newLabel, setNewLabel] = useState({ name: '', description: '', tier: 'tier_audit', dictionary_words: '' });
  const [isSaving, setIsSaving] = useState(false);
  const [globalTimeWindow, setGlobalTimeWindow] = useState(24);
  const [userTimeWindow, setUserTimeWindow] = useState(24);
  
  // State to track which sequences are unmasked
  const [unmaskedSequences, setUnmaskedSequences] = useState<Record<string, boolean>>({});

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [selectedLogMessage, setSelectedLogMessage] = useState<string | null>(null);

  // ponytail: set configUserId dynamically based on role type
  useEffect(() => {
    if (isLoaded) {
      setConfigUserId(!orgId ? 'me' : 'default_user');
    }
  }, [isLoaded, orgId]);

  // Auth is handled by the admin layout — mark as authenticated on mount
  useEffect(() => {
    setIsAuthenticated(true);
  }, []);

  useEffect(() => {
    fetchGlobalStats();
    fetchCustomLabels();
  }, [globalTimeWindow]);

  useEffect(() => {
    if (configUserId) {
      fetchUserStats();
      fetchConfig();
      fetchLogs();
    }
  }, [userTimeWindow, configUserId]);

  useEffect(() => {
    if (isAuthenticated && typeof window !== 'undefined') {
      const hasSeenTour = localStorage.getItem('adminTourSeen');
      if (!hasSeenTour) {
        const driverObj = driver({
          showProgress: true,
          steps: [
            { element: 'h1', popover: { title: 'Welcome Admin', description: 'Welcome to the Admin Control Panel. Here you can configure how PII Shield behaves globally.', side: 'bottom', align: 'start' } },
            { element: 'section:nth-of-type(1)', popover: { title: 'Stats Dashboard', description: 'At a glance, see how many requests have been blocked, redacted, or logged.', side: 'top', align: 'start' } },
            { element: 'section:nth-of-type(2)', popover: { title: 'User Profile & Logs', description: 'Search for specific users to see their custom interception logs.', side: 'top', align: 'start' } },
          ]
        });
        driverObj.drive();
        localStorage.setItem('adminTourSeen', 'true');
      }
    }
  }, [isAuthenticated]);

  const getTimeParams = (hours: number) => {
    if (hours === 0) return '';
    const end = new Date();
    const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
    return `?start_time=${start.toISOString()}&end_time=${end.toISOString()}`;
  };

  const fetchGlobalStats = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/stats${getTimeParams(globalTimeWindow)}`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.status === 401) {
        window.location.href = "/";
        return;
      }
      if (res.ok) setStats(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const fetchCustomLabels = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) setCustomLabels(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateLabel = async () => {
    if (!newLabel.name || !newLabel.description) return alert("Name and description required.");
    try {
      const payload = {
        name: newLabel.name,
        description: newLabel.description,
        tier: newLabel.tier,
        dictionary_words: newLabel.dictionary_words.split(',').map(s => s.trim()).filter(Boolean)
      };
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${await getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setNewLabel({ name: '', description: '', tier: 'tier_audit', dictionary_words: '' });
        fetchCustomLabels();
      } else {
        alert("Failed to create label.");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteLabel = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) fetchCustomLabels();
    } catch (e) {
      console.error(e);
    }
  };

  const fetchUserStats = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/stats/${configUserId}${getTimeParams(userTimeWindow)}`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) setUserStats(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/config/${configUserId}`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) setUserConfig(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/logs/${configUserId}?limit=50`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) setUserLogs(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const handleSearchUser = () => {
    fetchUserStats();
    fetchConfig();
    fetchLogs();
  };

  const toggleMask = (key: string) => {
    setUnmaskedSequences(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const renderMaskedText = (text: string, key: string) => {
    if (unmaskedSequences[key]) {
      return <span className="font-mono text-red-600 bg-red-50 px-1 rounded">{text}</span>;
    }
    // Simple mask
    if (text.length <= 4) return <span className="font-mono text-gray-500">***</span>;
    const masked = text.substring(0, 2) + '*'.repeat(Math.max(3, text.length - 4)) + text.substring(text.length - 2);
    return <span className="font-mono text-gray-500">{masked}</span>;
  };

  return (
    <div className="flex h-screen bg-[#FAFAFA] overflow-auto font-sans text-[#111111]">
      <div className="max-w-6xl w-full mx-auto p-8 space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-[#EAEAEA] pb-6">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">Admin Dashboard</h1>
          </div>
        </div>

        {/* Global Stats Section */}
        <section className="bg-white rounded-xl p-6 shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-[#EAEAEA]">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Activity size={18} /> {!orgId ? 'Security Statistics' : 'Global Security Statistics'}
            </h2>
            <div className="flex items-center gap-2 mt-4 md:mt-0 bg-[#FAFAFA] p-1.5 rounded-lg border border-[#EAEAEA]">
              <Clock size={14} className="text-[#888888] ml-2" />
              <select 
                className="bg-transparent text-[13px] font-medium outline-none py-1 px-2 text-[#111111] cursor-pointer"
                value={globalTimeWindow}
                onChange={e => setGlobalTimeWindow(Number(e.target.value))}
              >
                {TIME_WINDOWS.map(w => <option key={w.label} value={w.hours}>{w.label}</option>)}
              </select>
            </div>
          </div>
          
          {stats ? (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <div className="bg-[#FAFAFA] border border-[#EAEAEA] p-4 rounded-lg">
                <p className="text-[11px] text-[#888888] uppercase tracking-wider font-semibold mb-1">Total Requests</p>
                <p className="text-3xl font-semibold tracking-tight">{stats.total_requests}</p>
              </div>
              <div className="bg-[#FAFAFA] border border-[#EAEAEA] p-4 rounded-lg">
                <p className="text-[11px] text-[#888888] uppercase tracking-wider font-semibold mb-1">Actions Taken</p>
                <div className="space-y-1 mt-2">
                  {stats.actions.length > 0 ? stats.actions.map(a => (
                    <div key={a.name} className="flex justify-between text-[13px]">
                      <span className="font-medium text-[#444444]">{a.name}</span>
                      <span className="font-semibold">{a.count}</span>
                    </div>
                  )) : <p className="text-[13px] text-[#888888] italic">No actions yet</p>}
                </div>
              </div>
              <div className="bg-[#FAFAFA] border border-[#EAEAEA] p-4 rounded-lg max-h-48 overflow-y-auto">
                <p className="text-[11px] text-[#888888] uppercase tracking-wider font-semibold mb-1">Top Entities</p>
                <div className="space-y-1 mt-2">
                  {stats.detected_types.length > 0 ? stats.detected_types.map(t => (
                    <div key={t.name} className="flex justify-between text-[13px]">
                      <span className="font-medium text-[#444444] truncate mr-2" title={t.name}>{t.name}</span>
                      <span className="font-semibold">{t.count}</span>
                    </div>
                  )) : <p className="text-[13px] text-[#888888] italic">No entities yet</p>}
                </div>
              </div>
              {/* NEW: Top Sequences Panel */}
              <div className="bg-red-50/50 p-4 rounded-lg border border-red-100 max-h-48 overflow-y-auto relative">
                <p className="text-sm text-red-800 uppercase tracking-wider font-bold mb-1 flex items-center gap-1">
                  <AlertCircle size={14} /> Flagged Sequences
                </p>
                <div className="space-y-1 mt-2">
                  {stats.top_sequences.length > 0 ? stats.top_sequences.map(seq => (
                    <div key={seq.name} className="flex justify-between items-center text-[13px] bg-white p-1.5 rounded shadow-sm border border-red-100/50">
                      <div className="flex items-center gap-2 truncate mr-2">
                        <button onClick={() => toggleMask(seq.name)} className="text-gray-400 hover:text-gray-700 transition-colors">
                          {unmaskedSequences[seq.name] ? <EyeOff size={14}/> : <Eye size={14}/>}
                        </button>
                        {renderMaskedText(seq.name, seq.name)}
                      </div>
                      <span className="font-semibold text-red-700 bg-red-100 px-1.5 rounded">{seq.count}</span>
                    </div>
                  )) : <p className="text-sm text-red-700/70 italic">No sequences</p>}
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 animate-pulse">
              <div className="bg-[#F5F5F5] border border-[#EAEAEA] p-4 rounded-lg h-24"></div>
              <div className="bg-[#F5F5F5] border border-[#EAEAEA] p-4 rounded-lg h-24"></div>
              <div className="bg-[#F5F5F5] border border-[#EAEAEA] p-4 rounded-lg h-24"></div>
              <div className="bg-red-50/30 border border-red-100 p-4 rounded-lg h-24"></div>
            </div>
          )}
        </section>



        {/* User Search & Profile Section */}
        <section className="bg-white rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-[#EAEAEA] overflow-hidden">
          <div className="bg-white p-6 border-b border-[#EAEAEA]">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <Users size={18} /> {!orgId ? 'Recent Access Logs' : 'User Profile & Tiers'}
            </h2>
            {orgId && (
              <div className="flex flex-col md:flex-row gap-3">
                <input 
                  type="text" 
                  value={configUserId} 
                  onChange={e => setConfigUserId(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearchUser()}
                  className="px-3 py-2 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB] w-full md:w-64"
                  placeholder="Enter User ID (e.g. default_user)"
                />
                <button 
                  onClick={handleSearchUser}
                  className="px-5 py-2 bg-[#111111] text-white text-[14px] font-medium rounded-md hover:bg-[#333333] transition-colors"
                >
                  Search User
                </button>
              </div>
            )}
          </div>

          <div className="p-6">
            {/* User Specific Stats (Only for Org view since base user stats are already shown in Global Stats) */}
            {orgId && (
              userStats ? (
                <div className="mb-8">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-[15px] font-semibold text-[#111111]">User Activity Summary</h3>
                    <div className="bg-[#FAFAFA] p-1 rounded-md border border-[#EAEAEA]">
                      <select 
                        className="bg-transparent text-[13px] font-medium outline-none px-2 text-[#111111] cursor-pointer"
                        value={userTimeWindow}
                        onChange={e => setUserTimeWindow(Number(e.target.value))}
                      >
                        {TIME_WINDOWS.map(w => <option key={`user_${w.label}`} value={w.hours}>{w.label}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className="flex gap-4 overflow-x-auto pb-2">
                    <div className="min-w-[120px] bg-[#FAFAFA] border border-[#EAEAEA] p-3 rounded-lg">
                      <p className="text-[11px] text-[#888888] font-semibold uppercase tracking-wider mb-1">Requests</p>
                      <p className="text-2xl font-semibold tracking-tight">{userStats.total_requests}</p>
                    </div>
                    {userStats.actions.map(a => (
                      <div key={a.name} className={`min-w-[120px] p-3 rounded-lg border ${a.name === 'BLOCK' ? 'bg-red-50/50 border-red-100' : a.name === 'REDACT' ? 'bg-amber-50/50 border-amber-100' : 'bg-green-50/50 border-green-100'}`}>
                        <p className={`text-[11px] font-semibold uppercase tracking-wider mb-1 ${a.name === 'BLOCK' ? 'text-red-700' : a.name === 'REDACT' ? 'text-amber-700' : 'text-green-700'}`}>{a.name}</p>
                        <p className="text-2xl font-semibold tracking-tight text-[#111111]">{a.count}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mb-8 animate-pulse">
                  <div className="flex justify-between items-center mb-4">
                    <div className="h-5 bg-[#F5F5F5] rounded w-48"></div>
                    <div className="h-8 bg-[#F5F5F5] rounded w-32"></div>
                  </div>
                  <div className="flex gap-4 overflow-x-auto pb-2">
                    <div className="min-w-[120px] bg-[#F5F5F5] border border-[#EAEAEA] rounded-lg h-20"></div>
                    <div className="min-w-[120px] bg-[#F5F5F5] border border-[#EAEAEA] rounded-lg h-20"></div>
                    <div className="min-w-[120px] bg-[#F5F5F5] border border-[#EAEAEA] rounded-lg h-20"></div>
                  </div>
                </div>
              )
            )}



            {/* User Recent Logs Table */}
            <div>
              <h3 className="text-[15px] font-semibold text-[#111111] mb-4 flex items-center gap-2"><List size={16} /> Recent Access Logs</h3>
              {userStats ? (
                userLogs.length > 0 ? (
                  <div className="overflow-x-auto border border-[#EAEAEA] rounded-lg max-h-96">
                    <table className="w-full text-[13px] text-left">
                      <thead className="bg-[#FAFAFA] text-[#888888] font-medium sticky top-0 border-b border-[#EAEAEA]">
                        <tr>
                          <th className="px-4 py-3 font-medium">Timestamp</th>
                          <th className="px-4 py-3 font-medium">Action</th>
                          <th className="px-4 py-3 font-medium">Entities Detected</th>
                          <th className="px-4 py-3 font-medium min-w-[200px]">Flagged Sequences</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#EAEAEA]">
                        {userLogs.map((log) => (
                          <tr 
                            key={log.id} 
                            className={`hover:bg-[#FAFAFA] ${log.original_message ? 'cursor-pointer' : ''}`}
                            onClick={() => {
                              if (log.original_message) {
                                setSelectedLogMessage(log.original_message);
                              }
                            }}
                          >
                            <td className="px-4 py-3 whitespace-nowrap text-[#888888]">
                              {new Date(log.created_at).toLocaleString()}
                            </td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${log.action === 'BLOCK' ? 'bg-red-50 text-red-700 border border-red-100' : log.action === 'REDACT' ? 'bg-amber-50 text-amber-700 border border-amber-100' : 'bg-green-50 text-green-700 border border-green-100'}`}>
                                {log.action}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1">
                                {log.detected_types.map((type, i) => (
                                  <span key={i} className="bg-[#F5F5F5] text-[#444444] px-1.5 py-0.5 rounded text-[11px] font-medium border border-[#EAEAEA]">{type}</span>
                                ))}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-col gap-1">
                                {log.flagged_sequences && log.flagged_sequences.map((seq, i) => {
                                  const key = `log_${log.id}_${i}`;
                                  return (
                                    <div key={key} className="flex items-center gap-2">
                                      <button onClick={() => toggleMask(key)} className="text-[#BBBBBB] hover:text-[#444444] transition-colors">
                                        {unmaskedSequences[key] ? <EyeOff size={14} /> : <Eye size={14} />}
                                      </button>
                                      {renderMaskedText(seq, key)}
                                    </div>
                                  );
                                })}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="p-8 text-center text-[#888888] border border-[#EAEAEA] rounded-lg border-dashed text-[13px]">
                    No logs found for this user in the selected time window.
                  </div>
                )
              ) : (
                <div className="animate-pulse flex flex-col gap-2">
                  <div className="h-10 bg-[#F5F5F5] rounded border border-[#EAEAEA]"></div>
                  <div className="h-10 bg-[#F5F5F5] rounded border border-[#EAEAEA]"></div>
                  <div className="h-10 bg-[#F5F5F5] rounded border border-[#EAEAEA]"></div>
                  <div className="h-10 bg-[#F5F5F5] rounded border border-[#EAEAEA]"></div>
                </div>
              )}
            </div>

          </div>
        </section>
      </div>

      {selectedLogMessage && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl flex flex-col overflow-hidden">
            <div className="p-4 border-b border-[#EAEAEA] flex justify-between items-center bg-[#FAFAFA]">
              <h2 className="text-lg font-semibold flex items-center gap-2"><MessageSquare size={18} /> Original Message</h2>
              <button onClick={() => setSelectedLogMessage(null)} className="text-[#888888] hover:text-[#111111] transition-colors"><X size={20}/></button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              <div className="bg-[#FAFAFA] border border-[#EAEAEA] p-4 rounded-lg font-mono text-[13px] text-[#444444] whitespace-pre-wrap">
                {selectedLogMessage}
              </div>
            </div>
            <div className="p-4 border-t border-[#EAEAEA] bg-[#FAFAFA] flex justify-end">
              <button 
                onClick={() => setSelectedLogMessage(null)} 
                className="px-4 py-2 bg-[#111111] text-white font-medium text-[13px] rounded-md hover:bg-[#333333] transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

