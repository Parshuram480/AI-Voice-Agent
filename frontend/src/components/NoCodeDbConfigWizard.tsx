import React, { useState, useEffect } from 'react';
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
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import StorageIcon from '@mui/icons-material/Storage';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import SaveIcon from '@mui/icons-material/Save';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import TableChartIcon from '@mui/icons-material/TableChart';
import BuildIcon from '@mui/icons-material/Build';

import { tenantService } from '../services/tenantService';

export interface NoCodeDbConfigWizardProps {
  domainId?: number;
  initialDbConfig?: any;
  initialMetadata?: any;
  onSaveSuccess?: () => void;
  isRegistrationMode?: boolean;
  onConfigCompleted?: (data: {
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
  }) => void;
}

export default function NoCodeDbConfigWizard({
  domainId = 1,
  initialDbConfig,
  initialMetadata,
  onSaveSuccess,
  isRegistrationMode = false,
  onConfigCompleted,
}: NoCodeDbConfigWizardProps) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  // Step tracking (1: DB Credentials, 2: Rule Mapping, 3: AI Summary Review)
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

  // Step 2: Multi-Table Rule Configurator State
  const [customerTable, setCustomerTable] = useState<string>(
    initialMetadata?.identity?.table || initialMetadata?.customerTable || ''
  );
  const [verificationFields, setVerificationFields] = useState<string[]>(
    initialMetadata?.identity?.display_columns || initialMetadata?.verificationFields || []
  );
  
  // Map of selected related tables and their accessible columns: { [tableName]: string[] }
  const [selectedTables, setSelectedTables] = useState<Record<string, string[]>>(
    initialMetadata?.selected_tables || initialMetadata?.selectedTables || {}
  );

  const [step2Error, setStep2Error] = useState('');

  // Step 3: Summary State
  const [aiSummary, setAiSummary] = useState('');
  const [loadingSave, setLoadingSave] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('');

  // Pre-fill state whenever initialDbConfig or initialMetadata changes
  useEffect(() => {
    if (initialDbConfig) {
      if (initialDbConfig.db_type) setDbType(initialDbConfig.db_type);
      if (initialDbConfig.db_name) setDbName(initialDbConfig.db_name);
      if (initialDbConfig.server_name) setServerAddress(initialDbConfig.server_name);
      if (initialDbConfig.port) setPort(initialDbConfig.port);
      if (initialDbConfig.username) setUsername(initialDbConfig.username);
    }
    if (initialMetadata) {
      const custTab = initialMetadata.identity?.table || initialMetadata.customerTable || '';
      const verFields = initialMetadata.identity?.display_columns || initialMetadata.verificationFields || [];
      const selTables = initialMetadata.selected_tables || initialMetadata.selectedTables || {};
      
      if (custTab) setCustomerTable(custTab);
      if (verFields.length > 0) setVerificationFields(verFields);
      if (Object.keys(selTables).length > 0) setSelectedTables(selTables);
    }
  }, [initialDbConfig, initialMetadata]);

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
      if (res.success && res.schema) {
        // Map hierarchical schema { tables: { tableName: { columns: { colName: ... } } } } into flat Record<string, string[]>
        const flatSchema: Record<string, string[]> = {};
        if (res.schema.tables) {
          Object.keys(res.schema.tables).forEach((tableName) => {
            const tableObj = res.schema.tables[tableName];
            if (tableObj && tableObj.columns) {
              flatSchema[tableName] = Object.keys(tableObj.columns);
            }
          });
        } else {
          // Fallback if schema structure is already flat
          Object.keys(res.schema).forEach((key) => {
            if (Array.isArray(res.schema[key])) {
              flatSchema[key] = res.schema[key];
            }
          });
        }

        if (Object.keys(flatSchema).length > 0) {
          setSchemaData(flatSchema);
          const tables = Object.keys(flatSchema);
          
          // Preserve existing identity table if valid, or default to first table
          const custTab = customerTable && flatSchema[customerTable] ? customerTable : (tables[0] || '');
          setCustomerTable(custTab);

          // Preserve existing verification fields if valid, or default to first 2 matching columns
          if (flatSchema[custTab] && verificationFields.length === 0) {
            const cols = flatSchema[custTab];
            const defaults = cols.filter((c: string) => /name|dob|birth|email|phone|code|id/i.test(c));
            setVerificationFields(defaults.length > 0 ? defaults.slice(0, 2) : cols.slice(0, 2));
          }

          // Merge existing selectedTables with scanned schema
          const currentSavedTables = initialMetadata?.selected_tables || initialMetadata?.selectedTables || {};
          const initialSelectedTables: Record<string, string[]> = {};
          const hasSavedConfig = Boolean(initialMetadata);

          tables.forEach((tbl) => {
            if (tbl !== custTab) {
              if (currentSavedTables[tbl]) {
                initialSelectedTables[tbl] = currentSavedTables[tbl];
              } else if (!hasSavedConfig) {
                initialSelectedTables[tbl] = flatSchema[tbl] || [];
              }
            }
          });
          setSelectedTables(initialSelectedTables);

          setCurrentStep(2);
        } else {
          setStep1Error(res.message || 'Could not find readable tables in database.');
        }
      } else {
        setStep1Error(res.message || 'Could not find readable tables in database.');
      }
    } catch (e: any) {
      setStep1Error(e.message || 'Error connecting to database.');
    } finally {
      setLoadingIntrospect(false);
    }
  };

  // Toggle table selection
  const toggleTableSelection = (tableName: string, checked: boolean) => {
    const updated = { ...selectedTables };
    if (checked) {
      updated[tableName] = schemaData[tableName] || [];
    } else {
      delete updated[tableName];
    }
    setSelectedTables(updated);
  };

  // Toggle column selection inside a specific table
  const toggleColumnInTable = (tableName: string, colName: string, checked: boolean) => {
    const currentCols = selectedTables[tableName] || [];
    let newCols: string[];
    if (checked) {
      newCols = [...currentCols, colName];
    } else {
      newCols = currentCols.filter((c) => c !== colName);
    }
    setSelectedTables({
      ...selectedTables,
      [tableName]: newCols,
    });
  };

  // Step 2: Generate Agent Configuration Summary
  const handleGenerateRules = () => {
    setStep2Error('');
    if (!customerTable) {
      setStep2Error('Please select a Primary Identity table.');
      return;
    }
    if (verificationFields.length === 0) {
      setStep2Error('Please select at least one column for identity verification.');
      return;
    }

    const selectedTableNames = Object.keys(selectedTables);
    if (selectedTableNames.length === 0) {
      setStep2Error('Please select at least one Business Data table for the Voice Agent.');
      return;
    }

    // Generate client-side plain-English rule summary for display
    const summaryStr = `The AI Voice Agent will dynamically identify callers in table "${customerTable}" verifying details against columns: ${verificationFields.join(', ')}. Once verified, it will construct dynamic joins and SQL lookups to search business records in: ${selectedTableNames.join(', ')}.`;
    setAiSummary(summaryStr);
    setCurrentStep(3);
  };

  // Step 3: Save Final Rules
  const handleSaveFinalRules = async () => {
    const fullSelectedTablesMap: Record<string, string[]> = {
      [customerTable]: schemaData[customerTable] || verificationFields,
      ...selectedTables,
    };

    const identityPayload = {
      table: customerTable,
      name_column: verificationFields.find((f) => f.toLowerCase().includes('name')) || verificationFields[0] || 'full_name',
      verification_column: verificationFields.find((f) => !f.toLowerCase().includes('name')) || verificationFields[0] || 'date_of_birth',
      display_columns: verificationFields,
    };

    const uiMetadata = {
      identity: identityPayload,
      selected_tables: fullSelectedTablesMap,
      customerTable,
      verificationFields,
      selectedTables,
    };

    if (isRegistrationMode && onConfigCompleted) {
      onConfigCompleted({
        dbConfig: getDbConfigPayload(),
        domainId,
        identity: identityPayload,
        selectedTables: fullSelectedTablesMap,
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
        identity: identityPayload,
        selected_tables: fullSelectedTablesMap,
        ui_config_metadata: uiMetadata,
      });

      if (res.success) {
        setSaveSuccessMsg('Database configuration & AI Voice Agent dynamic rules saved successfully!');
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
              {currentStep === 1 && '1. Database Connection & Schema Scanning'}
              {currentStep === 2 && '2. Dynamic Multi-Table Rule Configurator'}
              {currentStep === 3 && '3. AI Agent Summary & Dynamic Tools Review'}
            </h3>
            <p className="text-xs text-slate-400">
              {currentStep === 1 && 'Enter credentials or upload SQLite file to discover tables and columns.'}
              {currentStep === 2 && 'Select tables & column fields for caller verification & AI access.'}
              {currentStep === 3 && 'Review plain-English agent summary & dynamic tools capabilities.'}
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

      {/* STEP 2: DYNAMIC MULTI-TABLE RULE CONFIGURATOR */}
      {currentStep === 2 && (
        <div className="space-y-6">
          {step2Error && <Alert severity="error" className="rounded-xl">{step2Error}</Alert>}

          {/* Primary Identity Table Selector */}
          <div>
            <FormControl fullWidth size="small">
              <InputLabel id="cust-table-label">Primary Identity Table (Caller Information)</InputLabel>
              <Select
                labelId="cust-table-label"
                value={customerTable}
                label="Primary Identity Table (Caller Information)"
                onChange={(e) => {
                  const t = e.target.value;
                  setCustomerTable(t);
                  if (schemaData[t]) {
                    setVerificationFields(schemaData[t].slice(0, 2));
                  }
                  const updatedRelated = { ...selectedTables };
                  delete updatedRelated[t];
                  setSelectedTables(updatedRelated);
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
                Which columns from <span className="text-sky-400 font-mono">{customerTable}</span> should verify callers?
              </h4>
              <p className="text-xs text-slate-400 mb-3">Select one or more identity verification columns from your table.</p>
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
                            let newFields = [...verificationFields, col];
                            if (newFields.length > 2) {
                              newFields = newFields.slice(1);
                            }
                            setVerificationFields(newFields);
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

          {/* Multi-Table Business Data Selector */}
          <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4">
            <div>
              <h4 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <TableChartIcon sx={{ fontSize: 18, color: '#a78bfa' }} />
                Which business tables & fields can the AI Agent search and speak about?
              </h4>
              <p className="text-xs text-slate-400 mt-1">
                Select one or more related business tables (e.g. orders, menu items, appointments) and pick accessible fields for each.
              </p>
            </div>

            <div className="space-y-3">
              {Object.keys(schemaData)
                .filter((tbl) => tbl !== customerTable)
                .map((tbl) => {
                  const isTableSelected = Boolean(selectedTables[tbl]);
                  const colsInTable = selectedTables[tbl] || [];

                  return (
                    <Accordion
                      key={tbl}
                      sx={{
                        background: isDark ? '#020617' : '#ffffff',
                        border: isDark ? '1px solid #1e293b' : '1px solid #e2e8f0',
                        borderRadius: '12px !important',
                        '&:before': { display: 'none' },
                        boxShadow: isDark ? 'none' : '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
                      }}
                    >
                      <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: isDark ? '#94a3b8' : '#64748b' }} />}>
                        <div className="flex items-center gap-3">
                          <FormControlLabel
                            onClick={(e) => e.stopPropagation()}
                            control={
                              <Checkbox
                                size="small"
                                checked={isTableSelected}
                                onChange={(e) => toggleTableSelection(tbl, e.target.checked)}
                                sx={{ color: '#10b981', '&.Mui-checked': { color: '#10b981' } }}
                              />
                            }
                            label={
                              <span className="text-sm font-bold text-slate-200 font-mono">
                                {tbl}
                              </span>
                            }
                          />
                          {isTableSelected && (
                            <span className="text-xs bg-emerald-950 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-mono">
                              {colsInTable.length} fields enabled
                            </span>
                          )}
                        </div>
                      </AccordionSummary>
                      <AccordionDetails className="border-t border-slate-900 pt-3">
                        <p className="text-xs text-slate-400 mb-2">Check the specific fields the agent is allowed to access:</p>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                          {schemaData[tbl].map((col) => (
                            <FormControlLabel
                              key={col}
                              control={
                                <Checkbox
                                  size="small"
                                  checked={colsInTable.includes(col)}
                                  onChange={(e) => toggleColumnInTable(tbl, col, e.target.checked)}
                                  sx={{ color: '#10b981', '&.Mui-checked': { color: '#10b981' } }}
                                />
                              }
                              label={<span className="text-xs text-slate-300 font-mono">{col}</span>}
                            />
                          ))}
                        </div>
                      </AccordionDetails>
                    </Accordion>
                  );
                })}
            </div>
          </div>

          <div className="flex justify-between items-center pt-4">
            <Button variant="outlined" onClick={() => setCurrentStep(1)}>
              Back to Connection
            </Button>
            <Button
              variant="contained"
              color="primary"
              onClick={handleGenerateRules}
              startIcon={<AutoAwesomeIcon />}
              sx={{ px: 4, py: 1.2, borderRadius: '12px', background: 'linear-gradient(to right, #8b5cf6, #ec4899)' }}
            >
              Continue to Review
            </Button>
          </div>
        </div>
      )}

      {/* STEP 3: AI SUMMARY & DYNAMIC TOOLS REVIEW */}
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

          {/* Dynamic Tools & Capabilities Preview */}
          <div className="bg-slate-950/50 border border-slate-800 rounded-2xl p-5 space-y-4">
            <h4 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <BuildIcon sx={{ color: '#38bdf8' }} />
              Dynamic Tools Capabilities Registered for Voice Agent
            </h4>
            
            <div className="space-y-2">
              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
                <div>
                  <span className="font-bold text-violet-400 font-mono">verify_customer_identity</span>
                  <p className="text-slate-400">Verifies caller identity on table <span className="text-violet-400 font-mono">{customerTable}</span> using {verificationFields.join(', ')}</p>
                </div>
                <span className="bg-violet-950 text-violet-400 border border-violet-500/30 px-2 py-0.5 rounded-full font-mono">
                  Authentication Tool
                </span>
              </div>

              {Object.keys(selectedTables).map((tbl) => (
                <div key={tbl} className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-emerald-400 font-mono">search_{tbl}</span>
                    <p className="text-slate-400">Dynamically constructs joins & SQL queries to search <span className="text-emerald-400 font-mono">{tbl}</span> ({selectedTables[tbl].length} fields enabled)</p>
                  </div>
                  <span className="bg-emerald-950 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-mono">
                    Dynamic Query Tool
                  </span>
                </div>
              ))}
            </div>
          </div>

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
              {loadingSave ? 'Saving Dynamic Rules...' : 'Save Agent Configuration'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
