import { useState, useEffect, useRef } from 'react';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PhoneIcon from '@mui/icons-material/Phone';
import StopIcon from '@mui/icons-material/Stop';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000';

interface Client {
  id: number;
  company_name: string;
  client_name: string;
  email: string;
  phone?: string;
}

interface AgentCallConsoleProps {
  client: Client;
  domainName: string;
  pipelineMode: string;
  onBackToDashboard: () => void;
}

export default function AgentCallConsolePage({ client, domainName, pipelineMode, onBackToDashboard }: AgentCallConsoleProps) {
  const [dialPhoneNumber, setDialPhoneNumber] = useState('');
  const [dialing, setDialing] = useState(false);
  const [callSid, setCallSid] = useState<string | null>(null);
  
  // Call status options: 'IDLE' | 'DIALING' | 'ACTIVE' | 'ENDED'
  const [callState, setCallState] = useState<'IDLE' | 'DIALING' | 'ACTIVE' | 'ENDED'>('IDLE');
  const [twilioStatus, setTwilioStatus] = useState('Idle');
  
  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState<'success' | 'error' | ''>('');
  
  const pollIntervalRef = useRef<number | null>(null);

  // Live WebSocket state variables
  const [consolePhase, setConsolePhase] = useState<'IDLE' | 'LISTENING' | 'SPEECH_DETECTED' | 'ENDPOINTING' | 'PROCESSING' | 'SPEAKING' | 'INTERRUPTED' | 'ENDED'>('IDLE');
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

  const wsRef = useRef<WebSocket | null>(null);

  // Poll Twilio API status
  const startPollingStatus = (sid: string) => {
    if (pollIntervalRef.current) {
      window.clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/twilio/call/${sid}`);
        const data = await response.json();
        if (response.ok && data.success) {
          const status = data.status; // e.g. queued, ringing, in-progress, completed, failed
          setTwilioStatus(status);

          if (status === 'in-progress') {
            setCallState('ACTIVE');
          } else if (['completed', 'failed', 'busy', 'no-answer', 'canceled'].includes(status)) {
            setCallState('ENDED');
            setCallSid(null);
            setTranscript('—');
            setReplyText('—');
            setIntent('—');
            setIdentityText('—');
            setRecordsText('—');
            setConsolePhase('ENDED');
            setStageStates({
              vad: 'idle',
              stt: 'idle',
              conversation: 'idle',
              llm: 'idle',
              tts: 'idle'
            });
            stopPolling();
          } else if (['queued', 'ringing'].includes(status)) {
            setCallState('DIALING');
          }
        }
      } catch (err) {
        console.error('Error polling call status:', err);
      }
    }, 2000);
  };

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      window.clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, []);

  // Listen to live pipeline logs for the Call Session
  useEffect(() => {
    if (!callSid) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    const wsUrl = `${WS_BASE}/ws/mic-stream?session_id=${encodeURIComponent(callSid)}&listener=true`;
    console.log('Connecting listener websocket to:', wsUrl);
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      console.log('Listener websocket connected.');
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Listener received event:', data);
        
        switch (data.type) {
          case 'phase':
            setConsolePhase(data.phase);
            if (data.phase === 'PROCESSING' || data.phase === 'SPEECH_DETECTED') {
              setStageStates({
                vad: 'idle',
                stt: 'idle',
                conversation: 'idle',
                llm: 'idle',
                tts: 'idle'
              });
              setTranscript('');
              setReplyText('');
            }
            break;

          case 'stage':
            setStageStates(prev => ({
              ...prev,
              [data.stage]: data.status
            }));
            break;

          case 'stt':
            setTranscript(data.text);
            break;

          case 'llm_token':
            setReplyText(prev => (prev === '—' ? '' : prev) + data.token);
            break;

          case 'turn_done':
            setTurn(prev => prev + 1);
            const r = data.result;
            if (r) {
              setIntent(r.intent || '—');
              if (r.customer) {
                setIdentityText(`${r.customer.full_name} (DOB: ${r.customer.date_of_birth})`);
              } else {
                setIdentityText('—');
              }
              if (r.orders && r.orders.length > 0) {
                if (domainName.toLowerCase() === 'healthcare') {
                  setRecordsText(
                    <div className="space-y-2 mt-1">
                      {r.orders.map((apt: any, idx: number) => (
                        <div key={idx} className="bg-slate-950/60 border border-slate-850 p-2.5 rounded-lg text-xs flex flex-col gap-1">
                          <div className="flex justify-between font-bold text-slate-300">
                            <span>Doctor: {apt.doctor_name}</span>
                            <span className="text-emerald-400 font-normal">{apt.status}</span>
                          </div>
                          <div className="text-slate-400 font-mono text-[10px]">Date: {apt.appointment_date}</div>
                          <div className="text-slate-400 italic">Reason: {apt.reason}</div>
                        </div>
                      ))}
                    </div>
                  );
                } else {
                  setRecordsText(
                    <div className="space-y-2 mt-1">
                      {r.orders.map((ord: any, idx: number) => (
                        <div key={idx} className="bg-slate-950/60 border border-slate-850 p-2.5 rounded-lg text-xs flex flex-col gap-1">
                          <div className="flex justify-between font-bold text-slate-300">
                            <span>Order #{ord.order_number}</span>
                            <span className="text-emerald-400 font-normal">{ord.status}</span>
                          </div>
                          <div className="text-slate-400 font-mono text-[10px]">Arrival: {ord.estimated_arrival}</div>
                          <div className="text-slate-400 italic">Items: {ord.items_summary}</div>
                        </div>
                      ))}
                    </div>
                  );
                }
              } else {
                setRecordsText('—');
              }
            }
            break;

          default:
            break;
        }
      } catch (err) {
        console.error('Error parsing listener message:', err);
      }
    };

    socket.onclose = () => {
      console.log('Listener websocket closed.');
    };

    return () => {
      socket.close();
      wsRef.current = null;
    };
  }, [callSid]);

  const handleDialCall = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMsg('');
    setStatusType('');
    setDialing(true);
    setCallState('DIALING');
    setTwilioStatus('Initiating outbound call...');

    try {
      const response = await fetch(`${API_BASE}/api/twilio/call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          phone_number: dialPhoneNumber,
          client_id: client.id 
        }),
        credentials: 'include'
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setCallSid(data.call_sid);
        setStatusType('success');
        setStatusMsg(`Call successfully placed! SID: ${data.call_sid}`);
        startPollingStatus(data.call_sid);
      } else {
        setCallState('IDLE');
        setTwilioStatus('Failed');
        setStatusType('error');
        setStatusMsg(data.detail || 'Failed to place call.');
      }
    } catch (err: any) {
      setCallState('IDLE');
      setTwilioStatus('Error');
      setStatusType('error');
      setStatusMsg('Error placing call: ' + err.message);
    } finally {
      setDialing(false);
    }
  };

  const handleEndCall = async () => {
    if (!callSid) return;
    setTwilioStatus('Hanging up...');

    try {
      const response = await fetch(`${API_BASE}/api/twilio/call/${callSid}/end`, {
        method: 'POST'
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setCallState('ENDED');
        setCallSid(null);
        setTranscript('—');
        setReplyText('—');
        setIntent('—');
        setIdentityText('—');
        setRecordsText('—');
        setConsolePhase('IDLE');
        setStageStates({
          vad: 'idle',
          stt: 'idle',
          conversation: 'idle',
          llm: 'idle',
          tts: 'idle'
        });
        setTwilioStatus('completed');
        setStatusType('success');
        setStatusMsg('Call successfully terminated.');
      } else {
        setStatusType('error');
        setStatusMsg('Failed to terminate call.');
      }
    } catch (err: any) {
      setStatusType('error');
      setStatusMsg('Error ending call: ' + err.message);
    } finally {
      stopPolling();
    }
  };

  return (
    <div className="max-w-xl mx-auto px-4 py-8">
      <header className="flex justify-between items-center mb-8 animate-fade-in">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">
            Voice Agent Dialer
          </h1>
          <p className="text-slate-400 text-xs mt-1">
            SaaS Domain: <span className="text-emerald-400 font-bold uppercase tracking-wider">{domainName}</span>
          </p>
        </div>
        <Button 
          variant="outlined"
          color="inherit"
          size="small"
          onClick={onBackToDashboard} 
          startIcon={<ArrowBackIcon />}
          className="cursor-pointer"
        >
          Back
        </Button>
      </header>

      {/* Centered Conversation Room Card */}
      <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-2xl shadow-slate-950/60 flex flex-col justify-between min-h-[350px] animate-slide-up space-y-6">
        <div className="flex justify-between items-center border-b border-slate-800/80 pb-4 select-none">
          <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Conversation Room</h2>
          <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wide transition-all duration-300
            ${callState === 'ACTIVE' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : ''}
            ${callState === 'DIALING' ? 'bg-amber-950 text-amber-400 border border-amber-800 animate-pulse' : ''}
            ${callState === 'ENDED' ? 'bg-red-950 text-red-400 border border-red-800' : ''}
            ${callState === 'IDLE' ? 'bg-slate-950 text-slate-500 border border-slate-900' : ''}
          `}>
            {callState === 'IDLE' && 'Idle'}
            {callState === 'DIALING' && 'Calling'}
            {callState === 'ACTIVE' && 'Active Call'}
            {callState === 'ENDED' && 'Ended'}
          </span>
        </div>

        {/* Status Indicator */}
        <div className="flex items-center space-x-3 bg-slate-950/40 border border-slate-850 rounded-xl p-3 select-none">
          <span className={`w-2.5 h-2.5 rounded-full transition-all duration-300
            ${callState === 'DIALING' ? 'bg-amber-400 shadow-lg shadow-amber-500/50 animate-pulse' : ''} 
            ${callState === 'ACTIVE' ? 'bg-emerald-400 shadow-lg shadow-emerald-500/50 animate-pulse' : ''}
            ${callState === 'ENDED' ? 'bg-red-500' : ''}
            ${callState === 'IDLE' ? 'bg-slate-700' : ''}
          `}></span>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide flex-1">
            Twilio Status: <span className="text-slate-200 normal-case font-mono">{twilioStatus}</span>
          </span>
          {callState === 'ACTIVE' && (
            <div className="flex items-center space-x-1.5">
              <span className={`w-2 h-2 rounded-full transition-all duration-300
                ${consolePhase === 'LISTENING' ? 'bg-emerald-400 shadow-lg shadow-emerald-500/50 animate-pulse' : ''} 
                ${consolePhase === 'SPEECH_DETECTED' ? 'bg-amber-400 shadow-lg shadow-amber-500/50 animate-pulse' : ''} 
                ${consolePhase === 'ENDPOINTING' || consolePhase === 'PROCESSING' ? 'bg-violet-400 shadow-lg shadow-violet-500/50 animate-bounce' : ''}
                ${consolePhase === 'SPEAKING' ? 'bg-fuchsia-400 shadow-lg shadow-fuchsia-500/50 animate-pulse' : ''}
                ${consolePhase === 'ENDED' ? 'bg-red-500' : ''}
                ${consolePhase === 'IDLE' ? 'bg-slate-700' : ''}
              `}></span>
              <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">
                {consolePhase}
              </span>
            </div>
          )}
        </div>

        {/* Input Form & Buttons */}
        <div className="flex flex-col items-center justify-center py-2 space-y-4">
          <div className="w-full space-y-3">
            {callState === 'IDLE' || callState === 'ENDED' ? (
              <>
                <p className="text-slate-400 text-xs text-center select-none uppercase tracking-wider">
                  Dial a number to query agent domain records via call
                </p>
                <form onSubmit={handleDialCall} className="space-y-4">
                  <TextField
                    label="Destination Phone Number"
                    placeholder="+15550199"
                    variant="outlined"
                    fullWidth
                    required
                    disabled={dialing}
                    value={dialPhoneNumber}
                    onChange={e => setDialPhoneNumber(e.target.value)}
                    slotProps={{ inputLabel: { shrink: true } }}
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    color="success"
                    size="large"
                    fullWidth
                    disabled={dialing}
                    startIcon={dialing ? <CircularProgress size={20} color="inherit" /> : <PhoneIcon />}
                    sx={{
                      py: 1.5,
                      background: 'linear-gradient(to right, #059669, #0d9488)',
                      '&:hover': {
                        background: 'linear-gradient(to right, #047857, #0f766e)',
                      }
                    }}
                  >
                    {dialing ? 'Calling...' : 'Dial Phone Number'}
                  </Button>
                </form>
              </>
            ) : (
              <Button
                onClick={handleEndCall}
                variant="contained"
                color="error"
                size="large"
                fullWidth
                startIcon={<StopIcon />}
                sx={{ py: 1.5 }}
              >
                End Call Session
              </Button>
            )}
          </div>
        </div>

        {/* Live Conversation Transcript Panel */}
        {callState === 'ACTIVE' && pipelineMode !== 'multimodal' && (
          <div className="border-t border-slate-800/80 pt-4 space-y-4">
            <div className="flex justify-between items-center select-none">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Live Call Logs</h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide bg-slate-950 text-slate-500 border border-slate-900 select-none">
                Turn {turn}
              </span>
            </div>

            <div className="divide-y divide-slate-850 bg-slate-950/40 border border-slate-850/80 rounded-xl p-4 space-y-3">
              <div className="pb-3 flex flex-col sm:flex-row sm:items-start border-b border-slate-850">
                <span className="w-20 text-[10px] font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Transcript</span>
                <span className="flex-1 text-xs font-semibold text-slate-200">{transcript}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start border-b border-slate-850">
                <span className="w-20 text-[10px] font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Reply</span>
                <span className="flex-1 text-xs font-semibold text-emerald-400">{replyText}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start border-b border-slate-850">
                <span className="w-20 text-[10px] font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Intent</span>
                <span className="flex-1 text-xs font-bold text-violet-400">{intent}</span>
              </div>
              <div className="py-3 flex flex-col sm:flex-row sm:items-start border-b border-slate-850">
                <span className="w-20 text-[10px] font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Identity</span>
                <span className="flex-1 text-xs font-semibold text-slate-200">{identityText}</span>
              </div>
              <div className="pt-3 flex flex-col sm:flex-row sm:items-start">
                <span className="w-20 text-[10px] font-bold text-slate-500 uppercase tracking-wider sm:pt-0.5 mb-1 sm:mb-0 select-none">Records</span>
                <div className="flex-1 text-xs font-semibold text-slate-200">{recordsText}</div>
              </div>
            </div>

            {/* Stage states pipeline */}
            <div className="flex justify-center flex-wrap gap-2 pt-2 select-none">
              {Object.entries(stageStates).map(([stage, status]) => (
                <span 
                  key={stage}
                  className={`inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider border transition-all duration-300
                    ${status === 'active' ? 'bg-violet-950/80 text-violet-400 border-violet-700/60 animate-pulse' : ''}
                    ${status === 'done' ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60' : ''}
                    ${status === 'error' ? 'bg-red-950/80 text-red-400 border-red-850' : ''}
                    ${status === 'idle' ? 'bg-slate-950/50 text-slate-500 border-slate-900' : ''}
                  `}
                >
                  <FiberManualRecordIcon 
                    sx={{ 
                      fontSize: 8,
                      animation: status === 'active' ? 'pulse 1s infinite' : 'none',
                      color: status === 'active' ? '#a78bfa' : status === 'done' ? '#34d399' : status === 'error' ? '#ef4444' : '#475569'
                    }} 
                  />
                  {stage}
                </span>
              ))}
            </div>
          </div>
        )}

        {statusMsg && (
          <Alert severity={statusType === 'success' ? 'success' : 'error'} variant="outlined" sx={{ width: '100%', mt: 2 }}>
            {statusMsg}
          </Alert>
        )}
      </div>
    </div>
  );
}
