'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Tag, AlertCircle, Save, Users, ChevronDown, ChevronUp, Download, Upload, X } from 'lucide-react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface UserConfigResponse {
  user_id: string;
  tier_block: string[];
  tier_redact: string[];
  tier_audit: string[];
}

interface CustomLabelResponse {
  id: number;
  name: string;
  description: string;
  tier: string;
}

interface PreviewItem {
  name: string;
  description: string;
  tier: string;
  dictionary_words: string[];
  is_new: boolean;
}

export default function LabelsManager() {
  const backendAuth = typeof window !== 'undefined' ? localStorage.getItem('basic_auth') : null;
  const [configUserId, setConfigUserId] = useState('default_user');
  const [userConfig, setUserConfig] = useState<UserConfigResponse | null>(null);
  const [customLabels, setCustomLabels] = useState<CustomLabelResponse[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [expandedTiers, setExpandedTiers] = useState<Record<string, boolean>>({});

  // New Label State
  const [newLabelName, setNewLabelName] = useState('');
  const [newLabelDesc, setNewLabelDesc] = useState('');
  const [newLabelTier, setNewLabelTier] = useState('tier_audit');
  const [isCreating, setIsCreating] = useState(false);

  // Import State
  const [isUploading, setIsUploading] = useState(false);
  const [previewItems, setPreviewItems] = useState<PreviewItem[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/config/${configUserId}`, {
        headers: { 'Authorization': `Basic ${backendAuth}` }
      });
      if (res.ok) {
        setUserConfig(await res.json());
      } else {
        console.error("Failed to fetch config:", res.status);
        setUserConfig({ user_id: configUserId, tier_block: [], tier_redact: [], tier_audit: [] });
      }
    } catch (e) {
      console.error(e);
      setUserConfig({ user_id: configUserId, tier_block: [], tier_redact: [], tier_audit: [] });
    }
  };

  const fetchCustomLabels = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels`, {
        headers: { 'Authorization': `Basic ${backendAuth}` }
      });
      if (res.ok) setCustomLabels(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchCustomLabels();
  }, []);

  const handleSearchUser = () => {
    fetchConfig();
  };

  const saveConfig = async () => {
    if (!userConfig) return;
    setIsSaving(true);
    try {
      await fetch(`${API_BASE_URL}/api/v1/admin/config/${userConfig.user_id}`, {
        method: 'POST',
        headers: { 
          'Authorization': `Basic ${backendAuth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          tier_block: userConfig.tier_block,
          tier_redact: userConfig.tier_redact,
          tier_audit: userConfig.tier_audit
        })
      });
      alert('Tiers saved successfully!');
    } catch (e) {
      console.error(e);
    }
    setIsSaving(false);
  };

  const handleCreateLabel = async () => {
    if (!newLabelName) return;
    setIsCreating(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels`, {
        method: 'POST',
        headers: { 
          'Authorization': `Basic ${backendAuth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: newLabelName,
          description: newLabelDesc,
          tier: newLabelTier,
          dictionary_words: []
        })
      });
      if (res.ok) {
        setNewLabelName('');
        setNewLabelDesc('');
        fetchCustomLabels();
        fetchConfig(); 
      } else {
        const err = await res.json();
        alert('Failed to create label: ' + err.detail);
      }
    } catch (e) {
      console.error(e);
    }
    setIsCreating(false);
  };

  const handleDeleteLabel = async (labelName: string) => {
    if (!window.confirm(`Are you sure you want to delete the label "${labelName}"? This action cannot be undone.`)) return;
    
    // Find ID
    const label = customLabels.find(l => l.name === labelName);
    if (!label) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/${label.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Basic ${backendAuth}` }
      });
      if (res.ok) {
        fetchCustomLabels();
        fetchConfig();
      } else {
        alert("Failed to delete label.");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleExportXLSX = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/xlsx`, {
        headers: { 'Authorization': `Basic ${backendAuth}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'custom_labels.xlsx';
        a.click();
        window.URL.revokeObjectURL(url);
      } else {
        alert("Failed to download XLSX");
      }
    } catch (e) {
      console.error("Export failed", e);
    }
  };

  const handleImportPreview = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/import/preview`, {
        method: 'POST',
        headers: { 'Authorization': `Basic ${backendAuth}` },
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        setPreviewItems(data.preview);
      } else {
        const err = await res.json();
        alert(`Failed to parse XLSX: ${err.detail}`);
      }
    } catch (e) {
      console.error(e);
      alert("Error uploading XLSX.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleConfirmImport = async () => {
    if (!previewItems) return;
    setIsUploading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/import/confirm`, {
        method: 'POST',
        headers: { 
          'Authorization': `Basic ${backendAuth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ items: previewItems })
      });
      if (res.ok) {
        alert("Import successful!");
        setPreviewItems(null);
        fetchCustomLabels();
        fetchConfig();
      } else {
        alert("Failed to confirm import.");
      }
    } catch (e) {
      console.error(e);
    }
    setIsUploading(false);
  };

  const handleDragStart = (e: React.DragEvent, label: string, sourceTier: string) => {
    e.dataTransfer.setData('label', label);
    e.dataTransfer.setData('sourceTier', sourceTier);
  };

  const handleDrop = (e: React.DragEvent, targetTier: 'tier_block' | 'tier_redact' | 'tier_audit') => {
    e.preventDefault();
    if (!userConfig) return;
    const label = e.dataTransfer.getData('label');
    const sourceTier = e.dataTransfer.getData('sourceTier') as keyof UserConfigResponse;
    if (sourceTier === targetTier) return;

    setUserConfig(prev => {
      if (!prev) return prev;
      const newSource = (prev[sourceTier] as string[]).filter(l => l !== label);
      const newTarget = [...(prev[targetTier] as string[]), label];
      return { ...prev, [sourceTier]: newSource, [targetTier]: newTarget };
    });
  };

  const getDisplayConfig = () => {
    if (!userConfig) return null;
    const allConfigLabels = new Set([...userConfig.tier_block, ...userConfig.tier_redact, ...userConfig.tier_audit]);
    const missingCustoms = customLabels.filter(c => !allConfigLabels.has(c.name)).map(c => c.name);
    return {
      ...userConfig,
      tier_audit: [...userConfig.tier_audit, ...missingCustoms]
    };
  };

  const displayConfig = getDisplayConfig();

  const toggleExpand = (tierId: string) => {
    setExpandedTiers(prev => ({ ...prev, [tierId]: !prev[tierId] }));
  };

  return (
    <div className="max-w-6xl w-full mx-auto p-8 space-y-8 relative font-sans text-[#111111]">
      <div className="flex justify-end gap-3">
        <button onClick={handleExportXLSX} className="flex items-center gap-2 px-4 py-2 border border-[#EAEAEA] bg-white text-[#444444] font-medium text-[13px] rounded-md hover:bg-[#F5F5F5] transition-colors">
          <Download size={16} /> Export XLSX
        </button>
        <div>
          <input type="file" accept=".xlsx" className="hidden" ref={fileInputRef} onChange={handleImportPreview} />
          <button onClick={() => fileInputRef.current?.click()} disabled={isUploading} className="flex items-center gap-2 px-4 py-2 bg-[#111111] text-white font-medium text-[13px] rounded-md hover:bg-[#333333] transition-colors disabled:opacity-50">
            <Upload size={16} /> {isUploading ? "Uploading..." : "Import XLSX"}
          </button>
        </div>
      </div>

      {/* Create Label Section */}
      <section className="bg-white rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-[#EAEAEA] overflow-hidden">
        <div className="bg-white p-6 border-b border-[#EAEAEA]">
          <h2 className="text-lg font-semibold flex items-center gap-2"><Tag size={18} /> Entity Types / Labels</h2>
          <p className="text-[13px] text-[#888888] mt-1.5">Define new classes of sensitive information to detect.</p>
        </div>
        <div className="p-6">
          <div className="flex flex-col md:flex-row gap-3 items-start md:items-center">
            <input 
              type="text" 
              placeholder="Label Name (e.g. Competitors)" 
              value={newLabelName}
              onChange={e => setNewLabelName(e.target.value)}
              className="flex-1 px-3 py-2 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB]"
            />
            <input 
              type="text" 
              placeholder="Description (optional)" 
              value={newLabelDesc}
              onChange={e => setNewLabelDesc(e.target.value)}
              className="flex-2 px-3 py-2 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB] w-full md:w-auto"
            />
            <select 
              value={newLabelTier} 
              onChange={e => setNewLabelTier(e.target.value)}
              className="px-3 py-2 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all"
            >
              <option value="tier_block">BLOCK</option>
              <option value="tier_redact">REDACT</option>
              <option value="tier_audit">AUDIT</option>
            </select>
            <button 
              onClick={handleCreateLabel}
              disabled={isCreating || !newLabelName}
              className="px-5 py-2 bg-[#111111] hover:bg-[#333333] text-white text-[14px] rounded-md font-medium disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              {isCreating ? 'Creating...' : 'Create Label'}
            </button>
          </div>
        </div>
      </section>

      {/* Tiers Section */}
      <section className="bg-white rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-[#EAEAEA] overflow-hidden">
        <div className="bg-white p-6 border-b border-[#EAEAEA] flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2"><Users size={18} /> Redaction Tiers</h2>
            <p className="text-[13px] text-[#888888] mt-1.5 flex items-center gap-1.5">
              <AlertCircle size={14} /> Drag and drop labels to customize protection rules for <b className="text-[#111111]">{configUserId}</b>.
            </p>
          </div>
          <div className="flex gap-2">
            <input 
              type="text" 
              value={configUserId} 
              onChange={e => setConfigUserId(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearchUser()}
              className="px-3 py-1.5 text-[13px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB]"
              placeholder="User ID"
            />
            <button 
              onClick={handleSearchUser}
              className="px-3 py-1.5 bg-[#FAFAFA] border border-[#EAEAEA] text-[#444444] text-[13px] font-medium rounded-md hover:bg-[#F5F5F5] transition-colors"
            >
              Load User
            </button>
          </div>
        </div>

        {displayConfig ? (
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {[
                { id: 'tier_block', title: 'BLOCK', color: 'bg-red-50/30 border-red-100', labelColor: 'bg-red-50 border-red-200 text-red-700 hover:border-red-300' },
                { id: 'tier_redact', title: 'REDACT', color: 'bg-amber-50/30 border-amber-100', labelColor: 'bg-amber-50 border-amber-200 text-amber-700 hover:border-amber-300' },
                { id: 'tier_audit', title: 'AUDIT (PASS)', color: 'bg-green-50/30 border-green-100', labelColor: 'bg-green-50 border-green-200 text-green-700 hover:border-green-300' }
              ].map(tier => {
                const allLabels = displayConfig[tier.id as keyof UserConfigResponse] as string[];
                const isExpanded = expandedTiers[tier.id];
                const visibleLabels = isExpanded ? allLabels : allLabels.slice(0, 10);
                const hasMore = allLabels.length > 10;

                return (
                  <div 
                    key={tier.id}
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => handleDrop(e, tier.id as any)}
                    className={`border border-dashed rounded-xl p-5 min-h-[250px] flex flex-col ${tier.color}`}
                  >
                    <div className="flex justify-between items-center mb-4">
                      <h4 className="text-[13px] font-semibold tracking-wide text-[#111111]">{tier.title}</h4>
                      <span className="text-[11px] font-semibold bg-white border border-[#EAEAEA] px-2 py-0.5 rounded-full text-[#888888]">{allLabels.length} labels</span>
                    </div>
                    
                    <div className="flex flex-wrap gap-2 flex-grow content-start">
                      {visibleLabels.map(label => {
                        return (
                          <div
                            key={label}
                            draggable
                            onDragStart={e => handleDragStart(e, label, tier.id)}
                            className={`group border shadow-[0_1px_2px_rgba(0,0,0,0.02)] px-2.5 py-1.5 rounded-md text-[13px] cursor-grab active:cursor-grabbing font-medium transition-colors flex items-center justify-between gap-2 ${tier.labelColor}`}
                          >
                            <span>{label}</span>
                            <button 
                              onClick={() => handleDeleteLabel(label)}
                              className="text-[#BBBBBB] hover:text-red-500 hover:bg-red-50 rounded-md p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                              title="Delete label"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                    
                    {hasMore && (
                      <button 
                        onClick={() => toggleExpand(tier.id)}
                        className="mt-4 flex items-center justify-center gap-1 text-[11px] font-semibold text-[#888888] hover:text-[#111111] uppercase tracking-wide pt-3 border-t border-[#EAEAEA]"
                      >
                        {isExpanded ? <><ChevronUp size={14}/> Show Less</> : <><ChevronDown size={14}/> View All ({allLabels.length - 10} more)</>}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-8 flex justify-end">
              <button onClick={saveConfig} disabled={isSaving} className="px-5 py-2.5 bg-[#111111] text-white text-[14px] font-medium rounded-md hover:bg-[#333333] transition-colors flex items-center gap-2">
                <Save size={16} /> {isSaving ? 'Saving...' : 'Save Tiers Configuration'}
              </button>
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-[#888888] text-[13px]">Loading configuration...</div>
        )}
      </section>

      {/* PREVIEW MODAL */}
      {previewItems && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[80vh] flex flex-col overflow-hidden">
            <div className="p-6 border-b flex justify-between items-center bg-gray-50">
              <h2 className="text-xl font-bold">Review Imported Labels</h2>
              <button onClick={() => setPreviewItems(null)} className="text-gray-500 hover:text-gray-800"><X size={24}/></button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1">
              <p className="mb-4 text-sm text-gray-600">Please verify the labels below. Any missing tiers have been automatically assigned by Gemini.</p>
              
              <table className="w-full text-sm text-left border">
                <thead className="bg-gray-100 uppercase text-gray-600 text-xs">
                  <tr>
                    <th className="px-4 py-2 border-b">Label Name</th>
                    <th className="px-4 py-2 border-b">Tier</th>
                    <th className="px-4 py-2 border-b">Status</th>
                    <th className="px-4 py-2 border-b">Dictionary Words</th>
                  </tr>
                </thead>
                <tbody>
                  {previewItems.map((item, idx) => (
                    <tr key={idx} className="border-b hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{item.name}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${item.tier === 'tier_block' ? 'bg-red-100 text-red-800' : item.tier === 'tier_redact' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'}`}>
                          {item.tier.replace('tier_', '').toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {item.is_new ? (
                          <span className="text-green-600 font-bold text-xs bg-green-50 px-2 py-1 rounded">NEW</span>
                        ) : (
                          <span className="text-gray-500 font-bold text-xs bg-gray-100 px-2 py-1 rounded">UPDATE</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {item.dictionary_words.length > 0 ? (
                          <span className="text-gray-500">{item.dictionary_words.length} terms</span>
                        ) : <span className="text-gray-400 italic">None</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="p-6 border-t bg-gray-50 flex justify-end gap-4">
              <button onClick={() => setPreviewItems(null)} className="px-4 py-2 text-gray-600 font-medium hover:bg-gray-200 rounded">Cancel</button>
              <button 
                onClick={handleConfirmImport} 
                disabled={isUploading}
                className="px-6 py-2 bg-primary text-white font-medium rounded hover:bg-primary/90 flex items-center gap-2"
              >
                {isUploading ? 'Saving...' : 'Confirm & Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
