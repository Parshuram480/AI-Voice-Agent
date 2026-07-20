import React, { useState } from 'react';
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
import Typography from '@mui/material/Typography';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import StorageIcon from '@mui/icons-material/Storage';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SaveIcon from '@mui/icons-material/Save';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';

import { tenantService } from '../services/tenantService';

export interface NoCodeDbConfigWizardProps {
  domainId?: number;
  onSaveSuccess?: () => void;
  isRegistrationMode?: boolean;
  onConfigCompleted?: (data: {
    dbConfig: any;
    domainId: number;
    verificationQuery: string;
    dataQuery: string;
    uiConfigMetadata: any;
  }) => void;
}

export default function NoCodeDbConfigWizard({
  domainId = 1,
  onSaveSuccess,
  isRegistrationMode = false,
  onConfigCompleted,
}: NoCodeDbConfigWizardProps) {
  // Step tracking (1: DB Credentials, 2: Rule Mapping, 3: AI Summary & Test)
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

  // Step 1: DB Credentials State
  const [dbType, setDbType] = useState('sqlite');
  const [dbName, setDbName] = useState();
  const [serverAddress, setServerAddress] = useState('localhost');
  const [port, setPort] = useState<number | ''>(5432);
  const [username, setUsername] = useState('postgres');
  const [passwordDb, setPasswordDb] = useState('');
  const [schemaName] = useState('');
  const [enableSsl] = useState(false);
  const [trustCert] = useState(false);
  const [timeout] = useState(5);

  const [schemaData, setSchemaData] = useState<Record<string, string[]>>({});
  const [loadingIntrospect, setLoadingIntrospect] = useState(false);
  const [uploadingDb, setUploadingDb] = useState(false);
  const [step1Error, setStep1Error] = useState('');

  // Step 2: Rule Configurator State
  const [customerTable, setCustomerTable] = useState<string>('');
  const [verificationFields, setVerificationFields] = useState<string[]>([]);
  const [dataTable, setDataTable] = useState<string>('');
  const [selectedDataFields, setSelectedDataFields] = useState<string[]>([]);
  const [loadingGenerate, setLoadingGenerate] = useState(false);
  const [step2Error, setStep2Error] = useState('');

  // Step 3: AI Summary & Test Preview State
  const [aiSummary, setAiSummary] = useState('');
  const [verificationQuery, setVerificationQuery] = useState('');
  const [dataQuery, setDataQuery] = useState('');

  // Dynamic test inputs map { [columnName]: inputValue }
  const [testInputs, setTestInputs] = useState<Record<string, string>>({});
  const [loadingTest, setLoadingTest] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    verified: boolean;
    message: string;
    customer?: any;
    records?: any[];
  } | null>(null);

  const [loadingSave, setLoadingSave] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('');

  // Helper to build DB config payload
  const getDbConfigPayload = () => ({
    db_type: dbType,
    server_name: dbType !== 'sqlite' ? serverAddress : undefined,
    port: dbType !== 'sqlite' && port !== '' ? Number(port) : undefined,
    db_name: dbName,
    username: dbType !== 'sqlite' ? username : undefined,
    password: dbType !== 'sqlite' ? passwordDb : undefined,
    schema_name: schemaName || undefined,
    enable_ssl: enableSsl,
    trust_server_certificate: trustCert,
    connection_timeout: Number(timeout) || 5,
  });

  // Handle SQLite File Upload
  const handleSqliteFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploadingDb(true);
    setStep1Error('');
    try {
      const res = await tenantService.uploadSqliteDb(files[0]);
      if (res.success && res.db_name) {
        setDbName(res.db_name);
      } else {
        setStep1Error(res.message || 'SQLite file upload failed.');
      }
    } catch (err: any) {
      setStep1Error(err.message || 'Error uploading file.');
    } finally {
      setUploadingDb(false);
    }
  };

  // Step 1: Introspect Database
  const handleIntrospect = async () => {
    setStep1Error('');
    if (!dbName.trim()) {
      setStep1Error('Database name is required');
      return;
    }
    setLoadingIntrospect(true);
    try {
      const res = await tenantService.introspectDb(getDbConfigPayload());
      if (res.success && res.schema && Object.keys(res.schema).length > 0) {
        setSchemaData(res.schema);
        const tables = Object.keys(res.schema);
        const custTab = tables[0] || '';
        const dataTab = tables[1] || tables[0] || '';
        setCustomerTable(custTab);
        setDataTable(dataTab);

        if (res.schema[custTab]) {
          const cols = res.schema[custTab];
          const defaults = cols.filter((c: string) => /name|dob|birth|email|phone|code|id/i.test(c));
          setVerificationFields(defaults.length > 0 ? defaults.slice(0, 2) : cols.slice(0, 2));
        }

        if (res.schema[dataTab]) {
          setSelectedDataFields(res.schema[dataTab]);
        }
        setCurrentStep(2);
      } else {
        setStep1Error(res.message || 'Could not find readable tables in database.');
      }
    } catch (e: any) {
      setStep1Error(e.message || 'Error connecting to database.');
    } finally {
      setLoadingIntrospect(false);
    }
  };

  // Step 2: Generate AI Rules
  const handleGenerateRules = async () => {
    setStep2Error('');
    if (!customerTable) {
      setStep2Error('Please select a Primary Identity table.');
      return;
    }
    if (!dataTable) {
      setStep2Error('Please select a Related Data table.');
      return;
    }
    if (verificationFields.length === 0) {
      setStep2Error('Please select at least one column for identity verification.');
      return;
    }

    setLoadingGenerate(true);
    try {
      const res = await tenantService.generateRules({
        db_config: getDbConfigPayload(),
        customer_table: customerTable,
        verification_fields: verificationFields,
        data_table: dataTable,
        data_fields: selectedDataFields,
        schema_data: schemaData,
      });

      if (res.success) {
        setAiSummary(res.summary);
        setVerificationQuery(res.verification_query);
        setDataQuery(res.data_query);

        // Pre-fill test inputs map for chosen verification fields
        const initialTestInputs: Record<string, string> = {};
        verificationFields.forEach((field) => {
          initialTestInputs[field] = field.toLowerCase().includes('name') ? 'John Smith' : '1990-05-15';
        });
        setTestInputs(initialTestInputs);

        setCurrentStep(3);
      } else {
        setStep2Error(res.message || 'Failed to generate AI rules.');
      }
    } catch (e: any) {
      setStep2Error(e.message || 'Error generating AI rules.');
    } finally {
      setLoadingGenerate(false);
    }
  };

  // Step 3: Test Query Execution
  const handleRunTest = async () => {
    setLoadingTest(true);
    setTestResult(null);
    try {
      const inputsArray = verificationFields.map((field) => testInputs[field] || '');
      const res = await tenantService.testQuery({
        db_config: getDbConfigPayload(),
        verification_query: verificationQuery,
        data_query: dataQuery,
        test_inputs: inputsArray,
      });
      setTestResult(res);
    } catch (e: any) {
      setTestResult({
        success: false,
        verified: false,
        message: e.message || 'Error executing test query.',
      });
    } finally {
      setLoadingTest(false);
    }
  };

  // Step 3: Save Final Rules
  const handleSaveFinalRules = async () => {
    const uiMetadata = {
      verificationFields,
      customerTable,
      dataTable,
      selectedDataFields,
    };

    if (isRegistrationMode && onConfigCompleted) {
      onConfigCompleted({
        dbConfig: getDbConfigPayload(),
        domainId,
        verificationQuery,
        dataQuery,
        uiConfigMetadata: uiMetadata,
      });
      return;
    }

    setLoadingSave(true);
    setSaveSuccessMsg('');
    try {
      const res = await tenantService.saveRules({
        db_config: getDbConfigPayload(),
        domain_id: domainId,
        verification_query: verificationQuery,
        data_query: dataQuery,
        ui_config_metadata: uiMetadata,
      });

      if (res.success) {
        setSaveSuccessMsg('Database configuration and AI voice agent rules saved successfully!');
        if (onSaveSuccess) {
          onSaveSuccess();
        }
      }
    } catch (e: any) {
      setStep2Error(e.message || 'Error saving rules.');
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
              {currentStep === 1 && '1. Database Connection & Introspection'}
              {currentStep === 2 && '2. Dynamic Visual Rule Configurator'}
              {currentStep === 3 && '3. AI Agent Summary & Connection Test'}
            </h3>
            <p className="text-xs text-slate-400">
              {currentStep === 1 && 'Enter credentials or upload SQLite file to discover tables and columns.'}
              {currentStep === 2 && 'Select table columns for identity verification & data lookup.'}
              {currentStep === 3 && 'Verify plain-English rules and test connection live.'}
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
        <div className="space-y-6">
          {step1Error && <Alert severity="error" className="rounded-xl">{step1Error}</Alert>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
            <FormControl fullWidth size="small">
              <InputLabel id="db-type-label">Database Type</InputLabel>
              <Select
                labelId="db-type-label"
                value={dbType}
                label="Database Type"
                onChange={(e) => setDbType(e.target.value)}
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
                placeholder="healthcare_db"
                required
              />
            )}
          </div>

          {/* SQLite File Upload Option */}
          {dbType === 'sqlite' && (
            <div className="bg-slate-950/50 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-bold text-slate-200">SQLite Database File</h4>
                  <p className="text-xs text-slate-400">Upload your .db or .sqlite database file to scan schema.</p>
                </div>
                <Button
                  component="label"
                  variant="contained"
                  color="secondary"
                  size="small"
                  startIcon={uploadingDb ? <CircularProgress size={16} color="inherit" /> : <CloudUploadIcon />}
                  disabled={uploadingDb}
                  sx={{ borderRadius: '10px', px: 3 }}
                >
                  {uploadingDb ? 'Uploading File...' : dbName && dbName !== 'healthcare_client.db' ? 'Change .db File' : 'Upload .db File'}
                  <input
                    type="file"
                    hidden
                    accept=".db,.sqlite,.sqlite3"
                    onChange={handleSqliteFileUpload}
                  />
                </Button>
              </div>

              {dbName && (
                <div className="flex items-center gap-2 bg-slate-900/90 px-3 py-2 rounded-xl border border-slate-800 text-xs font-mono text-emerald-400">
                  <CheckCircleIcon sx={{ fontSize: 16 }} />
                  <span className="text-slate-400">Selected File:</span>
                  <span className="font-bold text-slate-100">{dbName.includes('/') ? dbName.split('/').pop() : dbName}</span>
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
                type="number"
                label="Port"
                value={port}
                onChange={(e) => setPort(e.target.value === '' ? '' : Number(e.target.value))}
                placeholder={dbType === 'postgresql' ? '5432' : '3306'}
              />
              <TextField
                size="small"
                label="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <TextField
                size="small"
                type="password"
                label="Password"
                value={passwordDb}
                onChange={(e) => setPasswordDb(e.target.value)}
              />
            </div>
          )}

          <div className="flex justify-end pt-4">
            <Button
              variant="contained"
              color="primary"
              onClick={handleIntrospect}
              disabled={loadingIntrospect || uploadingDb}
              startIcon={loadingIntrospect ? <CircularProgress size={18} color="inherit" /> : <StorageIcon />}
              sx={{ px: 4, py: 1.2, borderRadius: '12px' }}
            >
              {loadingIntrospect ? 'Scanning Database...' : 'Connect & Scan Schema'}
            </Button>
          </div>
        </div>
      )}

      {/* STEP 2: DYNAMIC RULE CONFIGURATOR */}
      {currentStep === 2 && (
        <div className="space-y-6">
          {step2Error && <Alert severity="error" className="rounded-xl">{step2Error}</Alert>}

          {/* Table Dropdowns */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormControl fullWidth size="small">
              <InputLabel id="cust-table-label">Primary Identity Table</InputLabel>
              <Select
                labelId="cust-table-label"
                value={customerTable}
                label="Primary Identity Table"
                onChange={(e) => {
                  const t = e.target.value;
                  setCustomerTable(t);
                  if (schemaData[t]) {
                    setVerificationFields(schemaData[t].slice(0, 2));
                  }
                }}
              >
                {Object.keys(schemaData).map((t) => (
                  <MenuItem key={t} value={t}>{t}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small">
              <InputLabel id="data-table-label">Related Details / Data Table</InputLabel>
              <Select
                labelId="data-table-label"
                value={dataTable}
                label="Related Details / Data Table"
                onChange={(e) => {
                  const t = e.target.value;
                  setDataTable(t);
                  if (schemaData[t]) {
                    setSelectedDataFields(schemaData[t]);
                  }
                }}
              >
                {Object.keys(schemaData).map((t) => (
                  <MenuItem key={t} value={t}>{t}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </div>

          {/* Dynamic Verification Columns Checklist */}
          {customerTable && schemaData[customerTable] && (
            <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-4 sm:p-5">
              <h4 className="text-sm font-bold text-slate-200 mb-2 flex items-center gap-2">
                <VerifiedUserIcon sx={{ fontSize: 18, color: '#38bdf8' }} />
                Which columns from <span className="text-sky-400">{customerTable}</span> should verify callers?
              </h4>
              <p className="text-xs text-slate-400 mb-3">Select one or more identity verification columns from your database table.</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {schemaData[customerTable].map((col) => (
                  <FormControlLabel
                    key={col}
                    control={
                      <Checkbox
                        size="small"
                        checked={verificationFields.includes(col)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setVerificationFields([...verificationFields, col]);
                          } else {
                            setVerificationFields(verificationFields.filter((f) => f !== col));
                          }
                        }}
                        sx={{ color: '#8b5cf6', '&.Mui-checked': { color: '#8b5cf6' } }}
                      />
                    }
                    label={<span className="text-xs text-slate-300 font-mono">{col}</span>}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Accessible Data Fields Checklist */}
          {dataTable && schemaData[dataTable] && (
            <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-4 sm:p-5">
              <h4 className="text-sm font-bold text-slate-200 mb-2">
                Which fields from <span className="text-violet-400">{dataTable}</span> can the Agent access & speak?
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {schemaData[dataTable].map((col) => (
                  <FormControlLabel
                    key={col}
                    control={
                      <Checkbox
                        size="small"
                        checked={selectedDataFields.includes(col)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedDataFields([...selectedDataFields, col]);
                          } else {
                            setSelectedDataFields(selectedDataFields.filter((c) => c !== col));
                          }
                        }}
                        sx={{ color: '#10b981', '&.Mui-checked': { color: '#10b981' } }}
                      />
                    }
                    label={<span className="text-xs text-slate-300 font-mono">{col}</span>}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-between items-center pt-4">
            <Button variant="outlined" onClick={() => setCurrentStep(1)}>
              Back to Connection
            </Button>
            <Button
              variant="contained"
              color="primary"
              onClick={handleGenerateRules}
              disabled={loadingGenerate}
              startIcon={loadingGenerate ? <CircularProgress size={18} color="inherit" /> : <AutoAwesomeIcon />}
              sx={{ px: 4, py: 1.2, borderRadius: '12px', background: 'linear-gradient(to right, #8b5cf6, #ec4899)' }}
            >
              {loadingGenerate ? 'Generating AI Rules...' : 'Generate AI Agent Configuration'}
            </Button>
          </div>
        </div>
      )}

      {/* STEP 3: AI SUMMARY & TEST PREVIEW */}
      {currentStep === 3 && (
        <div className="space-y-6">
          {saveSuccessMsg && (
            <Alert severity="success" className="rounded-xl flex items-center">
              {saveSuccessMsg}
            </Alert>
          )}

          {/* Natural Language Summary Banner */}
          <div className="bg-gradient-to-r from-violet-950/40 via-slate-900 to-emerald-950/40 border border-violet-500/30 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center gap-3 mb-2">
              <AutoAwesomeIcon sx={{ color: '#a78bfa', fontSize: 24 }} />
              <h4 className="text-base font-bold text-slate-100">AI Voice Agent Behavior Summary</h4>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">{aiSummary}</p>
          </div>

          {/* Interactive Live Test Card with Dynamic Column Inputs */}
          <div className="bg-slate-950/50 border border-slate-800 rounded-2xl p-5 space-y-4">
            <h4 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <PlayArrowIcon sx={{ color: '#10b981' }} />
              Try a Live Test Connection Query
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {verificationFields.map((field) => (
                <TextField
                  key={field}
                  size="small"
                  label={`Sample value for '${field}'`}
                  value={testInputs[field] || ''}
                  onChange={(e) =>
                    setTestInputs({
                      ...testInputs,
                      [field]: e.target.value,
                    })
                  }
                />
              ))}
            </div>
            <Button
              variant="outlined"
              color="success"
              onClick={handleRunTest}
              disabled={loadingTest}
              startIcon={loadingTest ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
            >
              {loadingTest ? 'Executing Query...' : 'Run Test Verification'}
            </Button>

            {testResult && (
              <div
                className={`p-4 rounded-xl border ${
                  testResult.verified
                    ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
                    : 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                }`}
              >
                <div className="flex items-center gap-2 font-bold mb-2">
                  <CheckCircleIcon fontSize="small" />
                  {testResult.message}
                </div>
                {testResult.records && testResult.records.length > 0 && (
                  <div className="text-xs space-y-1 font-mono bg-slate-950/80 p-3 rounded-lg border border-slate-800 text-slate-300 max-h-40 overflow-y-auto">
                    {testResult.records.map((r, i) => (
                      <div key={i} className="border-b border-slate-800 pb-1 mb-1 last:border-none">
                        Record #{i + 1}: {JSON.stringify(r)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Collapsible Advanced Developer View */}
          <Accordion sx={{ background: '#020617', border: '1px solid #1e293b', borderRadius: '12px !important' }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#94a3b8' }} />}>
              <Typography sx={{ fontSize: '0.875rem', fontWeight: 600, color: '#94a3b8' }}>
                Advanced Developer SQL Queries View
              </Typography>
            </AccordionSummary>
            <AccordionDetails className="space-y-4">
              <div>
                <span className="text-xs text-slate-400 font-bold uppercase">Verification Query:</span>
                <pre className="text-xs bg-slate-950 p-3 rounded-lg border border-slate-800 text-violet-300 font-mono overflow-x-auto mt-1">
                  {verificationQuery}
                </pre>
              </div>
              <div>
                <span className="text-xs text-slate-400 font-bold uppercase">Data Retrieval Query:</span>
                <pre className="text-xs bg-slate-950 p-3 rounded-lg border border-slate-800 text-emerald-300 font-mono overflow-x-auto mt-1">
                  {dataQuery}
                </pre>
              </div>
            </AccordionDetails>
          </Accordion>

          {/* Action Footer */}
          <div className="flex justify-between items-center pt-4">
            <Button variant="outlined" onClick={() => setCurrentStep(2)}>
              Back to Configuration
            </Button>
            <Button
              variant="contained"
              color="success"
              onClick={handleSaveFinalRules}
              disabled={loadingSave}
              startIcon={loadingSave ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
              sx={{ px: 5, py: 1.2, borderRadius: '12px' }}
            >
              {loadingSave ? 'Saving Rules...' : 'Save Agent Configuration'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
