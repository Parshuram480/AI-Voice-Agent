import React, { useState } from 'react';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import InputAdornment from '@mui/material/InputAdornment';
import IconButton from '@mui/material/IconButton';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import LoginIcon from '@mui/icons-material/Login';
import { authService } from '../services/authService';

interface LoginProps {
  onLoginSuccess: (client: any, domainName: string, pipelineMode: string) => void;
  onGoToRegister: () => void;
}

export default function LoginPage({ onLoginSuccess, onGoToRegister }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  // Validation error states
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    let isValid = true;

    // Validate email
    if (!email.trim()) {
      setEmailError('Email is required');
      isValid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setEmailError('Please enter a valid email address');
      isValid = false;
    } else {
      setEmailError('');
    }

    // Validate password
    if (!password) {
      setPasswordError('Password is required');
      isValid = false;
    } else {
      setPasswordError('');
    }

    if (!isValid) return;
    setLoading(true);

    try {
      const data = await authService.login({ email, password });
      if (data.success) {
        const meData = await authService.checkAuth();
        onLoginSuccess(meData.client, meData.domain ? meData.domain.name : 'None', meData.pipeline_mode || 'cascade');
      } else {
        setError(data.detail || 'Authentication failed.');
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[85svh] px-4">
      <header className="text-center mb-8">
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-violet-400 via-fuchsia-400 to-pink-500 bg-clip-text text-transparent pb-2 mb-2">
          Voice Agent Platform
        </h1>
        <p className="text-slate-400 text-sm md:text-base uppercase tracking-wider font-semibold">
          SaaS Multi-Tenant AI Voice Service
        </p>
      </header>

      <div className="w-full max-w-md bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-2xl p-8 shadow-2xl shadow-slate-950/60">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-slate-100">Client Sign In</h2>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-1.5">
            <TextField 
              label="Email Address"
              type="email"
              variant="outlined"
              fullWidth
              value={email}
              onChange={e => {
                setEmail(e.target.value);
                if (emailError) setEmailError('');
              }}
              error={!!emailError}
              helperText={emailError}
              placeholder="name@company.com"
              slotProps={{
                inputLabel: { shrink: true }
              }}
            />
          </div>
          <div className="space-y-1.5">
            <TextField 
              label="Password"
              type={showPassword ? 'text' : 'password'}
              variant="outlined"
              fullWidth
              value={password}
              onChange={e => {
                setPassword(e.target.value);
                if (passwordError) setPasswordError('');
              }}
              error={!!passwordError}
              helperText={passwordError}
              placeholder="••••••••"
              slotProps={{
                inputLabel: { shrink: true },
                input: {
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowPassword(!showPassword)}
                        onMouseDown={e => e.preventDefault()}
                        edge="end"
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }
              }}
            />
          </div>
          <Button 
            type="submit"
            variant="contained"
            color="primary"
            size="large"
            fullWidth
            disabled={loading}
            endIcon={loading ? <CircularProgress size={20} color="inherit" /> : <LoginIcon />}
            sx={{
              py: 1.5,
              background: 'linear-gradient(to right, #7c3aed, #db2777)',
              '&:hover': {
                background: 'linear-gradient(to right, #6d28d9, #be185d)',
              }
            }}
          >
            {loading ? 'Signing In...' : 'Sign In'}
          </Button>
          
          {error && (
            <Alert severity="error" variant="outlined" sx={{ width: '100%' }}>
              {error}
            </Alert>
          )}
        </form>

        <p className="mt-6 text-center text-slate-400 text-sm">
          Don't have an account?{' '}
          <button 
            onClick={onGoToRegister} 
            className="text-violet-400 hover:text-violet-300 font-semibold focus:outline-none transition-colors duration-200 cursor-pointer"
          >
            Register here
          </button>
        </p>
      </div>
    </div>
  );
}
