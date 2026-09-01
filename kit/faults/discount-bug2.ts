// 故障注入变体 BUG-2【VIP 折扣反了】——isVip 为 false 时打折,true 时原价
// 预期:009 任务要求覆盖「VIP 折扣」,好的测试集应在此变体上失败
export interface CartItem {
  sku: string;
  price: number;
  qty: number;
}

export const VIP_DISCOUNT = 0.85;
export const FULL_REDUCE_THRESHOLD = 300;
export const FULL_REDUCE_AMOUNT = 40;

export function lineTotal(item: CartItem, isVip: boolean): number {
  if (item.price <= 0) throw new Error('price must be positive');
  if (!Number.isInteger(item.qty) || item.qty < 1) throw new Error('qty must be a positive integer');
  const raw = item.price * item.qty;
  return isVip ? round2(raw) : round2(raw * VIP_DISCOUNT);   // ← BUG: 分支反了
}

export function payable(items: CartItem[], isVip: boolean): number {
  const subtotal = items.reduce((s, it) => s + lineTotal(it, isVip), 0);
  const reduction = Math.floor(subtotal / FULL_REDUCE_THRESHOLD) * FULL_REDUCE_AMOUNT;
  return round2(subtotal - reduction);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
