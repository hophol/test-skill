import React from 'react';

// 故障注入变体 BUG-B【loading 漏禁用类】——loading 时不加 btn-disabled 类
export default function Button({ label, variant = 'primary', disabled = false, loading = false, onClick }) {
  const cls = ['btn', `btn-${variant}`, disabled ? 'btn-disabled' : ''].filter(Boolean).join(' ');   // ← BUG: 漏了 loading
  return (
    <button
      type="button"
      className={cls}
      disabled={disabled || loading}
      aria-busy={loading}
      onClick={() => { if (!disabled && !loading && onClick) onClick(); }}
    >
      {loading ? '处理中…' : label}
    </button>
  );
}
