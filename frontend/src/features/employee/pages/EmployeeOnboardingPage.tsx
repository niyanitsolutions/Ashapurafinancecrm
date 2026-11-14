import {EmployeeAccessReview} from "../components/EmployeeAccessReview";
import {ConfirmDialog} from "@/components/overlays/ConfirmDialog";
import {EmployeeEditRequests} from "../components/EmployeeEditRequests";
import {apiRequest} from "@/shared/api/client";
import {hrPath} from "../hrApi";
import {Link} from "react-router-dom";
import {useCallback,useEffect,useRef,useState} from "react";
import {useParams} from "react-router-dom";
import {SimplePageLayout} from "@/components/layout/SimplePageLayout";
import {FormField} from "@/components/forms/FormField";
import {Button} from "@/components/buttons/Button";
import {ErrorBanner} from "@/components/forms/ErrorBanner";
import {useAuth} from "@/features/auth/useAuth";
import {getErrorMessage} from "@/shared/api/errors";
import {getHrProfile,saveHrProfile,submitHrProfile,reviewHrProfile,type ProfileDraft,type HrProfile,type Address} from "../hrApi";
import {EmployeeHrDocuments} from "../components/EmployeeHrDocuments";
const address=():Address=>({line1:"",city:"",state:"",pincode:"",country:"India"});
function draft(row:HrProfile):ProfileDraft {return row.onboarding.profile??{first_name:row.current_profile.first_name??"",last_name:row.current_profile.last_name??"",email:row.current_profile.email??"",emergency_contact:row.current_profile.emergency_contact??{name:"",relationship:"",mobile:""},current_address:row.current_profile.current_address??address(),permanent_same_as_current:false,permanent_address:row.current_profile.permanent_address??address(),fresher:true,previous_company:null,experience_years:0,experience_months:0};}
export function EmployeeOnboardingPage({requestMode=false}:{requestMode?:boolean}){
 const {employeeId="me"}=useParams();return <EmployeeOnboardingForm key={employeeId+":"+requestMode} employeeId={employeeId} requestMode={requestMode}/>;
}
function EmployeeOnboardingForm({employeeId,requestMode}:{employeeId:string;requestMode:boolean}){
 const [reviewDecision,setReviewDecision]=useState<string|null>(null);
 const {role}=useAuth();const [row,setRow]=useState<HrProfile|null>(null);const [values,setValues]=useState<ProfileDraft|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState("");const [reason,setReason]=useState("");
 const loadSequence=useRef(0);
 const load=useCallback(async(keepDraft=false)=>{const sequence=++loadSequence.current;try{const result=await getHrProfile(employeeId);if(sequence!==loadSequence.current)return;setRow(result);setValues(old=>keepDraft&&old?old:draft(result));}catch(e){setError(getErrorMessage(e));}},[employeeId]);
 const cancelLoad=useCallback(()=>{loadSequence.current++;},[]);
 useEffect(()=>{void load();const timer=setInterval(()=>void load(true),30000);return()=>{cancelLoad();clearInterval(timer);};},[load,cancelLoad]);
 async function run(action:()=>Promise<HrProfile>,message:string){if(busy)return;setBusy(true);setError(null);try{const result=await action();setRow(result);setValues(draft(result));setNotice(message);}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
 if(!row||!values)return <SimplePageLayout title="Employee Onboarding"><ErrorBanner message={error}/><p role="status">{error?"Unable to load profile.":"Loading profile..."}</p></SimplePageLayout>;
 const editable=requestMode?row.onboarding.status==="verified":!["verified","pending_verification"].includes(row.onboarding.status);
 const field=(key:"first_name"|"last_name"|"email",label:string)=><FormField label={label} required disabled={!editable||busy} type={key==="email"?"email":"text"} value={values[key]} onChange={e=>setValues({...values,[key]:e.target.value})}/>;
 function addressFields(key:"current_address"|"permanent_address",label:string){const value=values![key]??address();return <fieldset className="rounded border border-border p-3"><legend>{label}</legend>{(["line1","city","state","pincode"] as const).map(name=><FormField key={name} label={`${label} ${name==="line1"?"address":name}`} required disabled={!editable||busy} value={value[name]} onChange={e=>setValues({...values!,[key]:{...value,[name]:e.target.value}})}/>)}</fieldset>;}
 return <SimplePageLayout title="Employee Onboarding" subtitle={`${row.employee_code} - ${row.onboarding.status.replaceAll("_"," ")}`} backTo={role==="owner"?`/employees/${employeeId}`:"/profile"}>
 <Button variant="ghost" disabled={busy} onClick={()=>void load(true)}>Refresh verification status</Button><ErrorBanner message={error}/>{notice&&<p role="status">{notice}</p>}
 <p className="mb-4 text-sm">Account status: {row.account_status}. Account-only employees retain authorized CRM access while profile verification is pending.</p>
 {row.onboarding.reason&&<p className="mb-4 rounded border border-warning p-3">Changes requested: {row.onboarding.reason}</p>}
 <ol className="mb-4 flex flex-wrap gap-4 text-sm"><li>1. Profile and experience</li><li>2. Documents</li><li>3. Submit</li><li>4. Owner verification</li></ol>
 <form onSubmit={e=>{e.preventDefault();void run(async()=>{if(requestMode){await apiRequest(hrPath(employeeId)+"/edit-requests",{method:"POST",body:JSON.stringify({...values,version:row.employee_version??1})});return getHrProfile(employeeId);}return saveHrProfile(employeeId,values,row.onboarding.version);},requestMode?"Edit request submitted. Official information remains unchanged.":"Profile saved. Upload documents, then submit for review.");}} className="space-y-4">
 <div className="grid gap-4 md:grid-cols-2">{field("first_name","First name")}{field("last_name","Last name")}{field("email","Email address")}<FormField label="Registered mobile number" value={row.mobile} disabled/>
 {(["name","relationship","mobile"] as const).map(key=><FormField key={key} label={`Emergency contact ${key}`} required disabled={!editable||busy} value={values.emergency_contact[key]} pattern={key==="mobile"?"[6-9][0-9]{9}":undefined} onChange={e=>setValues({...values,emergency_contact:{...values.emergency_contact,[key]:e.target.value}})}/>)}</div>
 {addressFields("current_address","Local")}
 <label className="flex gap-2"><input type="checkbox" checked={values.permanent_same_as_current} disabled={!editable||busy} onChange={e=>setValues({...values,permanent_same_as_current:e.target.checked})}/>Permanent address same as local address</label>
 {!values.permanent_same_as_current&&addressFields("permanent_address","Permanent")}
 <label className="flex gap-2"><input type="checkbox" checked={values.fresher} disabled={!editable||busy} onChange={e=>setValues({...values,fresher:e.target.checked})}/>Fresher</label>
 {!values.fresher&&<div className="grid gap-4 md:grid-cols-3"><FormField label="Previous company" required disabled={!editable||busy} value={values.previous_company??""} onChange={e=>setValues({...values,previous_company:e.target.value})}/>{(["experience_years","experience_months"] as const).map(key=><FormField key={key} label={key.replaceAll("_"," ")} type="number" min={0} max={key==="experience_months"?11:70} required disabled={!editable||busy} value={values[key]} onChange={e=>setValues({...values,[key]:Number(e.target.value)})}/>)}</div>}
 {editable&&<Button type="submit" disabled={busy}>{requestMode?"Submit edit request":"Save profile"}</Button>}</form>
 <EmployeeHrDocuments employeeId={employeeId} fresher={values.fresher} onChanged={()=>void load(true)}/>
 {role==="owner"&&row.onboarding.mode==="owner_complete"&&!row.onboarding.account_created_at&&<EmployeeAccessReview employeeId={row.employee_id} version={row.onboarding.version} acknowledged={!!row.onboarding.access_review} onChanged={()=>void load(true)}/>}
 {editable&&!requestMode&&<Button disabled={busy||!row.onboarding.profile} onClick={()=>void run(()=>submitHrProfile(employeeId,row.onboarding.version),"Submitted for owner verification.")}>Submit profile for verification</Button>}
 {role==="owner"&&row.onboarding.status==="pending_verification"&&<section className="my-5 rounded border border-border p-4"><h2 className="font-semibold">Owner review</h2><FormField label="Review reason" value={reason} onChange={e=>setReason(e.target.value)}/><div className="flex gap-3"><Button disabled={busy||(row.onboarding.mode==="owner_complete"&&!row.onboarding.account_created_at&&!row.onboarding.access_review)} onClick={()=>setReviewDecision("approve")}>{row.onboarding.mode==="owner_complete"&&!row.onboarding.account_created_at?"Create employee account":"Approve completed profile"}</Button><Button variant="secondary" disabled={busy||!reason.trim()} onClick={()=>setReviewDecision("changes_required")}>Request changes</Button></div></section>}
 {row.onboarding.status==="verified"&&!requestMode&&<Link className="mt-4 block text-primary" to={employeeId==="me"?"/profile/edit-request":`/employees/${employeeId}/edit-request`}>Request changes to official profile</Link>}
 <EmployeeEditRequests key={notice} employeeId={employeeId} onChanged={()=>void load(true)}/>
 <details className="mt-4"><summary>Profile verification history</summary>{row.onboarding.history.map((event,i)=><p key={i}>{event.action} ? {event.at} {event.reason}</p>)}</details>
 {role==="owner"&&row.onboarding.mode==="owner_complete"&&!row.onboarding.account_created_at&&row.onboarding.status==="verified"&&row.account_status!=="active"&&<Button disabled={busy} onClick={()=>setReviewDecision("activate")}>Finish approved account activation</Button>}
 <ConfirmDialog open={!!reviewDecision} title="Confirm profile review" message={reviewDecision==="approve"?"Verify this profile after reviewing all required documents?":"Request the specified changes and return this profile to the employee?"} confirmLabel={reviewDecision==="activate"?"Activate approved account":reviewDecision==="approve"?"Confirm profile approval":"Confirm changes required"} confirmDisabled={reviewDecision==="changes_required"&&!reason.trim()} onClose={()=>setReviewDecision(null)} onConfirm={async()=>{await run(async()=>{if(reviewDecision==="activate"){await apiRequest(`/employees/${row.employee_id}/activate`,{method:"PATCH"});return getHrProfile(employeeId);}return reviewHrProfile(employeeId,row.onboarding.version,reviewDecision!,reason);},reviewDecision==="approve"?"Profile verified.":"Changes requested.");setReviewDecision(null);}}/>
 </SimplePageLayout>;
}
