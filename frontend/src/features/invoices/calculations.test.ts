import { describe, expect, it } from "vitest";
import { calculateItems } from "./calculations";
import { money } from "./api";

const item={description:"Consultancy",hsn:"9971",quantity:"3",unit:"nos.s",rate:"7753.71",gst_rate:"18"};
describe("invoice monetary preview",()=>{
  it("matches the reference to the paise",()=>{
    expect(calculateItems([item],false)).toEqual({subtotal:"23261.13",gst:"4187.00",total:"27448.13",rows:[{taxable:"23261.13",gst:"4187.00",total:"27448.13"}]});
  });
  it("rounds lines and split GST identically to the backend",()=>{
    expect(calculateItems([{...item,quantity:"1",rate:"0.06"}],true).gst).toBe("0.02");
    expect(calculateItems([{...item,quantity:"0.125",rate:"0.04"}],false).subtotal).toBe("0.01");
  });
  it("handles large values without floating point accounting",()=>{
    expect(calculateItems([{...item,quantity:"1000000",rate:"999999999999.99",gst_rate:"0"}],false).total).toBe("999999999999990000.00");
    expect(money("999999999999990000.01")).toBe("₹9,99,99,99,99,99,99,90,000.01");
  });
  it("rejects invalid decimal input",()=>{
    expect(()=>calculateItems([{...item,rate:"NaN"}],false)).toThrow();
    expect(()=>calculateItems([{...item,rate:"0.001"}],false)).toThrow();
  });
});
