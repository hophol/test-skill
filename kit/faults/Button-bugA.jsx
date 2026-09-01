import React from 'react';

// 故障注入变体 BUG-A【disabled 漏判】——disabled 时点击仍上抛(漏了 !disabled 条件)
// 预期:011 任务明确要求「disabled/loading 不触发 onClick」,好的测试集应在此变体上失败
export default function Button({ label, variant = 'primary', disabled = false, loading = false, onClick }) {
  const cls = ['btn', `btn-${variant}`, (disabled || loading) ? 'btn-disabled' : ''].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={cls}
      disabled={disabled || loading}
      aria-busy={loading}
      onClick={() => { if (!loading && onClick) onClick(); }}   // ← BUG: 漏了 !disabled
    >
      {loading ? '处理中…' : label}
    </button>
  );
}
