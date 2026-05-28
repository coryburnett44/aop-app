import { useState, useEffect } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function SetPassword() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const token = params.get("token") || "";
    const [pwd, setPwd] = useState("");
    const [confirm, setConfirm] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => { if (!token) setError("Missing token — please use the link from your email."); }, [token]);

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        if (pwd.length < 6) { setError("Password must be at least 6 characters."); return; }
        if (pwd !== confirm) { setError("Passwords don't match."); return; }
        setBusy(true);
        try {
            const { data } = await api.post("/auth/set-password", { token, new_password: pwd });
            toast.success("Password set — please log in.");
            navigate(`/login?email=${encodeURIComponent(data.email || "")}`);
        } catch (e) {
            setError(e.response?.data?.detail || "Could not set password");
        }
        setBusy(false);
    }

    return (
        <div className="max-w-md mx-auto px-6 py-16">
            <div className="bg-card rounded-3xl p-8 shadow-warm border border-border">
                <div className="text-xs uppercase tracking-[0.25em] font-bold text-primary mb-2">Set your password</div>
                <h1 className="font-heading text-3xl font-bold tracking-tight">Welcome to Alpha Omega Phi</h1>
                <p className="text-muted-foreground mt-2">Choose a password to finish activating your account.</p>
                <form onSubmit={onSubmit} className="mt-8 space-y-4" data-testid="set-password-form">
                    <div>
                        <Label>New password</Label>
                        <Input required type="password" minLength={6} value={pwd} onChange={(e) => setPwd(e.target.value)} className="rounded-xl mt-1.5" data-testid="set-password-input" />
                    </div>
                    <div>
                        <Label>Confirm password</Label>
                        <Input required type="password" minLength={6} value={confirm} onChange={(e) => setConfirm(e.target.value)} className="rounded-xl mt-1.5" data-testid="set-password-confirm" />
                    </div>
                    {error && (
                        <div className="text-sm text-destructive bg-destructive/10 rounded-xl px-4 py-2" data-testid="set-password-error">{error}</div>
                    )}
                    <Button type="submit" disabled={busy || !token} className="w-full rounded-full bg-primary hover:bg-primary/90 shadow-warm py-6" data-testid="set-password-submit-btn">
                        {busy ? "Saving…" : "Set password & continue"}
                    </Button>
                </form>
                <p className="mt-6 text-sm text-center text-muted-foreground">
                    Already set up? <Link to="/login" className="text-primary font-semibold hover:underline">Log in</Link>
                </p>
            </div>
        </div>
    );
}
