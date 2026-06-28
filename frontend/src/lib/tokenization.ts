export type Vault = Record<string, string>;

type RedactedLike = { type: string; value?: string };

function shortHash(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(16).padStart(8, '0').slice(0, 6);
}

function tokenFor(type: string, value: string): string {
  const t = type.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return `[${t}_${shortHash(value)}]`;
}

export function tokenizeText(original: string, redacted: RedactedLike[]): { text: string; vault: Vault } {
  const vault: Vault = {};
  let text = original;

  // Longer values first — prevents a shorter value that is a substring of another being half-replaced.
  const items = redacted
    .filter((r) => r.value && r.value.length > 0)
    .sort((a, b) => (b.value!.length - a.value!.length));

  for (const r of items) {
    const value = r.value!;
    const token = tokenFor(r.type, value);
    if (text.includes(value)) {
      text = text.split(value).join(token);
      vault[token] = value;
    }
  }
  return { text, vault };
}

export function detokenize(text: string, vault: Vault): string {
  if (!vault) return text;
  let out = text;
  for (const token of Object.keys(vault).sort((a, b) => b.length - a.length)) {
    if (out.includes(token)) out = out.split(token).join(vault[token]);
  }
  return out;
}

// PII sits in localStorage until the chat is deleted — tradeoff for cross-refresh restore without server storage.
const vaultKey = (sessionId: string) => `adpsh_vault_${sessionId}`;

export function loadVault(sessionId: string): Vault {
  if (typeof window === 'undefined' || !sessionId) return {};
  try {
    return JSON.parse(localStorage.getItem(vaultKey(sessionId)) || '{}');
  } catch {
    return {};
  }
}

export function mergeVault(sessionId: string, vault: Vault) {
  if (typeof window === 'undefined' || !sessionId || !vault || Object.keys(vault).length === 0) return;
  try {
    const merged = { ...loadVault(sessionId), ...vault };
    localStorage.setItem(vaultKey(sessionId), JSON.stringify(merged));
  } catch {
    /* localStorage full or unavailable — reload-restore simply won't work */
  }
}

export function clearVault(sessionId: string) {
  if (typeof window === 'undefined' || !sessionId) return;
  try {
    localStorage.removeItem(vaultKey(sessionId));
  } catch {
  }
}
