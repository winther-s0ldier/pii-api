
document.addEventListener("DOMContentLoaded", () => {
    let chatStarted = false;
    let currentSessionId = crypto.randomUUID();
    
    loadSessions();
    
    // Auto resize textarea
    document.body.addEventListener('input', function(e) {
        if (e.target.tagName.toLowerCase() === 'textarea') {
            e.target.style.height = 'auto';
            e.target.style.height = (e.target.scrollHeight) + 'px';
        }
    });
    
    // Rotating placeholders
    const messages = [
        "How can I help you?",
        "What's on your mind?",
        "Need help with a draft?",
        "Securely process data...",
        "Ask me anything.",
        "Check for PII..."
    ];
    let index = 0;
    setInterval(() => {
        if (!chatStarted) {
            const chatInput = document.querySelector('textarea');
            if(chatInput) chatInput.placeholder = messages[index];
            index = (index + 1) % messages.length;
        }
    }, 3000);

    const chatBaseBody = `
  <aside id="sidebar" class="w-[260px] bg-[#111111] text-white flex-col transition-all duration-300 flex border-r border-gray-800 shrink-0 relative z-20">
    <div class="p-3 flex justify-between items-center">
      <button id="new-chat-btn" class="flex items-center gap-2 hover:bg-gray-800 p-2 rounded-lg transition-colors flex-1 text-sm font-medium">
        <span class="material-symbols-outlined text-[18px]">add</span>
        New Chat
      </button>
      <button id="sidebar-close" class="p-2 hover:bg-gray-800 rounded-lg ml-1 text-gray-400">
         <span class="material-symbols-outlined text-[18px]">dock_to_right</span>
      </button>
    </div>
    <div id="sidebar-sessions" class="flex-1 overflow-y-auto p-2">
      <!-- Dynamically populated -->
    </div>
  </aside>
  <div id="main-content-wrapper" class="flex-1 flex flex-col h-screen relative min-w-0 transition-all duration-300">

<!-- Header -->
<header class="flex items-center justify-between whitespace-nowrap border-b border-solid border-border-subtle px-6 py-4 bg-surface sticky top-0 z-10 w-full">

  <div class="flex items-center gap-3 text-primary w-full px-4">
    <button id="sidebar-open" class="p-2 hover:bg-gray-200 rounded-lg text-gray-500 hidden mr-2">
        <span class="material-symbols-outlined text-[20px]">dock_to_right</span>
    </button>

<span class="material-symbols-outlined text-2xl" data-icon="shield" style="font-variation-settings: 'FILL' 1;">shield</span>

</div>
</header>
<!-- Main Chat Area -->
<main class="flex-1 overflow-y-auto w-full relative">
<div class="max-w-[768px] mx-auto w-full px-4 pt-8 pb-4 flex flex-col gap-8">
</div>
</main>
<!-- Input Bar Area -->
<div class="w-full shrink-0 pt-4 pb-6 px-4 pointer-events-none z-10 bg-background-light">
<div class="max-w-[768px] mx-auto w-full pointer-events-auto">
<div class="relative flex items-center w-full bg-surface border border-border-subtle rounded-lg shadow-input focus-within:border-primary focus-within:ring-1 focus-within:ring-primary transition-all duration-200" style="background-color: white;">
<textarea class="w-full bg-transparent border-none rounded-lg px-4 py-4 text-[15px] placeholder:text-muted focus:ring-0 focus:outline-none resize-none py-[15px] leading-tight"      placeholder="Type your secure message..." rows="1" style="max-height: 150px; overflow-y: auto;"></textarea>
<button class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-primary hover:bg-blue-700 text-white rounded flex items-center justify-center transition-colors duration-200 shrink-0">
<span class="material-symbols-outlined" data-icon="arrow_upward">arrow_upward</span>
</button>
</div>
<div class="text-center mt-2">
<p class="text-[11px] text-muted font-mono tracking-tight flex items-center justify-center gap-1" style="color: #64748b;">
<span class="material-symbols-outlined text-[12px]" data-icon="lock" style="font-variation-settings: 'FILL' 1;">lock</span>
                    All messages filtered locally for PII before transmission.
                </p>
</div>
</div>
</div>
</div>`;

    const parseMarkdown = (text) => {
        if (!text) return "I am the pseudo LLM. I received your message securely.";
        return typeof marked !== 'undefined' ? marked.parse(text) : text;
    };

    const createClearBubble = (text, llm_reply) => `
<div class="flex flex-col items-end w-full group">
<div class="max-w-[80%] flex flex-col items-end gap-2 relative">
<div class="bg-white text-[#2B2B2B] border border-[#E5E5E5] rounded-lg rounded-tr-sm px-5 py-3 shadow-sm relative">
<p class="text-[15px] leading-relaxed">${text}</p>
</div>
<div class="tooltip-group relative flex items-center justify-end -mt-1">
<div class="flex items-center gap-1 bg-status-clear-bg text-status-clear-fg px-2 py-0.5 rounded text-[11px] font-medium tracking-wide">
<span class="material-symbols-outlined text-[14px]" data-icon="check_circle" style="font-variation-settings: 'FILL' 1;">check_circle</span>
Passed
</div>
<div class="tooltip absolute bottom-full right-0 mb-2 w-max bg-gray-900 text-white text-xs py-1 px-2 rounded opacity-0 invisible transition-opacity duration-200 pointer-events-none z-20">
No PII detected. Sent securely.
<svg class="absolute text-gray-900 h-2 left-1/2 -ml-1 top-full" viewbox="0 0 255 255" x="0px" xml:space="preserve" y="0px"><polygon class="fill-current" points="0,0 127.5,127.5 255,0"></polygon></svg>
</div>
</div>
</div>
</div>
<div class="flex flex-col items-start w-full">
<div class="max-w-[80%] flex items-start gap-3">
<div class="w-8 h-8 rounded bg-[#F3F2F1] flex items-center justify-center shrink-0 border border-[#E5E5E5]">
<span class="material-symbols-outlined text-[#8C8C8C] text-sm" data-icon="smart_toy">smart_toy</span>
</div>
<div class="bg-white text-[#2B2B2B] border border-[#E5E5E5] rounded-lg rounded-tl-sm px-5 py-3 shadow-sm">
<div class="prose prose-sm prose-slate max-w-none text-[15px] leading-relaxed">${parseMarkdown(llm_reply)}</div>
</div>
</div>
</div>
    `;

    const createRedactedBubble = (maskedMsg, redacted_types, llm_reply) => {
        let formatted = maskedMsg;
        if (redacted_types && redacted_types.length > 0) {
            redacted_types.forEach(rt => {
                const cleanLabel = rt.type.toUpperCase().replace(/ /g, '_');
                const searchStr = `[${cleanLabel}]`;
                formatted = formatted.replace(searchStr, `<span class="redacted-mono inline-flex items-center text-[#D97706] bg-[#FEF3C7] px-1.5 py-0.5 rounded-[4px] mx-1 text-[13px] border border-[#D97706]/20 align-baseline cursor-help" title="Original: ${rt.value}">[${cleanLabel}]</span>`);
            });
        } else {
            formatted = maskedMsg.replace(/\[([^\]]+)\]/g, '<span class="redacted-mono inline-flex items-center text-[#D97706] bg-[#FEF3C7] px-1.5 py-0.5 rounded-[4px] mx-1 text-[13px] border border-[#D97706]/20 align-baseline">[$1]</span>');
        }
        return `
<div class="flex flex-col items-end w-full group">
<div class="max-w-[80%] flex flex-col items-end gap-2 relative">
<div class="bg-white text-[#2B2B2B] border border-[#E5E5E5] rounded-lg rounded-tr-sm px-5 py-3 shadow-sm relative">
<p class="text-[15px] leading-relaxed text-[#2B2B2B]">${formatted}</p>
</div>
<div class="has-tooltip relative flex items-center gap-1 bg-[#FEF3C7] text-[#D97706] px-2 py-1 rounded text-[11px] font-medium border border-[#D97706]/20 cursor-help">
<span class="material-symbols-outlined text-[14px]">shield</span>
<span>Redacted</span>
</div>
</div>
</div>
<div class="flex flex-col items-start w-full">
<div class="max-w-[80%] flex items-start gap-3">
<div class="w-8 h-8 rounded bg-[#F3F2F1] flex items-center justify-center shrink-0 border border-[#E5E5E5]">
<span class="material-symbols-outlined text-[#8C8C8C] text-sm" data-icon="smart_toy">smart_toy</span>
</div>
<div class="bg-white text-[#2B2B2B] border border-[#E5E5E5] rounded-lg rounded-tl-sm px-5 py-3 shadow-sm">
<div class="prose prose-sm prose-slate max-w-none text-[15px] leading-relaxed">${parseMarkdown(llm_reply)}</div>
</div>
</div>
</div>
        `;
    };

    const createBlockedBubble = (text) => `
<div class="flex flex-col items-end w-full group">
<div class="max-w-[80%] flex flex-col items-end gap-2 relative">
<div class="bg-white text-[#2B2B2B] border border-[#E5E5E5] rounded-lg rounded-tr-sm px-5 py-3 shadow-sm relative">
<p class="text-[15px] leading-relaxed text-[#8C8C8C] line-through decoration-[#8C8C8C] decoration-2">${text}</p>
</div>
<div class="absolute -bottom-3 right-2 flex items-center gap-1 bg-[#FEE2E2] px-2 py-0.5 rounded border border-[#DC2626]/20 shadow-sm z-10">
<span class="material-symbols-outlined text-[14px] text-[#DC2626]" style="font-variation-settings: 'FILL' 1;">dangerous</span>
<span class="text-[11px] font-bold uppercase tracking-wider text-[#DC2626]">Blocked</span>
</div>
</div>
</div>
<div class="flex flex-col items-start w-full mt-2">
<p class="text-[#DC2626] text-[13px] font-medium ml-1 flex items-center gap-1 mb-1">
<span class="material-symbols-outlined text-[14px]">shield</span>
System Intervention
</p>
<div class="bg-surface border border-[#DC2626]/30 rounded-lg rounded-tl-sm px-4 py-3 max-w-[80%] shadow-sm relative overflow-hidden" style="background-color: white;">
<div class="absolute top-0 left-0 w-1 h-full bg-[#DC2626]"></div>
<p class="text-[15px] leading-relaxed text-[#DC2626] font-medium pl-2">
Transmission halted. Message contained critical PII. Incident logged.
</p>
</div>
</div>
        `;

    // Use event delegation for input and buttons since DOM changes
    document.body.addEventListener('click', async (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        
        if (btn.id === 'new-chat-btn') {
            window.location.reload();
            return;
        }
        
        if (btn.classList.contains('session-btn')) {
            const sid = btn.getAttribute('data-id');
            await loadSession(sid);
            return;
        }

        if (btn.querySelector('span') && btn.querySelector('span').textContent.includes('arrow_upward')) {
            const input = document.querySelector('textarea');
            if (input) {
                await handleSendMessage(input);
            }
        }

        if (btn.id === 'sidebar-open') {
            const sidebar = document.getElementById('sidebar');
            if (sidebar) {
                sidebar.style.marginLeft = '0px';
                btn.classList.add('hidden');
            }
        }

        if (btn.id === 'sidebar-close') {
            const sidebar = document.getElementById('sidebar');
            const openBtn = document.getElementById('sidebar-open');
            if (sidebar) {
                sidebar.style.marginLeft = '-260px';
                if (openBtn) openBtn.classList.remove('hidden');
            }
        }
    });
    
    document.body.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey && e.target.tagName === 'TEXTAREA') {
            e.preventDefault(); // Prevent new line
            await handleSendMessage(e.target);
        }
    });

    async function handleSendMessage(inputEl) {
        const text = inputEl.value.trim();
        if (!text) return;
        
        inputEl.value = '';
        inputEl.disabled = true;

        if (!chatStarted) {
            chatStarted = true;
            document.body.className = "font-body h-screen flex antialiased bg-background-light overflow-hidden";
            document.body.innerHTML = chatBaseBody;
            // The input field got replaced! We need to find the new one to refocus/enable
            loadSessions();
        }
        
        const tempId = 'temp-' + Date.now();
        const chatContainer = document.querySelector('main > div');
        if (chatContainer) {
            chatContainer.insertAdjacentHTML('beforeend', `<div id="${tempId}" class="flex flex-col items-end w-full group mb-4">
<div class="max-w-[80%] flex flex-col items-end gap-2 relative">
<div class="bg-surface text-text-main border border-border-subtle rounded-lg rounded-tr-sm px-5 py-3 shadow-sm relative opacity-50">
<p class="text-[15px] leading-relaxed">${text}</p>
</div>
<div class="text-[11px] text-gray-500 mt-1 flex items-center gap-1"><span class="material-symbols-outlined text-[12px] animate-spin">sync</span> Securing & transmitting...</div>
</div></div>`);
            document.querySelector('main').scrollTop = document.querySelector('main').scrollHeight;
        }

        try {
            const res = await fetch('/api/v1/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, session_id: currentSessionId })
            });
            
            const tempBubble = document.getElementById(tempId);
            
            if (!res.ok && res.status === 400) {
                const data = await res.json();
                if (tempBubble) tempBubble.remove();
                const currentChatContainer = document.querySelector('main > div');
                if(currentChatContainer) {
                    currentChatContainer.insertAdjacentHTML('beforeend', createBlockedBubble(text));
                    document.querySelector('main').scrollTop = document.querySelector('main').scrollHeight;
                }
                loadSessions();
                return;
            }
            
            if (tempBubble) tempBubble.remove();
            
            const reader = res.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = '';
            
            let action = '';
            let maskedMsg = '';
            let redacted_types = [];
            let fullReply = '';
            
            const chatContainer = document.querySelector('main > div');
            let bubbleWrapper = document.createElement('div');
            bubbleWrapper.className = 'w-full mb-4 flex flex-col gap-4';
            if (chatContainer) chatContainer.appendChild(bubbleWrapper);
            
            let updatePending = false;
            
            while (true) {
                const {done, value} = await reader.read();
                if (done) {
                    // Final update
                    const proseDiv = bubbleWrapper.querySelector('.prose');
                    if (proseDiv) {
                        proseDiv.innerHTML = parseMarkdown(fullReply);
                    }
                    break;
                }
                
                buffer += decoder.decode(value, {stream: true});
                let boundary = buffer.indexOf('\n\n');
                
                while (boundary !== -1) {
                    const messageStr = buffer.slice(0, boundary);
                    buffer = buffer.slice(boundary + 2);
                    
                    if (messageStr.startsWith('data: ')) {
                        const data = JSON.parse(messageStr.slice(6));
                        
                        if (data.type === 'metadata') {
                            action = data.action;
                            maskedMsg = data.message;
                            redacted_types = data.redacted_types;
                            
                            let initialHtml = '';
                            const typingIndicator = '<span class="inline-block w-1.5 h-4 ml-1 bg-gray-400 animate-pulse align-middle"></span>';
                            if (action === 'CLEAN' || action === 'CLEAR') {
                                initialHtml = createClearBubble(text, typingIndicator);
                            } else {
                                initialHtml = createRedactedBubble(maskedMsg || text, redacted_types, typingIndicator);
                            }
                            bubbleWrapper.innerHTML = initialHtml;
                            document.querySelector('main').scrollTop = document.querySelector('main').scrollHeight;
                            loadSessions();
                        } else if (data.type === 'chunk' || data.type === 'error') {
                            fullReply += data.text;
                            if (!updatePending) {
                                updatePending = true;
                                requestAnimationFrame(() => {
                                    const proseDiv = bubbleWrapper.querySelector('.prose');
                                    if (proseDiv) {
                                        proseDiv.innerHTML = parseMarkdown(fullReply) + '<span class="inline-block w-1.5 h-4 ml-1 bg-gray-400 animate-pulse align-middle"></span>';
                                        
                                        const main = document.querySelector('main');
                                        if (main.scrollHeight - main.scrollTop - main.clientHeight < 200) {
                                            main.scrollTop = main.scrollHeight;
                                        }
                                    }
                                    updatePending = false;
                                });
                            }
                        } else if (data.type === 'done') {
                            const proseDiv = bubbleWrapper.querySelector('.prose');
                            if (proseDiv) {
                                proseDiv.innerHTML = parseMarkdown(fullReply);
                            }
                        }
                    }
                    boundary = buffer.indexOf('\n\n');
                }
            }
        } catch (e) {
            console.error(e);
            alert('Error calling backend: ' + e.message);
        } finally {
            const newInput = document.querySelector('textarea');
            if(newInput) {
                newInput.disabled = false;
                newInput.focus();
            }
        }
    }
    
    async function loadSessions() {
        try {
            const res = await fetch('/api/v1/sessions');
            if (!res.ok) return;
            const data = await res.json();
            const container = document.getElementById('sidebar-sessions');
            if (!container) return;
            
            let html = '<div class="text-xs font-semibold text-gray-500 mb-2 mt-4 px-2">History</div>';
            data.sessions.forEach(s => {
                html += `<button class="session-btn w-full text-left p-2 hover:bg-gray-800 rounded-lg text-sm truncate text-gray-300" data-id="${s.id}">${s.title}</button>`;
            });
            container.innerHTML = html;
        } catch (e) {
            console.error('Failed to load sessions', e);
        }
    }
    
    async function loadSession(id) {
        currentSessionId = id;
        try {
            const res = await fetch(`/api/v1/sessions/${id}`);
            if (!res.ok) return;
            const data = await res.json();
            
            chatStarted = true;
            document.body.className = "font-body h-screen flex antialiased bg-background-light overflow-hidden";
            document.body.innerHTML = chatBaseBody;
            
            await loadSessions(); // re-populate since innerHTML wiped it
            
            const chatContainer = document.querySelector('main > div');
            if (!chatContainer) return;
            
            let html = '';
            for (let i = 0; i < data.messages.length; i += 2) {
                let userMsg = data.messages[i].content;
                let modelMsg = (i + 1 < data.messages.length) ? data.messages[i+1].content : "";
                
                // For historical messages, we just render them as simple clear bubbles for now.
                // You can still see the [REDACTED] tags visually in the text if they were redacted!
                html += createClearBubble(userMsg, modelMsg);
            }
            
            chatContainer.innerHTML = html;
            document.querySelector('main').scrollTop = document.querySelector('main').scrollHeight;
            
            const newInput = document.querySelector('textarea');
            if(newInput) {
                newInput.disabled = false;
                newInput.focus();
            }
        } catch (e) {
            console.error('Failed to load session history', e);
        }
    }
});
