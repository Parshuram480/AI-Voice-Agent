import React, { useState, useEffect, useRef } from 'react';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import MicIcon from '@mui/icons-material/Mic';
import StopIcon from '@mui/icons-material/Stop';
import RefreshIcon from '@mui/icons-material/Refresh';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
const WS_BASE = 'ws://localhost:8000';

interface Client {
  id: number;
  company_name: string;
  client_name: string;
  email: string;
  phone?: string;
}

interface AgentConsoleProps {
  client: Client;
  domainName: string;
  pipelineMode: string;
  onBackToDashboard: () => void;
}

interface LogEntry {
  tag: string;
  time: string;
  message: string;
}

export default function AgentConsolePage({ client, domainName, pipelineMode, onBackToDashboard }: AgentConsoleProps) {
  const [isSessionActive, setIsSessionActive] = useState(false);
  const [phase, setPhase] = useState<'IDLE' | 'LISTENING' | 'SPEECH_DETECTED' | 'ENDPOINTING' | 'PROCESSING' | 'SPEAKING' | 'INTERRUPTED' | 'ENDED'>('IDLE');
  const [stageStates, setStageStates] = useState<Record<string, 'idle' | 'active' | 'done' | 'error'>>({
    vad: 'idle',
    stt: 'idle',
    conversation: 'idle',
    llm: 'idle',
    tts: 'idle'
  });

  const [transcript, setTranscript] = useState('—');
  const [intent, setIntent] = useState('—');
  const [identityText, setIdentityText] = useState('—');
  const [recordsText, setRecordsText] = useState<React.ReactNode>('—');
  const [replyText, setReplyText] = useState('—');
  const [turn, setTurn] = useState(0);

  // Latency Metrics
  const [timings, setTimings] = useState<any>(null);

  // Debug Panel details
  const [debugSessionId, setDebugSessionId] = useState('—');
  const [debugVerified, setDebugVerified] = useState('No');
  const [debugState, setDebugState] = useState('—');

  // Logs
  const [logs, setLogs] = useState<LogEntry[]>([]);



  // Refs for Audio contexts and WS
  const wsRef = useRef<WebSocket | null>(null);
  const micAudioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const micProcessorRef = useRef<AudioWorkletNode | null>(null);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const playbackTimeRef = useRef<number>(0);
  const isSpeakingRef = useRef<boolean>(false);

  const addLog = (tag: string, message: string) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    setLogs(prev => [...prev, { tag, time, message }]);
  };

  useEffect(() => {
    addLog('system', 'Voice Agent Conversation Room ready. Click the microphone to start.');
    return () => {
      cleanupAudioAndWs();
    };
  }, []);

  const updateStage = (stage: string, status: 'idle' | 'active' | 'done' | 'error') => {
    setStageStates(prev => ({
      ...prev,
      [stage]: status
    }));
  };

  const setConsolePhase = (newPhase: any) => {
    setPhase(newPhase);
    addLog('phase', newPhase);

    if (newPhase === 'PROCESSING' || newPhase === 'SPEECH_DETECTED') {
      setStageStates({
        vad: 'idle',
        stt: 'idle',
        conversation: 'idle',
        llm: 'idle',
        tts: 'idle'
      });
      setTranscript('');
      setReplyText('');
      setTimings(null);
    }

    if (newPhase === 'LISTENING') {
      isSpeakingRef.current = false;
    }
  };

  const stopAllPlayback = () => {
    activeSourcesRef.current.forEach(src => {
      try { src.stop(); } catch (e) { }
    });
    activeSourcesRef.current = [];
    playbackTimeRef.current = 0;
    isSpeakingRef.current = false;

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'barge_in' }));
    }
  };

  const handleMicClick = async () => {
    if (isSessionActive) {
      if (phase === 'SPEAKING' || isSpeakingRef.current) {
        stopAllPlayback();
        addLog('system', 'Barge-in: stopped agent playback');
      }
      return;
    }
    await startSession();
  };

  const startSession = async () => {
    try {
      micAudioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      playbackContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 });

      await micAudioContextRef.current.audioWorklet.addModule('/audio-processor.js');

      micStreamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
      });

      micSourceRef.current = micAudioContextRef.current.createMediaStreamSource(micStreamRef.current);
      micProcessorRef.current = new AudioWorkletNode(micAudioContextRef.current, 'pcm-processor');

      const highPassFilter = micAudioContextRef.current.createBiquadFilter();
      highPassFilter.type = 'highpass';
      highPassFilter.frequency.value = 85;
      highPassFilter.Q.value = 0.7;

      const gainNode = micAudioContextRef.current.createGain();
      gainNode.gain.value = 1.1;

      let cachedSessionId = localStorage.getItem('voice_session_id');
      if (!cachedSessionId) {
        cachedSessionId = `mic-${Math.random().toString(16).slice(2, 10)}`;
        localStorage.setItem('voice_session_id', cachedSessionId);
      }

      const wsUrl = `${WS_BASE}/ws/mic-stream?session_id=${encodeURIComponent(cachedSessionId)}&client_id=${encodeURIComponent(client.id)}`;
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        addLog('system', 'Conversation session started. Speak naturally…');

        micProcessorRef.current!.port.onmessage = (event) => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && event.data.pcm) {
            wsRef.current.send(event.data.pcm);
          }
        };

        micSourceRef.current!.connect(highPassFilter);
        highPassFilter.connect(gainNode);
        gainNode.connect(micProcessorRef.current!);
      };

      socket.onmessage = handleWebSocketMessage;

      socket.onerror = () => {
        addLog('error', 'WebSocket connection error.');
        endSession();
      };

      socket.onclose = () => {
        addLog('system', 'WebSocket connection closed.');
        setIsSessionActive(false);
        setPhase('ENDED');
        setStageStates({ vad: 'idle', stt: 'idle', conversation: 'idle', llm: 'idle', tts: 'idle' });
      };

      setIsSessionActive(true);
      setTurn(0);
      setTranscript('');
      setReplyText('');
      playbackTimeRef.current = 0;
      setConsolePhase('LISTENING');

    } catch (err: any) {
      addLog('error', `Microphone capture failed: ${err.message}`);
    }
  };

  const endSession = () => {
    if (!isSessionActive) return;
    cleanupAudioAndWs();
    setIsSessionActive(false);
    setPhase('ENDED');
    addLog('system', 'Session ended.');
  };

  const resetSession = () => {
    endSession();
    localStorage.removeItem('voice_session_id');
    setTurn(0);
    setTranscript('—');
    setIntent('—');
    setIdentityText('—');
    setRecordsText('—');
    setReplyText('—');
    setDebugSessionId('—');
    setDebugVerified('No');
    setDebugState('—');
    setTimings(null);
    setLogs([]);
    addLog('system', 'Session reset. Click microphone to begin a new turn.');
  };

  const cleanupAudioAndWs = () => {
    stopAllPlayback();

    if (micSourceRef.current) {
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    if (micProcessorRef.current) {
      micProcessorRef.current.disconnect();
      micProcessorRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach(track => track.stop());
      micStreamRef.current = null;
    }
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'end_session' }));
        wsRef.current.close();
      }
      wsRef.current = null;
    }
  };

  const base64ToArrayBuffer = (base64: string) => {
    const binary_string = window.atob(base64);
    const len = binary_string.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binary_string.charCodeAt(i);
    }
    return bytes.buffer;
  };

  const playAudioChunk = (audioBuffer: AudioBuffer) => {
    if (!playbackContextRef.current) return;

    const source = playbackContextRef.current.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(playbackContextRef.current.destination);

    const currentTime = playbackContextRef.current.currentTime;
    if (playbackTimeRef.current < currentTime) {
      playbackTimeRef.current = currentTime + 0.05;
    }

    source.start(playbackTimeRef.current);
    playbackTimeRef.current += audioBuffer.duration;

    activeSourcesRef.current.push(source);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
    };
  };

  const handleWebSocketMessage = async (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'phase':
          setConsolePhase(data.phase);
          break;

        case 'stage':
          addLog(data.stage, `[${data.status.toUpperCase()}] ${data.detail}`);
          updateStage(data.stage, data.status);
          break;

        case 'stt':
          setTranscript(data.text);
          break;

        case 'llm_token':
          setReplyText(prev => (prev === '—' ? '' : prev) + data.token);
          break;

        case 'tts_audio':
          if (!playbackContextRef.current) break;
          const arrayBuffer = base64ToArrayBuffer(data.data);
          if (data.format === 'wav' || data.format === 'mp3') {
            const audioBuffer = await playbackContextRef.current.decodeAudioData(arrayBuffer);
            playAudioChunk(audioBuffer);
          } else {
            let pcm16Buffer = arrayBuffer;
            if (pcm16Buffer.byteLength % 2 !== 0) {
              pcm16Buffer = pcm16Buffer.slice(0, pcm16Buffer.byteLength - 1);
            }
            if (pcm16Buffer.byteLength === 0) break;
            const pcm16 = new Int16Array(pcm16Buffer);
            const sampleRate = data.sampleRate || 24000;
            const audioBuffer = playbackContextRef.current.createBuffer(1, pcm16.length, sampleRate);
            const channelData = audioBuffer.getChannelData(0);
            for (let i = 0; i < pcm16.length; i++) {
              channelData[i] = pcm16[i] / 32768.0;
            }
            playAudioChunk(audioBuffer);
          }
          break;

        case 'timing':
          setTimings(data.timings);
          break;

        case 'turn_done':
          setTurn(prev => prev + 1);
          const r = data.result;
          if (r) {
            setIntent(r.intent || '—');
            setDebugState(r.state || '—');
            setDebugVerified(r.verified ? 'Yes' : 'No');

            if (r.customer) {
              setIdentityText(`${r.customer.full_name} (DOB: ${r.customer.date_of_birth})`);
            } else {
              setIdentityText('—');
            }

            if (r.orders && r.orders.length > 0) {
              const elements = r.orders.map((o: any, idx: number) => {
                if (o.order_number) {
                  return <div key={idx} className="text-slate-200">#{o.order_number} — <span className="text-violet-400 font-semibold">{o.status}</span></div>;
                } else if (o.appointment_date) {
                  return <div key={idx} className="text-slate-200">{o.appointment_date} with {o.doctor_name} — <span className="text-violet-400 font-semibold">{o.status}</span></div>;
                } else {
                  return <div key={idx} className="text-slate-200">{Object.entries(o).map(([k, v]) => `${k}: ${v}`).join(', ')}</div>;
                }
              });
              setRecordsText(<div className="space-y-1">{elements}</div>);
            } else {
              setRecordsText('—');
            }

            if (r.reply_text) {
              setReplyText(r.reply_text);
            }
          }
          break;

        case 'session':
          if (data.session_id) {
            setDebugSessionId(data.session_id);
            addLog('system', `Session loaded: ${data.session_id}`);
          }
          break;

        case 'session_end':
          addLog('system', `Session ended — total turns: ${data.total_turns}`);
          setIsSessionActive(false);
          setPhase('ENDED');
          break;
      }
    } catch (e) {
      console.error('Failed to parse WS event', e);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8 animate-fade-in">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-100">
            Voice Agent Console
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            SaaS Domain:{' '}
            <span className="text-emerald-400 font-bold uppercase tracking-wider">{domainName}</span>
          </p>
        </div>
        <Button 
          variant="outlined"
          color="inherit"
          onClick={onBackToDashboard} 
          startIcon={<ArrowBackIcon />}
          className="cursor-pointer"
        >
          Back to Dashboard
        </Button>
      </header>

      <div className={`grid grid-cols-1 ${pipelineMode === 'multimodal' ? 'max-w-md mx-auto' : 'lg:grid-cols-2'} gap-6`}>
        
        {/* Panel 1: Conversation Room */}
        <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-2xl shadow-slate-950/60 flex flex-col justify-between min-h-[460px] animate-slide-up">
          <div className="flex justify-between items-center border-b border-slate-800/80 pb-4 select-none">
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Conversation Room</h2>
            <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wide transition-all duration-300 ${isSessionActive ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-slate-950 text-slate-500 border border-slate-900'}`}>
              {isSessionActive ? 'Connected' : 'Idle'}
            </span>
          </div>

          {/* Phase Dot & Label */}
          <div className="flex items-center space-x-3 bg-slate-950/40 border border-slate-850 rounded-xl p-3 my-4 select-none">
            <span className={`w-2.5 h-2.5 rounded-full transition-all duration-300
              ${phase === 'LISTENING' ? 'bg-emerald-400 shadow-lg shadow-emerald-500/50 animate-pulse' : ''} 
              ${phase === 'SPEECH_DETECTED' ? 'bg-amber-400 shadow-lg shadow-amber-500/50 animate-pulse' : ''} 
              ${phase === 'ENDPOINTING' || phase === 'PROCESSING' ? 'bg-violet-400 shadow-lg shadow-violet-500/50 animate-bounce' : ''}
              ${phase === 'SPEAKING' ? 'bg-fuchsia-400 shadow-lg shadow-fuchsia-500/50 animate-pulse' : ''}
              ${phase === 'ENDED' ? 'bg-red-500' : ''}
              ${phase === 'IDLE' ? 'bg-slate-700' : ''}
            `}></span>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
              {phase === 'IDLE' && 'Ready to start'}
              {phase === 'LISTENING' && 'Listening… speak now'}
              {phase === 'SPEECH_DETECTED' && 'Speech detected…'}
              {phase === 'ENDPOINTING' && 'Finalizing speech…'}
              {phase === 'PROCESSING' && 'Generating answer…'}
              {phase === 'SPEAKING' && 'Agent speaking… speak to interrupt'}
              {phase === 'INTERRUPTED' && 'Interrupted — listening…'}
              {phase === 'ENDED' && 'Session ended'}
            </span>
          </div>

          {/* PULSATING MIC BUTTON */}
          <div className="flex flex-col items-center justify-center py-6">
            <div className="relative">
              {/* Outer pulsing rings */}
              {(phase === 'LISTENING' || phase === 'SPEECH_DETECTED' || phase === 'SPEAKING' || phase === 'PROCESSING') && (
                <>
                  <div className="absolute inset-0 rounded-full bg-violet-600/30 scale-125 animate-ping opacity-60"></div>
                  <div className="absolute inset-0 rounded-full bg-fuchsia-600/20 scale-150 animate-pulse opacity-40"></div>
                </>
              )}
              
              <IconButton
                onClick={handleMicClick}
                className="cursor-pointer"
                sx={{
                  width: 112,
                  height: 112,
                  boxShadow: 8,
                  transition: 'transform 0.3s ease',
                  '&:hover': { transform: 'scale(1.03)' },
                  background: phase === 'LISTENING' || phase === 'SPEECH_DETECTED' || phase === 'INTERRUPTED' 
                    ? 'linear-gradient(to right, #059669, #0d9488)' 
                    : phase === 'SPEAKING' 
                    ? 'linear-gradient(to right, #c026d3, #db2777)'
                    : phase === 'PROCESSING' || phase === 'ENDPOINTING'
                    ? 'linear-gradient(to right, #7c3aed, #c026d3)'
                    : 'linear-gradient(to right, #1e293b, #334155)'
                }}
              >
                <MicIcon sx={{ fontSize: 44, color: '#f8fafc' }} />
              </IconButton>
            </div>
            
            <p className="mt-6 text-sm font-semibold text-slate-400 text-center select-none uppercase tracking-wider">
              {!isSessionActive && 'Click mic to start conversation'}
              {isSessionActive && phase === 'SPEAKING' && 'Interrupt by speaking out loud'}
              {isSessionActive && phase !== 'SPEAKING' && 'Recording audio… speak now'}
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex gap-4 justify-center pt-4 mt-auto border-t border-slate-850">
            <Button 
              onClick={endSession} 
              disabled={!isSessionActive}
              variant="contained"
              color="error"
              size="small"
              startIcon={<StopIcon />}
              className="cursor-pointer"
            >
              End Session
            </Button>
            <Button 
              onClick={resetSession} 
              variant="outlined"
              color="inherit"
              size="small"
              startIcon={<RefreshIcon />}
              className="cursor-pointer"
            >
              Reset Session
            </Button>
          </div>

          {/* Stage states pipeline */}
          <div className="flex justify-center flex-wrap gap-3 pt-6 select-none">
            {Object.entries(stageStates).map(([stage, status]) => (
              <span 
                key={stage}
                className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full uppercase tracking-wider border transition-all duration-300
                  ${status === 'active' ? 'bg-violet-950/80 text-violet-400 border-violet-700/60 animate-pulse' : ''}
                  ${status === 'done' ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60' : ''}
                  ${status === 'error' ? 'bg-red-950/80 text-red-400 border-red-850' : ''}
                  ${status === 'idle' ? 'bg-slate-950/50 text-slate-500 border-slate-900' : ''}
                `}
              >
                <FiberManualRecordIcon 
                  sx={{ 
                    fontSize: 10,
                    animation: status === 'active' ? 'pulse 1s infinite' : 'none',
                    color: status === 'active' ? '#a78bfa' : status === 'done' ? '#34d399' : status === 'error' ? '#ef4444' : '#475569'
                  }} 
                />
                {stage}
              </span>
            ))}
          </div>
        </div>

        {pipelineMode !== 'multimodal' && (
          <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-2xl shadow-slate-950/60 flex flex-col justify-between animate-slide-up">
          <div>
            <div className="flex justify-between items-center border-b border-slate-800/80 pb-4 mb-5 select-none">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Current Turn</h2>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wide bg-slate-950 text-slate-400 border border-slate-900 select-none">
                Turn {turn}
              </span>
            </div>

            <div className="divide-y divide-slate-850">
              <div className="py-3 flex flex-col sm:flex-row sm:items-start">
                <span className="w-24 text-xs font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Transcript</span>
                <span className="flex-1 text-sm font-medium text-slate-200">{transcript}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start">
                <span className="w-24 text-xs font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Intent</span>
                <span className="flex-1 text-sm font-bold text-violet-400">{intent}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start">
                <span className="w-24 text-xs font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Identity</span>
                <span className="flex-1 text-sm font-medium text-slate-200">{identityText}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start">
                <span className="w-24 text-xs font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Records</span>
                <span className="flex-1 text-sm font-medium text-slate-200">{recordsText}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start col-span-2">
                <span className="w-24 text-xs font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Reply</span>
                <span className="flex-1 text-sm font-semibold text-slate-100">{replyText}</span>
              </div>
            </div>
          </div>

          {/* Latency Timing Metrics */}
          {timings && (
            <div className="grid grid-cols-4 gap-2 pt-4 mt-6 border-t border-slate-850 text-center bg-slate-950/30 p-3 rounded-xl select-none">
              <div className="space-y-0.5">
                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider">STT</span>
                <span className="block text-xs font-semibold text-slate-300">{timings.stt_ms ? `${timings.stt_ms.toFixed(0)}ms` : '—'}</span>
              </div>
              <div className="space-y-0.5">
                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider">LLM</span>
                <span className="block text-xs font-semibold text-slate-300">{timings.llm_ms ? `${timings.llm_ms.toFixed(0)}ms` : '—'}</span>
              </div>
              <div className="space-y-0.5">
                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider">TTS</span>
                <span className="block text-xs font-semibold text-slate-300">{timings.tts_first_ms ? `${timings.tts_first_ms.toFixed(0)}ms` : '—'}</span>
              </div>
              <div className="space-y-0.5 border-l border-slate-850">
                <span className="block text-[10px] font-bold text-violet-400 uppercase tracking-wider">Total</span>
                <span className="block text-xs font-bold text-violet-400">{timings.ttfa_total_ms ? `${timings.ttfa_total_ms.toFixed(0)}ms` : '—'}</span>
              </div>
            </div>
          )}
          </div>
        )}

        {pipelineMode !== 'multimodal' && (
          <>
            {/* Panel 3: Debug Details */}
            <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-2xl shadow-slate-950/60 lg:col-span-2 select-none animate-slide-up">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div className="space-y-1">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Session ID</span>
                  <span className="block text-xs font-bold text-slate-300 font-mono break-all">{debugSessionId}</span>
                </div>
                <div className="space-y-1">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Phase</span>
                  <span className="block text-sm font-bold text-slate-300">{phase}</span>
                </div>
                <div className="space-y-1">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Verified</span>
                  <span className={`block text-sm font-bold ${debugVerified === 'Yes' ? 'text-emerald-400' : 'text-slate-400'}`}>{debugVerified}</span>
                </div>
                <div className="space-y-1">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Graph State</span>
                  <span className="block text-xs font-bold text-slate-300 font-mono">{debugState}</span>
                </div>
              </div>
            </div>

            {/* Panel 4: Live Event Logs */}
            <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-2xl shadow-slate-950/60 lg:col-span-2 animate-slide-up">
              <div className="border-b border-slate-800/80 pb-4 mb-4 select-none">
                <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Pipeline Live Logs</h2>
              </div>
              <div className="h-60 overflow-y-auto bg-slate-950/80 border border-slate-900/60 rounded-xl p-4 font-mono text-xs space-y-2 select-text">
                {logs.length === 0 ? (
                  <div className="text-slate-600 italic text-center py-20 select-none">Waiting for pipeline events…</div>
                ) : (
                  logs.map((log, idx) => (
                    <div className="flex items-start space-x-2" key={idx}>
                      <span className="text-slate-600 select-none">{log.time}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider select-none shrink-0
                        ${log.tag === 'system' ? 'bg-slate-800 text-slate-300' : ''}
                        ${log.tag === 'phase' ? 'bg-violet-950 text-violet-400' : ''}
                        ${log.tag === 'error' ? 'bg-red-950 text-red-400 border border-red-900/40' : ''}
                        ${log.tag !== 'system' && log.tag !== 'phase' && log.tag !== 'error' ? 'bg-emerald-950 text-emerald-400' : ''}
                      `}>
                        {log.tag}
                      </span>
                      <span className="text-slate-300 break-all">{log.message}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
