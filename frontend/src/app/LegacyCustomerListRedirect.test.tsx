import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, it } from "vitest";
import { LegacyCustomerListRedirect } from "./LegacyCustomerListRedirect";
function Destination(){return <p data-testid="destination">{useLocation().search}</p>;}
it.each([["/applications?status=submitted&search=AFS-APP-1","application_status=submitted"],["/customers?status=active&search=Name","customer_status=active"],["/applications?unassigned_only=true","assigned_to=__unassigned__"]])("redirects %s into grouped intake with preserved intent",async(path, expected)=>{
 render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/applications" element={<LegacyCustomerListRedirect/>}/><Route path="/customers" element={<LegacyCustomerListRedirect/>}/><Route path="/leads/document-collection" element={<Destination/>}/></Routes></MemoryRouter>);expect(await screen.findByTestId("destination")).toHaveTextContent(expected);
});
