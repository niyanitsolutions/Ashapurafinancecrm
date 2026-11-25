import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { QuickSearch } from "./QuickSearch";
const lookup=vi.hoisted(()=>vi.fn());
vi.mock("@/features/dashboard/api",()=>({search:lookup}));
afterEach(()=>{vi.useRealTimers();lookup.mockReset();});
it("debounces queries and opens the selected result with the keyboard",async()=>{
 vi.useFakeTimers();lookup.mockResolvedValue({results:[{type:"application",id:"app1",label:"AFS-APP-1",subtitle:"Current customer",route:"/applications/app1"}]});
 render(<MemoryRouter><Routes><Route path="/" element={<QuickSearch/>}/><Route path="/applications/app1" element={<p>Correct application</p>}/></Routes></MemoryRouter>);
 const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"AFS"}});fireEvent.change(input,{target:{value:"AFS-APP-1"}});
 expect(lookup).not.toHaveBeenCalled();await act(async()=>{await vi.advanceTimersByTimeAsync(251);});expect(lookup).toHaveBeenCalledTimes(1);expect(lookup).toHaveBeenCalledWith("AFS-APP-1",1);
 fireEvent.keyDown(input,{key:"ArrowDown"});fireEvent.keyDown(input,{key:"Enter"});expect(screen.getByText("Correct application")).toBeInTheDocument();
});
it("does not reveal results for a query cleared while its request is pending",async()=>{
 vi.useFakeTimers();let resolve!:(value:unknown)=>void;lookup.mockImplementation(()=>new Promise(r=>{resolve=r;}));render(<MemoryRouter><QuickSearch/></MemoryRouter>);
 const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"customer"}});await act(async()=>{await vi.advanceTimersByTimeAsync(251);});fireEvent.change(input,{target:{value:""}});
 await act(async()=>{resolve({results:[{type:"customer",id:"c1",label:"Stale identity",route:"/customers/c1"}]});});expect(screen.queryByText("Stale identity")).not.toBeInTheDocument();
});
