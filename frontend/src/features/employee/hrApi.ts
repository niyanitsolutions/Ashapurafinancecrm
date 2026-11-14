import {apiRequest} from "@/shared/api/client";
export interface Address {line1:string;line2?:string|null;city:string;state:string;pincode:string;country?:string}
export interface ProfileDraft {first_name:string;last_name:string;email:string;emergency_contact:{name:string;relationship:string;mobile:string};current_address:Address;permanent_same_as_current:boolean;permanent_address:Address|null;fresher:boolean;previous_company:string|null;experience_years:number;experience_months:number}
export interface HrProfile {employee_id:string;employee_version?:number;employee_code:string;mobile:string;account_status:string;current_profile:Partial<ProfileDraft>;onboarding:{account_created_at?:string;access_review?:{reviewed_at:string;role_ids:string[]};mode?:string;status:string;version:number;profile?:ProfileDraft;reason?:string;history:{action:string;reason?:string;at:string}[]}}
export interface DocumentVersion {id:string;version:number;status:string;files:{file_name:string;content_type:string;part:string;size:number}[];malware_scan:string;history:{status:string;reason:string;at:string}[];versions?:DocumentVersion[]}
export const hrPath=(employeeId:string)=>`/employees/hr/${encodeURIComponent(employeeId)}`;
export const getHrProfile=(id:string)=>apiRequest<HrProfile>(hrPath(id)+"/profile");
export const saveHrProfile=(id:string,profile:ProfileDraft,version:number)=>apiRequest<HrProfile>(hrPath(id)+"/profile",{method:"PUT",body:JSON.stringify({...profile,version})});
export const submitHrProfile=(id:string,version:number)=>apiRequest<HrProfile>(hrPath(id)+"/profile/submit",{method:"POST",body:JSON.stringify({version})});
export const reviewHrProfile=(id:string,version:number,decision:string,reason:string)=>apiRequest<HrProfile>(hrPath(id)+"/profile/review",{method:"POST",body:JSON.stringify({version,decision,reason})});
export const getHrDocuments=(id:string)=>apiRequest<Record<string,DocumentVersion>>(hrPath(id)+"/documents");
