import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { toast } from "sonner";

/**
 * Public landing page hit after a member clicks the Unsubscribe link in an
 * email blast or dues reminder. No auth required — we identify the recipient
 * by the HMAC token already attached to the URL by the backend redirect.
 *
 * UX:
 *   • Confirms the opt-out and shows the email it was applied to.
 *   • Offers a single "Re-subscribe" button in case the click was accidental.
 *   • Shows an error state when the token is missing or tampered with.
 */
export default function Unsubscribed() {
    const [params] = useSearchParams();
    const token = params.get("token") || "";
    const initialStatus = params.get("status") || "ok";
    const [state, setState] = useState({ loading: true, email: "", opted_out: false, error: "" });
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!token) { setState({ loading: false, email: "", opted_out: false, error: "Missing token" }); return; }
        if (initialStatus === "invalid") { setState({ loading: false, email: "", opted_out: false, error: "This unsubscribe link is invalid or expired." }); return; }
        api.get(`/email/unsubscribe-status?token=${encodeURIComponent(token)}`)
            .then(({ data }) => setState({ loading: false, email: data.email || "", opted_out: !!data.opted_out, error: "" }))
            .catch((err) => setState({ loading: false, email: "", opted_out: false, error: err.response?.data?.detail || "Could not load your subscription status." }));
    }, [token, initialStatus]);

    async function resubscribe() {
        setBusy(true);
        try {
            await api.post(`/email/resubscribe?token=${encodeURIComponent(token)}`);
            setState((s) => ({ ...s, opted_out: false }));
            toast.success("You're back on the list. Welcome back!");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Could not re-subscribe.");
        }
        setBusy(false);
    }

    return (
        <div className="min-h-[70vh] flex items-center justify-center px-6 py-16">
            <div className="w-full max-w-md bg-card rounded-3xl border border-border shadow-warm p-8 text-center" data-testid="unsubscribed-page">
                {state.loading ? (
                    <div className="text-muted-foreground text-sm">Loading…</div>
                ) : state.error ? (
                    <>
                        <div className="text-5xl mb-3">⚠️</div>
                        <h1 className="font-heading text-2xl font-bold mb-2">Link not valid</h1>
                        <p className="text-sm text-muted-foreground" data-testid="unsubscribed-error">{state.error}</p>
                        <p className="text-xs text-muted-foreground mt-4">If you wanted to unsubscribe, reply to any Alpha Omega Phi email and we'll handle it manually.</p>
                    </>
                ) : state.opted_out ? (
                    <>
                        <div className="text-5xl mb-3">✅</div>
                        <h1 className="font-heading text-2xl font-bold mb-2" data-testid="unsubscribed-title">You're unsubscribed</h1>
                        <p className="text-sm text-muted-foreground">
                            We won't send marketing or reminder emails to{" "}
                            <strong className="text-foreground" data-testid="unsubscribed-email">{state.email}</strong> anymore.
                        </p>
                        <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                            Account-critical emails (password resets, your own RSVP receipts, security alerts) will still be delivered — those aren't marketing.
                        </p>
                        <div className="mt-6">
                            <Button
                                onClick={resubscribe}
                                disabled={busy}
                                className="rounded-full bg-primary hover:bg-primary/90"
                                data-testid="resubscribe-btn"
                            >
                                {busy ? "Re-subscribing…" : "I clicked by mistake — re-subscribe"}
                            </Button>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="text-5xl mb-3">📬</div>
                        <h1 className="font-heading text-2xl font-bold mb-2">You're subscribed</h1>
                        <p className="text-sm text-muted-foreground">
                            <strong className="text-foreground">{state.email}</strong> is on the list and receiving Alpha Omega Phi updates.
                        </p>
                    </>
                )}
            </div>
        </div>
    );
}
