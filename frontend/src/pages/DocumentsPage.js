import React, { useState, useEffect, useRef } from 'react';
import { api } from '../lib/supabase';
import { useAuth } from '../context/AuthContext';

const Icon = ({ d, size = 16, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const UPLOAD = 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12';
const DOC    = 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8';
const TRASH  = 'M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2';
const CHECK  = 'M20 6L9 17l-5-5';
const ALERT  = 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01';

const DOC_TYPES = [
  { key: 'fcom', label: 'FCOM', desc: 'Flight Crew Operating Manual' },
  { key: 'fctm', label: 'FCTM', desc: 'Flight Crew Training Manual' },
  { key: 'mel',  label: 'MEL',  desc: 'Minimum Equipment List' },
  { key: 'qrh',  label: 'QRH',  desc: 'Quick Reference Handbook' },
  { key: 'notam',label: 'NOTAM',desc: 'Notice to Air Missions' },
  { key: 'other',label: 'OTHER',desc: 'Other operational document' },
];

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [uploadForm, setUploadForm] = useState({ type: 'fcom', revision: '', aircraft_type: 'A320' });
  const [toast, setToast] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
 const fileRef = useRef(null);
const { loading: authLoading } = useAuth();

 useEffect(() => {
  if (!authLoading) loadDocs();
}, [authLoading]);

  async function loadDocs() {
    setLoading(true);
    try {
      const data = await api.documents.list();
      setDocuments(data || []);
    } catch (e) {
      showToast('Failed to load documents', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(files) {
    if (!files?.length) return;
    const file = files[0];

    if (!['application/pdf'].includes(file.type) && !file.name.endsWith('.pdf')) {
      showToast('Only PDF files are supported', 'error');
      return;
    }

    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('document_type', uploadForm.type);
    fd.append('revision', uploadForm.revision);
    fd.append('aircraft_type', uploadForm.aircraft_type);

    try {
      const doc = await api.documents.upload(fd);
      setDocuments(prev => [doc, ...prev]);
      showToast('Document uploaded and queued for processing', 'success');
    } catch (e) {
      showToast(e.message || 'Upload failed', 'error');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDelete(id) {
    try {
      await api.documents.delete(id);
      setDocuments(prev => prev.filter(d => d.id !== id));
      showToast('Document removed', 'success');
    } catch (e) {
      showToast('Failed to delete document', 'error');
    } finally {
      setConfirmDelete(null);
    }
  }

  function showToast(msg, type = 'success') {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    handleUpload(e.dataTransfer.files);
  }

  const statusColor = {
    ready:      'var(--teal)',
    processing: 'var(--amber)',
    error:      'var(--red)',
    pending:    'var(--text-dim)',
  };

  return (
    <div style={styles.root}>
      {/* Toast */}
      {toast && (
        <div style={{
          ...styles.toast,
          background: toast.type === 'error' ? 'var(--red-dim)' : 'var(--teal-dim)',
          borderColor: toast.type === 'error' ? 'var(--red)' : 'var(--teal)',
          color: toast.type === 'error' ? 'var(--red)' : 'var(--teal)',
        }}>
          {toast.type === 'error'
            ? <Icon d={ALERT} size={14} />
            : <Icon d={CHECK} size={14} />}
          {toast.msg}
        </div>
      )}

      {/* Delete confirm modal */}
      {confirmDelete && (
        <div style={styles.modalOverlay}>
          <div style={styles.modal}>
            <div style={styles.modalTitle}>Remove document?</div>
            <div style={styles.modalBody}>
              This will delete <strong>{confirmDelete.name}</strong> and all associated chunks.
              Previous sessions that cited this document will be marked with invalidation warnings.
            </div>
            <div style={styles.modalActions}>
              <button style={styles.btnCancel} onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button style={styles.btnDelete} onClick={() => handleDelete(confirmDelete.id)}>
                Remove document
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={styles.inner}>
        {/* Page header */}
        <div style={styles.pageHeader}>
          <div>
            <h1 style={styles.pageTitle}>Document Library</h1>
            <p style={styles.pageSubtitle}>
              {documents.length} document{documents.length !== 1 ? 's' : ''} · A320 fleet
            </p>
          </div>
        </div>

        {/* Upload zone */}
        <div style={styles.uploadSection}>
          <div style={styles.sectionLabel}>ADD DOCUMENT</div>

          {/* Form row */}
          <div style={styles.formRow}>
            <label style={styles.formField}>
              <span style={styles.fieldLabel}>TYPE</span>
              <select
                style={styles.select}
                value={uploadForm.type}
                onChange={e => setUploadForm(f => ({ ...f, type: e.target.value }))}
              >
                {DOC_TYPES.map(t => (
                  <option key={t.key} value={t.key}>{t.label} — {t.desc}</option>
                ))}
              </select>
            </label>
            <label style={styles.formField}>
              <span style={styles.fieldLabel}>REVISION</span>
              <input
                type="text"
                style={styles.input}
                value={uploadForm.revision}
                onChange={e => setUploadForm(f => ({ ...f, revision: e.target.value }))}
                placeholder="e.g. Rev 47, Jan 2025"
              />
            </label>
            <label style={styles.formField}>
              <span style={styles.fieldLabel}>AIRCRAFT TYPE</span>
              <input
                type="text"
                style={styles.input}
                value={uploadForm.aircraft_type}
                onChange={e => setUploadForm(f => ({ ...f, aircraft_type: e.target.value }))}
                placeholder="A320"
              />
            </label>
          </div>

          {/* Drop zone */}
          <div
            style={{
              ...styles.dropZone,
              borderColor: dragOver ? 'var(--amber)' : uploading ? 'var(--teal)' : 'var(--border-2)',
              background: dragOver ? 'rgba(232,162,52,0.04)' : 'var(--surface)',
            }}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => !uploading && fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf"
              style={{ display: 'none' }}
              onChange={e => handleUpload(e.target.files)}
            />
            {uploading ? (
              <>
                <div style={styles.spinner} />
                <span style={{ color: 'var(--teal)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                  UPLOADING & PROCESSING…
                </span>
              </>
            ) : (
              <>
                <Icon d={UPLOAD} size={28} color={dragOver ? 'var(--amber)' : 'var(--text-dim)'} />
                <div style={styles.dropText}>
                  <span style={{ color: dragOver ? 'var(--amber)' : 'var(--text-2)' }}>
                    Drop PDF here or click to browse
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)' }}>
                    PDF only · Max 50 MB
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Document list */}
        <div style={styles.docList}>
          <div style={styles.sectionLabel}>LIBRARY</div>

          {loading ? (
            <div style={styles.loadingRow}>
              <div style={styles.spinner} />
              <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                Loading…
              </span>
            </div>
          ) : documents.length === 0 ? (
            <div style={styles.empty}>
              <Icon d={DOC} size={32} color="var(--text-dim)" />
              <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                No documents uploaded yet
              </span>
            </div>
          ) : (
            <div style={styles.table}>
              {/* Header */}
              <div style={styles.tableHeader}>
                <span style={{ flex: '0 0 80px' }}>TYPE</span>
                <span style={{ flex: 1 }}>DOCUMENT NAME</span>
                <span style={{ flex: '0 0 120px' }}>AIRCRAFT</span>
                <span style={{ flex: '0 0 120px' }}>REVISION</span>
                <span style={{ flex: '0 0 90px' }}>STATUS</span>
                <span style={{ flex: '0 0 80px', textAlign: 'right' }}>CHUNKS</span>
                <span style={{ flex: '0 0 40px' }} />
              </div>

              {documents.map((doc, i) => (
                <div key={doc.id} style={{
                  ...styles.tableRow,
                  animation: `fadeUp 0.2s ease ${i * 0.04}s both`,
                }}>
                  <span style={{ flex: '0 0 80px' }}>
                    <span style={styles.typeTag}>{doc.document_type?.toUpperCase() || '—'}</span>
                  </span>
                  <span style={{ flex: 1, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {doc.name || doc.filename}
                  </span>
                  <span style={{ flex: '0 0 120px', color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                    {doc.aircraft_type || '—'}
                  </span>
                  <span style={{ flex: '0 0 120px', color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                    {doc.revision || '—'}
                  </span>
                  <span style={{ flex: '0 0 90px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{
                      width: '6px', height: '6px', borderRadius: '50%', flexShrink: 0,
                      background: statusColor[doc.status] || 'var(--text-dim)',
                      ...(doc.status === 'processing' ? { animation: 'pulse 1.2s ease infinite' } : {}),
                    }} />
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: statusColor[doc.status] || 'var(--text-dim)' }}>
                      {doc.status?.toUpperCase() || 'UNKNOWN'}
                    </span>
                  </span>
                  <span style={{ flex: '0 0 80px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-dim)' }}>
                    {doc.chunk_count ?? '—'}
                  </span>
                  <span style={{ flex: '0 0 40px', display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      style={styles.deleteBtn}
                      onClick={() => setConfirmDelete(doc)}
                      title="Remove document"
                    >
                      <Icon d={TRASH} size={14} />
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  root: {
    height: '100vh', overflowY: 'auto',
    padding: '32px',
    position: 'relative',
  },
  inner: { maxWidth: '900px', margin: '0 auto' },
  pageHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    marginBottom: '32px',
  },
  pageTitle: {
    fontFamily: 'var(--font-display)', fontSize: '28px', letterSpacing: '3px',
    color: 'var(--text)', marginBottom: '4px',
  },
  pageSubtitle: {
    fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '1px',
    color: 'var(--text-dim)',
  },
  sectionLabel: {
    fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '2px',
    color: 'var(--text-dim)', marginBottom: '12px',
  },
  uploadSection: { marginBottom: '40px' },
  formRow: {
    display: 'flex', gap: '12px', marginBottom: '12px', flexWrap: 'wrap',
  },
  formField: { display: 'flex', flexDirection: 'column', gap: '5px', flex: 1, minWidth: '160px' },
  fieldLabel: {
    fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '1.5px',
    color: 'var(--text-dim)',
  },
  select: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius)', padding: '8px 10px',
    color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '12px',
    outline: 'none', cursor: 'pointer',
  },
  input: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius)', padding: '8px 10px',
    color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '12px',
    outline: 'none',
  },
  dropZone: {
    border: '2px dashed', borderRadius: 'var(--radius-lg)',
    padding: '40px', display: 'flex',
    flexDirection: 'column', alignItems: 'center', gap: '12px',
    cursor: 'pointer', transition: 'all 0.2s',
  },
  dropText: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
    fontSize: '14px',
  },
  docList: {},
  loadingRow: {
    display: 'flex', alignItems: 'center', gap: '12px',
    padding: '32px', justifyContent: 'center',
  },
  empty: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px',
    padding: '48px', color: 'var(--text-dim)',
  },
  table: {
    border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden',
  },
  tableHeader: {
    display: 'flex', alignItems: 'center', gap: '12px',
    padding: '10px 16px',
    background: 'var(--bg-2)',
    borderBottom: '1px solid var(--border)',
    fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '1.5px',
    color: 'var(--text-dim)',
  },
  tableRow: {
    display: 'flex', alignItems: 'center', gap: '12px',
    padding: '12px 16px',
    borderBottom: '1px solid var(--border)',
    background: 'var(--surface)',
    transition: 'background 0.1s',
    fontSize: '13px',
  },
  typeTag: {
    fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '1px',
    color: 'var(--amber)', background: 'var(--amber-dim)',
    padding: '2px 8px', borderRadius: 'var(--radius)',
    border: '1px solid var(--amber-dim)',
  },
  deleteBtn: {
    background: 'none', border: 'none', color: 'var(--text-dim)',
    cursor: 'pointer', padding: '4px', display: 'flex',
    borderRadius: 'var(--radius)', transition: 'color 0.15s',
  },
  spinner: {
    width: '20px', height: '20px',
    border: '2px solid var(--border-2)',
    borderTopColor: 'var(--amber)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  toast: {
    position: 'fixed', top: '20px', right: '20px',
    display: 'flex', alignItems: 'center', gap: '8px',
    padding: '10px 16px', borderRadius: 'var(--radius-lg)',
    border: '1px solid',
    fontFamily: 'var(--font-mono)', fontSize: '12px',
    zIndex: 1000, animation: 'fadeUp 0.2s ease',
    boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
  },
  modalOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 200,
  },
  modal: {
    background: 'var(--bg-2)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)', padding: '28px', width: '100%', maxWidth: '420px',
    animation: 'fadeUp 0.2s ease',
  },
  modalTitle: {
    fontFamily: 'var(--font-display)', fontSize: '22px', letterSpacing: '2px',
    color: 'var(--text)', marginBottom: '12px',
  },
  modalBody: {
    color: 'var(--text-2)', fontSize: '14px', lineHeight: 1.6, marginBottom: '24px',
  },
  modalActions: {
    display: 'flex', gap: '10px', justifyContent: 'flex-end',
  },
  btnCancel: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius)', padding: '9px 18px',
    color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: '12px',
    cursor: 'pointer',
  },
  btnDelete: {
    background: 'var(--red)', border: 'none',
    borderRadius: 'var(--radius)', padding: '9px 18px',
    color: 'white', fontFamily: 'var(--font-mono)', fontSize: '12px',
    cursor: 'pointer', letterSpacing: '1px',
  },
};
