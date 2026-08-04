import React, { useState } from 'react';
import { useTheme } from '@mui/material/styles';
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
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SaveIcon from '@mui/icons-material/Save';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import TableChartIcon from '@mui/icons-material/TableChart';
import CampaignIcon from '@mui/icons-material/Campaign';

import { tenantService } from '../services/tenantService';
import { outreachService } from '../services/outreachService';

export interface OutreachConfigWizardProps {
  initialDbConfig?: any;
  initialOutreachConfig?: any;
  domainName?: string;
  onSaveSuccess?: () => void;
}

export default function OutreachConfigWizard({
  initialDbConfig,
  initialOutreachConfig,
  domainName,
  onSaveSuccess,
}: OutreachConfigWizardProps) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  // Step tracking (1: DB Credentials, 2: Outreach Rules, 3: Summary Review)
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

  // Step 1: DB Credentials State
  const [dbType, setDbType] = useState(initialDbConfig?.db_type || 'postgresql');
  const [dbName, setDbName] = useState<string>(initialDbConfig?.db_name || '');
  const [serverAddress, setServerAddress] = useState(initialDbConfig?.server_name || 'localhost');
  const [port, setPort] = useState<number | ''>(initialDbConfig?.port || 5432);
  const [username, setUsername] = useState(initialDbConfig?.username || 'postgres');
  const [passwordDb, setPasswordDb] = useState(initialDbConfig?.password || '');
  const [schemaName] = useState('');
  const [enableSsl] = useState(false);
  const [trustCert] = useState(false);
  const [timeout] = useState(5);

  const [schemaData, setSchemaData] = useState<Record<string, string[]>>({});
  const [loadingIntrospect, setLoadingIntrospect] = useState(false);
  const [uploadingDb, setUploadingDb] = useState(false);
  const [step1Error, setStep1Error] = useState('');
  // Step 2: Outreach Config State
  const derivedCampaignType = domainName?.toLowerCase().includes('real estate') ? 'real_estate' : 'sales';
  const [companyName, setCompanyName] = useState<string>(initialOutreachConfig?.company_name || '');
  const [closingGoal, setClosingGoal] = useState<string>(initialOutreachConfig?.closing_goal || '');
  const [productTable, setProductTable] = useState<string>(initialOutreachConfig?.product_table || '');
  const [selectedColumns, setSelectedColumns] = useState<string[]>(initialOutreachConfig?.selected_columns || []);

  const [step2Error, setStep2Error] = useState('');

  // Step 3: Summary State
  const [loadingSave, setLoadingSave] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('');

  const getDbConfigPayload = () => ({
    db_type: dbType.toLowerCase(),
    db_name: dbName,
    server_name: serverAddress || undefined,
    port: port !== '' ? Number(port) : undefined,
    username: username || undefined,
    password: passwordDb || undefined,
    schema_name: schemaName || undefined,
    enable_ssl: enableSsl,
    trust_server_certificate: trustCert,
    connection_timeout: timeout,
  });

  const handleSqliteFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files || event.target.files.length === 0) return;
    const file = event.target.files[0];

    setUploadingDb(true);
    setStep1Error('');
    try {
      const result = await tenantService.uploadSqlite(file);
      if (result.success && result.db_path) {
        setDbName(result.db_path);
      } else {
        setStep1Error('Failed to upload SQLite database.');
      }
    } catch (e: any) {
      setStep1Error(e.message || 'Error uploading SQLite file.');
    } finally {
      setUploadingDb(false);
    }
  };

  // Helper to flatten the hierarchical schema into Record<string, string[]>
  const flattenSchema = (schema: any): Record<string, string[]> => {
    const flat: Record<string, string[]> = {};
    if (schema?.tables) {
      Object.keys(schema.tables).forEach((tableName) => {
        const tableObj = schema.tables[tableName];
        if (tableObj && tableObj.columns) {
          flat[tableName] = Object.keys(tableObj.columns);
        }
      });
    } else {
      // Fallback if already flat
      Object.keys(schema || {}).forEach((key) => {
        if (Array.isArray(schema[key])) {
          flat[key] = schema[key];
        }
      });
    }
    return flat;
  };

  const handleIntrospect = async () => {
    setStep1Error('');
    if (dbType !== 'sqlite' && (!serverAddress || !dbName || !username)) {
      setStep1Error('Please fill in required database connection fields.');
      return;
    }

    setLoadingIntrospect(true);
    try {
      if (dbType === 'sqlite') {
        const res = await outreachService.generateDummyDb(derivedCampaignType);
        if (res.success && res.schema) {
          setDbName(res.db_path);
          setSchemaData(flattenSchema(res.schema));
          setCurrentStep(2);
        } else {
          setStep1Error('Failed to generate dummy database.');
        }
      } else {
        const res = await tenantService.introspectDb(getDbConfigPayload());
        if (res.success && res.schema) {
          setSchemaData(flattenSchema(res.schema));
          setCurrentStep(2);
        } else {
          setStep1Error(res.error || 'Failed to connect to database.');
        }
      }
    } catch (e: any) {
      setStep1Error(e.message || 'Error connecting to database.');
    } finally {
      setLoadingIntrospect(false);
    }
  };

  const handleColumnToggle = (col: string) => {
    setSelectedColumns((prev) => 
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  const handleValidateStep2 = () => {
    setStep2Error('');
    if (!companyName || !closingGoal || !productTable) {
      setStep2Error('Please provide Company Name, Closing Goal, and select a Product Table.');
      return;
    }
    setCurrentStep(3);
  };

  const handleSaveConfig = async () => {
    setLoadingSave(true);
    setSaveSuccessMsg('');
    setStep2Error('');
    
    try {
      const res = await outreachService.saveConfig({
        db_config: getDbConfigPayload(),
        campaign_type: derivedCampaignType,
        company_name: companyName,
        closing_goal: closingGoal,
        product_table: productTable,
        selected_columns: schemaData[productTable] || []
      });
      
      setSaveSuccessMsg('Outreach Pipeline configuration saved successfully!');
      if (onSaveSuccess) {
        onSaveSuccess();
      }
    } catch (e: any) {
      setStep2Error(e.message || 'Error saving outreach config.');
    } finally {
      setLoadingSave(false);
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-6 sm:p-8 shadow-2xl">
      {/* Wizard Header Stepper */}
      <div className="flex items-center justify-between mb-8 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400 font-bold">
            {currentStep}
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-100">
              {currentStep === 1 && '1. Database Connection & Schema Scanning'}
              {currentStep === 2 && '2. Outreach Strategy & Catalog Configurator'}
              {currentStep === 3 && '3. Save Pipeline Configuration'}
            </h3>
            <p className="text-xs text-slate-400">
              {currentStep === 1 && 'Connect your database to securely access your product catalog.'}
              {currentStep === 2 && 'Define your company persona and map the product inventory table.'}
              {currentStep === 3 && 'Finalize your outbound sales agent pipeline.'}
            </p>
          </div>
        </div>

        {/* Step Indicator Badges */}
        <div className="hidden sm:flex items-center gap-2">
          {[1, 2, 3].map((step) => (
            <div
              key={step}
              className={`w-8 h-2 rounded-full transition-all duration-300 ${
                currentStep === step
                  ? 'bg-violet-500 w-12'
                  : currentStep > step
                  ? 'bg-emerald-500'
                  : 'bg-slate-800'
              }`}
            />
          ))}
        </div>
      </div>

      {/* STEP 1: DB CREDENTIALS & CONNECT */}
      {currentStep === 1 && (
        <div className="space-y-6 animate-slide-up">
          {step1Error && <Alert severity="error" className="rounded-xl">{step1Error}</Alert>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
            <FormControl fullWidth size="small">
              <InputLabel id="db-type-label">Database Type</InputLabel>
              <Select
                labelId="db-type-label"
                value={dbType}
                label="Database Type"
                onChange={(e) => setDbType(e.target.value as string)}
              >
                <MenuItem value="sqlite">SQLite</MenuItem>
                <MenuItem value="postgresql">PostgreSQL</MenuItem>
                <MenuItem value="mysql">MySQL / MariaDB</MenuItem>
                <MenuItem value="sql server">Microsoft SQL Server</MenuItem>
              </Select>
            </FormControl>

            {dbType !== 'sqlite' && (
              <TextField
                size="small"
                label="Database Name"
                value={dbName}
                onChange={(e) => setDbName(e.target.value)}
                placeholder="sales_db"
                required
              />
            )}
          </div>

          {/* SQLite Dummy Generator */}
          {dbType === 'sqlite' && (
            <div className="bg-slate-950/50 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4">
              
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-bold text-slate-200">Dummy Database Generator</h4>
                  <p className="text-xs text-slate-400">We will automatically generate a dummy SQLite database with a {derivedCampaignType === 'sales' ? 'product catalog' : 'property listings'} for testing based on your active domain ({domainName}).</p>
                </div>
              </div>

              {dbName && (
                <div className="flex items-center gap-2 bg-slate-900/90 px-3 py-2 rounded-xl border border-slate-800 text-xs font-mono text-emerald-400">
                  <CheckCircleIcon sx={{ fontSize: 16 }} />
                  <span className="text-slate-400">Database Generated:</span>
                  <span className="font-bold text-slate-100">{dbName.includes('/') || dbName.includes('\\') ? dbName.split(/[/\\]/).pop() : dbName}</span>
                </div>
              )}
            </div>
          )}

          {dbType !== 'sqlite' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField
                size="small"
                label="Server Address / Host"
                value={serverAddress}
                onChange={(e) => setServerAddress(e.target.value)}
                placeholder="localhost"
              />
              <TextField
                size="small"
                label="Port"
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value ? Number(e.target.value) : '')}
                placeholder={dbType === 'postgresql' ? '5432' : dbType === 'mysql' ? '3306' : '1433'}
              />
              <TextField
                size="small"
                label="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="postgres"
              />
              <TextField
                size="small"
                label="Password"
                type="password"
                value={passwordDb}
                onChange={(e) => setPasswordDb(e.target.value)}
              />
            </div>
          )}

          <div className="pt-4 flex justify-end">
            <Button
              variant="contained"
              onClick={handleIntrospect}
              disabled={loadingIntrospect}
              startIcon={loadingIntrospect ? <CircularProgress size={20} color="inherit" /> : null}
              sx={{ px: 4, py: 1, borderRadius: '12px' }}
            >
              {loadingIntrospect ? 'Scanning Schema...' : 'Connect & Scan Schema'}
            </Button>
          </div>
        </div>
      )}

      {/* STEP 2: OUTREACH CONFIGURATOR */}
      {currentStep === 2 && (
        <div className="space-y-8 animate-slide-up">
          {step2Error && <Alert severity="error" className="rounded-xl">{step2Error}</Alert>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <TextField
              size="small"
              label="Company Name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g. Nova Telecom"
              required
              helperText="The name the AI will use to introduce itself."
            />
            <TextField
              size="small"
              label="Closing Goal"
              value={closingGoal}
              onChange={(e) => setClosingGoal(e.target.value)}
              placeholder="e.g. schedule a demo or make a sale"
              required
              helperText="The ultimate objective of the outbound call."
            />
          </div>

          <div className="bg-slate-950/50 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-inner">
            <div className="flex items-center gap-3 mb-6">
              <TableChartIcon sx={{ color: '#8b5cf6' }} />
              <div>
                <h4 className="font-bold text-slate-100 text-lg">Product Catalog Mapping</h4>
                <p className="text-xs text-slate-400">Select the table containing your products, then pick the columns the AI can use to pitch features.</p>
              </div>
            </div>

            <FormControl fullWidth size="small" className="mb-6">
              <InputLabel>Product Table</InputLabel>
              <Select
                value={productTable}
                label="Product Table"
                onChange={(e) => {
                  setProductTable(e.target.value);
                  setSelectedColumns([]); // reset columns on table change
                }}
              >
                {Object.keys(schemaData).map((table) => (
                  <MenuItem key={table} value={table}>
                    <span className="font-mono text-sm">{table}</span>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Column selection removed per user request: 'only table can be selected' */}
          </div>

          <div className="flex justify-between pt-4">
            <Button
              variant="outlined"
              color="inherit"
              onClick={() => setCurrentStep(1)}
              sx={{ borderRadius: '12px' }}
            >
              Back
            </Button>
            <Button
              variant="contained"
              onClick={handleValidateStep2}
              sx={{ px: 4, py: 1, borderRadius: '12px' }}
            >
              Review Configuration
            </Button>
          </div>
        </div>
      )}

      {/* STEP 3: SUMMARY */}
      {currentStep === 3 && (
        <div className="space-y-6 animate-slide-up">
          {step2Error && <Alert severity="error">{typeof step2Error === 'string' ? step2Error : JSON.stringify(step2Error)}</Alert>}
          {saveSuccessMsg && <Alert severity="success">{saveSuccessMsg}</Alert>}

          <div className="bg-emerald-950/20 border border-emerald-900/50 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <CampaignIcon sx={{ color: '#34d399', fontSize: 32 }} />
              <h4 className="text-xl font-bold text-emerald-400">Outreach Agent Ready</h4>
            </div>
            
            <p className="text-slate-300 mb-6 leading-relaxed">
              Your AI outbound sales representative for <strong>{companyName}</strong> is configured. 
              The agent will proactively dial leads, introduce itself, and attempt to <strong>{closingGoal}</strong> by dynamically querying the <code className="bg-slate-900 px-1.5 py-0.5 rounded text-emerald-300 text-sm border border-slate-800">{productTable}</code> catalog.
            </p>

            <Accordion 
              className="bg-slate-900/50" 
              sx={{ 
                bgcolor: 'transparent',
                backgroundImage: 'none',
                boxShadow: 'none',
                '&:before': { display: 'none' },
                border: '1px solid #1e293b',
                borderRadius: '12px !important'
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#94a3b8' }} />}>
                <span className="text-sm font-semibold text-slate-300">View Data Access Rules</span>
              </AccordionSummary>
              <AccordionDetails className="border-t border-slate-800">
                <ul className="list-disc pl-5 text-sm text-slate-400 space-y-1">
                  <li><strong>Target Catalog:</strong> {productTable}</li>
                  <li><strong>AI Access Columns:</strong> {selectedColumns.join(', ')}</li>
                </ul>
              </AccordionDetails>
            </Accordion>
          </div>

          <div className="flex justify-between pt-4">
            <Button
              variant="outlined"
              color="inherit"
              onClick={() => setCurrentStep(2)}
              disabled={loadingSave}
              sx={{ borderRadius: '12px' }}
            >
              Back
            </Button>
            <Button
              variant="contained"
              onClick={handleSaveConfig}
              disabled={loadingSave}
              startIcon={loadingSave ? <CircularProgress size={20} color="inherit" /> : <SaveIcon />}
              sx={{ px: 4, py: 1, borderRadius: '12px', background: 'linear-gradient(to right, #059669, #10b981)' }}
            >
              {loadingSave ? 'Saving...' : 'Deploy Pipeline'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
