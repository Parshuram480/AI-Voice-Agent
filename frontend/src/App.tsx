import { useState, useEffect } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import LightModeIcon from '@mui/icons-material/LightMode';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import AgentModeSelectPage from './pages/AgentModeSelectPage';
import AgentConsolePage from './pages/AgentConsolePage';
import AgentCallConsolePage from './pages/AgentCallConsolePage';

const API_BASE = 'http://localhost:8000';

type Page = 'LOGIN' | 'REGISTER' | 'DASHBOARD' | 'AGENT_MODE_SELECT' | 'AGENT_CONSOLE' | 'AGENT_CALL_CONSOLE';

interface Client {
  id: number;
  company_name: string;
  client_name: string;
  email: string;
  phone?: string;
}

// Custom Slate Material-UI Theme Creator
const createAppTheme = (mode: 'light' | 'dark') => createTheme({
  palette: {
    mode,
    primary: {
      main: '#8b5cf6', // violet-500
    },
    secondary: {
      main: '#ec4899', // pink-500
    },
    background: {
      default: mode === 'dark' ? '#020617' : '#f8fafc', // slate-950 in dark, slate-50 in light
      paper: mode === 'dark' ? '#0f172a' : '#ffffff', // slate-900 in dark, white in light
    },
    text: {
      primary: mode === 'dark' ? '#f8fafc' : '#0f172a', // slate-100 in dark, slate-950 in light
      secondary: mode === 'dark' ? '#94a3b8' : '#475569', // slate-400 in dark, slate-600 in light
    },
  },
  typography: {
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: '8px',
          fontWeight: 600,
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
        },
      },
    },
  },
});

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>('LOGIN');
  const [client, setClient] = useState<Client | null>(null);
  const [domainName, setDomainName] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [pipelineMode, setPipelineMode] = useState<string>('cascade');
  const [themeMode, setThemeMode] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme_mode');
    return (saved === 'light' || saved === 'dark') ? saved : 'dark';
  });

  // Sync theme mode with document element (HTML) class for Tailwind v4 custom dark variant
  useEffect(() => {
    const root = window.document.documentElement;
    if (themeMode === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('theme_mode', themeMode);
  }, [themeMode]);

  const toggleTheme = () => {
    setThemeMode((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  const appTheme = createAppTheme(themeMode);

  // Check auth session on startup
  useEffect(() => {
    async function checkAuth() {
      try {
        const response = await fetch(`${API_BASE}/api/auth/me`, {
          credentials: 'include'
        });
        if (response.ok) {
          const data = await response.json();
          setClient(data.client);
          setDomainName(data.domain ? data.domain.name : 'None');
          setPipelineMode(data.pipeline_mode || 'cascade');
          setCurrentPage('DASHBOARD');
        } else {
          setCurrentPage('LOGIN');
        }
      } catch (err) {
        setCurrentPage('LOGIN');
      } finally {
        setLoading(false);
      }
    }
    checkAuth();
  }, []);

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
    } catch (e) {
      console.error('Logout failed', e);
    }
    setClient(null);
    setDomainName('');
    localStorage.removeItem('voice_session_id');
    setCurrentPage('LOGIN');
  };

  if (loading) {
    return (
      <ThemeProvider theme={appTheme}>
        <CssBaseline />
        <div className="flex flex-col items-center justify-center min-h-screen bg-slate-950 text-slate-400 transition-colors duration-300">
          <CircularProgress color="primary" className="mb-4" />
          <p className="text-xs uppercase tracking-widest font-semibold select-none">Loading voice platform...</p>
        </div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <div className="bg-slate-950 text-slate-100 min-h-screen font-sans selection:bg-violet-500 selection:text-white antialiased relative transition-colors duration-300">
        
        {/* Floating Glassmorphic Theme Toggle Button */}
        <div className="fixed top-4 right-4 z-50 animate-fade-in">
          <IconButton 
            onClick={toggleTheme} 
            color="inherit" 
            className="cursor-pointer bg-slate-900/60 hover:bg-slate-900 border border-slate-800/80 rounded-full p-2.5 backdrop-blur-xl shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 transition-all duration-300"
            aria-label={`Switch to ${themeMode === 'light' ? 'dark' : 'light'} theme`}
          >
            {themeMode === 'dark' ? (
              <LightModeIcon className="text-amber-400 w-5 h-5 transition-transform duration-300 hover:rotate-45" />
            ) : (
              <DarkModeIcon className="text-violet-500 w-5 h-5 transition-transform duration-300 hover:-rotate-12" />
            )}
          </IconButton>
        </div>

        {currentPage === 'LOGIN' && (
          <LoginPage 
            onLoginSuccess={(c, d, pm) => {
              setClient(c);
              setDomainName(d);
              setPipelineMode(pm);
              setCurrentPage('DASHBOARD');
            }}
            onGoToRegister={() => setCurrentPage('REGISTER')}
          />
        )}
        
        {currentPage === 'REGISTER' && (
          <RegisterPage 
            onRegisterSuccess={() => setCurrentPage('LOGIN')}
            onGoToLogin={() => setCurrentPage('LOGIN')}
          />
        )}

        {currentPage === 'DASHBOARD' && client && (
          <DashboardPage 
            client={client}
            domainName={domainName}
            onLogout={handleLogout}
            onLaunchAgent={() => setCurrentPage('AGENT_MODE_SELECT')}
          />
        )}

        {currentPage === 'AGENT_MODE_SELECT' && (
          <AgentModeSelectPage
            domainName={domainName}
            onBackToDashboard={() => setCurrentPage('DASHBOARD')}
            onSelectMode={(mode) => {
              if (mode === 'mic') {
                setCurrentPage('AGENT_CONSOLE');
              } else {
                setCurrentPage('AGENT_CALL_CONSOLE');
              }
            }}
          />
        )}

        {currentPage === 'AGENT_CONSOLE' && client && (
          <AgentConsolePage 
            client={client}
            domainName={domainName}
            pipelineMode={pipelineMode}
            onBackToDashboard={() => setCurrentPage('AGENT_MODE_SELECT')}
          />
        )}
        
        {currentPage === 'AGENT_CALL_CONSOLE' && client && (
          <AgentCallConsolePage 
            client={client}
            domainName={domainName}
            pipelineMode={pipelineMode}
            onBackToDashboard={() => setCurrentPage('AGENT_MODE_SELECT')}
          />
        )}
      </div>
    </ThemeProvider>
  );
}
