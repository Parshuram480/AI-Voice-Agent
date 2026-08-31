import { useState, useEffect } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Tooltip from '@mui/material/Tooltip';
import CloseIcon from '@mui/icons-material/Close';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import DeleteIcon from '@mui/icons-material/Delete';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ArticleIcon from '@mui/icons-material/Article';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import DescriptionIcon from '@mui/icons-material/Description';
import QuizIcon from '@mui/icons-material/Quiz';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { API_BASE } from '../services/apiClient';

interface KBEntry {
  id: number;
  client_id: number;
  title: string;
  content: string;
  file_name?: string;
  created_at: string;
}

interface KnowledgeBaseManagerModalProps {
  open: boolean;
  onClose: () => void;
  clientId: number;
}

export default function KnowledgeBaseManagerModal({
  open,
  onClose,
  clientId
}: KnowledgeBaseManagerModalProps) {
  const [entries, setEntries] = useState<KBEntry[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form toggles
  const [activeForm, setActiveForm] = useState<'none' | 'upload' | 'manual'>('none');

  // Manual FAQ Form State
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [submittingManual, setSubmittingManual] = useState(false);

  // File Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadingFile, setUploadingFile] = useState(false);

  // Expandable cards state
  const [expandedItems, setExpandedItems] = useState<Record<number, boolean>>({});

  const fetchEntries = async () => {
    if (!clientId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/clients/${clientId}/knowledge-base`);
      const data = await res.json();
      if (data.success) {
        setEntries(data.entries || []);
      } else {
        setError(data.message || 'Failed to fetch knowledge base entries.');
      }
    } catch (err: any) {
      setError(err.message || 'Server error loading knowledge base.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchEntries();
      setSuccessMsg(null);
      setError(null);
      setActiveForm('none');
    }
  }, [open, clientId]);

  const handleAddManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) {
      setError('Both title and content are required.');
      return;
    }

    setSubmittingManual(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const res = await fetch(`${API_BASE}/api/clients/${clientId}/knowledge-base`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content })
      });
      const data = await res.json();
      if (data.success) {
        setSuccessMsg(`Added "${title}"! Vector embeddings generated successfully.`);
        setTitle('');
        setContent('');
        setActiveForm('none');
        fetchEntries();
      } else {
        setError(data.detail || data.message || 'Failed to save knowledge base item.');
      }
    } catch (err: any) {
      setError(err.message || 'Network error saving knowledge item.');
    } finally {
      setSubmittingManual(false);
    }
  };

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setError('Please select a file (.pdf or .txt) to upload.');
      return;
    }

    setUploadingFile(true);
    setError(null);
    setSuccessMsg(null);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await fetch(`${API_BASE}/api/clients/${clientId}/knowledge-base/upload`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (data.success) {
        setSuccessMsg(`Ingested "${data.file_name}"! Split into ${data.count} vector chunk(s).`);
        setSelectedFile(null);
        setActiveForm('none');
        fetchEntries();
      } else {
        setError(data.detail || data.message || 'Failed to upload document.');
      }
    } catch (err: any) {
      setError(err.message || 'Error processing document upload.');
    } finally {
      setUploadingFile(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this knowledge base entry?')) return;

    try {
      const res = await fetch(`${API_BASE}/api/clients/${clientId}/knowledge-base/${id}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (data.success) {
        setSuccessMsg('Entry deleted successfully.');
        setEntries(entries.filter((e) => e.id !== id));
      } else {
        setError(data.message || 'Failed to delete entry.');
      }
    } catch (err: any) {
      setError(err.message || 'Error deleting entry.');
    }
  };

  const toggleExpand = (id: number) => {
    setExpandedItems(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredEntries = entries.filter(item => {
    const q = searchQuery.toLowerCase();
    return (
      item.title.toLowerCase().includes(q) ||
      item.content.toLowerCase().includes(q) ||
      (item.file_name && item.file_name.toLowerCase().includes(q))
    );
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      {/* Modal Header */}
      <DialogTitle className="flex justify-between items-center bg-slate-900 border-b border-slate-800 text-white py-4 px-6">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 flex items-center justify-center shadow-lg shadow-amber-500/20 text-slate-950 font-bold">
            <AutoAwesomeIcon fontSize="small" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100 leading-tight">Knowledge Base & RAG Documents</h2>
            <p className="text-xs text-slate-400">Vector search engine for Gemini Live calls & Chatbot console</p>
          </div>
        </div>
        <IconButton onClick={onClose} className="text-slate-400 hover:text-white hover:bg-slate-800">
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent className="p-6 bg-slate-950 text-slate-100 min-h-[500px]">
        {/* Alerts */}
        {error && (
          <Alert severity="error" onClose={() => setError(null)} className="mb-4 bg-red-950/80 text-red-200 border border-red-800/80 rounded-xl">
            {error}
          </Alert>
        )}

        {successMsg && (
          <Alert severity="success" onClose={() => setSuccessMsg(null)} className="mb-4 bg-emerald-950/80 text-emerald-200 border border-emerald-800/80 rounded-xl">
            {successMsg}
          </Alert>
        )}

        {/* Action Controls & Search Bar */}
        <div className="flex flex-col sm:flex-row justify-between items-center gap-3 mb-6 bg-slate-900/60 p-3 rounded-2xl border border-slate-800/80">
          <TextField
            size="small"
            placeholder="Search stored knowledge & documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full sm:w-72"
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon className="text-slate-500" fontSize="small" />
                </InputAdornment>
              ),
            }}
            sx={{
              input: { color: 'white', fontSize: '0.875rem' },
              '& .MuiOutlinedInput-root': {
                backgroundColor: '#0f172a',
                borderRadius: '12px',
                '& fieldset': { borderColor: '#334155' },
                '&:hover fieldset': { borderColor: '#f59e0b' }
              }
            }}
          />

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Button
              variant={activeForm === 'upload' ? 'contained' : 'outlined'}
              onClick={() => setActiveForm(activeForm === 'upload' ? 'none' : 'upload')}
              startIcon={<CloudUploadIcon />}
              className={activeForm === 'upload' ? 'bg-amber-500 hover:bg-amber-600 text-slate-950 font-semibold' : 'border-slate-700 text-amber-400 hover:bg-slate-800'}
              sx={{ borderRadius: '12px', textTransform: 'none', px: 2, fontSize: '0.85rem' }}
            >
              Upload Document
            </Button>

            <Button
              variant={activeForm === 'manual' ? 'contained' : 'outlined'}
              onClick={() => setActiveForm(activeForm === 'manual' ? 'none' : 'manual')}
              startIcon={<AddIcon />}
              className={activeForm === 'manual' ? 'bg-violet-600 hover:bg-violet-700 text-white font-semibold' : 'border-slate-700 text-violet-400 hover:bg-slate-800'}
              sx={{ borderRadius: '12px', textTransform: 'none', px: 2, fontSize: '0.85rem' }}
            >
              Add Manual FAQ
            </Button>
          </div>
        </div>

        {/* Collapsible Form 1: Document Upload */}
        {activeForm === 'upload' && (
          <form onSubmit={handleFileUpload} className="mb-6 p-5 bg-slate-900 border border-amber-500/40 rounded-2xl space-y-4 animate-fadeIn">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-amber-400 flex items-center gap-2">
                <CloudUploadIcon fontSize="small" /> Upload Document (.pdf / .txt)
              </h3>
              <IconButton size="small" onClick={() => setActiveForm('none')} className="text-slate-400">
                <CloseIcon fontSize="small" />
              </IconButton>
            </div>

            <div className="border-2 border-dashed border-slate-700 rounded-xl p-6 text-center hover:border-amber-500 transition-colors bg-slate-950/60">
              <input
                type="file"
                accept=".pdf,.txt"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="hidden"
                id="modal-kb-file-input"
              />
              <label htmlFor="modal-kb-file-input" className="cursor-pointer block">
                <DescriptionIcon className="text-4xl text-amber-400 mb-2" />
                <p className="text-slate-200 text-sm font-medium">Click to select a file</p>
                <p className="text-slate-500 text-xs mt-1">Supports PDF and TXT files up to 10MB</p>
              </label>

              {selectedFile && (
                <div className="mt-3 inline-flex items-center space-x-2 bg-amber-950/50 border border-amber-500/30 px-3 py-1.5 rounded-lg text-xs text-amber-300 font-medium">
                  <span>{selectedFile.name}</span>
                  <span className="text-amber-500">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                </div>
              )}
            </div>

            <div className="flex justify-end space-x-2">
              <Button onClick={() => setActiveForm('none')} size="small" className="text-slate-400">Cancel</Button>
              <Button
                type="submit"
                variant="contained"
                disabled={!selectedFile || uploadingFile}
                className="bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold px-4"
                sx={{ borderRadius: '10px' }}
              >
                {uploadingFile ? (
                  <span className="flex items-center space-x-2">
                    <CircularProgress size={16} color="inherit" />
                    <span>Processing Document & Vectorizing...</span>
                  </span>
                ) : (
                  'Ingest & Generate Embeddings'
                )}
              </Button>
            </div>
          </form>
        )}

        {/* Collapsible Form 2: Add Manual FAQ */}
        {activeForm === 'manual' && (
          <form onSubmit={handleAddManual} className="mb-6 p-5 bg-slate-900 border border-violet-500/40 rounded-2xl space-y-4 animate-fadeIn">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-violet-400 flex items-center gap-2">
                <QuizIcon fontSize="small" /> Add Manual FAQ / Guideline
              </h3>
              <IconButton size="small" onClick={() => setActiveForm('none')} className="text-slate-400">
                <CloseIcon fontSize="small" />
              </IconButton>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1">Title / Question</label>
              <TextField
                fullWidth
                size="small"
                placeholder="e.g. What are your hospital visiting hours?"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                sx={{
                  input: { color: 'white', fontSize: '0.875rem' },
                  '& .MuiOutlinedInput-root': {
                    backgroundColor: '#0f172a',
                    borderRadius: '10px',
                    '& fieldset': { borderColor: '#334155' }
                  }
                }}
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1">Content / Answer / Guidelines</label>
              <TextField
                fullWidth
                multiline
                rows={4}
                placeholder="Type detailed answers, policies, or procedures..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
                sx={{
                  textarea: { color: 'white', fontSize: '0.875rem' },
                  '& .MuiOutlinedInput-root': {
                    backgroundColor: '#0f172a',
                    borderRadius: '10px',
                    '& fieldset': { borderColor: '#334155' }
                  }
                }}
              />
            </div>

            <div className="flex justify-end space-x-2">
              <Button onClick={() => setActiveForm('none')} size="small" className="text-slate-400">Cancel</Button>
              <Button
                type="submit"
                variant="contained"
                disabled={submittingManual}
                className="bg-violet-600 hover:bg-violet-700 text-white font-bold px-4"
                sx={{ borderRadius: '10px' }}
              >
                {submittingManual ? (
                  <span className="flex items-center space-x-2">
                    <CircularProgress size={16} color="inherit" />
                    <span>Generating Vector Embedding...</span>
                  </span>
                ) : (
                  'Save Knowledge Entry'
                )}
              </Button>
            </div>
          </form>
        )}

        {/* DEFAULT & MAIN VIEW: Stored Knowledge Items List */}
        <div>
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <span>Active Knowledge Base Chunks</span>
              <span className="bg-slate-800 text-amber-400 px-2 py-0.5 rounded-full text-[11px] font-mono border border-slate-700">
                {filteredEntries.length}
              </span>
            </h3>
            {searchQuery && (
              <span className="text-xs text-slate-500">Filtered by "{searchQuery}"</span>
            )}
          </div>

          {loading ? (
            <div className="flex justify-center items-center py-16">
              <CircularProgress color="warning" />
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800/80">
              <ArticleIcon className="text-5xl text-slate-600 mb-2 opacity-50" />
              <p className="text-slate-300 font-medium">No Knowledge Base Entries Stored</p>
              <p className="text-xs text-slate-500 mt-1 mb-4">Upload a `.pdf` or `.txt` document or add a manual FAQ to seed your agent's memory.</p>
              <div className="flex justify-center gap-3">
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setActiveForm('upload')}
                  className="border-amber-500/50 text-amber-400 hover:bg-amber-950/30"
                  sx={{ borderRadius: '10px', textTransform: 'none' }}
                >
                  Upload File
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setActiveForm('manual')}
                  className="border-violet-500/50 text-violet-400 hover:bg-violet-950/30"
                  sx={{ borderRadius: '10px', textTransform: 'none' }}
                >
                  Add FAQ
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
              {filteredEntries.map((item) => {
                const isExpanded = !!expandedItems[item.id];
                const isLong = item.content.length > 220;
                const displayContent = (!isExpanded && isLong) ? `${item.content.substring(0, 220)}...` : item.content;

                return (
                  <div
                    key={item.id}
                    className="p-4 bg-slate-900/90 rounded-2xl border border-slate-800 hover:border-slate-700 transition-all shadow-md group"
                  >
                    <div className="flex justify-between items-start space-x-3">
                      <div className="flex-1 min-w-0">
                        {/* Header Badge & Title */}
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          {item.file_name ? (
                            <span className="inline-flex items-center gap-1 text-[11px] bg-amber-950/60 text-amber-300 px-2.5 py-0.5 rounded-md border border-amber-500/30 font-medium">
                              <DescriptionIcon style={{ fontSize: 13 }} /> {item.file_name}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] bg-violet-950/60 text-violet-300 px-2.5 py-0.5 rounded-md border border-violet-500/30 font-medium">
                              <QuizIcon style={{ fontSize: 13 }} /> Manual FAQ
                            </span>
                          )}

                          <h4 className="font-bold text-slate-100 text-sm">{item.title}</h4>
                        </div>

                        {/* Content text */}
                        <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-line font-sans">
                          {displayContent}
                        </p>

                        {/* Expand / Collapse Button */}
                        {isLong && (
                          <button
                            onClick={() => toggleExpand(item.id)}
                            className="mt-2 text-[11px] text-amber-400 hover:underline inline-flex items-center gap-0.5 font-medium"
                          >
                            {isExpanded ? (
                              <><span>Show Less</span><ExpandLessIcon style={{ fontSize: 14 }} /></>
                            ) : (
                              <><span>Show Full Chunk</span><ExpandMoreIcon style={{ fontSize: 14 }} /></>
                            )}
                          </button>
                        )}

                        <span className="text-[10px] text-slate-500 mt-2 block">
                          Ingested: {new Date(item.created_at).toLocaleString()}
                        </span>
                      </div>

                      <Tooltip title="Delete Entry">
                        <IconButton
                          onClick={() => handleDelete(item.id)}
                          size="small"
                          className="text-slate-500 hover:text-red-400 hover:bg-red-950/30 transition-colors"
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>

      <DialogActions className="bg-slate-900 px-6 py-3 border-t border-slate-800">
        <Button onClick={onClose} variant="contained" className="bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold px-6" sx={{ borderRadius: '10px' }}>
          Done
        </Button>
      </DialogActions>
    </Dialog>
  );
}
