import { useState, useEffect } from 'react';
import Button from '@mui/material/Button';
import LogoutIcon from '@mui/icons-material/Logout';
import EditIcon from '@mui/icons-material/Edit';
import StorageIcon from '@mui/icons-material/Storage';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import KeyboardDoubleArrowRightIcon from '@mui/icons-material/KeyboardDoubleArrowRight';
import CloseIcon from '@mui/icons-material/Close';
import { useNavigate } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import NoCodeDbConfigWizard from '../components/NoCodeDbConfigWizard';
import { authService } from '../services/authService';

interface Client {
  id: number;
  company_name: string;
  client_name: string;
  email: string;
  phone?: string;
}

interface DashboardProps {
  client: Client;
  domainName: string;
  onLogout: () => void;
}

export default function DashboardPage({ client, domainName, onLogout }: DashboardProps) {
  const navigate = useNavigate();

  const [dbConfig, setDbConfig] = useState<any>(null);
  const [domainData, setDomainData] = useState<any>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [, setLoadingConfig] = useState(true);

  const loadConfig = async () => {
    setLoadingConfig(true);
    try {
      const data = await authService.checkAuth();
      if (data.db_config) {
        setDbConfig(data.db_config);
      }
      if (data.domain) {
        setDomainData(data.domain);
      }
    } catch (err) {
      console.error('Failed to load DB configuration', err);
    } finally {
      setLoadingConfig(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  // Parse UI metadata if available
  let parsedMetadata: any = null;
  if (domainData?.ui_config_metadata) {
    try {
      parsedMetadata = typeof domainData.ui_config_metadata === 'string'
        ? JSON.parse(domainData.ui_config_metadata)
        : domainData.ui_config_metadata;
    } catch {
      parsedMetadata = null;
    }
  }

  const isConfigured = Boolean(dbConfig && dbConfig.db_name && dbConfig.db_name !== 'placeholder.db');

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold bg-gradient-to-r from-violet-400 to-pink-500 bg-clip-text text-transparent pb-2">
            Client Dashboard
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Manage settings and launch your AI Voice Agent console
          </p>
        </div>
        <Button
          variant="outlined"
          color="inherit"
          size="small"
          onClick={onLogout}
          startIcon={<LogoutIcon />}
          className="cursor-pointer"
        >
          Sign Out
        </Button>
      </header>

      <div className="space-y-8 animate-slide-up">
        {/* Profile Card */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 shadow-xl select-none">
          <div className="space-y-1">
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Company</span>
            <span className="block text-base font-bold text-slate-100">{client.company_name}</span>
          </div>
          <div className="space-y-1">
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Contact</span>
            <span className="block text-base font-bold text-slate-100">{client.client_name}</span>
          </div>
          <div className="space-y-1">
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Domain</span>
            <span className="block text-base font-bold text-emerald-400">{domainName}</span>
          </div>
        </div>

        {/* Launch Button Room */}
        <div className="text-center py-4 bg-slate-900/40 border border-slate-800 rounded-2xl">
          <Button
            onClick={() => navigate('/agent-mode-select')}
            variant="contained"
            color="primary"
            size="large"
            disabled={!isConfigured}
            endIcon={<KeyboardDoubleArrowRightIcon />}
            className="cursor-pointer"
            sx={{
              py: 1.5,
              px: 4,
              fontSize: '1.05rem',
              background: isConfigured ? 'linear-gradient(to right, #7c3aed, #db2777)' : '#1e293b',
              '&:hover': {
                background: isConfigured ? 'linear-gradient(to right, #6d28d9, #be185d)' : '#1e293b',
              }
            }}
          >
            Open AI Voice Agent Console
          </Button>
          {!isConfigured && (
            <p className="text-xs text-rose-400 mt-2 font-medium">
              Please complete your Database Connection setup below to activate the Voice Agent console.
            </p>
          )}
        </div>

        {/* Database Configuration Section */}
        {isConfigured && !isEditing ? (
          <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-6 sm:p-8 space-y-6 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-950/50 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <StorageIcon />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                    Active Database Connection
                    <span className="text-xs bg-emerald-950 text-emerald-400 border border-emerald-500/30 px-2.5 py-0.5 rounded-full flex items-center gap-1 font-medium">
                      <CheckCircleIcon sx={{ fontSize: 14 }} /> Connected
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400">Configured database & AI verification rules</p>
                </div>
              </div>

              <Button
                variant="contained"
                color="primary"
                startIcon={<EditIcon />}
                onClick={() => setIsEditing(true)}
                sx={{
                  borderRadius: '12px',
                  background: 'linear-gradient(to right, #8b5cf6, #ec4899)',
                  px: 3,
                }}
              >
                Edit Configuration
              </Button>
            </div>

            {/* Read-only Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 space-y-2">
                <span className="text-xs text-slate-500 font-bold uppercase tracking-wider block">Database Settings</span>
                <div className="text-sm text-slate-200">
                  <span className="font-semibold text-slate-400">Type:</span> <span className="uppercase font-bold text-violet-400">{dbConfig.db_type}</span>
                </div>
                <div className="text-sm text-slate-200">
                  <span className="font-semibold text-slate-400">Database Name:</span> <span className="font-mono text-slate-200">{dbConfig.db_name?.includes('/') ? dbConfig.db_name.split('/').pop() : dbConfig.db_name}</span>
                </div>
                {dbConfig.db_type !== 'sqlite' && (
                  <div className="text-sm text-slate-200">
                    <span className="font-semibold text-slate-400">Server:</span> <span className="font-mono text-slate-300">{dbConfig.server_name || 'localhost'}:{dbConfig.port || ''}</span>
                  </div>
                )}
              </div>

              <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 space-y-2">
                <span className="text-xs text-slate-500 font-bold uppercase tracking-wider block">Agent AI Rules Mapping</span>
                {parsedMetadata ? (
                  <>
                    <div className="text-sm text-slate-200">
                      <span className="font-semibold text-slate-400">Primary Table:</span> <span className="font-mono text-sky-400">{parsedMetadata.customerTable || 'Configured'}</span>
                    </div>
                    <div className="text-sm text-slate-200">
                      <span className="font-semibold text-slate-400">Verified Columns:</span>{' '}
                      <span className="font-mono text-violet-300">
                        {Array.isArray(parsedMetadata.verificationFields) ? parsedMetadata.verificationFields.join(', ') : 'Default'}
                      </span>
                    </div>
                    <div className="text-sm text-slate-200">
                      <span className="font-semibold text-slate-400">Related Tables:</span> <span className="font-mono text-emerald-400">{Object.keys(parsedMetadata.selectedTables || {}).join(', ') || 'Configured'}</span>
                    </div>
                  </>
                ) : (
                  <div className="text-xs text-emerald-400 font-medium pt-1">
                    AI verification and business record queries compiled and ready.
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex justify-between items-center bg-slate-900/40 p-4 rounded-2xl border border-slate-800">
              <span className="text-sm text-slate-300 font-medium">
                {isConfigured ? 'Modifying Database Configuration & Rules Stepper' : 'Database Setup Needed'}
              </span>
              {isConfigured && (
                <Button
                  size="small"
                  variant="outlined"
                  color="inherit"
                  startIcon={<CloseIcon />}
                  onClick={() => setIsEditing(false)}
                >
                  Cancel Edit
                </Button>
              )}
            </div>

            {!isConfigured && (
              <Alert severity="warning" className="rounded-xl">
                Please complete your database configuration setup below to proceed.
              </Alert>
            )}

            {/* Reusable No-Code Database Introspection & Rule Configurator Wizard */}
            <NoCodeDbConfigWizard
              domainId={domainData?.id || 1}
              initialDbConfig={isConfigured ? dbConfig : undefined}
              initialMetadata={isConfigured ? parsedMetadata : undefined}
              onSaveSuccess={() => {
                loadConfig();
                setIsEditing(false);
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
