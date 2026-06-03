import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { Mail, ArrowLeft, CheckCircle2 } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [busy, setBusy] = useState(false);
    const [sent, setSent] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        setBusy(true);
        try {
            await api.post("/auth/forgot-password", { email: email.trim().toLowerCase() });
            setSent(true);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Couldn't send the reset link");
        }
        setBusy(false);
    }

    return (
        <div className="min-h-screen bg-slate-50 grid place-items-center px-6 py-12">
            <div className="w-full max-w-md bg-white rounded-3xl shadow-warm border border-slate-200 p-8">
                <Link to="/login" className="text-sm text-slate-500 hover:text-primary inline-flex items-center gap-1 mb-4" data-testid="back-to-login">
                    <ArrowLeft className="h-4 w-4" /> Back to login
                </Link>
                {!sent ? (
                    <>
                        <div className="text-xs uppercase tracking-[0.3em] font-bold mb-2" style={{ color: RED }}>Password recovery</div>
                        <h1 className="font-heading text-3xl font-black tracking-tighter" style={{ color: NAVY }}>Forgot your password?</h1>
                        <p className="text-sm text-slate-600 mt-2">Enter the email you used to register and we'll send you a reset link. It's valid for one hour.</p>
                        <form onSubmit={onSubmit} className="mt-6 space-y-4">
                            <div>
                                <Label htmlFor="email">Email</Label>
                                <Input
                                    id="email"
                                    type="email"
                                    autoComplete="email"
                                    autoCapitalize="none"
                                    autoCorrect="off"
                                    spellCheck="false"
                                    inputMode="email"
                                    required
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="rounded-xl mt-1.5"
                                    data-testid="forgot-email-input"
                                />
                            </div>
                            <Button
                                type="submit"
                                disabled={busy || !email.trim()}
                                className="w-full rounded-full bg-primary hover:bg-primary/90 text-white shadow-warm py-6"
                                data-testid="forgot-submit-btn"
                            >
                                {busy ? "Sending…" : "Send me a reset link"}
                            </Button>
                        </form>
                    </>
                ) : (
                    <div className="text-center" data-testid="forgot-sent-state">
                        <CheckCircle2 className="h-14 w-14 text-green-500 mx-auto" />
                        <h2 className="font-heading text-2xl font-black mt-3" style={{ color: NAVY }}>Check your inbox</h2>
                        <p className="text-sm text-slate-600 mt-2">
                            If <strong>{email}</strong> is registered with us, we sent a reset link to that address. It's good for 1 hour and only works once.
                        </p>
                        <div className="mt-4 bg-slate-50 rounded-2xl p-4 text-xs text-slate-500 inline-flex items-start gap-2 max-w-sm mx-auto text-left">
                            <Mail className="h-4 w-4 mt-0.5 flex-shrink-0" />
                            <span>Don't see it after a minute? Check your spam folder, or send another link by going back.</span>
                        </div>
                        <Button onClick={() => setSent(false)} variant="outline" className="rounded-full mt-5" data-testid="forgot-send-again-btn">
                            Send another link
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}
