import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { apiRequest } from "@/shared/api/client";
export interface BankOption {id:string;name:string;version:number;is_active:boolean;created_by_name:string;created_at:string;updated_at:string}
export interface BankSelection {option_id:string|null;name:string}
type OptionKind = "bank" | "loan-type";
const baseFor=(kind:OptionKind)=>`/daily-operations/${kind}-options`;
export const listBankOptions=(kind:OptionKind="bank")=>apiRequest<BankOption[]>(`${baseFor(kind)}?include_archived=true`);
export const createBankOption=(name:string,kind:OptionKind="bank")=>apiRequest<BankOption>(baseFor(kind),{method:"POST",body:JSON.stringify({name})});
export const editBankOption=(row:BankOption,name:string,kind:OptionKind="bank")=>apiRequest<BankOption>(`${baseFor(kind)}/${row.id}`,{method:"PATCH",body:JSON.stringify({name,version:row.version})});
export const archiveBankOption=(row:BankOption,restore=false,kind:OptionKind="bank")=>apiRequest<BankOption>(`${baseFor(kind)}/${row.id}/${restore?"restore":"archive"}`,{method:"POST",body:JSON.stringify({version:row.version})});
export function useBankOptions(kind:OptionKind="bank"){const {userId}=useAuth();return useQuery({queryKey:[kind === "bank" ? "daily-bank-options" : "daily-loan-type-options",userId],queryFn:()=>listBankOptions(kind),staleTime:3000,refetchInterval:5000,refetchOnWindowFocus:true});}
export function recordBanks(record?:Record<string,unknown>):BankSelection[]{return Array.isArray(record?.banks)?record.banks as BankSelection[]:record?.bank?[{option_id:null,name:String(record.bank)}]:[];}
