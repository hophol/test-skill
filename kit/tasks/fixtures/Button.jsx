import React from 'react';

/**
 * 通用按钮组件 —— 被测对象
 * variant: primary | secondary | danger;disabled 时点击不上抛;loading 时显示「处理中」
 */
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
      {loading ? '处理中…' : label}
    </button>
  );
}
