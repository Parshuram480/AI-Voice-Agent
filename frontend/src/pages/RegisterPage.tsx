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
import WifiIcon from '@mui/icons-material/Wifi';
import AssignmentIndIcon from '@mui/icons-material/AssignmentInd';
import { useNavigate } from 'react-router-dom';
import { authService } from '../services/authService';
import { domainService } from '../services/domainService';
import { tenantService } from '../services/tenantService';

interface Domain {
  id: number;
  name: string;
  description: string;
  status: string;
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const [companyName, setCompanyName] = useState('');
  const [clientName, setClientName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [domainId, setDomainId] = useState<number | ''>('');
  const [domains, setDomains] = useState<Domain[]>([]);

  // DB Config
  const [dbType, setDbType] = useState('sqlite');
  const [dbName, setDbName] = useState('healthcare_client.db');
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
  const [submitting, setSubmitting] = useState(false);

  // Validation States
  const [errors, setErrors] = useState({
    companyName: '',
    clientName: '',
    email: '',
    password: '',
    phone: '',
    dbName: '',
    serverAddress: '',
    port: '',
    username: '',
    timeout: ''
  });

  const validateForm = (configOnly = false): boolean => {
    let isValid = true;
    const newErrors = {
      companyName: '',
      clientName: '',
      email: '',
      password: '',
      phone: '',
      dbName: '',
      serverAddress: '',
      port: '',
      username: '',
      timeout: ''
    };

    if (!configOnly) {
      if (!companyName.trim()) {
        newErrors.companyName = 'Company name is required';
        isValid = false;
      } else if (companyName.trim().length < 2) {
        newErrors.companyName = 'Company name must be at least 2 characters';
        isValid = false;
      }

      if (!clientName.trim()) {
        newErrors.clientName = 'Contact name is required';
        isValid = false;
      } else if (clientName.trim().length < 2) {
        newErrors.clientName = 'Contact name must be at least 2 characters';
        isValid = false;
      }

      if (!email.trim()) {
        newErrors.email = 'Email is required';
        isValid = false;
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        newErrors.email = 'Please enter a valid email address';
        isValid = false;
      }

      if (!password) {
        newErrors.password = 'Password is required';
        isValid = false;
      } else if (password.length < 6) {
        newErrors.password = 'Password must be at least 6 characters';
        isValid = false;
      }

      if (phone.trim() && !/^\+[1-9][0-9\s-]{7,14}$/.test(phone.trim())) {
        newErrors.phone = 'Please enter a valid phone number with "+" and country code (e.g. +15551234567)';
        isValid = false;
      }
    }

    // Validate db config
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

  const handleDomainChange = (selectedId: number, currentDomains: Domain[] = domains) => {
    setDomainId(selectedId);
    const selectedDomain = currentDomains.find(d => d.id === selectedId);
    if (selectedDomain) {
      if (selectedDomain.name === 'Order Tracking') {
        setDbType('postgresql');
        setDbName('voice_agent');
        setPort(5432);
        setUsername('postgres');
        setServerAddress('localhost');
      } else if (selectedDomain.name === 'Healthcare') {
        setDbType('sqlite');
        setDbName('healthcare_client.db');
        setPort('');
        setUsername('');
        setServerAddress('');
      }
    }
  };

  useEffect(() => {
    async function loadDomains() {
      try {
        const data = await domainService.getDomains();
        data.sort((a: Domain, b: Domain) => {
          if (a.name === 'Healthcare') return -1;
          if (b.name === 'Healthcare') return 1;
          if (a.name === 'Order Tracking') return -1;
          if (b.name === 'Order Tracking') return 1;
          return a.name.localeCompare(b.name);
        });
        setDomains(data);
        if (data.length > 0) {
          handleDomainChange(data[0].id, data);
        }
      } catch (err) {
        console.error('Failed to load domains', err);
      }
    }
    loadDomains();
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
    if (!validateForm(true)) {
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
    if (!validateForm(false)) {
      setStatusType('error');
      setStatusMsg('Please correct the highlighted form errors.');
      return;
    }
    setStatusMsg('');
    setStatusType('');
    setSubmitting(true);

    const config = getDbConfigObject();
    const payload = {
      company_name: companyName,
      client_name: clientName,
      email,
      password,
      phone: phone || null,
      domain_id: Number(domainId),
      db_type: config.db_type,
      server_name: config.server_name,
      port: config.port,
      db_name: config.db_name,
      username: config.username,
      password_db: config.password,
      schema_name: config.schema_name,
      enable_ssl: config.enable_ssl,
      trust_server_certificate: config.trust_server_certificate,
      connection_timeout: config.connection_timeout
    };

    try {
      const data = await authService.register(payload);
      if (data.success) {
        setStatusType('success');
        setStatusMsg('Registration successful! Redirecting to login...');
        setTimeout(() => {
          navigate('/login');
        }, 1500);
      } else {
        setStatusType('error');
        setStatusMsg('Registration failed: ' + (data.detail || 'Unknown error'));
      }
    } catch (err: any) {
      setStatusType('error');
      setStatusMsg('Error registering: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const isSqlite = dbType === 'sqlite';

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="text-center mb-8">
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-violet-400 via-fuchsia-400 to-pink-500 bg-clip-text text-transparent pb-2 mb-2">
          Tenant Registration
        </h1>
        <p className="text-slate-400 text-sm md:text-base uppercase tracking-wider font-semibold">
          Register your company and configure your AI Voice Agent database
        </p>
      </header>

      <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-6 md:p-8 shadow-2xl shadow-slate-950/60">
        <form onSubmit={handleSubmit} className="space-y-8">

          {/* Section 1: Client Info */}
          <div>
            <h2 className="text-md font-bold text-violet-400 uppercase tracking-wider border-b border-slate-800 pb-2 mb-6 select-none">
              Client Details
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <TextField
                label="Company Name"
                placeholder="Acme Corp"
                variant="outlined"
                fullWidth
                value={companyName}
                onChange={e => {
                  setCompanyName(e.target.value);
                  if (errors.companyName) setErrors(prev => ({ ...prev, companyName: '' }));
                }}
                error={!!errors.companyName}
                helperText={errors.companyName}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Contact Name"
                placeholder="John Doe"
                variant="outlined"
                fullWidth
                value={clientName}
                onChange={e => {
                  setClientName(e.target.value);
                  if (errors.clientName) setErrors(prev => ({ ...prev, clientName: '' }));
                }}
                error={!!errors.clientName}
                helperText={errors.clientName}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Email Address"
                placeholder="john@acme.com"
                type="email"
                variant="outlined"
                fullWidth
                value={email}
                onChange={e => {
                  setEmail(e.target.value);
                  if (errors.email) setErrors(prev => ({ ...prev, email: '' }));
                }}
                error={!!errors.email}
                helperText={errors.email}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Password"
                placeholder="••••••••"
                type="password"
                variant="outlined"
                fullWidth
                value={password}
                onChange={e => {
                  setPassword(e.target.value);
                  if (errors.password) setErrors(prev => ({ ...prev, password: '' }));
                }}
                error={!!errors.password}
                helperText={errors.password}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Phone Number (Optional)"
                placeholder="+15551234567"
                variant="outlined"
                fullWidth
                value={phone}
                onChange={e => {
                  setPhone(e.target.value);
                  if (errors.phone) setErrors(prev => ({ ...prev, phone: '' }));
                }}
                error={!!errors.phone}
                helperText={errors.phone}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <FormControl fullWidth required>
                <InputLabel shrink id="domain-select-label">Select Agent Domain</InputLabel>
                <Select
                  labelId="domain-select-label"
                  label="Select Agent Domain"
                  value={domainId}
                  displayEmpty
                  onChange={e => handleDomainChange(Number(e.target.value))}
                  notched
                >
                  {domains.map(d => (
                    <MenuItem key={d.id} value={d.id}>{d.name} — {d.description}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </div>
          </div>

          {/* Section 2: Database Config */}
          <div>
            <h2 className="text-md font-bold text-violet-400 uppercase tracking-wider border-b border-slate-800 pb-2 mb-2 select-none">
              Client Database Configuration
            </h2>
            <p className="text-slate-400 text-sm mb-6 select-none">
              Specify the connection settings for the database hosting your business records.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <FormControl fullWidth required>
                <InputLabel shrink id="db-type-label">Database Type</InputLabel>
                <Select
                  labelId="db-type-label"
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
                placeholder="••••••••"
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
          </div>

          <div className="flex flex-col sm:flex-row gap-4 pt-4">
            <Button
              type="button"
              variant="outlined"
              color="inherit"
              size="large"
              onClick={handleTestConnection}
              disabled={testingConnection}
              startIcon={testingConnection ? <CircularProgress size={20} color="inherit" /> : <WifiIcon />}
              className="flex-1 cursor-pointer"
              sx={{ py: 1.5 }}
            >
              {testingConnection ? 'Testing...' : 'Test Connection'}
            </Button>
            <Button
              type="submit"
              variant="contained"
              color="primary"
              size="large"
              disabled={submitting}
              startIcon={submitting ? <CircularProgress size={20} color="inherit" /> : <AssignmentIndIcon />}
              className="flex-1 cursor-pointer"
              sx={{
                py: 1.5,
                background: 'linear-gradient(to right, #7c3aed, #db2777)',
                '&:hover': {
                  background: 'linear-gradient(to right, #6d28d9, #be185d)',
                }
              }}
            >
              {submitting ? 'Registering...' : 'Register & Save'}
            </Button>
          </div>

          {statusMsg && (
            <Alert severity={statusType === 'success' ? 'success' : 'error'} variant="outlined" sx={{ width: '105%' }}>
              {statusMsg}
            </Alert>
          )}
        </form>

        <p className="mt-8 text-center text-slate-400 text-sm">
          Already registered?{' '}
          <button
            onClick={() => navigate('/login')}
            className="text-violet-400 hover:text-violet-300 font-semibold focus:outline-none transition-colors duration-200 cursor-pointer"
          >
            Sign in here
          </button>
        </p>
      </div>
    </div>
  );
}
