import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { NativeConnectionsPanel } from "./NativeConnectionsPanel";
import { ProviderConnectionsPanel } from "./ProviderConnectionsPanel";
import { SelfHostedServicesPanel } from "./SelfHostedServicesPanel";
import { AirtelConnectionsPanel } from "./AirtelConnectionsPanel";

export function ProviderConnectionsScreen() {
  const [adapter, setAdapter] = useState("native");
  return <div className="space-y-5"><div aria-label="Telephony connection types" className="flex flex-wrap gap-2">
    <Button variant={adapter === "native" ? "primary" : "secondary"} aria-pressed={adapter === "native"} onClick={() => setAdapter("native")}>Native PBX &amp; telephone numbers</Button>
    <Button variant={adapter === "smartflo" ? "primary" : "secondary"} aria-pressed={adapter === "smartflo"} onClick={() => setAdapter("smartflo")}>Smartflo (optional)</Button>
    <Button variant={adapter === "airtel" ? "primary" : "secondary"} aria-pressed={adapter === "airtel"} onClick={() => setAdapter("airtel")}>Airtel IQ VoiceBOT</Button>
  </div>{adapter === "native" ? <><SelfHostedServicesPanel /><NativeConnectionsPanel /></> : adapter === "airtel" ? <AirtelConnectionsPanel /> : <ProviderConnectionsPanel />}</div>;
}
