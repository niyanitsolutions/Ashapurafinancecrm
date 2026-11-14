import {BankMultiSelect} from "./BankMultiSelect";
export function LoanTypeField({value,onChange}:{value:string;onChange:(value:string)=>void}) {
 return <BankMultiSelect kind="loan-type" single value={value?[{option_id:null,name:value}]:[]} onChange={rows=>onChange(rows[0]?.name??"")}/>;
}
