import React from 'react';

// 故障注入变体 BUG-C【loading 文案丢失】——恒显 label,不显示「处理中…」
export default function Button({ label, variant = 'primary', disabled = false, loading = false, onClick }) {
  const cls = ['btn', `btn-${variant}`, (disabled || loading) ? 'btn-disabled' : ''].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={cls}
      disabled={disabled || loading}
      aria-busy={loading}
      onClick={() => { if (!disabled && !loading && onClick) onClick(); }}
    >
      {label}   {/* ← BUG: loading 文案分支丢失 */}
    </button>
  );
}
