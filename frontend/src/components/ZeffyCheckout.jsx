import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { ExternalLink, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Zeffy dues checkout. Member clicks "Pay with Zeffy" → opens the Zeffy hosted
 * ticketing page in a new tab. When they come back, they click "I completed
 * payment" → enters their Zeffy confirmation number → creates a PENDING
 * transaction that an admin must approve. Once approved, membership extends 365 days.
 *
 * Mirrors the PayPal flow except the verification step is manual (Zeffy free tier
 * has no webhook/API).
 */
export default function ZeffyCheckout({ onComplete }) {
    const [cfg, setCfg] = useState(null);
    const [opened, setOpened] = useState(false);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [reference, setReference] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get("/payments/zeffy/config").then(({ data }) => setCfg(data)).catch(() => setCfg({ enabled: false }));
    }, []);

    if (!cfg) return <div className="text-xs text-slate-500 py-2 text-center">Loading Zeffy…</div>;
    if (!cfg.enabled) return null;

    function openZeffy() {
        // Always show the "I completed payment" confirmation UI as soon as the
        // user clicks the button — even if the popup is blocked, they may have
        // completed payment via a fallback redirect or another tab.
        setOpened(true);
        // Use noopener via rel attribute pattern (target=_blank already isolates
        // the opener on all modern browsers). Passing 'noopener' to window.open
        // forces it to return null, breaking popup-blocked detection.
        try {
            window.open(cfg.url, "_blank");
        } catch {
            // Hard popup-block fallback: copy URL to clipboard + show toast
            navigator.clipboard?.writeText(cfg.url).catch(() => {});
            toast.info("Popup blocked — Zeffy URL copied to clipboard. Open it in a new tab.");
        }
    }

    async function submitConfirm() {
        if (reference.trim().length < 3) {
            toast.error("Please enter your Zeffy receipt # or confirmation email");
            return;
        }
        setBusy(true);
        try {
            const { data } = await api.post("/payments/zeffy/confirm", {
                confirmation: reference.trim(),
                amount: cfg.default_amount || 105,
            });
            toast.success("Submitted for admin verification 🎉");
            setConfirmOpen(false);
            setReference("");
            setOpened(false);
            onComplete?.(data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not record payment");
        }
        setBusy(false);
    }

    return (
        <div data-testid="zeffy-checkout">
            <button
                type="button"
                onClick={openZeffy}
                className="w-full rounded-full px-5 py-3 font-bold text-white shadow-warm transition-all hover:-translate-y-0.5 flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg, #ff5757 0%, #ff7a3d 100%)" }}
                data-testid="zeffy-open-btn"
            >
                <ExternalLink className="h-4 w-4" />
                Pay dues with Zeffy
            </button>

            {opened && (
                <button
                    type="button"
                    onClick={() => setConfirmOpen(true)}
                    className="w-full mt-2 rounded-full px-4 py-2.5 text-sm font-semibold border-2 border-emerald-500 text-emerald-700 hover:bg-emerald-50 transition-colors flex items-center justify-center gap-2"
                    data-testid="zeffy-confirm-btn"
                >
                    <CheckCircle2 className="h-4 w-4" />
                    I completed my Zeffy payment
                </button>
            )}

            <p className="text-[11px] text-muted-foreground mt-2 leading-snug">
                Zeffy opens in a new tab. After completing payment there, return here and confirm with your receipt # so an admin can verify and apply your dues.
            </p>

            <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <DialogContent
                    className="max-w-md z-[9999]"
                    overlayClassName="z-[9998]"
                    data-testid="zeffy-confirm-dialog"
                >
                    <DialogHeader>
                        <DialogTitle className="font-heading text-xl">Confirm Zeffy dues payment</DialogTitle>
                        <DialogDescription>
                            Enter the Zeffy receipt number or confirmation email you received. An admin will verify and your annual dues will be marked paid (membership extended 365 days).
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 mt-2">
                        <div>
                            <Label htmlFor="zeffy-ref">Receipt # or confirmation email</Label>
                            <Input
                                id="zeffy-ref"
                                value={reference}
                                onChange={(e) => setReference(e.target.value)}
                                placeholder="e.g. ZF-12345 or you@example.com"
                                className="rounded-xl mt-1.5"
                                data-testid="zeffy-ref-input"
                                autoFocus
                            />
                        </div>
                        <div className="text-xs text-muted-foreground bg-amber-50 border border-amber-200 rounded-xl p-3">
                            <strong>Note:</strong> Your dues transaction will be marked <em>pending</em> until an admin verifies your Zeffy receipt.
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmOpen(false)} className="rounded-full">Cancel</Button>
                        <Button onClick={submitConfirm} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="zeffy-submit-btn">
                            {busy ? "Submitting…" : "Submit confirmation"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
