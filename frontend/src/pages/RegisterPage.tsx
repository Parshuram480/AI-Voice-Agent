import React, { useState, useEffect } from 'react';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';

import { useNavigate } from 'react-router-dom';
import { authService } from '../services/authService';
import { domainService } from '../services/domainService';

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
  const [confirmPassword, setConfirmPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [domainId, setDomainId] = useState<number>(1);
  const [domains, setDomains] = useState<Domain[]>([]);

  // Page level message
  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState<'success' | 'error' | ''>('');
  const [submitting, setSubmitting] = useState(false);

  // OTP Verification flow state
  const [showOtpModal, setShowOtpModal] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [otpError, setOtpError] = useState('');
  const [verifyingOtp, setVerifyingOtp] = useState(false);
  const [resendingOtp, setResendingOtp] = useState(false);

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

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMsg('');
    setStatusType('');

    if (!companyName.trim() || !clientName.trim() || !email.trim() || !password.trim()) {
      setStatusType('error');
      setStatusMsg('Please complete all required fields.');
      return;
    }

    if (password !== confirmPassword) {
      setStatusType('error');
      setStatusMsg('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      // Step 1: Request OTP code send
      const res = await authService.sendOtp(email, clientName);
      if (res.success) {
        setOtpError('');
        setOtpCode('');
        setShowOtpModal(true);
      } else {
        setStatusType('error');
        setStatusMsg(res.detail || 'Failed to dispatch verification email.');
      }
    } catch (err: any) {
      setStatusType('error');
      setStatusMsg(err.message || 'Error requesting verification code.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyAndRegister = async () => {
    setOtpError('');
    if (!otpCode.trim() || otpCode.length !== 6) {
      setOtpError('Please enter a valid 6-digit verification code.');
      return;
    }

    setVerifyingOtp(true);
    try {
      // Step 2: Validate OTP Code on server
      const verifyRes = await authService.verifyOtp(email, otpCode);
      if (verifyRes.success) {
        // Step 3: Complete actual registration
        const payload = {
          company_name: companyName,
          client_name: clientName,
          email,
          password,
          phone,
          domain_id: domainId,
          // Placeholder settings to keep Pydantic schemas content
          db_type: 'sqlite',
          db_name: 'placeholder.db',
          server_name: '',
          port: 5432,
          username: '',
          password_db: '',
          schema_name: '',
          enable_ssl: false,
          trust_server_certificate: false,
          connection_timeout: 5,
        };

        const regRes = await authService.register(payload);
        if (regRes.success && regRes.token) {
          localStorage.setItem('auth_token', regRes.token);
          setShowOtpModal(false);
          setStatusType('success');
          setStatusMsg('Email verified & account registered successfully! Redirecting...');
          setTimeout(() => navigate('/'), 1200);
        } else {
          setOtpError(regRes.detail || 'Registration failed after validation.');
        }
      } else {
        setOtpError(verifyRes.detail || 'Invalid or expired passcode.');
      }
    } catch (err: any) {
      setOtpError(err.message || 'Verification failed. Please retry.');
    } finally {
      setVerifyingOtp(false);
    }
  };

  const handleResendOtp = async () => {
    setResendingOtp(true);
    setOtpError('');
    try {
      const res = await authService.sendOtp(email, clientName);
      if (res.success) {
        setOtpError('A new verification code has been sent to your email.');
      } else {
        setOtpError(res.detail || 'Resend request failed.');
      }
    } catch (err: any) {
      setOtpError(err.message || 'Error resending verification code.');
    } finally {
      setResendingOtp(false);
    }
  };

  return (
    <div className="min-h-screen py-12 px-4 flex flex-col justify-center items-center">
      <div className="w-full max-w-xl space-y-8 animate-slide-up">
        <div className="text-center">
          <h1 className="text-4xl font-extrabold bg-gradient-to-r from-violet-400 via-pink-500 to-emerald-400 bg-clip-text text-transparent pb-2">
            Create Client Account
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Register your company details and choose your voice agent domain to get started.
          </p>
        </div>

        {statusMsg && (
          <Alert severity={statusType === 'error' ? 'error' : 'success'} className="rounded-xl">
            {statusMsg}
          </Alert>
        )}

        {/* Client Account Form */}
        <form onSubmit={handleRegisterSubmit} className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-6 sm:p-8 space-y-6 shadow-2xl">
          <h3 className="text-lg font-bold text-slate-100 border-b border-slate-800 pb-3">
            Account & Company Details
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <TextField
              size="small"
              fullWidth
              label="Company Name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
            <TextField
              size="small"
              fullWidth
              label="Contact Full Name"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
            />
            <TextField
              size="small"
              fullWidth
              type="email"
              label="Email Address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              size="small"
              fullWidth
              label="Phone Number"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
            <TextField
              size="small"
              fullWidth
              type="password"
              label="Account Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <TextField
              size="small"
              fullWidth
              type="password"
              label="Confirm Password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />

            <FormControl fullWidth size="small" className="sm:col-span-2">
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

          <Button
            type="submit"
            fullWidth
            variant="contained"
            disabled={submitting}
            startIcon={submitting && <CircularProgress size={16} color="inherit" />}
            sx={{
              py: 1.2,
              borderRadius: '12px',
              fontWeight: 600,
              background: 'linear-gradient(to right, #8b5cf6, #ec4899)',
              boxShadow: '0 4px 14px 0 rgba(139, 92, 246, 0.4)',
            }}
          >
            {submitting ? 'Sending verification code...' : 'Register Account'}
          </Button>
        </form>

        <div className="text-center text-sm text-slate-400">
          Already registered?{' '}
          <Button color="primary" onClick={() => navigate('/login')} className="cursor-pointer">
            Sign In Here
          </Button>
        </div>
      </div>

      {/* Verification Code dialog Modal */}
      <Dialog
        open={showOtpModal}
        onClose={() => setShowOtpModal(false)}
        sx={{
          '& .MuiPaper-root': {
            background: '#0f172a',
            border: '1px solid #1e293b',
            color: '#cbd5e1',
            borderRadius: '24px',
            paddingLeft: '16px',
            paddingRight: '16px',
            paddingTop: '8px',
            paddingBottom: '8px',
            maxWidth: '440px',
            width: '100%',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 800, color: '#f1f5f9', pb: 1 }}>
          Verify Email Address
        </DialogTitle>
        
        <DialogContent>
          <DialogContentText sx={{ color: '#94a3b8', fontSize: '0.875rem', mb: 3 }}>
            We've sent a 6-digit verification code to your email <strong>{email}</strong>. Enter the passcode below to verify and activate your profile.
          </DialogContentText>
          
          <TextField
            autoFocus
            fullWidth
            label="Verification Code (OTP)"
            variant="outlined"
            size="medium"
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            slotProps={{
              htmlInput: {
                maxLength: 6,
                style: {
                  textAlign: 'center',
                  letterSpacing: '8px',
                  fontSize: '1.25rem',
                  fontFamily: 'monospace',
                  color: '#f8fafc',
                },
              }
            }}
          />

          {otpError && (
            <Alert
              severity={otpError.includes('sent') ? 'info' : 'error'}
              sx={{ mt: 2, borderRadius: '12px' }}
            >
              {otpError}
            </Alert>
          )}
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 3, flexDirection: 'column', gap: 2 }}>
          <Button
            onClick={handleVerifyAndRegister}
            fullWidth
            variant="contained"
            disabled={verifyingOtp}
            startIcon={verifyingOtp && <CircularProgress size={16} color="inherit" />}
            sx={{
              py: 1.2,
              borderRadius: '12px',
              fontWeight: 600,
              background: 'linear-gradient(to right, #10b981, #059669)',
              '&:hover': {
                background: 'linear-gradient(to right, #059669, #047857)',
              },
            }}
          >
            {verifyingOtp ? 'Verifying & Registering...' : 'Verify & Register'}
          </Button>

          <Button
            onClick={handleResendOtp}
            variant="text"
            disabled={resendingOtp}
            sx={{ color: '#8b5cf6', fontSize: '0.8rem', textTransform: 'none' }}
          >
            {resendingOtp ? 'Resending Code...' : 'Resend Verification Code'}
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
