import { useState, useEffect } from 'react';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';

import { useNavigate } from 'react-router-dom';
import { authService } from '../services/authService';
import { domainService } from '../services/domainService';
import { tenantService } from '../services/tenantService';
import NoCodeDbConfigWizard from '../components/NoCodeDbConfigWizard';

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
  const [domainId, setDomainId] = useState<number>(1);
  const [domains, setDomains] = useState<Domain[]>([]);

  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState<'success' | 'error' | ''>('');
  const [, setSubmitting] = useState(false);

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
          setDomainId(data[0].id);
        }
      } catch (err) {
        console.error('Failed to load domains', err);
      }
    }
    loadDomains();
  }, []);

  const handleConfigCompleted = async (configData: {
    dbConfig: any;
    domainId: number;
    identity: {
      table: string;
      name_column: string;
      verification_column: string;
      display_columns: string[];
    };
    selectedTables: Record<string, string[]>;
    uiConfigMetadata: any;
  }) => {
    setStatusMsg('');
    setStatusType('');

    if (!companyName.trim() || !clientName.trim() || !email.trim() || !password.trim()) {
      setStatusType('error');
      setStatusMsg('Please complete all account details (Company, Name, Email, Password) at the top first.');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        company_name: companyName,
        client_name: clientName,
        email,
        password,
        phone,
        domain_id: domainId,
        db_type: configData.dbConfig.db_type,
        server_name: configData.dbConfig.server_name,
        port: configData.dbConfig.port,
        db_name: configData.dbConfig.db_name,
        username: configData.dbConfig.username,
        password_db: configData.dbConfig.password,
        schema_name: configData.dbConfig.schema_name,
        enable_ssl: configData.dbConfig.enable_ssl,
        trust_server_certificate: configData.dbConfig.trust_server_certificate,
        connection_timeout: configData.dbConfig.connection_timeout,
      };

      const res = await authService.register(payload);
      if (res.client_id) {
        // Save the AI rules
        await tenantService.saveRules({
          client_id: res.client_id,
          db_config: configData.dbConfig,
          domain_id: domainId,
          identity: configData.identity,
          selected_tables: configData.selectedTables,
          ui_config_metadata: configData.uiConfigMetadata,
        });

        setStatusType('success');
        setStatusMsg('Account and AI Voice Agent registered successfully!');
        setTimeout(() => navigate('/agent-mode-select'), 1200);
      } else {
        setStatusType('error');
        setStatusMsg(res.detail || 'Registration failed.');
      }
    } catch (err: any) {
      setStatusType('error');
      setStatusMsg(err.message || 'Error completing registration.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen py-12 px-4 flex flex-col justify-center items-center">
      <div className="w-full max-w-4xl space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-extrabold bg-gradient-to-r from-violet-400 via-pink-500 to-emerald-400 bg-clip-text text-transparent pb-2">
            Create Client Account
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Register your company, choose your domain, and visually configure your AI Voice Agent database.
          </p>
        </div>

        {statusMsg && (
          <Alert severity={statusType === 'error' ? 'error' : 'success'} className="rounded-xl">
            {statusMsg}
          </Alert>
        )}

        {/* Client Account Form */}
        <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-6 sm:p-8 space-y-6 shadow-2xl">
          <h3 className="text-lg font-bold text-slate-100 border-b border-slate-800 pb-3">
            1. Account & Company Details
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextField
              size="small"
              label="Company Name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              required
            />
            <TextField
              size="small"
              label="Contact Full Name"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              required
            />
            <TextField
              size="small"
              type="email"
              label="Email Address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <TextField
              size="small"
              type="password"
              label="Account Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <TextField
              size="small"
              label="Phone Number"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />

            <FormControl fullWidth size="small">
              <InputLabel id="domain-select-label">Industry Domain</InputLabel>
              <Select
                labelId="domain-select-label"
                value={domainId}
                label="Industry Domain"
                onChange={(e) => setDomainId(Number(e.target.value))}
              >
                {domains.map((d) => (
                  <MenuItem key={d.id} value={d.id}>
                    {d.name} — {d.description}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </div>
        </div>

        {/* 3-Step No-Code DB Configurator Wizard */}
        <NoCodeDbConfigWizard
          domainId={Number(domainId) || 1}
          isRegistrationMode={true}
          onConfigCompleted={handleConfigCompleted}
        />

        <div className="text-center text-sm text-slate-400">
          Already registered?{' '}
          <Button color="primary" onClick={() => navigate('/login')} className="cursor-pointer">
            Sign In Here
          </Button>
        </div>
      </div>
    </div>
  );
}
