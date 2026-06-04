import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "./ui/select";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { ExternalLink, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Paid-event checkout flow.
 *
 *   1. Member clicks "Pay $X with Zeffy" → opens Zeffy in a new tab.
 *   2. After paying, member returns and clicks "I completed payment".
 *   3. Member submits their receipt # (with live format hint) + picks ticket type.
 *   4. Backend creates a pending event_ticket transaction; admin approves to materialize the RSVP.
 *      If member.trust_zeffy=true AND receipt matches a known Zeffy format,
 *      auto-approval kicks in and the ticket email is fired immediately.
 */
export default function PaidEventCheckout({ event, onPaid }) {
    const [opened, setOpened] = useState(false);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [reference, setReference] = useState("");
    const [ticketType, setTicketType] = useState("general");
    const [busy, setBusy] = useState(false);
    const [validation, setValidation] = useState(null);

    const enabled = event.allows_ticket_types && (event.enabled_ticket_types || []).length > 0
        ? event.enabled_ticket_types
        : null;

    useEffect(() => {
        if (enabled && !enabled.includes(ticketType)) setTicketType(enabled[0]);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [event.id]);

    // Live debounce-validate the receipt # so the member sees green ✓ before submit.
    useEffect(() => {
        const v = reference.trim();
        if (v.length < 4) { setValidation(null); return; }
        const t = setTimeout(() => {
            api.get(`/payments/zeffy/validate?value=${encodeURIComponent(v)}`)
                .then(({ data }) => setValidation(data))
                .catch(() => setValidation(null));
        }, 300);
        return () => clearTimeout(t);
    }, [reference]);

    function openZeffy() {
        setOpened(true);
        try {
            window.open(event.payment_url, "_blank");
        } catch {
            navigator.clipboard?.writeText(event.payment_url).catch(() => {});
            toast.info("Popup blocked — payment URL copied to clipboard");
        }
    }

    async function submit() {
        if (reference.trim().length < 3) { toast.error("Enter your Zeffy receipt # or confirmation email"); return; }
        setBusy(true);
        try {
            const { data } = await api.post(`/events/${event.id}/payment/confirm`, {
                confirmation: reference.trim(),
                ticket_type: ticketType,
                guests: [],
            });
            toast.success(data.auto_approved ? "🎉 Approved! Ticket emailed." : "Submitted for admin verification 🎉");
            setConfirmOpen(false);
            setReference("");
            setOpened(false);
            onPaid?.(data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Could not record payment");
        }
        setBusy(false);
    }

    return (
        <div data-testid="paid-event-checkout">
            <button
                type="button"
                onClick={openZeffy}
                className="w-full rounded-full px-5 py-3 font-bold text-white shadow-warm transition-all hover:-translate-y-0.5 flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg, #10b981 0%, #059669 100%)" }}
                data-testid="paid-event-open-btn"
            >
                <ExternalLink className="h-4 w-4" />
                Pay ${event.payment_amount.toFixed(2)} with Zeffy
            </button>

            {opened && (
                <button
                    type="button"
                    onClick={() => setConfirmOpen(true)}
                    className="w-full mt-2 rounded-full px-4 py-2.5 text-sm font-semibold border-2 border-emerald-500 text-emerald-700 hover:bg-emerald-50 transition-colors flex items-center justify-center gap-2"
                    data-testid="paid-event-confirm-btn"
                >
                    <CheckCircle2 className="h-4 w-4" />
                    I completed my Zeffy payment
                </button>
            )}

            <p className="text-[11px] text-muted-foreground mt-2 leading-snug">
                Zeffy opens in a new tab. After paying, return here and submit your receipt # — admin will verify and email your ticket.
            </p>

            <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <DialogContent className="max-w-md z-[9999]" overlayClassName="z-[9998]" data-testid="paid-event-confirm-dialog">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-xl">Confirm payment for {event.title}</DialogTitle>
                        <DialogDescription>
                            Enter the Zeffy receipt # or confirmation email you received. Your RSVP and ticket will be issued once admin verifies your receipt (or instantly if you're a trusted member).
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 mt-2">
                        {enabled && (
                            <div>
                                <Label className="text-xs">Ticket type</Label>
                                <Select value={ticketType} onValueChange={setTicketType}>
                                    <SelectTrigger className="rounded-xl mt-1.5" data-testid="paid-event-ticket-type"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {enabled.map((t) => <SelectItem key={t} value={t} className="capitalize">{t.replace("_", " ")}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                        <div>
                            <Label htmlFor="pe-ref">Receipt # or confirmation email</Label>
                            <Input
                                id="pe-ref"
                                value={reference}
                                onChange={(e) => setReference(e.target.value)}
                                placeholder="e.g. RCT-0401-5406 or you@example.com"
                                className="rounded-xl mt-1.5"
                                data-testid="paid-event-ref-input"
                                autoFocus
                            />
                            {validation && reference.trim().length >= 4 && (
                                <div
                                    className={`mt-2 text-xs rounded-lg px-3 py-2 flex items-center gap-2 ${
                                        validation.valid
                                            ? "bg-emerald-50 border border-emerald-200 text-emerald-800"
                                            : "bg-slate-50 border border-slate-200 text-slate-600"
                                    }`}
                                    data-testid="paid-event-format-hint"
                                >
                                    {validation.valid ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" /> : <span className="text-slate-400">•</span>}
                                    <span>
                                        {validation.label}
                                        {validation.will_auto_approve && (
                                            <strong className="ml-1 text-emerald-700">— eligible for instant ticket</strong>
                                        )}
                                    </span>
                                </div>
                            )}
                        </div>
                        <div className="text-xs text-muted-foreground bg-amber-50 border border-amber-200 rounded-xl p-3">
                            <strong>Note:</strong> RSVP is <em>pending</em> until an admin verifies your Zeffy receipt. You'll get the ticket email once approved.
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmOpen(false)} className="rounded-full">Cancel</Button>
                        <Button onClick={submit} disabled={busy} className="rounded-full bg-primary hover:bg-primary/90" data-testid="paid-event-submit-btn">
                            {busy ? "Submitting…" : "Submit confirmation"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
