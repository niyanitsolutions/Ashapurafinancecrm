import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { apiRequest, setSessionExpiredHandler, setAccessToken } from "./client";
beforeEach(()=>{localStorage.clear();setAccessToken(null);});
afterEach(()=>{vi.unstubAllGlobals();setSessionExpiredHandler(null);});
it("treats a rejected PIN login as credentials failure without refresh or session expiration",async()=>{
 const expired=vi.fn();setSessionExpiredHandler(expired);
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({success:false,data:null,error:{code:"unauthorized",message:"Invalid customer credentials"}}),{status:401,headers:{"Content-Type":"application/json"}}));vi.stubGlobal("fetch",fetch);
 await expect(apiRequest("/auth/pin/login",{method:"POST",body:JSON.stringify({mobile:"9000000000",pin:"1234"})})).rejects.toMatchObject({code:"unauthorized"});
 expect(fetch).toHaveBeenCalledTimes(1);expect(expired).not.toHaveBeenCalled();
});
