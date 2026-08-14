import React, { useState, useEffect, useRef } from 'react';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SendIcon from '@mui/icons-material/Send';
import RefreshIcon from '@mui/icons-material/Refresh';
import ChatIcon from '@mui/icons-material/Chat';
import { useNavigate } from 'react-router-dom';

interface Client {
  id: number;
  company_name: string;
  client_name: string;
  email: string;
  phone?: string;
}

interface AgentChatConsoleProps {
  client: Client;
  domainName: string;
  pipelineMode: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  time: string;
}

export default function AgentChatConsolePage({ client, domainName, pipelineMode }: AgentChatConsoleProps) {
  console.log("Chat Console Pipeline Mode:", pipelineMode);
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState('');
  
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 1. Generate or restore Session ID on load
  useEffect(() => {
    let cachedId = localStorage.getItem('chat_session_id');
    if (!cachedId) {
      cachedId = `chat-${Math.random().toString(16).slice(2, 10)}`;
      localStorage.setItem('chat_session_id', cachedId);
    }
    setSessionId(cachedId);
  }, []);

  // 2. Load initial greeting / pitch from backend dynamically
  useEffect(() => {
    if (!sessionId || !client?.id) return;

    const fetchInitialGreeting = async () => {
      setLoading(true);
      try {
        const response = await fetch('http://localhost:8000/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            client_id: client.id,
            session_id: sessionId,
            message: '__START__'
          })
        });

        if (!response.ok) {
          throw new Error('Failed to fetch initial greeting');
        }

        const data = await response.json();
        setMessages([
          {
            id: 'greet',
            role: 'assistant',
            text: data.reply_text,
            time: new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
          }
        ]);
      } catch (err) {
        console.error(err);
        setMessages([
          {
            id: 'greet',
            role: 'assistant',
            text: `Hello! I am your ${domainName} assistant. How can I assist you today?`,
            time: new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
          }
        ]);
      } finally {
        setLoading(false);
      }
    };

    fetchInitialGreeting();
  }, [sessionId, client?.id, domainName]);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || loading) return;

    const userText = inputText.trim();
    setInputText('');

    // Append user message
    const msgId = `msg-${Date.now()}`;
    const userMsg: Message = {
      id: msgId,
      role: 'user',
      text: userText,
      time: new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
    };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          client_id: client.id,
          session_id: sessionId,
          message: userText
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned error status ${response.status}`);
      }

      const data = await response.json();

      // Append assistant reply
      const assistantMsg: Message = {
        id: `reply-${Date.now()}`,
        role: 'assistant',
        text: data.reply_text || "I'm sorry, I couldn't process that response.",
        time: new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
      };
      setMessages(prev => [...prev, assistantMsg]);

    } catch (err: any) {
      console.error(err);
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'system',
          text: `Connection Error: ${err.message}. Please check if the server is running at localhost:8000.`,
          time: new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleResetSession = () => {
    localStorage.removeItem('chat_session_id');
    const newId = `chat-${Math.random().toString(16).slice(2, 10)}`;
    localStorage.setItem('chat_session_id', newId);
    setSessionId(newId);
    
    setInputText('');
    setMessages([
      {
        id: 'greet-reset',
        role: 'assistant',
        text: `Hello! I am your ${domainName} assistant. The chat memory has been cleared. How can I help you?`,
        time: new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
      }
    ]);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 h-[calc(100vh-48px)] flex flex-col justify-between overflow-hidden">
      {/* Header section */}
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6 animate-fade-in">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-100 flex items-center gap-2.5">
            <ChatIcon sx={{ fontSize: 32, color: '#8b5cf6' }} /> Chatbot Console
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Domain:{' '}
            <span className="text-emerald-400 font-bold uppercase tracking-wider">{domainName}</span>
            {/* <span className="mx-2 text-slate-600">|</span>
            Engine Mode:{' '}
            <span className="text-violet-400 font-bold uppercase tracking-wider">
              {pipelineMode === 'multimodal' ? 'Gemini Text (Unified)' : 'Groq/Cascade Text'}
            </span> */}
          </p>
        </div>
        <Button 
          variant="outlined"
          color="inherit"
          onClick={() => navigate('/agent-mode-select')} 
          startIcon={<ArrowBackIcon />}
          className="cursor-pointer"
        >
          Back to Modes
        </Button>
      </header>

      {/* Centered Chat Window Container */}
      <div className="max-w-4xl mx-auto w-full flex-1 flex flex-col min-h-0 mb-4">
        
        <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-2xl shadow-slate-950/60 flex flex-col justify-between flex-1 min-h-0 animate-slide-up">
          
          {/* Chat room header */}
          <div className="flex justify-between items-center border-b border-slate-800/85 pb-4 select-none">
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Chat Console</h2>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wide border bg-slate-950 text-emerald-400 border-emerald-800`}>
                Online
              </span>
              <IconButton size="small" onClick={handleResetSession} title="Reset Chat session" sx={{ color: '#94a3b8' }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </div>
          </div>

          {/* Messages list (Scroll panel) */}
          <div className="flex-1 overflow-y-auto my-4 pr-1 space-y-4 min-h-0 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
            {messages.map((msg) => (
              <div 
                key={msg.id}
                className={`flex flex-col ${msg.role === 'user' ? 'items-end' : msg.role === 'system' ? 'items-center' : 'items-start'}`}
              >
                <div 
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm font-normal transition-all duration-300 ${
                    msg.role === 'user' 
                      ? 'bg-violet-600 text-[#ffffff] rounded-tr-none shadow-md shadow-violet-850/40' 
                      : msg.role === 'system'
                      ? 'bg-red-950/45 border border-red-900/50 text-red-300 font-semibold'
                      : 'bg-slate-800/60 border border-slate-700/50 text-slate-100 rounded-tl-none'
                  }`}
                >
                  <p className={`margin-0 leading-relaxed whitespace-pre-wrap ${
                    msg.role === 'user' 
                      ? 'text-[#ffffff]' 
                      : msg.role === 'system'
                      ? 'text-red-300'
                      : 'text-slate-100'
                  }`}>{msg.text}</p>
                </div>
                <span className="text-[10px] text-slate-500 mt-1 px-1">
                  {msg.role === 'user' ? 'You' : msg.role === 'system' ? 'System' : 'Agent'} • {msg.time}
                </span>
              </div>
            ))}

            {/* Typing indicator */}
            {loading && (
              <div className="flex flex-col items-start animate-pulse">
                <div className="bg-slate-800/40 border border-slate-700/30 rounded-2xl rounded-tl-none px-4 py-3 text-sm text-slate-400 flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-2.5 h-2.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-2.5 h-2.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }}></span>
                </div>
                <span className="text-[10px] text-slate-500 mt-1 px-1">Agent is typing…</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Form input bar */}
          <form onSubmit={handleSendMessage} className="flex gap-2 items-center pt-4 border-t border-slate-850 mt-auto">
            <input 
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Type your message here..."
              disabled={loading}
              className="flex-1 bg-slate-950/60 border border-slate-800/85 text-slate-100 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-violet-500 transition-all placeholder-slate-600 disabled:opacity-50"
            />
            <Button
              type="submit"
              disabled={!inputText.trim() || loading}
              variant="contained"
              color="primary"
              className="cursor-pointer"
              sx={{ py: 1.2, minWidth: 'auto', px: 2.5 }}
              endIcon={<SendIcon />}
            >
              Send
            </Button>
          </form>

        </div>
      </div>
    </div>
  );
}
