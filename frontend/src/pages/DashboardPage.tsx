import React, { useState, useEffect } from 'react';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import LogoutIcon from '@mui/icons-material/Logout';
import SettingsInputComponentIcon from '@mui/icons-material/SettingsInputComponent';
import SaveIcon from '@mui/icons-material/Save';
import KeyboardDoubleArrowRightIcon from '@mui/icons-material/KeyboardDoubleArrowRight';
import { authService } from '../services/authService';
import { tenantService } from '../services/tenantService';

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
  onLaunchAgent: () => void;
}

export default function DashboardPage({ client, domainName, onLogout, onLaunchAgent }: DashboardProps) {
  const [dbType, setDbType] = useState('sqlite');
  const [dbName, setDbName] = useState('');
  const [serverAddress, setServerAddress] = useState('');
  const [port, setPort] = useState<number | ''>('');
  const [username, setUsername] = useState('');
  const [passwordDb, setPasswordDb] = useState('');
  const [schemaName, setSchemaName] = useState('');
  const [enableSsl, setEnableSsl] = useState(false);
  const [trustCert, setTrustCert] = useState(false);
  const [timeout, setTimeoutSec] = useState(5);

  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState<'success' | 'error' | ''>('');
  const [testingConnection, setTestingConnection] = useState(false);
  const [saving, setSaving] = useState(false);

  // Validation States
  const [errors, setErrors] = useState({
    dbName: '',
    serverAddress: '',
    port: '',
    username: '',
    timeout: ''
  });

  const validateForm = (): boolean => {
    let isValid = true;
    const newErrors = {
      dbName: '',
      serverAddress: '',
      port: '',
      username: '',
      timeout: ''
    };

    if (!dbName.trim()) {
      newErrors.dbName = 'Database name is required';
      isValid = false;
    }

    if (dbType !== 'sqlite') {
      if (!serverAddress.trim()) {
        newErrors.serverAddress = 'Server address is required';
        isValid = false;
      }

      if (port === '') {
        newErrors.port = 'Port is required';
        isValid = false;
      } else {
        const portNum = Number(port);
        if (isNaN(portNum) || portNum < 1 || portNum > 65535) {
          newErrors.port = 'Port must be a valid number between 1 and 65535';
          isValid = false;
        }
      }

      if (!username.trim()) {
        newErrors.username = 'Username is required';
        isValid = false;
      }
    }

    if (timeout === '' || isNaN(Number(timeout))) {
      newErrors.timeout = 'Timeout is required';
      isValid = false;
    } else {
      const t = Number(timeout);
      if (t < 1 || t > 120) {
        newErrors.timeout = 'Timeout must be between 1 and 120 seconds';
        isValid = false;
      }
    }

    setErrors(newErrors);
    return isValid;
  };

  useEffect(() => {
    async function loadConfig() {
      try {
        const data = await authService.checkAuth();
        const db = data.db_config;
        if (db) {
          setDbType(db.db_type);
          setDbName(db.db_name);
          setServerAddress(db.server_name || '');
          setPort(db.port || '');
          setUsername(db.username || '');
          setSchemaName(db.schema_name || '');
          setEnableSsl(!!db.enable_ssl);
          setTrustCert(!!db.trust_server_certificate);
          setTimeoutSec(db.connection_timeout || 5);
        }
      } catch (err) {
        console.error('Failed to load DB config', err);
      }
    }
    loadConfig();
  }, []);

  const handleDbTypeChange = (type: string) => {
    setDbType(type);
    if (type === 'sqlite') {
      setDbName('healthcare_client.db');
    } else {
      setDbName('voice_agent');
      if (type === 'postgresql') setPort(5432);
      else if (type === 'mysql') setPort(3306);
      else if (type === 'sql server') setPort(1433);
    }
  };

  const getDbConfigObject = () => {
    return {
      db_type: dbType,
      server_name: serverAddress || null,
      port: port ? Number(port) : null,
      db_name: dbName,
      username: username || null,
      password: passwordDb || null,
      schema_name: schemaName || null,
      enable_ssl: enableSsl,
      trust_server_certificate: trustCert,
      connection_timeout: timeout
    };
  };

  const handleTestConnection = async () => {
    if (!validateForm()) {
      setStatusType('error');
      setStatusMsg('Please correct the database configuration errors before testing connection.');
      return;
    }
    setStatusMsg('');
    setStatusType('');
    setTestingConnection(true);
    try {
      const config = getDbConfigObject();
      const data = await tenantService.testConnection(config);
      if (data.success) {
        setStatusType('success');
        setStatusMsg('Database connection test successful!');
      } else {
        setStatusType('error');
        setStatusMsg('Connection failed: ' + data.message);
      }
    } catch (err: any) {
      setStatusType('error');
      setStatusMsg('Error testing connection: ' + err.message);
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) {
      setStatusType('error');
      setStatusMsg('Please correct the highlighted form errors.');
      return;
    }
    setStatusMsg('');
    setStatusType('');
    setSaving(true);

    try {
      const config = getDbConfigObject();
      const data = await tenantService.saveDbConfig(config);
      if (data.success) {
        setStatusType('success');
        setStatusMsg('Database configuration saved successfully!');
      } else {
        setStatusType('error');
        setStatusMsg('Failed to save database configuration: ' + (data.detail || 'Unknown error'));
      }
    } catch (err: any) {
      setStatusType('error');
      setStatusMsg('Error saving configuration: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const isSqlite = dbType === 'sqlite';

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

      <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 md:p-8 shadow-2xl shadow-slate-950/60 space-y-8 animate-slide-up">
        {/* Profile Card */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-slate-950/40 border border-slate-800/60 rounded-xl p-6 select-none">
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
        <div className="text-center py-4 border-y border-slate-850/80">
          <Button
            onClick={onLaunchAgent}
            variant="contained"
            color="primary"
            size="large"
            endIcon={<KeyboardDoubleArrowRightIcon />}
            className="cursor-pointer"
            sx={{
              py: 1.5,
              px: 4,
              fontSize: '1.05rem',
              background: 'linear-gradient(to right, #7c3aed, #db2777)',
              '&:hover': {
                background: 'linear-gradient(to right, #6d28d9, #be185d)',
              }
            }}
          >
            Open AI Voice Agent Console
          </Button>
        </div>

        {/* Edit Config Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <h2 className="text-md font-bold text-violet-400 uppercase tracking-wider border-b border-slate-800 pb-2 mb-4 select-none">
            Edit Database Configuration
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <FormControl fullWidth required>
              <InputLabel shrink id="db-type-label-dashboard">Database Type</InputLabel>
              <Select
                labelId="db-type-label-dashboard"
                label="Database Type"
                value={dbType}
                onChange={e => handleDbTypeChange(e.target.value as string)}
                notched
              >
                <MenuItem value="sqlite">SQLite</MenuItem>
                <MenuItem value="postgresql">PostgreSQL</MenuItem>
                <MenuItem value="mysql">MySQL</MenuItem>
                <MenuItem value="sql server">SQL Server</MenuItem>
                <MenuItem value="oracle">Oracle</MenuItem>
              </Select>
            </FormControl>
            <TextField
              label="Database Name / Path"
              placeholder="healthcare_client.db"
              variant="outlined"
              fullWidth
              value={dbName}
              onChange={e => {
                setDbName(e.target.value);
                if (errors.dbName) setErrors(prev => ({ ...prev, dbName: '' }));
              }}
              error={!!errors.dbName}
              helperText={errors.dbName}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Server Address"
              placeholder="localhost"
              variant="outlined"
              fullWidth
              value={serverAddress}
              onChange={e => {
                setServerAddress(e.target.value);
                if (errors.serverAddress) setErrors(prev => ({ ...prev, serverAddress: '' }));
              }}
              error={!!errors.serverAddress}
              helperText={errors.serverAddress}
              disabled={isSqlite}
              sx={{ opacity: isSqlite ? 0.45 : 1.0 }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Port"
              placeholder="5432"
              type="number"
              variant="outlined"
              fullWidth
              value={port}
              onChange={e => {
                setPort(e.target.value ? Number(e.target.value) : '');
                if (errors.port) setErrors(prev => ({ ...prev, port: '' }));
              }}
              error={!!errors.port}
              helperText={errors.port}
              disabled={isSqlite}
              sx={{ opacity: isSqlite ? 0.45 : 1.0 }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Username"
              placeholder="postgres"
              variant="outlined"
              fullWidth
              value={username}
              onChange={e => {
                setUsername(e.target.value);
                if (errors.username) setErrors(prev => ({ ...prev, username: '' }));
              }}
              error={!!errors.username}
              helperText={errors.username}
              disabled={isSqlite}
              sx={{ opacity: isSqlite ? 0.45 : 1.0 }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Password"
              placeholder="•••••••• (Leave blank to keep unchanged)"
              type="password"
              variant="outlined"
              fullWidth
              value={passwordDb}
              onChange={e => setPasswordDb(e.target.value)}
              disabled={isSqlite}
              sx={{ opacity: isSqlite ? 0.45 : 1.0 }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Schema Name (Optional)"
              placeholder="public"
              variant="outlined"
              fullWidth
              value={schemaName}
              onChange={e => setSchemaName(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Timeout (Seconds)"
              type="number"
              variant="outlined"
              fullWidth
              value={timeout}
              onChange={e => {
                setTimeoutSec(Number(e.target.value));
                if (errors.timeout) setErrors(prev => ({ ...prev, timeout: '' }));
              }}
              error={!!errors.timeout}
              helperText={errors.timeout}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            {/* <div className="flex items-center space-x-3 pt-3">
              <FormControlLabel
                control={
                  <Checkbox
                    checked={enableSsl}
                    onChange={e => setEnableSsl(e.target.checked)}
                    color="primary"
                  />
                }
                label="Enable SSL"
              />
            </div>
            <div className="flex items-center space-x-3 pt-3">
              <FormControlLabel
                control={
                  <Checkbox
                    checked={trustCert}
                    onChange={e => setTrustCert(e.target.checked)}
                    color="primary"
                  />
                }
                label="Trust Server Certificate"
              />
            </div> */}
          </div>

          <div className="flex flex-col sm:flex-row gap-4 pt-4">
            <Button
              type="button"
              variant="outlined"
              color="inherit"
              size="large"
              onClick={handleTestConnection}
              disabled={testingConnection}
              startIcon={testingConnection ? <CircularProgress size={20} color="inherit" /> : <SettingsInputComponentIcon />}
              className="flex-1 cursor-pointer"
              sx={{ py: 1.5 }}
            >
              {testingConnection ? 'Testing Connection...' : 'Test Connection'}
            </Button>
            <Button
              type="submit"
              variant="contained"
              color="primary"
              size="large"
              disabled={saving}
              startIcon={saving ? <CircularProgress size={20} color="inherit" /> : <SaveIcon />}
              className="flex-1 cursor-pointer"
              sx={{
                py: 1.5,
                background: 'linear-gradient(to right, #7c3aed, #db2777)',
                '&:hover': {
                  background: 'linear-gradient(to right, #6d28d9, #be185d)',
                }
              }}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>

          {statusMsg && (
            <Alert severity={statusType === 'success' ? 'success' : 'error'} variant="outlined" sx={{ width: '105%' }}>
              {statusMsg}
            </Alert>
          )}
        </form>
      </div>
    </div>
  );
}
