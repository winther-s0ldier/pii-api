'use client';
import { useAuth } from '@clerk/nextjs';

import React, { useState, useEffect, useRef } from 'react';
import { BookOpen, Download, Upload, Plus, X, ChevronDown, ChevronUp, Search, Trash } from 'lucide-react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type CustomLabel = { id: number; name: string; description: string; tier: string; dictionary_words: string[]; created_at: string };

interface UserConfigResponse {
  user_id: string;
  tier_block: string[];
  tier_redact: string[];
  tier_audit: string[];
}

interface PreviewItem {
  name: string;
  description: string;
  tier: string;
  dictionary_words: string[];
  is_new: boolean;
}

export default function DictionaryManager() {
  const { getToken, orgId, isLoaded } = useAuth();
  const [customLabels, setCustomLabels] = useState<CustomLabel[]>([]);
  const [userConfig, setUserConfig] = useState<UserConfigResponse | null>(null);
  const [selectedLabelId, setSelectedLabelId] = useState<number | null>(null);
  const [newTerms, setNewTerms] = useState('');
  
  const [searchQuery, setSearchQuery] = useState('');
  
  const [isUploading, setIsUploading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [previewItems, setPreviewItems] = useState<PreviewItem[] | null>(null);

  // ponytail: set configUserId dynamically based on role type
  const configUserId = isLoaded && !orgId ? 'me' : 'default_user';

  useEffect(() => {
    if (isLoaded) {
      fetchCustomLabels();
      fetchConfig();
    }
  }, [isLoaded, configUserId]);

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

  const fetchCustomLabels = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) {
        const labels = await res.json();
        setCustomLabels(labels);
        if (labels.length > 0 && !selectedLabelId) {
          setSelectedLabelId(labels[0].id);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Determine effective tier from user config, fallback to label's default tier
  const getEffectiveTier = (labelName: string, defaultTier: string) => {
    if (!userConfig) return defaultTier;
    if (userConfig.tier_block.includes(labelName)) return 'tier_block';
    if (userConfig.tier_redact.includes(labelName)) return 'tier_redact';
    if (userConfig.tier_audit.includes(labelName)) return 'tier_audit';
    return defaultTier;
  };

  const selectedLabel = customLabels.find(l => l.id === selectedLabelId);

  const handleAddTerms = async () => {
    if (!selectedLabel || !newTerms.trim()) return;
    const termsToAdd = newTerms.split(',').map(s => s.trim()).filter(Boolean);
    if (termsToAdd.length === 0) return;

    const updatedWords = Array.from(new Set([...selectedLabel.dictionary_words, ...termsToAdd]));
    
    setIsSaving(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/${selectedLabel.id}`, {
        method: 'PUT',
        headers: { 
          'Authorization': `Bearer ${await getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ dictionary_words: updatedWords })
      });
      if (res.ok) {
        setNewTerms('');
        fetchCustomLabels();
      } else {
        alert("Failed to add terms.");
      }
    } catch (e) {
      console.error(e);
    }
    setIsSaving(false);
  };

  const handleRemoveTerm = async (termToRemove: string) => {
    if (!selectedLabel) return;
    const updatedWords = selectedLabel.dictionary_words.filter(w => w !== termToRemove);
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/${selectedLabel.id}`, {
        method: 'PUT',
        headers: { 
          'Authorization': `Bearer ${await getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ dictionary_words: updatedWords })
      });
      if (res.ok) {
        fetchCustomLabels();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteLabel = async () => {
    if (!selectedLabel) return;
    if (!window.confirm(`Are you sure you want to delete the entire label "${selectedLabel.name}"? This action cannot be undone.`)) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/${selectedLabel.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) {
        setSelectedLabelId(null);
        fetchCustomLabels();
        fetchConfig();
      } else {
        alert("Failed to delete label.");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteLabelById = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete the entire label "${name}"? This action cannot be undone.`)) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/custom_labels/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) {
        if (selectedLabelId === id) setSelectedLabelId(null);
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
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/dictionary/xlsx`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
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
        headers: { 'Authorization': `Bearer ${await getToken()}` },
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
          'Authorization': `Bearer ${await getToken()}`,
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

  const displayedTerms = isExpanded ? selectedLabel?.dictionary_words : selectedLabel?.dictionary_words?.slice(0, 10);
  const hasMoreTerms = (selectedLabel?.dictionary_words?.length || 0) > 10;

  const filteredLabels = customLabels.filter(l => l.name.toLowerCase().includes(searchQuery.toLowerCase()));

  return (
    <div className="max-w-6xl w-full mx-auto p-8 space-y-8 relative font-sans text-[#111111]">
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-[#EAEAEA] pb-6">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-3 tracking-tight"><BookOpen className="text-[#111111]" size={24} /> Dictionary Manager</h1>
          <p className="text-[13px] text-[#888888] mt-1.5">Map specific terms and phrases to your defined Entity Labels.</p>
        </div>
        <div className="flex items-center gap-3 mt-4 md:mt-0">
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
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Left sidebar: Select Label */}
        <div className="col-span-1 space-y-4 flex flex-col h-full max-h-[700px]">
          <div className="bg-white rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-[#EAEAEA] overflow-hidden flex flex-col flex-grow">
            <div className="bg-white p-4 border-b border-[#EAEAEA] space-y-3">
              <h2 className="text-[13px] font-semibold text-[#111111]">Select Entity Label</h2>
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#BBBBBB]" />
                <input 
                  type="text"
                  placeholder="Search labels..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 bg-[#FAFAFA] border border-[#EAEAEA] rounded-md outline-none focus:bg-white focus:border-[#999] focus:ring-0 transition-all text-[13px] placeholder:text-[#BBBBBB]"
                />
              </div>
            </div>
            <div className="p-4 overflow-y-auto space-y-2 flex-grow">
              {filteredLabels.length > 0 ? (
                filteredLabels.map(label => (
                  <div key={label.id} className="relative group">
                    <button
                      onClick={() => { setSelectedLabelId(label.id); setIsExpanded(false); }}
                      className={`w-full text-left px-3 py-2.5 rounded-md border transition-colors flex justify-between items-center ${selectedLabelId === label.id ? 'bg-[#FAFAFA] border-[#111111] text-[#111111]' : 'bg-white border-[#EAEAEA] hover:border-[#CCCCCC]'}`}
                    >
                      <div>
                        <div className="text-[13px] font-medium text-[#111111]">{label.name}</div>
                        <div className="text-[11px] text-[#888888] mt-0.5">{label.dictionary_words.length} terms</div>
                      </div>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteLabelById(label.id, label.name); }}
                      className="absolute right-3 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity text-[#BBBBBB] hover:text-red-500 hover:bg-red-50 p-1.5 rounded-md"
                      title="Delete label"
                    >
                      <Trash size={14} />
                    </button>
                  </div>
                ))
              ) : (
                <div className="text-[13px] text-[#888888] text-center py-4">
                  {customLabels.length === 0 ? "No custom labels created yet." : "No labels match your search."}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right content: Manage Terms */}
        <div className="col-span-1 md:col-span-2">
          {selectedLabel ? (
            <div className="bg-white rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-[#EAEAEA] overflow-hidden flex flex-col h-full min-h-[500px]">
              <div className="bg-white p-6 border-b border-[#EAEAEA]">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <h2 className="text-lg font-semibold text-[#111111]">{selectedLabel.name} Dictionary</h2>
                      <button 
                        onClick={handleDeleteLabel}
                        className="text-[#BBBBBB] hover:text-red-500 transition-colors bg-white border border-[#EAEAEA] p-1.5 rounded-md"
                        title="Delete entire label"
                      >
                        <X size={14} />
                      </button>
                    </div>
                    <p className="text-[13px] text-[#888888] mt-1.5">{selectedLabel.description}</p>
                  </div>
                  <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-md border ${
                    getEffectiveTier(selectedLabel.name, selectedLabel.tier) === 'tier_block' ? 'bg-red-50 text-red-700 border-red-100' : 
                    getEffectiveTier(selectedLabel.name, selectedLabel.tier) === 'tier_redact' ? 'bg-amber-50 text-amber-700 border-amber-100' : 
                    'bg-[#FAFAFA] text-[#888888] border-[#EAEAEA]'
                  }`}>
                    {getEffectiveTier(selectedLabel.name, selectedLabel.tier).replace('tier_', '').toUpperCase()}
                  </span>
                </div>
              </div>
              
              <div className="p-6 flex-grow flex flex-col">
                <div className="flex gap-2 mb-6">
                  <input 
                    type="text"
                    placeholder="Add terms (comma-separated, e.g. Project Apollo, TopSecret)"
                    value={newTerms}
                    onChange={e => setNewTerms(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddTerms()}
                    className="flex-1 px-3 py-2 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB]"
                  />
                  <button 
                    onClick={handleAddTerms}
                    disabled={isSaving || !newTerms.trim()}
                    className="px-5 py-2 bg-[#111111] text-white text-[14px] font-medium rounded-md hover:bg-[#333333] transition-colors disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
                  >
                    <Plus size={16} /> Add Terms
                  </button>
                </div>

                <div className="flex-grow">
                  {displayedTerms && displayedTerms.length > 0 ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap gap-2">
                        {displayedTerms.map((word, i) => (
                          <div key={i} className="group flex items-center gap-1.5 bg-[#FAFAFA] border border-[#EAEAEA] px-2.5 py-1.5 rounded-md text-[13px] hover:border-[#CCCCCC] transition-colors">
                            <span className="font-medium text-[#444444]">{word}</span>
                            <button 
                              onClick={() => handleRemoveTerm(word)}
                              className="text-[#BBBBBB] hover:text-red-500 hover:bg-red-50 rounded-md p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                              title="Remove term"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                      
                      {hasMoreTerms && (
                        <button 
                          onClick={() => setIsExpanded(!isExpanded)}
                          className="flex items-center gap-1 text-[11px] font-semibold text-[#888888] hover:text-[#111111] uppercase tracking-wide mt-4"
                        >
                          {isExpanded ? <><ChevronUp size={14}/> Show Less</> : <><ChevronDown size={14}/> View All ({selectedLabel.dictionary_words.length - 10} more)</>}
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-[#BBBBBB] py-12">
                      <BookOpen size={40} className="mb-4 opacity-20" />
                      <p className="text-[13px] text-[#888888]">No dictionary terms defined yet.</p>
                      <p className="text-[11px]">Gemini zero-shot detection will be used as a fallback.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full bg-[#FAFAFA] rounded-xl border border-dashed border-[#EAEAEA] flex flex-col items-center justify-center text-[#BBBBBB] py-24">
              <BookOpen size={40} className="mb-4 opacity-20" />
              <p className="font-medium text-[13px] text-[#888888]">Select an Entity Label to manage its dictionary</p>
            </div>
          )}
        </div>
      </div>

      {/* PREVIEW MODAL */}
      {previewItems && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[80vh] flex flex-col overflow-hidden">
            <div className="p-6 border-b flex justify-between items-center bg-gray-50">
              <h2 className="text-xl font-bold">Review Dictionary Import</h2>
              <button onClick={() => setPreviewItems(null)} className="text-gray-500 hover:text-gray-800"><X size={24}/></button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1">
              <p className="mb-4 text-sm text-gray-600">
                Please verify the labels below. Any labels completely new to the system have been auto-assigned a Tier by Gemini and their Regex logic will be generated upon save.
              </p>
              
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
                          <span className="text-green-600 font-bold text-xs bg-green-50 px-2 py-1 rounded">NEW LABEL</span>
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
