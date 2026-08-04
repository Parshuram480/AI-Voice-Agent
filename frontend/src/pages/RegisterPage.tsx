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
import Snackbar from '@mui/material/Snackbar';

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

  // Validation errors state
  const [errors, setErrors] = useState<{
    companyName?: string;
    clientName?: string;
    email?: string;
    password?: string;
    confirmPassword?: string;
  }>({});

  // Floating toaster notification state
  const [toast, setToast] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({
    open: false,
    message: '',
    severity: 'success',
  });

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

  const showToast = (message: string, severity: 'success' | 'error' | 'info' | 'warning') => {
    setToast({ open: true, message, severity });
  };

  const handleCloseToast = (_event?: React.SyntheticEvent | Event, reason?: string) => {
    if (reason === 'clickaway') return;
    setToast((prev) => ({ ...prev, open: false }));
  };

  const validateForm = () => {
    const newErrors: typeof errors = {};
    if (!companyName.trim()) {
      newErrors.companyName = 'Company name is required';
    }
    if (!clientName.trim()) {
      newErrors.clientName = 'Contact full name is required';
    }
    if (!email.trim()) {
      newErrors.email = 'Email address is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Please enter a valid email address';
    }
    if (!password) {
      newErrors.password = 'Password is required';
    } else if (password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters';
    }
    if (!confirmPassword) {
      newErrors.confirmPassword = 'Confirm password is required';
    } else if (password !== confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) {
      showToast('Please fill all the required fields', 'error');
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
        showToast('Verification code sent successfully to your email!', 'success');
      } else {
        showToast(res.detail || 'Failed to dispatch verification email.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Error requesting verification code.', 'error');
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
          showToast('Account created successfully!', 'success');
          setTimeout(() => navigate('/'), 1200);
        } else {
          setOtpError(regRes.detail || 'Registration failed after validation.');
          showToast(regRes.detail || 'Registration failed.', 'error');
        }
      } else {
        setOtpError(verifyRes.detail || 'Invalid or expired passcode.');
        showToast(verifyRes.detail || 'OTP verification failed.', 'error');
      }
    } catch (err: any) {
      setOtpError(err.message || 'Verification failed. Please retry.');
      showToast(err.message || 'Error verifying OTP.', 'error');
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
        showToast('Verification code resent successfully.', 'success');
      } else {
        setOtpError(res.detail || 'Resend request failed.');
        showToast(res.detail || 'Resend request failed.', 'error');
      }
    } catch (err: any) {
      setOtpError(err.message || 'Error resending verification code.');
      showToast(err.message || 'Error resending verification code.', 'error');
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

        {/* Client Account Form */}
        <form onSubmit={handleRegisterSubmit} noValidate className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-6 sm:p-8 space-y-6 shadow-2xl">
          <h3 className="text-lg font-bold text-slate-100 border-b border-slate-800 pb-3">
            Account & Company Details
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <TextField
              size="small"
              fullWidth
              label="Company Name"
              value={companyName}
              onChange={(e) => {
                const val = e.target.value;
                setCompanyName(val);
                if (val.trim()) {
                  setErrors((prev) => ({ ...prev, companyName: undefined }));
                }
              }}
              error={Boolean(errors.companyName)}
              helperText={errors.companyName}
            />
            <TextField
              size="small"
              fullWidth
              label="Contact Full Name"
              value={clientName}
              onChange={(e) => {
                const val = e.target.value;
                setClientName(val);
                if (val.trim()) {
                  setErrors((prev) => ({ ...prev, clientName: undefined }));
                }
              }}
              error={Boolean(errors.clientName)}
              helperText={errors.clientName}
            />
            <TextField
              size="small"
              fullWidth
              type="email"
              label="Email Address"
              value={email}
              onChange={(e) => {
                const val = e.target.value;
                setEmail(val);
                if (val.trim() && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
                  setErrors((prev) => ({ ...prev, email: undefined }));
                }
              }}
              error={Boolean(errors.email)}
              helperText={errors.email}
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
              onChange={(e) => {
                const val = e.target.value;
                setPassword(val);
                if (val && val.length >= 6) {
                  setErrors((prev) => ({ ...prev, password: undefined }));
                }
                if (confirmPassword && val === confirmPassword) {
                  setErrors((prev) => ({ ...prev, confirmPassword: undefined }));
                }
              }}
              error={Boolean(errors.password)}
              helperText={errors.password}
            />
            <TextField
              size="small"
              fullWidth
              type="password"
              label="Confirm Password"
              value={confirmPassword}
              onChange={(e) => {
                const val = e.target.value;
                setConfirmPassword(val);
                if (val && val === password) {
                  setErrors((prev) => ({ ...prev, confirmPassword: undefined }));
                }
              }}
              error={Boolean(errors.confirmPassword)}
              helperText={errors.confirmPassword}
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

      {/* Floating Snackbar Toaster Notifications */}
      <Snackbar
        open={toast.open}
        autoHideDuration={4000}
        onClose={handleCloseToast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={handleCloseToast}
          severity={toast.severity}
          variant="filled"
          sx={{ width: '100%', borderRadius: '12px' }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </div>
  );
}
