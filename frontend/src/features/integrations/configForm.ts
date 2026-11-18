export const AIRTEL_CREDENTIAL_KEYS = ["customer_id","username","password"];
import type {IntegrationConfig} from "./api";
import {fieldsFor} from "./providerFields";
export function editValues(config:IntegrationConfig):Record<string,string>{
 return Object.fromEntries(fieldsFor(config.integration_type,config.provider).filter(field=>!field.secret).map(field=>[field.key,config.config[field.key]??""]));
}
export function changedValues(config:IntegrationConfig,values:Record<string,string>):Record<string,string>{
 return Object.fromEntries(Object.entries(values).filter(([key,value])=>value!==""&&value!==config.config[key]));
}
export function airtelSendReason(config:IntegrationConfig):string|null{
 if(config.airtel_workflow?.authentication_ready===false)return config.airtel_workflow.authentication_message??"Save Customer ID, Username and Password before sending.";
 if(!config.airtel_workflow?.validated_at)return "Save the settings and run successful configuration validation first.";
 if(config.config.contract_confirmed!=="true")return "Confirm and save the account-specific Airtel contract first.";
 if(!config.is_enabled)return "Enable this integration before sending a test SMS.";
 return null;
}
