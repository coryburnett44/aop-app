import { useEffect, useState } from "react";
import { PayPalScriptProvider, PayPalButtons } from "@paypal/react-paypal-js";
import { api } from "../lib/api";
import { toast } from "sonner";

let _config = null;
async function loadConfig() {
    if (_config) return _config;
    const { data } = await api.get("/payments/paypal/client-id");
    _config = data;
    return data;
}

/**
 * <PayPalCheckout
 *   purpose="donation" | "gear" | "event" | "dues"
 *   amount={25}
 *   cause_id / gear_id / event_id
 *   quantity={1}
 *   anonymous={false}
 *   note=""
 *   disabled
 *   onComplete={(tx) => ...}
 * />
 */
export default function PayPalCheckout({ purpose, amount, cause_id, gear_id, event_id, quantity = 1, anonymous = false, note = "", disabled = false, onComplete }) {
    const [cfg, setCfg] = useState(null);
    useEffect(() => { loadConfig().then(setCfg).catch(() => setCfg({ enabled: false })); }, []);

    if (!cfg) return <div className="text-xs text-slate-500 py-2 text-center">Loading checkout…</div>;
    if (!cfg.enabled) return <div className="text-xs text-slate-500 py-2 text-center">PayPal not configured.</div>;
    if (!amount || amount <= 0) return <div className="text-xs text-slate-500 py-2 text-center">Enter an amount to continue.</div>;

    return (
        <PayPalScriptProvider options={{ clientId: cfg.client_id, currency: "USD", intent: "capture" }}>
            <div data-testid={`paypal-${purpose}-${cause_id || gear_id || event_id || "x"}`}>
                <PayPalButtons
                    disabled={disabled}
                    style={{ layout: "vertical", shape: "pill", color: "gold", label: "paypal" }}
                    forceReRender={[amount, purpose, cause_id, gear_id, event_id, quantity, anonymous]}
                    createOrder={async () => {
                        try {
                            const { data } = await api.post("/payments/paypal/orders", {
                                purpose, amount: Number(amount), cause_id, gear_id, event_id,
                                quantity, anonymous, note,
                            });
                            return data.order_id;
                        } catch (e) {
                            toast.error(e.response?.data?.detail || "Couldn't start checkout");
                            throw e;
                        }
                    }}
                    onApprove={async (data) => {
                        try {
                            const { data: cap } = await api.post(`/payments/paypal/orders/${data.orderID}/capture`);
                            if (cap.status === "completed") {
                                toast.success("Payment complete 🎉");
                            } else {
                                toast.info(`Status: ${cap.paypal_status || cap.status}`);
                            }
                            onComplete?.(cap);
                        } catch (e) {
                            toast.error(e.response?.data?.detail || "Capture failed");
                        }
                    }}
                    onError={(err) => {
                        console.error(err);
                        toast.error("PayPal error — please try again");
                    }}
                />
            </div>
        </PayPalScriptProvider>
    );
}
