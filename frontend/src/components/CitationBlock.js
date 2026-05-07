import React, { useState } from 'react';

export default function CitationBlock({ citation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={styles.root} onClick={() => setExpanded(v => !v)}>
      <div style={styles.header}>
        <span style={styles.icon}>📄</span>
        <div style={styles.meta}>
          <span style={styles.docName}>{citation.document_name || 'Source document'}</span>
          {citation.section && (
            <span style={styles.section}>§ {citation.section}</span>
          )}
        </div>
        {citation.revision && (
          <span style={styles.rev}>Rev {citation.revision}</span>
        )}
        <span style={styles.chevron}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && citation.excerpt && (
        <div style={styles.excerpt}>
          "{citation.excerpt}"
        </div>
      )}
    </div>
  );
}

const styles = {
  root: {
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: '8px 10px',
    cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: '8px',
  },
  icon: { fontSize: '12px', flexShrink: 0 },
  meta: {
    flex: 1, display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center',
    minWidth: 0,
  },
  docName: {
    fontFamily: 'var(--font-mono)', fontSize: '11px',
    color: 'var(--teal)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  section: {
    fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-dim)',
  },
  rev: {
    fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '1px',
    color: 'var(--text-dim)', background: 'var(--surface)',
    padding: '1px 6px', borderRadius: 'var(--radius)',
    border: '1px solid var(--border)', flexShrink: 0,
  },
  chevron: {
    fontSize: '9px', color: 'var(--text-dim)', flexShrink: 0,
  },
  excerpt: {
    marginTop: '8px', paddingTop: '8px',
    borderTop: '1px solid var(--border)',
    fontFamily: 'var(--font-mono)', fontSize: '12px',
    color: 'var(--text-2)', lineHeight: 1.6,
    fontStyle: 'italic',
  },
};
