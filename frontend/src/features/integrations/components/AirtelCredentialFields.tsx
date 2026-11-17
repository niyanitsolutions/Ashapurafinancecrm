import {AIRTEL_CREDENTIAL_KEYS} from "../configForm";
import {useEffect,useState} from "react";
import {useAuth} from "@/features/auth/useAuth";
import {getOwnOwnerAccount} from "@/features/owner/api";
import {Button} from "@/components/buttons/Button";


export function AirtelCredentialFields({values,saved={},onChange}:{values:Record<string,string>;saved?:Record<string,string>;onChange:(key:string,value:string)=>void}){
 const {role,userId}=useAuth();const [primary,setPrimary]=useState(false);const [loaded,setLoaded]=useState(false);const [visible,setVisible]=useState(false);
 useEffect(()=>{let live=true;setPrimary(false);setLoaded(false);if(role!=="owner"){setLoaded(true);return;}void getOwnOwnerAccount().then(row=>{if(live)setPrimary(row.owner_type==="primary");}).catch(()=>{if(live)setPrimary(false);}).finally(()=>{if(live)setLoaded(true);});return()=>{live=false;};},[role,userId]);
 useEffect(()=>{if(!values.password)setVisible(false);},[values.password]);
 const editable=loaded&&primary;
 return <><p className="sm:col-span-2 text-sm">{!loaded?"Checking Primary Owner access...":!primary?"Only the Primary Owner can enter Airtel credentials.":"Credentials are encrypted. Saved values are never reloaded into these inputs. Leave an edit blank to retain the saved value."}</p>{AIRTEL_CREDENTIAL_KEYS.map(key=><label key={key} className="text-xs text-text/60">{key==="customer_id"?"Customer ID":key==="username"?"Username":"Password"}{saved[key]&&<span className="ml-2">Saved: ********</span>}<input aria-label={key==="customer_id"?"Customer ID":key==="username"?"Username":"Password"} name={`airtel-sms-${key}`} autoComplete={key==="password"?"new-password":"off"} type={key==="password"&&!visible?"password":"text"} disabled={!editable} value={values[key]??""} placeholder={saved[key]?"Leave blank to keep saved credential":"Enter from Airtel IQ Technical Settings"} onChange={e=>{if(editable)onChange(key,e.target.value);}} className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm"/>{key==="password"&&<Button type="button" variant="ghost" size="sm" disabled={!editable} aria-pressed={visible} onClick={()=>setVisible(old=>!old)}>{visible?"Hide Airtel password":"Show Airtel password"}</Button>}</label>)}</>;
}
