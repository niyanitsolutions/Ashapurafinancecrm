import type { Item } from "./api";

function scaled(value: string, places: number): bigint {
  if (!/^\d+(\.\d+)?$/.test(value)) throw new Error("Enter a positive decimal value.");
  const [whole, originalFraction = ""] = value.split(".");
  const fraction = originalFraction.replace(/0+$/, "");
  if (fraction.length > places) throw new Error(`Use at most ${places} decimal places.`);
  return BigInt(whole + fraction.padEnd(places, "0"));
}
const round = (value: bigint, divisor: bigint) => (value + divisor / 2n) / divisor;
export const decimal = (value: bigint) => `${value / 100n}.${(value % 100n).toString().padStart(2, "0")}`;
export function calculateItems(items: Item[], split: boolean) {
  let subtotal = 0n, gst = 0n;
  const rows = items.map(item => {
    const taxable = round(scaled(item.quantity, 3) * scaled(item.rate, 2), 1000n);
    const rate = scaled(item.gst_rate, 2);
    const tax = split ? round(taxable * rate, 20000n) * 2n : round(taxable * rate, 10000n);
    subtotal += taxable; gst += tax;
    return {taxable: decimal(taxable), gst: decimal(tax), total: decimal(taxable + tax)};
  });
  return {rows, subtotal: decimal(subtotal), gst: decimal(gst), total: decimal(subtotal + gst)};
}
