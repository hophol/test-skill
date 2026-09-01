// 折扣计算模块 —— 被测对象
export interface CartItem {
  sku: string;
  price: number;   // 单价(元),>0
  qty: number;     // 数量,>=1 整数
}

export const VIP_DISCOUNT = 0.85;
export const FULL_REDUCE_THRESHOLD = 300;  // 满 300 减 40
export const FULL_REDUCE_AMOUNT = 40;

/** 会员折扣:VIP 打 85 折,非 VIP 原价;价格为 0/负数或数量非正整数抛错 */
export function lineTotal(item: CartItem, isVip: boolean): number {
  if (item.price <= 0) throw new Error('price must be positive');
  if (!Number.isInteger(item.qty) || item.qty < 1) throw new Error('qty must be a positive integer');
  const raw = item.price * item.qty;
  return isVip ? round2(raw * VIP_DISCOUNT) : round2(raw);
}

/** 满减:总额达到阈值每满 300 减 40(可叠加),VIP 折后参与满减 */
export function payable(items: CartItem[], isVip: boolean): number {
  const subtotal = items.reduce((s, it) => s + lineTotal(it, isVip), 0);
  const reduction = Math.floor(subtotal / FULL_REDUCE_THRESHOLD) * FULL_REDUCE_AMOUNT;
  return round2(subtotal - reduction);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
