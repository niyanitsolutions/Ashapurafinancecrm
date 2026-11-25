import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { DateInput } from "./DateInput";
function Harness(){const [value,setValue]=useState("2026-10-01");return <><DateInput aria-label="Business date" value={value} onChange={e=>setValue(e.target.value)}/><output data-testid="stored-date">{value}</output></>;}
it("never submits the old ISO date while the displayed date is incomplete",()=>{
 render(<Harness/>);const input=screen.getByLabelText("Business date");expect(input).toHaveValue("01/10/2026");fireEvent.change(input,{target:{value:"25/"}});expect(input).toHaveValue("25/");expect(screen.getByTestId("stored-date")).toHaveTextContent("");expect(input).toBeInvalid();fireEvent.change(input,{target:{value:"25/11/2026"}});expect(input).toHaveValue("25/11/2026");expect(screen.getByTestId("stored-date")).toHaveTextContent("2026-11-25");expect(input).toBeValid();
});
