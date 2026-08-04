import React, { useState, useEffect, useRef } from 'react';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PhoneIcon from '@mui/icons-material/Phone';
import StopIcon from '@mui/icons-material/Stop';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import Autocomplete from '@mui/material/Autocomplete';
import MenuItem from '@mui/material/MenuItem';
import { useNavigate } from 'react-router-dom';
import { outreachService } from '../services/outreachService';
import { twilioService } from '../services/twilioService'; // for polling call status

const WS_BASE = 'ws://localhost:8000';

interface Country {
  code: string;
  flagUrl: string;
  name: string;
}

export default function OutreachCallConsolePage() {
  const navigate = useNavigate();
  const [countries, setCountries] = useState<Country[]>([]);
  const [selectedCountry, setSelectedCountry] = useState<Country | null>(null);
  const [localPhoneNumber, setLocalPhoneNumber] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [language, setLanguage] = useState<'en' | 'hi'>('en');
  
  const [dialing, setDialing] = useState(false);
  const [callSid, setCallSid] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState('');
  const [codeError, setCodeError] = useState('');
  const [nameError, setNameError] = useState('');

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
  const [replyText, setReplyText] = useState('—');

  const wsRef = useRef<WebSocket | null>(null);

  // Poll Twilio API status
  const startPollingStatus = (sid: string) => {
    if (pollIntervalRef.current) {
      window.clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const data = await twilioService.getCallStatus(sid);
        if (data.success) {
          const status = data.status;
          setTwilioStatus(status);

          if (status === 'in-progress') {
            setCallState('ACTIVE');
          } else if (['completed', 'failed', 'busy', 'no-answer', 'canceled'].includes(status)) {
            setCallState('ENDED');
            setCallSid(null);
            setTranscript('—');
            setReplyText('—');
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
    async function fetchCountries() {
      try {
        const res = await fetch('https://countries.dev/countries');
        if (!res.ok) throw new Error('Failed to load countries');
        const data: any[] = await res.json();

        const mapped: Country[] = data
          .map((item: any) => {
            const rawCode = item.callingCodes?.[0] || '';
            const formattedCode = rawCode ? (rawCode.startsWith('+') ? rawCode : `+${rawCode}`) : '';
            return {
              code: formattedCode,
              flagUrl: item.flags?.png || item.flags?.svg || '',
              name: item.name || '',
            };
          })
          .filter((c: Country) => c.code && c.flagUrl && c.name);

        mapped.sort((a, b) => a.name.localeCompare(b.name));

        const seen = new Set<string>();
        const uniqueMapped: Country[] = [];
        for (const c of mapped) {
          const key = `${c.code}-${c.name}`;
          if (!seen.has(key)) {
            seen.add(key);
            uniqueMapped.push(c);
          }
        }

        setCountries(uniqueMapped);

        const defaultCountry = uniqueMapped.find(
          (c) => c.code === '+91' && c.name.toLowerCase().includes('india')
        ) || uniqueMapped.find((c) => c.code === '+91') || uniqueMapped.find((c) => c.code === '+1') || uniqueMapped[0];

        setSelectedCountry(defaultCountry || null);
      } catch (err) {
        console.error('Failed to fetch country codes from API, using fallbacks:', err);
        const fallback = [
          { code: '+91', flagUrl: 'https://flagcdn.com/w320/in.png', name: 'India' },
          { code: '+1', flagUrl: 'https://flagcdn.com/w320/us.png', name: 'United States' },
          { code: '+44', flagUrl: 'https://flagcdn.com/w320/gb.png', name: 'United Kingdom' },
        ];
        setCountries(fallback);
        setSelectedCountry(fallback[0]);
      }
    }
    fetchCountries();
  }, []);

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
    setPhoneError('');
    setCodeError('');
    setNameError('');

    if (!selectedCountry) {
      setCodeError('Country code is required');
      return;
    }
    const cleanedNumber = localPhoneNumber.trim().replace(/\D/g, '');
    if (!cleanedNumber) {
      setPhoneError('Phone number is required');
      return;
    }
    if (!customerName.trim()) {
      setNameError('Customer Name is required for Outreach.');
      return;
    }

    const combinedNumber = selectedCountry.code + cleanedNumber;
    const phoneRegex = /^\+[1-9]\d{6,14}$/;
    if (!phoneRegex.test(combinedNumber)) {
      setPhoneError('Please enter a valid phone number');
      return;
    }

    setDialing(true);
    setCallState('DIALING');
    setTwilioStatus('Initiating outbound call...');

    try {
      const data = await outreachService.triggerCall({
        phone_number: combinedNumber,
        customer_name: customerName,
        language: language,
      });
      
      if (data.success) {
        setCallSid(data.call_sid);
        setStatusType('success');
        setStatusMsg(`Call successfully placed! SID: ${data.call_sid}`);
        startPollingStatus(data.call_sid);
      } else {
        setCallState('IDLE');
        setTwilioStatus('Failed');
        setStatusType('error');
        setStatusMsg(data.error || 'Failed to place call');
      }
    } catch (err: any) {
      setCallState('IDLE');
      setTwilioStatus('Error');
      setStatusType('error');
      setStatusMsg(err.message || 'Error occurred while placing call');
    } finally {
      setDialing(false);
    }
  };

  const handleHangUp = async () => {
    if (!callSid) return;
    try {
      setTwilioStatus('Hanging up...');
      await twilioService.endCall(callSid);
      setCallState('ENDED');
      setTwilioStatus('Completed');
      stopPolling();
      setCallSid(null);
    } catch (err) {
      console.error('Error ending call', err);
    }
  };

  return (
    <div className="max-w-xl mx-auto px-4 py-8">
      <header className="flex justify-between items-center mb-8 animate-fade-in">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">
            Outreach Console
          </h1>
          <p className="text-slate-400 text-xs mt-1">
            Trigger proactive outbound sales calls
          </p>
        </div>
        <Button
          variant="outlined"
          color="inherit"
          size="small"
          onClick={() => navigate('/dashboard')}
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
                <p className="text-slate-400 text-xs text-center select-none uppercase tracking-wider pb-2">
                  Enter customer details to initiate an outbound call
                </p>
                <form onSubmit={handleDialCall} className="flex flex-col gap-4">
                  <TextField
                    label="Customer Name"
                    placeholder="e.g. John Doe"
                    variant="outlined"
                    size="medium"
                    fullWidth
                    disabled={dialing}
                    value={customerName}
                    onChange={e => {
                      setCustomerName(e.target.value);
                      if (nameError) setNameError('');
                    }}
                    error={!!nameError}
                    helperText={nameError}
                    slotProps={{ inputLabel: { shrink: true } }}
                  />
                  <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-start">
                    <Autocomplete
                      id="country-code-select"
                      options={countries}
                      getOptionLabel={(option) => `${option.code} (${option.name})`}
                      value={selectedCountry}
                      onChange={(_event, newValue) => {
                        setSelectedCountry(newValue);
                        if (codeError) setCodeError('');
                      }}
                      disabled={dialing}
                      sx={{ width: { xs: '100%', sm: 140 }, flexShrink: 0 }}
                      renderOption={(props, option) => {
                        const { key, ...optionProps } = props as any;
                        return (
                          <li key={key} {...optionProps} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem' }}>
                            {option.flagUrl && (
                              <img src={option.flagUrl} alt={option.name} style={{ width: '20px', height: '14px', borderRadius: '2px', objectFit: 'cover' }} loading="lazy" />
                            )}
                            <span>{option.code}</span>
                            <span style={{ color: '#64748b', fontSize: '0.75rem' }}>({option.name})</span>
                          </li>
                        );
                      }}
                      renderInput={(params) => {
                        const p = params as any;
                        const customParams = {
                          ...params,
                          InputProps: {
                            ...p.InputProps,
                            startAdornment: (
                              <>
                                {selectedCountry && selectedCountry.flagUrl && (
                                  <img src={selectedCountry.flagUrl} alt={selectedCountry.name} style={{ width: '20px', height: '14px', borderRadius: '2px', objectFit: 'cover', marginRight: '4px' }} />
                                )}
                                {p.InputProps?.startAdornment}
                              </>
                            )
                          }
                        } as any;
                        return <TextField {...customParams} label="Country Code" size="medium" error={!!codeError} helperText={codeError} />;
                      }}
                    />

                    <TextField
                      label="Phone Number"
                      placeholder="e.g. 9876543210"
                      variant="outlined"
                      size="medium"
                      fullWidth
                      disabled={dialing}
                      value={localPhoneNumber}
                      onChange={e => {
                        setLocalPhoneNumber(e.target.value.replace(/\D/g, ''));
                        if (phoneError) setPhoneError('');
                      }}
                      error={!!phoneError}
                      helperText={phoneError}
                      slotProps={{ inputLabel: { shrink: true } }}
                    />
                  </div>

                  <TextField
                    select
                    fullWidth
                    label="Language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value as 'en' | 'hi')}
                    disabled={dialing}
                    size="medium"
                  >
                    <MenuItem value="en">English</MenuItem>
                    <MenuItem value="hi">Hindi</MenuItem>
                  </TextField>

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
                      '&:hover': { background: 'linear-gradient(to right, #047857, #0f766e)' }
                    }}
                  >
                    {dialing ? 'Calling...' : 'Dial Phone Number'}
                  </Button>
                </form>
              </>
            ) : (
              <Button
                onClick={handleHangUp}
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


        {statusMsg && (
          <Alert severity={statusType === 'success' ? 'success' : 'error'} variant="outlined" sx={{ width: '100%', mt: 2 }}>
            {statusMsg}
          </Alert>
        )}
      </div>
    </div>
  );
}
