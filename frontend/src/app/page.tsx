'use client';

import React, { useState, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Plus, PanelLeft, Send, CheckCircle2, ShieldAlert, X, ShieldBan, MessageSquare, Trash2, HatGlasses } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { driver } from "driver.js";
import "driver.js/dist/driver.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
};

type SessionInfo = {
  id: string;
  title: string;
  created_at: string;
};

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
  const [authHeader, setAuthHeader] = useState('');
  const [loginUser, setLoginUser] = useState('');
  const [loginPass, setLoginPass] = useState('');
  const [loginError, setLoginError] = useState('');
  const [keepLoggedIn, setKeepLoggedIn] = useState(false);
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [loadingIndex, setLoadingIndex] = useState(0);

  const placeholders = [
    "How can I help you today?",
    "Paste a document to check for PII...",
    "Analyze a customer complaint...",
    "Write an email draft securely...",
    "Check text for phone numbers..."
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

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    setCurrentSessionId(crypto.randomUUID());
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
    const savedAuth = localStorage.getItem('basic_auth');
    const authExpiry = localStorage.getItem('basic_auth_expiry');
    
    if (savedAuth && authExpiry) {
      if (Date.now() < parseInt(authExpiry, 10)) {
        setAuthHeader(savedAuth);
        setIsAuthenticated(true);
        loadSessions(savedAuth);
      } else {
        localStorage.removeItem('basic_auth');
        localStorage.removeItem('basic_auth_expiry');
      }
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    
    const hasSeenTour = localStorage.getItem('hasSeenTour');
    if (!hasSeenTour) {
      setTimeout(() => {
        const isMobile = window.innerWidth < 768;
        const steps = isMobile ? [
          { element: '#tour-chat-input', popover: { title: 'Secure Chat', description: 'Paste your message or text here. PII is redacted in real-time before reaching the LLM.' } },
          { element: '#tour-mobile-menu', popover: { title: 'Menu', description: 'Open the sidebar to track PII redactions, configure what to block, and see history.' } }
        ] : [
          { element: '#tour-chat-input', popover: { title: 'Secure Chat', description: 'Paste your message or text here. PII is redacted in real-time before reaching the LLM.' } },
          { element: '#tour-pii-settings', popover: { title: 'PII Settings', description: 'Toggle exactly which types of sensitive data you want to allow or block.' } },
          { element: '#tour-session-stats', popover: { title: 'Session Stats', description: 'Track how many entities were safely passed, redacted, or blocked.' } },
          { element: '#tour-new-chat', popover: { title: 'New Chat', description: 'Click here to wipe context and securely start a fresh session.' } }
        ];

        const driverObj = driver({
          showProgress: true,
          steps: steps,
          onDestroyed: () => {
            localStorage.setItem('hasSeenTour', 'true');
          }
        });
        driverObj.drive();
      }, 500);
    }
  }, [isAuthenticated]);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  };

  const loadSessions = async (overrideAuth?: string) => {
    const auth = overrideAuth || authHeader;
    if (!auth) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sessions`, {
        headers: { 'Authorization': `Basic ${auth}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Failed to load sessions', err);
    }
  };

  const loadSession = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sessions/${id}`, {
        headers: { 'Authorization': `Basic ${authHeader}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCurrentSessionId(data.id);
        setMessages(data.messages.map((m: any, i: number) => ({
          id: `db-${i}`,
          role: m.role,
          content: m.content,
          status: 'clear',
          redactedTypes: m.redacted_types
        })));
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
        headers: { 'Authorization': `Basic ${authHeader}` }
      });
      setSessions(prev => prev.filter(s => s.id !== id));
      if (currentSessionId === id) {
        startNewChat();
      }
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  const startNewChat = () => {
    setCurrentSessionId(crypto.randomUUID());
    setMessages([]);
    setInput('');
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

  const handleSendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const originalText = input.trim();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setIsLoading(true);

    const previewId = crypto.randomUUID();
    
    // Add temporary checking message
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
          'Authorization': `Basic ${authHeader}`
        },
        body: JSON.stringify({ message: originalText, session_id: currentSessionId, allowed_pii: allowedPII, ignored_values: [] })
      });
      
      const data = await res.json();
      
      setMessages(prev => prev.filter(m => m.id !== previewId));

      if (data.action === 'BLOCK') {
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'user',
          content: originalText,
          status: 'blocked'
        }]);
        setIsLoading(false);
        return;
      }

      if (data.action === 'CLEAN' || data.action === 'CLEAR') {
        await executeLLM(originalText);
        return;
      }

      // REDACT - show preview
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

  const executeLLM = async (text: string, ignoredValues: string[] = []) => {
    setIsLoading(true);
    const tempId = crypto.randomUUID();
    setMessages(prev => [...prev.filter(m => m.role !== 'preview'), { id: tempId, role: 'user', content: text, status: 'sending' }]);
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/check`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Basic ${authHeader}`
        },
        body: JSON.stringify({ message: text, session_id: currentSessionId, allowed_pii: allowedPII, ignored_values: ignoredValues })
      });

      if (!res.ok && res.status === 400) {
        setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content: text, status: 'blocked' }]);
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
                  content: data.message,
                  status: (action === 'CLEAN' || action === 'CLEAR') ? ('clear' as const) : ('redacted' as const),
                  redactedTypes: data.redacted_types
                } : m);
                return [...mapped, { id: modelMsgId, role: 'model', content: '', status: 'sending' as const }];
              });
              hasAddedModelMsg = true;
            } else if (data.type === 'chunk') {
              setMessages(prev => prev.map(m => m.id === modelMsgId ? { ...m, content: m.content + data.text, status: 'clear' as const } : m));
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
      
      loadSessions();

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

  const renderMessageContent = (msgId: string, content: string, redactedTypes?: RedactedType[], role?: string) => {
    if (!redactedTypes || redactedTypes.length === 0) {
      return content;
    }
    
    let parts: (string | React.ReactNode)[] = [content];
    
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

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');
    if (loginUser === 'admin' && loginPass === 'password') {
      const token = btoa(`${loginUser}:${loginPass}`);
      if (keepLoggedIn) {
        localStorage.setItem('basic_auth', token);
        localStorage.setItem('basic_auth_expiry', (Date.now() + 2 * 60 * 60 * 1000).toString());
      }
      setAuthHeader(token);
      setIsAuthenticated(true);
      loadSessions(token);
    } else {
      setLoginError('Invalid username or password');
    }
  };


  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#FAF9F5] font-sans text-[#2A1F1A]">
        <div className="bg-white p-8 rounded-xl shadow-lg w-full max-w-sm border border-[#E0D9C8]">
          <div className="flex justify-center mb-6 text-primary">
            <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="h-12 w-auto object-contain" />
          </div>
          <h2 className="text-2xl font-bold text-center mb-6">Secure Login</h2>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Username</label>
              <input 
                type="text" 
                value={loginUser}
                autoComplete="username"
                onChange={e => setLoginUser(e.target.value)}
                className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-primary outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Password</label>
              <input 
                type="password" 
                value={loginPass}
                autoComplete="current-password"
                onChange={e => setLoginPass(e.target.value)}
                className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-primary outline-none"
              />
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="keepLoggedIn"
                checked={keepLoggedIn}
                onChange={e => setKeepLoggedIn(e.target.checked)}
                className="w-4 h-4 text-primary rounded border-gray-300 focus:ring-primary"
              />
              <label htmlFor="keepLoggedIn" className="text-sm font-medium">Keep me logged in</label>
            </div>
            {loginError && <p className="text-red-500 text-sm text-center">{loginError}</p>}
            <button type="submit" className="w-full py-2 bg-primary text-white font-medium rounded hover:bg-primary/90 transition-colors">
              Sign In
            </button>
          </form>

          <div className="mt-6 text-center">
            <a href="/admin/login" className="text-xs text-muted-foreground hover:text-primary transition-colors inline-flex items-center gap-1">
              <ShieldAlert size={12} /> Admin Login
            </a>
          </div>
        </div>
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

          <div id="tour-pii-settings" className="p-4 border-t border-border bg-secondary/50">
            <div className="text-xs font-bold text-muted-foreground mb-3 uppercase tracking-wider">PII Settings</div>
            <div className="flex flex-col gap-2">
              {piiTypes.map(pt => (
                <label key={pt.value} className="flex items-center gap-2 text-sm text-foreground cursor-pointer group">
                  <input 
                    type="checkbox" 
                    value={pt.value}
                    checked={allowedPII.includes(pt.value)}
                    onChange={() => togglePII(pt.value)}
                    className="rounded border-border text-primary focus:ring-primary/50 w-4 h-4 accent-primary transition-all"
                  />
                  <span className="group-hover:text-primary transition-colors">{pt.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Mini Rail Content (Desktop Only) */}
        <div className={cn(
          "absolute top-0 left-0 w-[60px] h-full hidden md:flex flex-col items-center py-3 gap-4 transition-opacity duration-200",
          !isSidebarOpen ? "opacity-100 delay-100" : "opacity-0 pointer-events-none"
        )}>
          <button onClick={() => setIsSidebarOpen(true)} className="p-2 hover:bg-black/5 rounded-lg text-muted-foreground hover:text-foreground transition-all" title="Open sidebar">
            <PanelLeft size={20} />
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
            <a 
              href="/admin/login" 
              className="p-2 hover:bg-black/5 rounded-full text-muted-foreground hover:text-primary transition-colors flex items-center justify-center"
              title="Admin Login"
            >
              <HatGlasses size={20} />
            </a>
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
                  <h1 className="text-4xl font-serif text-[#2A1F1A] mb-8 flex items-center gap-3">
                  <motion.span 
                    animate={{ rotate: 360 }} 
                    transition={{ repeat: Infinity, duration: 20, ease: "linear" }}
                    className="text-[#C2543A] text-5xl font-sans inline-block origin-center"
                  >*</motion.span> {getGreeting()}
                </h1>

                {/* Centered Input Area */}
                <div className="w-full max-w-3xl relative">
                  <div id="tour-chat-input" className="relative flex flex-col w-full bg-white border border-[#E0D9C8] rounded-2xl shadow-sm focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50 transition-all">
                    <textarea
                      ref={textareaRef}
                      value={input}
                      onChange={handleInput}
                      onKeyDown={handleKeyDown}
                      placeholder={placeholders[placeholderIndex]}
                      className="w-full bg-transparent border-none px-4 pt-4 pb-2 text-[15px] placeholder:text-muted-foreground focus:ring-0 focus:outline-none resize-none min-h-[60px]"
                      rows={1}
                      disabled={isLoading}
                    />
                    <div className="flex items-center justify-end px-3 pb-3">
                      <button 
                        onClick={handleSendMessage}
                        disabled={!input.trim() || isLoading}
                        className="p-2 bg-[#2A1F1A] hover:bg-black disabled:opacity-30 text-white rounded-lg flex items-center justify-center transition-all shrink-0"
                      >
                        <Send size={16} />
                      </button>
                    </div>
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
                        <div className="text-[15px] leading-relaxed mb-4">
                           {renderMessageContent(msg.id, msg.content, msg.redactedTypes, msg.role)}
                        </div>
                        <div className="flex justify-end gap-2">
                          <button 
                            onClick={() => {
                              setMessages(prev => prev.filter(m => m.id !== msg.id));
                              setInput(msg.originalContent || '');
                            }}
                            className="px-4 py-2 text-sm font-medium text-foreground hover:bg-background rounded-lg transition-colors border border-transparent hover:border-border"
                          >
                            Cancel
                          </button>
                          <button 
                            onClick={() => {
                              setMessages(prev => prev.filter(m => m.id !== msg.id));
                              executeLLM(msg.content, msg.ignoredValues || []);
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
                        msg.status === 'blocked' && "bg-destructive text-destructive-foreground opacity-90 line-through decoration-2"
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
                           <div>{renderMessageContent(msg.id, msg.content, msg.redactedTypes, msg.role)}</div>
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
                          <div className="text-[13px] text-destructive bg-destructive/10 px-3 py-2 rounded-lg mt-1 max-w-sm text-right border border-destructive/20">
                             Transmission halted. Message contained critical PII.
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
            <div className="max-w-3xl mx-auto relative">
              <div className="relative flex flex-col w-full bg-white border border-[#E0D9C8] rounded-2xl shadow-sm focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50 transition-all">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInput}
                  onKeyDown={handleKeyDown}
                  placeholder={placeholders[placeholderIndex]}
                  className="w-full bg-transparent border-none px-4 pt-4 pb-2 text-[15px] placeholder:text-muted-foreground focus:ring-0 focus:outline-none resize-none min-h-[60px]"
                  rows={1}
                  disabled={isLoading}
                />
                <div className="flex items-center justify-end px-3 pb-3">
                  <button 
                    onClick={handleSendMessage}
                    disabled={!input.trim() || isLoading}
                    className="p-2 bg-[#2A1F1A] hover:bg-black disabled:opacity-30 text-white rounded-lg flex items-center justify-center transition-all shrink-0"
                  >
                    <Send size={16} />
                  </button>
                </div>
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
