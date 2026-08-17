import Button from '@mui/material/Button';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ChatIcon from '@mui/icons-material/Chat';
import { useNavigate } from 'react-router-dom';
import ChatConsoleWidget from '../components/ChatConsoleWidget';

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

export default function AgentChatConsolePage({ client, domainName, pipelineMode }: AgentChatConsoleProps) {
  const navigate = useNavigate();

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
        <ChatConsoleWidget
          client={client}
          domainName={domainName}
          pipelineMode={pipelineMode}
          isFloating={false}
        />
      </div>
    </div>
  );
}
