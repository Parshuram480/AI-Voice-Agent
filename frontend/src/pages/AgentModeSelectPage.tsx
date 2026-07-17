
import Button from '@mui/material/Button';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import MicIcon from '@mui/icons-material/Mic';
import PhoneInTalkIcon from '@mui/icons-material/PhoneInTalk';
import { useNavigate } from 'react-router-dom';

interface ModeSelectProps {
  domainName: string;
}

export default function AgentModeSelectPage({ domainName }: ModeSelectProps) {
  const navigate = useNavigate();

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="flex justify-between items-center mb-10 select-none">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-100">
            Select Connection Mode
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Agent Domain: <span className="text-emerald-400 font-bold uppercase tracking-wider">{domainName}</span>
          </p>
        </div>
        <Button 
          variant="outlined"
          color="inherit"
          onClick={() => navigate('/dashboard')} 
          startIcon={<ArrowBackIcon />}
          className="cursor-pointer"
        >
          Back to Dashboard
        </Button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 select-none">
        {/* Option 1: Web Mic */}
        <div 
          onClick={() => navigate('/agent-console')}
          className="group bg-slate-900/50 hover:bg-slate-900/80 backdrop-blur-xl border border-slate-800/85 hover:border-violet-500/55 rounded-3xl p-8 shadow-xl shadow-slate-950/60 hover:shadow-violet-600/5 transition-all duration-300 flex flex-col justify-between items-center text-center cursor-pointer min-h-[350px] relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-b from-violet-600/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
          
          <div className="w-16 h-16 rounded-2xl bg-violet-950/50 border border-violet-850 flex items-center justify-center mb-6 group-hover:scale-105 transition-transform duration-300">
            <MicIcon sx={{ fontSize: 36, color: '#a78bfa' }} />
          </div>
          
          <div>
            <h2 className="text-xl font-bold text-slate-200 mb-3 group-hover:text-violet-400 transition-colors duration-200">
              Web Browser Mic Agent
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed max-w-xs">
              Interact with the AI Voice Agent locally in your browser. Perfect for immediate microphone validation, state checks, and pipeline testing.
            </p>
          </div>

          <Button 
            variant="contained" 
            color="primary"
            sx={{
              mt: 6,
              background: 'linear-gradient(to right, #7c3aed, #db2777)',
              px: 4,
              py: 1.2
            }}
          >
            Launch Browser Console
          </Button>
        </div>

        {/* Option 2: Twilio Call */}
        <div 
          onClick={() => navigate('/agent-call-console')}
          className="group bg-slate-900/50 hover:bg-slate-900/80 backdrop-blur-xl border border-slate-800/85 hover:border-emerald-500/55 rounded-3xl p-8 shadow-xl shadow-slate-950/60 hover:shadow-emerald-600/5 transition-all duration-300 flex flex-col justify-between items-center text-center cursor-pointer min-h-[350px] relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-b from-emerald-600/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
          
          <div className="w-16 h-16 rounded-2xl bg-emerald-950/50 border border-emerald-850 flex items-center justify-center mb-6 group-hover:scale-105 transition-transform duration-300">
            <PhoneInTalkIcon sx={{ fontSize: 36, color: '#34d399' }} />
          </div>
          
          <div>
            <h2 className="text-xl font-bold text-slate-200 mb-3 group-hover:text-emerald-400 transition-colors duration-200">
              Twilio Telephony Call
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed max-w-xs">
              Configure and place a real outbound call to a mobile number to test the voice agent's latency, speech detection, and pipeline end-to-end.
            </p>
          </div>

          <Button 
            variant="contained" 
            color="success"
            sx={{
              mt: 6,
              background: 'linear-gradient(to right, #059669, #0d9488)',
              px: 4,
              py: 1.2
            }}
          >
            Open Call Dialer
          </Button>
        </div>
      </div>
    </div>
  );
}
