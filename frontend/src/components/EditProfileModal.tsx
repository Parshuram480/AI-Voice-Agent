import React, { useState, useEffect } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';

import { authService } from '../services/authService';

interface Client {
  id: number;
  company_name: string;
  client_name: string;
  email: string;
  phone?: string;
}

interface Domain {
  id: number;
  name: string;
  description: string;
  status: string;
  path_type: string;
}

interface EditProfileModalProps {
  open: boolean;
  onClose: () => void;
  client: Client;
  domainName: string;
  domains: Domain[];
  onSaveSuccess: (updatedClient: Client, newDomainName: string) => void;
}

export default function EditProfileModal({
  open,
  onClose,
  client,
  domainName,
  domains,
  onSaveSuccess,
}: EditProfileModalProps) {
  const [companyName, setCompanyName] = useState(client.company_name);
  const [clientName, setClientName] = useState(client.client_name);
  const [email, setEmail] = useState(client.email);
  const [phone, setPhone] = useState(client.phone || '');
  const [pathType, setPathType] = useState('customer_support');
  const [domainId, setDomainId] = useState<number>(1);
  const [submitting, setSubmitting] = useState(false);

  // Field validation states
  const [errors, setErrors] = useState<{
    companyName?: string;
    clientName?: string;
    email?: string;
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

  // Pre-populate fields whenever dialog opens or client changes
  useEffect(() => {
    if (open) {
      setCompanyName(client.company_name);
      setClientName(client.client_name);
      setEmail(client.email);
      setPhone(client.phone || '');
      setErrors({});
      const currentDom = domains.find((d) => d.name === domainName);
      if (currentDom) {
        setPathType(currentDom.path_type || 'customer_support');
        setDomainId(currentDom.id);
      }
    }
  }, [open, client, domainName, domains]);

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
      newErrors.clientName = 'Contact name is required';
    }
    if (!email.trim()) {
      newErrors.email = 'Email address is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validateForm()) {
      showToast('Please fill all the required fields', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const res = await authService.updateProfile({
        company_name: companyName,
        client_name: clientName,
        email,
        phone,
        domain_id: domainId,
      });

      if (res.success && res.client) {
        showToast('Profile updated successfully!', 'success');
        onSaveSuccess(res.client, res.domain_name);
        onClose();
      } else {
        showToast(res.detail || 'Failed to update profile.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Error updating profile details.', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        sx={{
          '& .MuiPaper-root': {
            background: 'background.paper',
            borderColor: 'divider',
            borderWidth: '1px',
            borderStyle: 'solid',
            borderRadius: '24px',
            paddingLeft: '24px',
            paddingRight: '24px',
            paddingTop: '16px',
            paddingBottom: '16px',
            maxWidth: '500px',
            width: '100%',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 800, pb: 1, px: 0 }}>
          Update Profile Details
        </DialogTitle>
        
        <DialogContent sx={{ px: 0, py: 2 }}>
          <DialogContentText sx={{ color: 'text.secondary', fontSize: '0.875rem', mb: 3 }}>
            Update your company profile information and industry domain.
          </DialogContentText>
          
          <div className="flex flex-col gap-4">
            <TextField
              size="small"
              fullWidth
              label="Company Name"
              value={companyName}
              onChange={(e) => {
                setCompanyName(e.target.value);
                if (e.target.value.trim()) {
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
                setClientName(e.target.value);
                if (e.target.value.trim()) {
                  setErrors((prev) => ({ ...prev, clientName: undefined }));
                }
              }}
              error={Boolean(errors.clientName)}
              helperText={errors.clientName}
            />
            <TextField
              size="small"
              fullWidth
              disabled={true}
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

            <FormControl fullWidth size="small">
              <InputLabel id="edit-path-label">Pipeline Path</InputLabel>
              <Select
                labelId="edit-path-label"
                value={pathType}
                label="Pipeline Path"
                onChange={(e) => {
                  const newPath = e.target.value;
                  setPathType(newPath);
                  const filtered = domains.filter((d) => d.path_type === newPath);
                  if (filtered.length > 0) {
                    setDomainId(filtered[0].id);
                  }
                }}
              >
                <MenuItem value="customer_support">Customer Support</MenuItem>
                <MenuItem value="outreach">Outreach</MenuItem>
              </Select>
            </FormControl>

            <FormControl fullWidth size="small">
              <InputLabel id="edit-profile-domain-label">Industry Sub-domain</InputLabel>
              <Select
                labelId="edit-profile-domain-label"
                value={domainId}
                label="Industry Sub-domain"
                onChange={(e) => setDomainId(Number(e.target.value))}
              >
                {domains.filter((d) => d.path_type === pathType).map((d) => (
                  <MenuItem key={d.id} value={d.id}>
                    {d.name} — {d.description}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </div>
        </DialogContent>

        <DialogActions sx={{ px: 0, pt: 2, gap: 1.5 }}>
          <Button
            onClick={onClose}
            variant="outlined"
            color="inherit"
            sx={{ borderRadius: '12px', flex: 1, py: 1 }}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            variant="contained"
            disabled={submitting}
            startIcon={submitting && <CircularProgress size={16} color="inherit" />}
            sx={{
              py: 1.2,
              borderRadius: '12px',
              fontWeight: 600,
              flex: 1,
              background: 'linear-gradient(to right, #8b5cf6, #ec4899)',
              boxShadow: '0 4px 14px 0 rgba(139, 92, 246, 0.4)',
            }}
          >
            {submitting ? 'Saving...' : 'Save Changes'}
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
    </>
  );
}
