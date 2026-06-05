import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { ArrowLeft, AlertCircle } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";

export default function SetPassword() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const token = params.get("token") || "";
    const [pw1, setPw1] = useState("");
    const [pw2, setPw2] = useState("");
    const [busy, setBusy] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        if (pw1.length < 6) { toast.error("Password must be at least 6 characters"); return; }
        if (pw1 !== pw2) { toast.error("Passwords don't match"); return; }
        setBusy(true);
        try {
            await api.post("/auth/set-password", { token, new_password: pw1 });
            toast.success("Password set — please sign in.");
            navigate("/login");
        } catch (err) {
            toast.error(err.response?.data?.detail || "Could not set password — your link may have expired. Ask an admin to resend.");
        }
        setBusy(false);
    }

    return (
        <div className="min-h-screen bg-slate-50 grid place-items-center px-6 py-12">
            <div className="w-full max-w-md bg-white rounded-3xl shadow-warm border border-slate-200 p-8">
                <Link to="/login" className="text-sm text-slate-500 hover:text-primary inline-flex items-center gap-1 mb-4" data-testid="back-to-login">
                    <ArrowLeft className="h-4 w-4" /> Back to login
                </Link>
                <div className="text-xs uppercase tracking-[0.3em] font-bold mb-2" style={{ color: RED }}>Welcome to Alpha Omega Phi</div>
                <h1 className="font-heading text-3xl font-black tracking-tighter" style={{ color: NAVY }}>Set your password</h1>
                <p className="text-sm text-slate-500 mt-2">Choose a password you'll use to sign in to the member portal.</p>
                {!token ? (
                    <div className="mt-4 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2" data-testid="setpw-no-token">
                        <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                        <span>This page needs a valid set-password token. Please use the link we emailed you.</span>
                    </div>
                ) : (
                    <form onSubmit={onSubmit} className="mt-5 space-y-4">
                        <div>
                            <Label htmlFor="pw1">New password</Label>
                            <Input
                                id="pw1"
                                type="password"
                                autoComplete="new-password"
                                required
                                minLength={6}
                                value={pw1}
                                onChange={(e) => setPw1(e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid="setpw-pw1-input"
                            />
                        </div>
                        <div>
                            <Label htmlFor="pw2">Confirm new password</Label>
                            <Input
                                id="pw2"
                                type="password"
                                autoComplete="new-password"
                                required
                                minLength={6}
                                value={pw2}
                                onChange={(e) => setPw2(e.target.value)}
                                className="rounded-xl mt-1.5"
                                data-testid="setpw-pw2-input"
                            />
                        </div>
                        <Button
                            type="submit"
                            disabled={busy || !pw1 || !pw2}
                            className="w-full rounded-full bg-primary hover:bg-primary/90 text-white shadow-warm py-6"
                            data-testid="setpw-submit-btn"
                        >
                            {busy ? "Setting password…" : "Set password and continue"}
                        </Button>
                    </form>
                )}
            </div>
        </div>
    );
}
