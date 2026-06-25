'use client';

import { useAuth } from '@/lib/useDevAuth';
import { useEffect, useState } from 'react';
import { Key, Plus, Copy, Check, Trash2, AlertTriangle } from 'lucide-react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type ApiKeyInfo = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  rate_limit_per_min: number;
  total_calls?: number;
  calls_24h?: number;
  last_used_at: string | null;
  last_used_ip: string | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
};

const ALL_SCOPES = [
  { id: 'check', label: 'PII Detection', desc: 'Run text through the detection pipeline (/api/v1/check, /api/v1/preview)' },
  { id: 'read:stats', label: 'Read Stats', desc: 'Read detection statistics' },
];

export default function ApiKeysPage() {
  const { getToken } = useAuth();
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newScopes, setNewScopes] = useState<string[]>(['check']);
  const [newExpiry, setNewExpiry] = useState<string>('never');
  const [newRateLimit, setNewRateLimit] = useState<string>('60');
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [creating, setCreating] = useState(false);

  async function load() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/api-keys`, {
        headers: { Authorization: `Bearer ${await getToken()}` },
      });
      if (res.ok) {
        const data = await res.json();
        setKeys(data.api_keys || []);
      }
    } catch (e) {
      console.error('Failed to load API keys', e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createKey() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const body: Record<string, unknown> = {
        name: newName.trim(),
        scopes: newScopes,
        rate_limit_per_min: Math.max(1, parseInt(newRateLimit, 10) || 60),
      };
      if (newExpiry !== 'never') body.expires_in_days = parseInt(newExpiry, 10);
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/api-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${await getToken()}` },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        setCreatedKey(data.key);
        setNewName('');
        setNewScopes(['check']);
        setNewExpiry('never');
        setNewRateLimit('60');
        load();
      }
    } catch (e) {
      console.error('Failed to create key', e);
    } finally {
      setCreating(false);
    }
  }

  async function revokeKey(id: string) {
    if (!confirm('Revoke this key? Any integrations using it will stop working immediately.')) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/api-keys/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${await getToken()}` },
      });
      if (res.ok) load();
    } catch (e) {
      console.error('Failed to revoke key', e);
    }
  }

  function toggleScope(scope: string) {
    setNewScopes((prev) => (prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]));
  }

  function copyKey() {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function closeCreate() {
    setShowCreate(false);
    setCreatedKey(null);
    setCopied(false);
  }

  const fmt = (s: string | null) => (s ? new Date(s).toLocaleDateString() : '—');

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Key size={22} /> API Keys
          </h1>
          <p className="text-sm text-[#666666] mt-1">
            Use these to call the PII detection API directly from your own systems — no login required.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-[#111111] text-white text-sm font-medium rounded-lg hover:bg-black transition-colors"
        >
          <Plus size={16} /> Create Key
        </button>
      </div>

      {loading ? (
        <div className="text-sm text-[#888888] animate-pulse">Loading...</div>
      ) : keys.length === 0 ? (
        <div className="border border-dashed border-[#DDDDDD] rounded-xl p-12 text-center">
          <Key size={32} className="mx-auto text-[#CCCCCC] mb-3" />
          <p className="text-sm text-[#666666]">No API keys yet. Create one to start integrating.</p>
        </div>
      ) : (
        <div className="border border-[#EAEAEA] rounded-xl overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead className="bg-[#FAFAFA] text-[#888888] text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left font-medium px-4 py-3">Name</th>
                <th className="text-left font-medium px-4 py-3">Key</th>
                <th className="text-left font-medium px-4 py-3">Scopes</th>
                <th className="text-left font-medium px-4 py-3">Rate Limit</th>
                <th className="text-left font-medium px-4 py-3">Usage</th>
                <th className="text-left font-medium px-4 py-3">Last Used</th>
                <th className="text-left font-medium px-4 py-3">Expires</th>
                <th className="text-left font-medium px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-t border-[#EAEAEA]">
                  <td className="px-4 py-3 font-medium">{k.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#666666]">{k.prefix}…</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {k.scopes.map((s) => (
                        <span key={s} className="px-2 py-0.5 bg-[#F5F5F5] text-[#444444] rounded text-xs">
                          {s}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#666666]">{k.rate_limit_per_min}/min</td>
                  <td className="px-4 py-3 text-[#666666]">
                    {(k.total_calls ?? 0).toLocaleString()}
                    {(k.calls_24h ?? 0) > 0 && (
                      <span className="text-[#999999] text-xs"> ({k.calls_24h} today)</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[#666666]">{fmt(k.last_used_at)}</td>
                  <td className="px-4 py-3 text-[#666666]">{fmt(k.expires_at)}</td>
                  <td className="px-4 py-3">
                    {k.is_active ? (
                      <span className="text-green-600 text-xs font-medium">Active</span>
                    ) : (
                      <span className="text-[#999999] text-xs">Revoked</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {k.is_active && (
                      <button
                        onClick={() => revokeKey(k.id)}
                        className="text-[#999999] hover:text-red-600 transition-colors"
                        title="Revoke"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={closeCreate}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl" onClick={(e) => e.stopPropagation()}>
            {createdKey ? (
              <div>
                <h2 className="text-lg font-semibold mb-2">Your new API key</h2>
                <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
                  <AlertTriangle size={16} className="text-amber-600 shrink-0 mt-0.5" />
                  <p className="text-xs text-amber-800">
                    Copy it now — this is the only time it will be shown. Store it somewhere safe.
                  </p>
                </div>
                <div className="flex items-center gap-2 bg-[#FAFAFA] border border-[#EAEAEA] rounded-lg p-3 mb-4">
                  <code className="flex-1 text-xs font-mono break-all">{createdKey}</code>
                  <button onClick={copyKey} className="shrink-0 text-[#666666] hover:text-[#111111]">
                    {copied ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
                  </button>
                </div>
                <button
                  onClick={closeCreate}
                  className="w-full py-2 bg-[#111111] text-white text-sm font-medium rounded-lg hover:bg-black"
                >
                  Done
                </button>
              </div>
            ) : (
              <div>
                <h2 className="text-lg font-semibold mb-4">Create API Key</h2>
                <label className="block text-xs font-medium text-[#666666] mb-1">Name</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Production backend"
                  className="w-full border border-[#DDDDDD] rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:border-[#111111]"
                />
                <label className="block text-xs font-medium text-[#666666] mb-2">Scopes</label>
                <div className="space-y-2 mb-4">
                  {ALL_SCOPES.map((s) => (
                    <label key={s.id} className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={newScopes.includes(s.id)}
                        onChange={() => toggleScope(s.id)}
                        className="mt-0.5"
                      />
                      <div>
                        <div className="text-sm font-medium">{s.label}</div>
                        <div className="text-xs text-[#888888]">{s.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
                <label className="block text-xs font-medium text-[#666666] mb-1">Expires</label>
                <select
                  value={newExpiry}
                  onChange={(e) => setNewExpiry(e.target.value)}
                  className="w-full border border-[#DDDDDD] rounded-lg px-3 py-2 text-sm mb-6 focus:outline-none focus:border-[#111111]"
                >
                  <option value="never">Never</option>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                  <option value="365">1 year</option>
                </select>
                <label className="block text-xs font-medium text-[#666666] mb-1">Rate limit (requests per minute)</label>
                <input
                  type="number"
                  min={1}
                  value={newRateLimit}
                  onChange={(e) => setNewRateLimit(e.target.value)}
                  className="w-full border border-[#DDDDDD] rounded-lg px-3 py-2 text-sm mb-6 focus:outline-none focus:border-[#111111]"
                />
                <div className="flex gap-2">
                  <button onClick={closeCreate} className="flex-1 py-2 border border-[#DDDDDD] text-sm font-medium rounded-lg hover:bg-[#FAFAFA]">
                    Cancel
                  </button>
                  <button
                    onClick={createKey}
                    disabled={!newName.trim() || newScopes.length === 0 || creating}
                    className="flex-1 py-2 bg-[#111111] text-white text-sm font-medium rounded-lg hover:bg-black disabled:opacity-40"
                  >
                    {creating ? 'Creating...' : 'Create'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
