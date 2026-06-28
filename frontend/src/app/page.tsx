'use client';

import React, { useState, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Plus, PanelLeft, Send, CheckCircle2, ShieldAlert, X, ShieldBan, MessageSquare, Trash2, HatGlasses, Paperclip, Eye, EyeOff, ChevronDown } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { driver } from "driver.js";
import "driver.js/dist/driver.css";
import { SignIn, UserButton } from "@clerk/nextjs";
import { useAuth } from "@/lib/useDevAuth";
import { tokenizeText, detokenize, loadVault, mergeVault, clearVault, type Vault } from "@/lib/tokenization";
import { storeFile, getFile, clearSessionFiles } from "@/lib/imageStore";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

type RedactedType = {
  type: string;
  subtype?: string;
  confidence?: number;
  value: string;
};

type Message = {
  id: string;
  role: 'user' | 'model' | 'preview';
  content: string;
  originalContent?: string;
  status?: 'sending' | 'clear' | 'redacted' | 'blocked' | 'error';
  redactedTypes?: RedactedType[];
  ignoredValues?: string[];
  fileName?: string;
  pendingUserMessage?: string;
  fileUrl?: string;            // blob URL of the uploaded file (current session only)
  fileKind?: 'image' | 'doc';  // how to render the attachment
  uploadBubbleId?: string;     // links a preview back to its upload bubble
  tokenized?: string;          // server-built tokenised doc text (reversible tokenisation)
  vault?: Vault;               // token -> real value for the doc (browser-only)
};

type SessionInfo = {
  id: string;
  title: string;
  created_at: string;
};

type ModelInfo = {
  id: string;
  display: string;
  tier: string;
  provider: string;
  is_default: boolean;
};

function ModelSelector({
  models,
  value,
  onChange,
}: {
  models: ModelInfo[];
  value: string;
  onChange: (id: string) => void;
}) {
  if (models.length <= 1) return null;
  return (
    <div className="relative inline-flex items-center shrink-0">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        title="Choose a model"
        className="appearance-none bg-transparent text-xs font-medium text-muted-foreground hover:text-foreground pl-2 pr-6 py-1.5 rounded-lg hover:bg-black/5 focus:outline-none cursor-pointer transition-colors"
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.display}
          </option>
        ))}
      </select>
      <ChevronDown size={13} className="absolute right-1.5 pointer-events-none text-muted-foreground" />
    </div>
  );
}

const LAST_SESSION_KEY = 'adpsh_last_session_id';

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const totalPassed = messages.filter(m => m.status === 'clear' && m.role === 'user').length;
  const totalRedacted = messages.reduce((acc, m) => acc + (m.redactedTypes?.length || 0), 0);
  const totalBlocked = messages.filter(m => m.status === 'blocked' && m.role === 'user').length;
  const [input, setInput] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [allowedPII, setAllowedPII] = useState<string[]>([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [loadingIndex, setLoadingIndex] = useState(0);
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const { getToken, isLoaded, isSignedIn, orgId, orgRole } = useAuth();

  const placeholders = [
    "How can I help you today?",
    "Paste a document to check for PII...",
    "What would you like to review?",
    "Upload a file to get started..."
  ];

  const loadingStates = [
    "Analyzing text...",
    "Running our models...",
    "Proxying our servers...",
    "Validating context...",
    "Sanitizing output..."
  ];

  useEffect(() => {
    const int = setInterval(() => {
      setPlaceholderIndex(prev => (prev + 1) % placeholders.length);
    }, 3000);
    return () => clearInterval(int);
  }, []);

  useEffect(() => {
    let int: NodeJS.Timeout;
    if (isLoading) {
      int = setInterval(() => {
        setLoadingIndex(prev => (prev + 1) % loadingStates.length);
      }, 1500);
    }
    return () => clearInterval(int);
  }, [isLoading]);

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const emptyFileInputRef = useRef<HTMLInputElement>(null);
  const bottomFileInputRef = useRef<HTMLInputElement>(null);
  const sessionRestoredRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const savedId = localStorage.getItem(LAST_SESSION_KEY);
    setCurrentSessionId(savedId || crypto.randomUUID());
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, []);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    setIsAuthenticated(true);
    loadModels();
    loadSessions().then(list => {
      if (sessionRestoredRef.current) return;
      sessionRestoredRef.current = true;
      const savedId = localStorage.getItem(LAST_SESSION_KEY);
      if (!savedId) return;
      if (list.some(s => s.id === savedId)) {
        loadSession(savedId);
      } else {
        localStorage.removeItem(LAST_SESSION_KEY);
      }
    });
  }, [isLoaded, isSignedIn]);

  useEffect(() => {
    if (!isAuthenticated || !isLoaded) return;

    const userType = !orgId ? 'base' : orgRole === 'org:admin' ? 'admin' : 'user';
    const tourKey = `hasSeenTour_${userType}`;
    if (localStorage.getItem(tourKey)) return;

    setTimeout(() => {
      const isMobile = window.innerWidth < 768;

      const chatStep = { element: '#tour-chat-input', popover: { title: 'Secure Chat', description: 'Type or paste messages here. PII is detected and redacted in real-time before anything reaches the AI.' } };
      const statsStep = { element: '#tour-session-stats', popover: { title: 'Session Stats', description: 'See how many messages were passed clean, redacted, or blocked in this session.' } };
      const newChatStep = { element: '#tour-new-chat', popover: { title: 'New Chat', description: 'Start a fresh session to clear context and history.' } };
      const mobileMenuStep = { element: '#tour-mobile-menu', popover: { title: 'Sidebar', description: 'Open the sidebar to track PII detections, start new chats, and access session stats.' } };

      const steps =
        userType === 'base'
          ? isMobile
            ? [chatStep, mobileMenuStep]
            : [chatStep, statsStep, newChatStep, { element: '#tour-admin-btn', popover: { title: 'Your Admin Panel', description: "Configure which PII types to block, redact, or audit. Add custom labels and dictionary terms — you're your own admin." } }]
          : userType === 'admin'
          ? isMobile
            ? [chatStep, mobileMenuStep]
            : [chatStep, statsStep, newChatStep, { element: '#tour-admin-btn', popover: { title: 'Admin Panel', description: "Manage your organization's PII policy — set tier rules, add custom labels, build dictionaries, and control user access." } }]
          : // enterprise user — no admin access, no 4th step
          isMobile
          ? [chatStep, mobileMenuStep]
          : [chatStep, statsStep, newChatStep];

      const driverObj = driver({
        showProgress: true,
        steps,
        onDestroyed: () => localStorage.setItem(tourKey, 'true'),
      });
      driverObj.drive();
    }, 500);
  }, [isAuthenticated, isLoaded, orgId, orgRole]);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  };

  const loadSessions = async (): Promise<SessionInfo[]> => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sessions`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.status === 401) {
        setIsAuthenticated(false);
        return [];
      }
      if (res.ok) {
        const data = await res.json();
        const list: SessionInfo[] = data.sessions || [];
        setSessions(list);
        return list;
      }
    } catch (err) {
      console.error('Failed to load sessions', err);
    }
    return [];
  };

  const loadModels = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/models`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) {
        const data = await res.json();
        const models: ModelInfo[] = data.models || [];
        setAvailableModels(models);
        const def = models.find(m => m.is_default) || models[0];
        if (def) setSelectedModel(prev => prev || def.id);
      }
    } catch (err) {
      console.error('Failed to load models', err);
    }
  };

  const loadSession = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sessions/${id}`, {
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCurrentSessionId(data.id);
        localStorage.setItem(LAST_SESSION_KEY, data.id);
        if (data.model_used) setSelectedModel(data.model_used);
        const vault = loadVault(data.id);
        const mappedMessages = await Promise.all(
          (data.messages as any[]).map(async (m, i) => {
            const base: Message = {
              id: `db-${i}`,
              role: m.role === 'blocked' ? 'user' : m.role,
              content: detokenize(m.content, vault),
              status: m.role === 'blocked'
                ? 'blocked'
                : (m.redacted_types?.length > 0 ? 'redacted' : 'clear'),
              redactedTypes: m.redacted_types,
            };
            const docMatch = m.role !== 'model' && (m.content as string)?.match(/^\[Document: (.+?)\]/);
            if (docMatch) {
              const stored = await getFile(data.id, docMatch[1]);
              if (stored) {
                return { ...base, fileName: docMatch[1], fileUrl: URL.createObjectURL(stored.blob), fileKind: stored.fileKind };
              }
            }
            return base;
          })
        );
        setMessages(mappedMessages);
      }
    } catch (err) {
      console.error("Failed to load session", err);
    }
  };

  const deleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await fetch(`${API_BASE_URL}/api/v1/sessions/${id}`, { 
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${await getToken()}` }
      });
      setSessions(prev => prev.filter(s => s.id !== id));
      clearVault(id);
      clearSessionFiles(id);
      if (currentSessionId === id) {
        startNewChat();
      }
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  const startNewChat = () => {
    localStorage.removeItem(LAST_SESSION_KEY);
    setCurrentSessionId(crypto.randomUUID());
    setMessages([]);
    setInput('');
    const def = availableModels.find(m => m.is_default) || availableModels[0];
    if (def) setSelectedModel(def.id);
  };

  const togglePII = (type: string) => {
    setAllowedPII(prev => 
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    );
  };

  const piiTypes = [
    { value: 'email', label: 'Email' },
    { value: 'person', label: 'Names' },
    { value: 'phone number', label: 'Phone' },
    { value: 'physical address', label: 'Address' },
    { value: 'IP address', label: 'IP Address' },
    { value: 'US SSN', label: 'SSN' },
    { value: 'US ITIN', label: 'Tax ID' },
    { value: 'US passport', label: 'Passport' },
    { value: 'US driver license', label: 'Driver License' },
    { value: 'UK NHS number', label: 'UK NHS' },
    { value: 'US bank number', label: 'Bank Account' }
  ];

  const isSendDisabled = isLoading || (input.trim().length === 0 && stagedFile === null);

  const handleSendMessage = async () => {
    if (isSendDisabled) return;
    localStorage.setItem(LAST_SESSION_KEY, currentSessionId);

    if (stagedFile) {
        const file = stagedFile;
        const msg = input.trim();
        setStagedFile(null);
        setInput('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto';
        await uploadAndSendFile(file, msg);
        return;
    }

    const originalText = input.trim();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setIsLoading(true);

    const previewId = crypto.randomUUID();
    
    setMessages(prev => [...prev, {
      id: previewId,
      role: 'user',
      content: originalText,
      status: 'sending'
    }]);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/preview`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getToken()}`
        },
        body: JSON.stringify({ message: originalText, session_id: currentSessionId, allowed_pii: allowedPII, ignored_values: [] })
      });
      
      const data = await res.json();
      
      setMessages(prev => prev.filter(m => m.id !== previewId));

      if (data.action === 'BLOCK') {
        const uniqueTypes = Array.from(new Set((data.blocked_types || []).map((t: any) => t.type)));
        const typesStr = uniqueTypes.join(', ');
        
        setMessages(prev => [
          ...prev, 
          {
            id: crypto.randomUUID(),
            role: 'user',
            content: originalText,
            status: 'blocked',
            redactedTypes: data.blocked_types
          },
          {
            id: crypto.randomUUID(),
            role: 'model',
            content: `This has been blocked because it contains: ${typesStr}, hence it has been blocked.`,
            status: 'clear'
          }
        ]);
        fetch(`${API_BASE_URL}/api/v1/sessions/save-blocked`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${await getToken()}` },
          body: JSON.stringify({ session_id: currentSessionId, message: originalText, blocked_types: data.blocked_types })
        }).then(() => { loadSessions(); localStorage.setItem(LAST_SESSION_KEY, currentSessionId); }).catch(e => console.error('Failed to save blocked message', e));
        setIsLoading(false);
        return;
      }

      if (data.action === 'CLEAN' || data.action === 'CLEAR') {
        await executeLLM(originalText);
        return;
      }

      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'preview',
        content: data.message,
        originalContent: originalText,
        redactedTypes: data.redacted_types,
        ignoredValues: []
      }]);
      setIsLoading(false);

    } catch (err) {
      console.error(err);
      setIsLoading(false);
      setMessages(prev => prev.filter(m => m.id !== previewId));
    }
  };

  const MAX_UPLOAD_MB = 50; // keep in sync with backend MAX_UPLOAD_MB / nginx client_max_body_size

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'user',
        content: `"${file.name}" is ${sizeMb}MB, which exceeds the ${MAX_UPLOAD_MB}MB limit. Please upload a smaller file.`,
        status: 'error'
      }]);
      return;
    }
    setStagedFile(file);
  };

  const uploadAndSendFile = async (file: File, userMessage: string) => {
    localStorage.setItem(LAST_SESSION_KEY, currentSessionId);
    setIsLoading(true);
    const uploadBubbleId = crypto.randomUUID();
    const fileUrl = URL.createObjectURL(file);
    const fileKind: 'image' | 'doc' = file.type.startsWith('image/') ? 'image' : 'doc';
    storeFile(currentSessionId, file.name, file);

    setMessages(prev => [...prev, {
      id: uploadBubbleId,
      role: 'user',
      content: userMessage,
      status: 'sending',
      fileName: file.name,
      fileUrl,
      fileKind,
    }]);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', 'admin');
    formData.append('session_id', currentSessionId);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/document/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${await getToken()}`
        },
        body: formData
      });

      const data = await res.json();

      if (res.ok) localStorage.setItem(LAST_SESSION_KEY, currentSessionId);

      if (!res.ok) {
        setMessages(prev => [
          ...prev.map(m => m.id === uploadBubbleId ? { ...m, status: 'error' as const } : m),
          {
            id: crypto.randomUUID(),
            role: 'model',
            content: `Couldn't process ${file.name}: ${data.detail || 'Unknown error'}`,
            status: 'clear'
          }
        ]);
        setIsLoading(false);
        return;
      }

      if (data.action === 'BLOCK') {
        const uniqueTypes = Array.from(new Set((data.blocked_types || []).map((t: any) => t.type)));
        const typesStr = uniqueTypes.join(', ');
        const explanation = `I couldn't process this because it contains sensitive information (${typesStr}). For your security, the transmission was blocked.`;

        setMessages(prev => [
          ...prev.map(m => m.id === uploadBubbleId ? { ...m, status: 'blocked' as const } : m),
          {
            id: crypto.randomUUID(),
            role: 'model',
            content: explanation,
            status: 'clear'
          }
        ]);

        fetch(`${API_BASE_URL}/api/v1/sessions/save-blocked`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${await getToken()}` },
          body: JSON.stringify({ session_id: currentSessionId, message: `[Document: ${file.name}]`, model_explanation: explanation })
        }).then(() => { loadSessions(); localStorage.setItem(LAST_SESSION_KEY, currentSessionId); }).catch(e => console.error('Failed to save blocked document', e));

        setIsLoading(false);
        return;
      }

      if (data.action === 'CLEAN' || !data.redacted_types?.length) {
        const docText = `[Document: ${file.name}]\n${data.message}` + (userMessage.trim() ? `\n\n${userMessage.trim()}` : '');
        await executeLLM(docText, allowedPII, false, { existingBubbleId: uploadBubbleId, keepContent: true });
        return;
      }

      setIsLoading(false);

      setMessages(prev => [
        ...prev.map(m => m.id === uploadBubbleId ? { ...m, status: 'redacted' as const } : m),
        {
          id: crypto.randomUUID(),
          role: 'preview',
          content: data.message,
          originalContent: data.message,
          redactedTypes: data.redacted_types,
          fileName: file.name,
          pendingUserMessage: userMessage,
          uploadBubbleId,
          tokenized: data.tokenized,
          vault: data.vault,
        }
      ]);
    } catch (err) {
      console.error(err);
      setIsLoading(false);
      setMessages(prev => [
        ...prev.map(m => m.id === uploadBubbleId ? { ...m, status: 'error' as const } : m),
        {
          id: crypto.randomUUID(),
          role: 'model',
          content: `Couldn't process ${file.name}. The file may be too large or the server took too long. Please try again or use a smaller/clearer file.`,
          status: 'clear'
        }
      ]);
    }
  };

  const executeLLM = async (
    text: string,
    ignoredValues: string[] = [],
    isPreRedacted: boolean = false,
    opts: { existingBubbleId?: string; keepContent?: boolean; vault?: Vault; displayText?: string } = {}
  ) => {
    const { existingBubbleId, keepContent, vault, displayText } = opts;
    if (vault) mergeVault(currentSessionId, vault);  // browser-only; never sent to server
    setIsLoading(true);
    const tempId = existingBubbleId || crypto.randomUUID();
    if (existingBubbleId) {
      setMessages(prev => prev.filter(m => m.role !== 'preview').map(m => m.id === tempId ? { ...m, status: 'sending' as const } : m));
    } else {
      setMessages(prev => [...prev.filter(m => m.role !== 'preview'), { id: tempId, role: 'user', content: text, status: 'sending' }]);
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/check`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getToken()}`
        },
        body: JSON.stringify({ message: text, session_id: currentSessionId, allowed_pii: allowedPII, ignored_values: ignoredValues, model: selectedModel || undefined })
      });

      if (!res.ok && res.status === 400) {
        const errorData = await res.json().catch(() => ({}));
        let typesStr = "";
        let redactedTypes = undefined;
        if (errorData.detail && errorData.detail.action === "BLOCK") {
           const uniqueTypes = Array.from(new Set((errorData.detail.blocked_types || []).map((t: any) => t.type)));
           typesStr = uniqueTypes.join(', ');
           redactedTypes = errorData.detail.blocked_types;
        }
        const explanation = `I couldn't process this because it contains sensitive information (${typesStr}). For your security, the transmission was blocked.`;

        setMessages(prev => {
          const base = existingBubbleId
            ? prev.map(m => m.id === tempId ? { ...m, status: 'blocked' as const, redactedTypes } : m)
            : [...prev.filter(m => m.id !== tempId), { id: crypto.randomUUID(), role: 'user' as const, content: text, status: 'blocked' as const, redactedTypes }];
          return [...base, { id: crypto.randomUUID(), role: 'model' as const, content: explanation, status: 'clear' as const }];
        });
        
        fetch(`${API_BASE_URL}/api/v1/sessions/save-blocked`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${await getToken()}` },
          body: JSON.stringify({ session_id: currentSessionId, message: text, model_explanation: explanation, blocked_types: errorData.detail?.blocked_types })
        }).then(() => { loadSessions(); localStorage.setItem(LAST_SESSION_KEY, currentSessionId); }).catch(e => console.error('Failed to save blocked message', e));

        setIsLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      if (!reader) throw new Error('No reader available');

      let buffer = '';
      let action = '';
      let modelMsgId = crypto.randomUUID();
      let hasAddedModelMsg = false;
      let rawModelReply = '';  // accumulates tokenised reply; we de-tokenise for display

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');

        while (boundary !== -1) {
          const messageStr = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);

          if (messageStr.startsWith('data: ')) {
            const data = JSON.parse(messageStr.slice(6));

            if (data.type === 'metadata') {
              action = data.action;
              setMessages(prev => {
                const mapped = prev.map(m => m.id === tempId ? {
                  ...m,
                  content: keepContent ? m.content : (displayText ?? data.message),
                  // isPreRedacted: backend saw clean tokens but original had PII — keep 'redacted' badge
                  status: (isPreRedacted || action === 'REDACT') ? ('redacted' as const) : ('clear' as const),
                  redactedTypes: keepContent ? m.redactedTypes : data.redacted_types
                } : m);
                return [...mapped, { id: modelMsgId, role: 'model', content: '', status: 'sending' as const }];
              });
              hasAddedModelMsg = true;
            } else if (data.type === 'chunk') {
              rawModelReply += data.text;
              const display = vault ? detokenize(rawModelReply, vault) : rawModelReply;
              setMessages(prev => prev.map(m => m.id === modelMsgId ? { ...m, content: display, status: 'clear' as const } : m));
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
      
      loadSessions();
      localStorage.setItem(LAST_SESSION_KEY, currentSessionId);

    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const renderMessageContent = (msgId: string, content: string, redactedTypes?: RedactedType[], role?: string, status?: string) => {
    let displayContent = content;
    if (role === 'user' && content.startsWith('[Document: ')) {
      const firstLineEnd = content.indexOf('\n');
      if (firstLineEnd !== -1) {
        displayContent = content.substring(0, firstLineEnd);
      }
    }

    if (!redactedTypes || redactedTypes.length === 0) {
      return displayContent;
    }

    if (status === 'blocked') {
      let parts: (string | React.ReactNode)[] = [displayContent];
      redactedTypes.forEach((rt, rtIdx) => {
        if (!rt.value) return;
        parts = parts.flatMap(part => {
          if (typeof part !== 'string') return [part];
          const segments = part.split(rt.value);
          const newParts: (string | React.ReactNode)[] = [];
          segments.forEach((seg, i) => {
            newParts.push(seg);
            if (i < segments.length - 1) {
              newParts.push(
                <s key={`blocked-${rtIdx}-${i}`} className="opacity-60 decoration-white/80" title={rt.type}>
                  {rt.value}
                </s>
              );
            }
          });
          return newParts;
        });
      });
      return parts;
    }

    let parts: (string | React.ReactNode)[] = [displayContent];
    
    redactedTypes.forEach(rt => {
      const originalLabel = rt.type.toUpperCase().replace(/ /g, '_');
      const displayLabel = originalLabel.endsWith('_ID') ? 'ID' : originalLabel;
      const searchStr = `[${originalLabel}]`;
      
      parts = parts.flatMap(part => {
        if (typeof part !== 'string') return [part];
        const segments = part.split(searchStr);
        const newParts: (string | React.ReactNode)[] = [];
        segments.forEach((seg, i) => {
          newParts.push(seg);
          if (i < segments.length - 1) {
            newParts.push(
              <span key={`${rt.type}-${i}`} className={cn(
                "inline-flex items-center pl-1.5 pr-1 py-0.5 rounded text-[13px] align-baseline font-mono tracking-tight mx-1",
                role === 'user' ? "bg-white/20 text-white border border-white/30" : "text-primary bg-primary/10 border border-primary/20"
              )} title={`Original: ${rt.value}`}>
                <span className="cursor-help">[{displayLabel}]</span>
                {role === 'preview' && (
                  <button 
                    onClick={() => handleUnredact(msgId, rt, searchStr)}
                    className="hover:text-red-500 hover:bg-black/5 rounded-sm transition-colors flex items-center justify-center ml-1 p-0.5"
                    title="Remove redaction"
                  >
                    <X size={10} strokeWidth={4} />
                  </button>
                )}
              </span>
            );
          }
        });
        return newParts;
      });
    });
    
    return parts;
  };

  const handleUnredact = (msgId: string, rt: RedactedType, searchStr: string) => {
    setMessages(prev => prev.map(m => {
      if (m.id === msgId) {
        const newContent = m.content.replace(searchStr, rt.value);
        const newRedactedTypes = m.redactedTypes?.filter(r => r !== rt) || [];
        const newIgnoredValues = [...(m.ignoredValues || []), rt.value];
        return {
          ...m,
          content: newContent,
          redactedTypes: newRedactedTypes,
          ignoredValues: newIgnoredValues
        };
      }
      return m;
    }));
  };

  if (!isLoaded) return <div className="h-screen flex items-center justify-center bg-[#FAF9F5]">Loading Secure Environment...</div>;
  
  if (!isSignedIn) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[#FAF9F5] font-sans p-4 text-[#2A1F1A]">
        <div className="flex justify-center mb-6">
          <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="h-12 w-auto object-contain" />
        </div>
        <SignIn routing="hash" />
      </div>
    );
  }

  return (
        <div className="flex h-screen bg-[#FAF9F5] overflow-hidden font-sans text-[#2A1F1A]">
      
      {/* Sidebar Overlay for Mobile */}
      <AnimatePresence>
        {isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/20 z-40 md:hidden"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar Container */}
      <aside 
        className={cn(
          "fixed md:relative top-0 left-0 h-full bg-[#F3EFE7] border-r border-[#E0D9C8] z-50 shrink-0 transition-all duration-300 ease-in-out overflow-hidden flex",
          isSidebarOpen ? "w-[260px] translate-x-0" : "w-[60px] -translate-x-full md:translate-x-0"
        )}
      >
        {/* Full Sidebar Content */}
        <div className={cn(
          "w-[260px] shrink-0 flex flex-col h-full transition-opacity duration-200",
          isSidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}>
          <div className="p-3 flex items-center justify-between">
            <div className="font-semibold text-foreground px-2 flex items-center gap-2">
              <img src="/logo-t.png" alt="Logo" className="h-5 w-auto" />
              ADOPSHUN AI
            </div>
            <button 
              onClick={() => setIsSidebarOpen(false)}
              className="p-2 hover:bg-black/5 rounded-lg text-muted-foreground hover:text-foreground transition-all shrink-0"
              title="Close sidebar"
            >
              <PanelLeft size={20} />
            </button>
          </div>

          <div className="px-3 pb-3">
            <button 
              id="tour-new-chat"
              onClick={startNewChat}
              className="w-full flex items-center gap-2 bg-[#F3EFE7] hover:bg-black/5 p-2 rounded-lg transition-colors text-sm font-medium border border-transparent text-foreground"
            >
              <Plus size={16} /> New chat
            </button>
            <div className="mt-2 flex items-center gap-2 p-2">
              <UserButton appearance={{ elements: { userButtonPopoverActionButton__manageOrganization: { display: !orgId ? 'none' : undefined } } }} />
              <span className="text-sm font-medium">My Account</span>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            <div className="text-xs font-bold text-muted-foreground mb-3 uppercase tracking-wider px-2 pt-2">Recent Chats</div>
            {sessions.map(s => (
              <div key={s.id} className="relative group">
                <button
                  onClick={() => { loadSession(s.id); setIsSidebarOpen(false); }}
                  className={cn(
                    "w-full text-left p-2 pr-8 rounded-lg text-sm truncate flex items-center gap-2 transition-colors",
                    currentSessionId === s.id ? "bg-black/5 text-primary font-medium shadow-sm" : "text-foreground hover:bg-black/5"
                  )}
                >
                  <MessageSquare size={14} className="opacity-50 shrink-0" />
                  <span className="truncate">{s.title}</span>
                </button>
                <button 
                  onClick={(e) => deleteSession(e, s.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 opacity-0 group-hover:opacity-100 hover:bg-black/10 hover:text-red-600 rounded text-muted-foreground transition-all"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>

          <div id="tour-session-stats" className="p-4 border-t border-border bg-secondary/30">
            <div className="text-xs font-bold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
              <Shield size={14} className="text-primary/70" /> Session Stats
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
              <div className="bg-white/50 border border-[#E0D9C8] rounded-md py-2 flex flex-col items-center justify-center">
                <span className="font-bold text-green-600/80 text-base">{totalPassed}</span>
                <span className="text-muted-foreground font-medium">Passed</span>
              </div>
              <div className="bg-white/50 border border-[#E0D9C8] rounded-md py-2 flex flex-col items-center justify-center">
                <span className="font-bold text-amber-600/80 text-base">{totalRedacted}</span>
                <span className="text-muted-foreground font-medium">Redacted</span>
              </div>
              <div className="bg-white/50 border border-[#E0D9C8] rounded-md py-2 flex flex-col items-center justify-center">
                <span className="font-bold text-destructive/80 text-base">{totalBlocked}</span>
                <span className="text-muted-foreground font-medium">Blocked</span>
              </div>
            </div>
          </div>
        </div>

        {/* Mini Rail Content (Desktop Only) */}
        <div className={cn(
          "absolute top-0 left-0 w-[60px] h-full hidden md:flex flex-col items-center py-3 gap-4 transition-opacity duration-200",
          !isSidebarOpen ? "opacity-100 delay-100" : "opacity-0 pointer-events-none"
        )}>
          <button onClick={() => setIsSidebarOpen(true)} className="p-1.5 hover:bg-black/5 rounded-lg transition-all" title="Expand sidebar">
            <img src="/logo-t.png" alt="ADOPSHUN AI" className="w-7 h-7 object-contain" />
          </button>
          <button onClick={startNewChat} className="p-2 hover:bg-black/5 rounded-lg text-muted-foreground hover:text-foreground transition-all" title="New chat">
            <Plus size={20} />
          </button>
          <div className="flex-1" />
          <button onClick={() => setIsSidebarOpen(true)} className="p-2 hover:bg-black/5 rounded-lg text-muted-foreground hover:text-foreground transition-all mb-4" title="Stats & Settings">
            <Shield size={20} />
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 relative h-full bg-[#FAF9F5]">
        <header className="absolute top-0 w-full flex items-center justify-between px-4 py-3 z-10">
          <div className="flex items-center gap-3">
            {!isSidebarOpen && (
              <button 
                id="tour-mobile-menu"
                onClick={() => setIsSidebarOpen(true)}
                className="p-2 hover:bg-black/5 rounded-lg text-muted-foreground hover:text-foreground transition-colors md:hidden"
                title="Open sidebar"
              >
                <PanelLeft size={20} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {isLoaded && isSignedIn && (!orgId || orgRole === 'org:admin') && (
              <a
                id="tour-admin-btn"
                href="/admin"
                className="p-2 hover:bg-black/5 rounded-full text-muted-foreground hover:text-primary transition-colors flex items-center justify-center"
                title="Admin Dashboard"
              >
                <HatGlasses size={20} />
              </a>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 flex flex-col">
          <div className={cn("max-w-3xl w-full mx-auto flex flex-col gap-6 pb-20", messages.length === 0 && "flex-1 justify-center")}>
            <AnimatePresence mode="wait">
              {messages.length === 0 ? (
                <motion.div 
                  key="empty-state"
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                  className="w-full flex flex-col items-center justify-center"
                >
                  <h1 className="text-4xl font-serif text-[#2A1F1A] mb-8 flex items-start gap-1">
                  <motion.span 
                    animate={{ rotate: 360 }} 
                    transition={{ repeat: Infinity, duration: 20, ease: "linear" }}
                    className="text-[#C2543A] text-4xl font-sans inline-block origin-center -mt-1"
                  >*</motion.span> {getGreeting()}
                </h1>

                {/* Centered Input Area */}
                <div className="w-full max-w-3xl relative">
                  {stagedFile && (
                    <div className="flex items-center gap-3 bg-[#2A1F1A] text-white rounded-2xl px-3 py-2.5 w-fit mb-3 shadow-sm mx-auto">
                      <div className="w-9 h-9 bg-[#0084ff] rounded-xl flex items-center justify-center shrink-0">
                        <Paperclip size={18} className="text-white" />
                      </div>
                      <div className="flex flex-col pr-6">
                        <span className="text-[14px] font-bold leading-tight">{stagedFile.name}</span>
                        <span className="text-[12px] text-gray-300 leading-tight">Document</span>
                      </div>
                      <button onClick={() => setStagedFile(null)} className="absolute right-2 top-2 p-1 bg-white/20 hover:bg-white/30 rounded-full transition-colors flex items-center justify-center">
                        <X size={12} strokeWidth={3} />
                      </button>
                    </div>
                  )}
                  <div id="tour-chat-input" className="relative flex flex-row items-end w-full bg-white border border-[#E0D9C8] rounded-2xl shadow-sm focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50 transition-all p-2 gap-2">
                    <input type="file" ref={emptyFileInputRef} onChange={(e) => { handleFileUpload(e); e.target.value = ''; }} className="hidden" />
                    <button 
                      onClick={() => emptyFileInputRef.current?.click()}
                      disabled={isLoading}
                      className="p-2.5 text-muted-foreground hover:bg-black/5 hover:text-foreground rounded-xl transition-all shrink-0"
                      title="Upload Document"
                    >
                      <Paperclip size={20} />
                    </button>
                    <textarea
                      ref={textareaRef}
                      value={input}
                      onChange={handleInput}
                      onKeyDown={handleKeyDown}
                      placeholder={placeholders[placeholderIndex]}
                      className="flex-1 bg-transparent border-none px-2 py-2.5 text-[15px] placeholder:text-muted-foreground focus:ring-0 focus:outline-none resize-none max-h-[200px]"
                      rows={1}
                      disabled={isLoading}
                    />
                    <ModelSelector models={availableModels} value={selectedModel} onChange={setSelectedModel} />
                    <button
                      onClick={handleSendMessage}
                      disabled={isSendDisabled}
                      className="p-2.5 bg-[#2A1F1A] hover:bg-black disabled:opacity-30 text-white rounded-xl flex items-center justify-center transition-all shrink-0"
                    >
                      <Send size={18} />
                    </button>
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.div 
                  key="chat-state"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="w-full flex flex-col gap-6"
                >
                  <AnimatePresence initial={false}>
                {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn(
                    "flex w-full",
                    (msg.role === 'user' || msg.role === 'preview') ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === 'model' && (
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mr-3 border border-primary/20 overflow-hidden">
                      <img src="/logo-t.png" alt="ADOPSHUN AI" className="w-5 h-5 object-contain" />
                    </div>
                  )}
                  
                  <div className={cn(
                    "flex flex-col gap-1 max-w-[85%]",
                    (msg.role === 'user' || msg.role === 'preview') ? "items-end" : "items-start"
                  )}>
                    
                    {msg.role === 'preview' ? (
                      <div className="bg-secondary text-foreground rounded-2xl rounded-tr-sm px-5 py-4 shadow-sm border border-border">
                        <p className="text-xs font-bold text-primary mb-2 uppercase tracking-wider flex items-center gap-1">
                          <ShieldAlert size={14} /> Preview Before Sending
                        </p>

                        {msg.fileName ? (
                          <div className="mb-4">
                            <div className="flex items-center gap-2 mb-3 pb-3 border-b border-border">
                              <Paperclip size={13} className="text-muted-foreground shrink-0" />
                              <span className="text-sm font-medium truncate">{msg.fileName}</span>
                            </div>
                            {msg.redactedTypes && msg.redactedTypes.length > 0 ? (
                              <div className="space-y-2">
                                <p className="text-xs text-muted-foreground">The following PII will be redacted before sending:</p>
                                {(() => {
                                  const seen = new Map<string, { rt: RedactedType; count: number }>();
                                  for (const rt of msg.redactedTypes!) {
                                    const key = `${rt.type}::${rt.value}`;
                                    const existing = seen.get(key);
                                    existing ? existing.count++ : seen.set(key, { rt, count: 1 });
                                  }
                                  const unique = Array.from(seen.values());
                                  return unique.map(({ rt, count }, i) => (
                                    <div key={i} className="flex items-center gap-2 text-sm">
                                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono bg-amber-50 text-amber-700 border border-amber-200 shrink-0">
                                        {rt.type.toUpperCase().replace(/ /g, '_')}
                                      </span>
                                      <span className="text-muted-foreground text-xs truncate max-w-[200px]" title={rt.value}>
                                        "{rt.value}"
                                      </span>
                                      {count > 1 && (
                                        <span className="text-[10px] font-semibold text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-1.5 py-0.5 shrink-0">
                                          ×{count}
                                        </span>
                                      )}
                                    </div>
                                  ));
                                })()}
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground">No PII detected — document is clean.</p>
                            )}
                          </div>
                        ) : (
                          <div className="text-[15px] leading-relaxed mb-4">
                            {renderMessageContent(msg.id, msg.content, msg.redactedTypes, msg.role)}
                          </div>
                        )}

                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => {
                              setMessages(prev => prev.filter(m => m.id !== msg.id));
                              if (!msg.fileName) setInput(msg.originalContent || '');
                            }}
                            className="px-4 py-2 text-sm font-medium text-foreground hover:bg-background rounded-lg transition-colors border border-transparent hover:border-border"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => {
                              setMessages(prev => prev.filter(m => m.id !== msg.id));
                              if (msg.fileName) {
                                const CHUNK_LIMIT = 100000;
                                const MAX_CHUNKS = 5;
                                const docContent = msg.tokenized || msg.content;  // prefer server-built tokens when available
                                const docVault = msg.vault;
                                const fileName = msg.fileName;
                                const pendingMsg = msg.pendingUserMessage || '';
                                if (docContent.length > CHUNK_LIMIT) {
                                  const chunks: string[] = [];
                                  for (let i = 0; i < docContent.length; i += CHUNK_LIMIT) {
                                    chunks.push(docContent.substring(i, i + CHUNK_LIMIT));
                                    if (chunks.length === MAX_CHUNKS) break;
                                  }
                                  (async () => {
                                    for (let i = 0; i < chunks.length; i++) {
                                      await executeLLM(`[Document: ${fileName} (Part ${i+1}/${chunks.length})]\n${chunks[i]}`, [], true, { vault: docVault });
                                    }
                                    if (pendingMsg.trim()) await executeLLM(pendingMsg.trim(), [], false);
                                  })();
                                } else {
                                  const docText = `[Document: ${fileName}]\n${docContent}` + (pendingMsg.trim() ? `\n\n${pendingMsg.trim()}` : '');
                                  executeLLM(docText, [], true, { vault: docVault, ...(msg.uploadBubbleId ? { existingBubbleId: msg.uploadBubbleId, keepContent: true } : {}) });
                                }
                              } else {
                                if (msg.originalContent && msg.redactedTypes && msg.redactedTypes.length > 0) {
                                  const { text: tokenized, vault } = tokenizeText(msg.originalContent, msg.redactedTypes);
                                  executeLLM(tokenized, msg.ignoredValues || [], true, { vault, displayText: msg.content });
                                } else {
                                  executeLLM(msg.content, msg.ignoredValues || [], true);
                                }
                              }
                            }}
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 rounded-lg flex items-center gap-2 transition-opacity"
                          >
                            <Send size={14} /> Approve & Send
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className={cn(
                        "rounded-2xl px-5 py-3 text-[15px] leading-relaxed relative",
                        msg.role === 'user' ? "bg-primary text-primary-foreground rounded-tr-sm shadow-sm" : "bg-card text-card-foreground rounded-tl-sm shadow-sm border border-border",
                        msg.status === 'blocked' && "bg-destructive text-destructive-foreground opacity-90"
                      )}>
                        {msg.role === 'model' ? (
                           msg.status === 'sending' ? (
                             <div className="flex items-center gap-2 text-primary py-0.5 text-[14px] font-medium">
                               <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
                                  <img src="/logo-t.png" alt="Loading" className="w-4 h-4 object-contain" />
                               </motion.div>
                               {loadingStates[loadingIndex]}
                             </div>
                           ) : (
                             <div className="prose prose-sm prose-p:leading-relaxed prose-pre:bg-muted prose-pre:text-foreground prose-a:text-primary max-w-none break-words">
                               <ReactMarkdown>{msg.content}</ReactMarkdown>
                             </div>
                           )
                        ) : (
                           <div>
                             {msg.fileUrl && msg.fileKind === 'image' && (
                               <img
                                 src={msg.fileUrl}
                                 alt={msg.fileName || 'attachment'}
                                 onClick={() => window.open(msg.fileUrl, '_blank')}
                                 className="max-h-48 rounded-lg mb-2 cursor-zoom-in border border-white/20 object-cover"
                                 title="Click to view full size"
                               />
                             )}
                             {msg.fileUrl && msg.fileKind === 'doc' && (
                               <a
                                 href={msg.fileUrl}
                                 download={msg.fileName}
                                 className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg bg-black/10 hover:bg-black/20 transition-colors no-underline"
                                 title="Click to download"
                               >
                                 <Paperclip size={15} className="shrink-0" />
                                 <span className="text-sm font-medium truncate">{msg.fileName}</span>
                               </a>
                             )}
                             {/* attachment with no extracted-text body shows just the filename label */}
                             {msg.content
                               ? renderMessageContent(msg.id, msg.content, msg.redactedTypes, msg.role, msg.status)
                               : (!msg.fileUrl && <span className="opacity-60">{msg.fileName}</span>)}
                           </div>
                        )}
                      </div>
                    )}

                    {/* Status Indicators */}
                    {msg.status === 'sending' && msg.role === 'user' && (
                      <div className="text-[11px] text-muted-foreground mt-1 flex items-center justify-end gap-1">
                        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
                           <img src="/logo-t.png" alt="Loading" className="w-3 h-3 object-contain opacity-70" />
                        </motion.div>
                        {loadingStates[loadingIndex]}
                      </div>
                    )}
                    {msg.status === 'clear' && msg.role === 'user' && (
                      <div className="text-[11px] text-green-600/80 font-medium flex items-center gap-1 mt-0.5">
                        <CheckCircle2 size={12} /> Passed
                      </div>
                    )}
                    {msg.status === 'redacted' && msg.role === 'user' && (
                      <div className="text-[11px] text-amber-600/80 font-medium flex items-center gap-1 mt-0.5">
                        <ShieldAlert size={12} /> Redacted
                      </div>
                    )}
                    {msg.status === 'blocked' && (
                       <div className="flex flex-col items-end mt-1">
                          <div className="text-[11px] text-destructive font-bold flex items-center gap-1 uppercase tracking-wider">
                            <ShieldBan size={12} /> Blocked
                          </div>
                       </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={messagesEndRef} />
            </motion.div>
            )}
            </AnimatePresence>
          </div>
        </div>

        {/* Bottom Input Area for Ongoing Chat */}
        {messages.length > 0 && (
          <div className="p-4 bg-gradient-to-t from-[#FAF9F5] via-[#FAF9F5] to-transparent pt-10">
            <div className="max-w-3xl mx-auto relative flex flex-col items-center">
              {stagedFile && (
                <div className="flex items-center gap-3 bg-[#2A1F1A] text-white rounded-2xl px-3 py-2.5 w-fit mb-3 shadow-sm self-start ml-2 relative">
                  <div className="w-9 h-9 bg-[#0084ff] rounded-xl flex items-center justify-center shrink-0">
                    <Paperclip size={18} className="text-white" />
                  </div>
                  <div className="flex flex-col pr-6">
                    <span className="text-[14px] font-bold leading-tight">{stagedFile.name}</span>
                    <span className="text-[12px] text-gray-300 leading-tight">Document</span>
                  </div>
                  <button onClick={() => setStagedFile(null)} className="absolute right-2 top-2 p-1 bg-white/20 hover:bg-white/30 rounded-full transition-colors flex items-center justify-center">
                    <X size={12} strokeWidth={3} />
                  </button>
                </div>
              )}
              <div className="relative flex flex-row items-end w-full bg-white border border-[#E0D9C8] rounded-2xl shadow-sm focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50 transition-all p-2 gap-2">
                <input type="file" ref={bottomFileInputRef} onChange={handleFileUpload} className="hidden" />
                <button 
                  onClick={() => bottomFileInputRef.current?.click()}
                  disabled={isLoading}
                  className="p-2.5 text-muted-foreground hover:bg-black/5 hover:text-foreground rounded-xl transition-all shrink-0"
                  title="Upload Document"
                >
                  <Paperclip size={20} />
                </button>
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInput}
                  onKeyDown={handleKeyDown}
                  placeholder={placeholders[placeholderIndex]}
                  className="flex-1 bg-transparent border-none px-2 py-2.5 text-[15px] placeholder:text-muted-foreground focus:ring-0 focus:outline-none resize-none max-h-[200px]"
                  rows={1}
                  disabled={isLoading}
                />
                <ModelSelector models={availableModels} value={selectedModel} onChange={setSelectedModel} />
                <button
                  onClick={handleSendMessage}
                  disabled={isSendDisabled}
                  className="p-2.5 bg-[#2A1F1A] hover:bg-black disabled:opacity-30 text-white rounded-xl flex items-center justify-center transition-all shrink-0"
                >
                  <Send size={18} />
                </button>
              </div>
              <div className="text-center mt-3">
                <p className="text-[12px] text-muted-foreground font-medium tracking-tight flex items-center justify-center gap-1.5">
                  <Shield size={12} className="text-primary/70" />
                  All messages filtered locally for PII before transmission.
                </p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
