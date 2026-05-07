import React from 'react';

export default function InvalidationBanner({ data }) {
  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <span style={styles.icon}>⛔</span>
        <span style={styles.title}>INVALIDATED REFERENCE</span>
      </div>
      <div style={styles.body}>
        <p style={styles.docName}>
          <strong>{data.document_name}</strong>
          {data.revision && <span style={styles.rev}> — Rev {data.revision}</span>}
        </p>
        {data.section && (
          <p style={styles.section}>Section: {data.section}</p>
        )}
        <p style={styles.message}>
          {data.message || 'This document section has been updated or removed since this session was created. Information provided in this session may no longer be current. Please refer to the current revision.'}
        </p>
      </div>
    </div>
  );
}

const styles = {
  root: {
    background: 'var(--red-dim)',
    border: '1px solid var(--red)',
    borderRadius: 'var(--radius-lg)',
    padding: '14px 16px',
    animation: 'fadeUp 0.3s ease both',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px',
  },
  icon: { fontSize: '16px' },
  title: {
    fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '2px',
    color: 'var(--red)', fontWeight: 600,
  },
  body: { paddingLeft: '24px' },
  docName: {
    fontFamily: 'var(--font-mono)', fontSize: '12px',
    color: 'var(--text)', marginBottom: '4px',
  },
  rev: { color: 'var(--text-dim)', fontWeight: 400 },
  section: {
    fontFamily: 'var(--font-mono)', fontSize: '11px',
    color: 'var(--text-2)', marginBottom: '8px',
  },
  message: {
    fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.6,
  },
};
