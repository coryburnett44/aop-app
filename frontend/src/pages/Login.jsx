import { useState } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const nextPath = params.get("next") || "/";
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function onSubmit(e) {
        e.preventDefault();
        setLoading(true);
        setError("");
        // Trim whitespace to defend against iOS/Safari autofill leaking a
        // leading/trailing space — common cause of "credentials rejected".
        const cleanEmail = (email || "").trim().toLowerCase();
        const cleanPassword = (password || "").trim();
        const res = await login(cleanEmail, cleanPassword);
        setLoading(false);
        if (res.ok) {
            toast.success("Welcome back!");
            navigate(nextPath || "/");
        } else {
            setError(res.error);
        }
    }

    return (
        <div className="max-w-md mx-auto px-6 py-16">
            <div className="bg-card rounded-3xl p-8 shadow-warm border border-border">
                <h1 className="font-heading text-3xl font-bold tracking-tight">Welcome back</h1>
                <p className="text-muted-foreground mt-2">Log in to manage your membership.</p>
                <form onSubmit={onSubmit} className="mt-8 space-y-4" data-testid="login-form">
                    <div>
                        <Label htmlFor="email">Email or username</Label>
                        <Input
                            id="email"
                            type="text"
                            autoComplete="username"
                            autoCapitalize="none"
                            autoCorrect="off"
                            spellCheck="false"
                            inputMode="text"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="you@example.com or your username"
                            className="rounded-xl mt-1.5"
                            data-testid="login-email-input"
                        />
                    </div>
                    <div>
                        <Label htmlFor="password">Password</Label>
                        <Input
                            id="password"
                            type="password"
                            autoComplete="current-password"
                            required
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="rounded-xl mt-1.5"
                            data-testid="login-password-input"
                        />
                        <div className="text-right mt-1.5">
                            <Link to="/forgot-password" className="text-xs text-primary hover:underline" data-testid="login-forgot-link">
                                Forgot password?
                            </Link>
                        </div>
                    </div>
                    {error && (
                        <div className="text-sm text-destructive bg-destructive/10 rounded-xl px-4 py-2" data-testid="login-error">
                            {error}
                        </div>
                    )}
                    <Button
                        type="submit"
                        className="w-full rounded-full bg-primary hover:bg-primary/90 shadow-warm py-6"
                        disabled={loading}
                        data-testid="login-submit-btn"
                    >
                        {loading ? "Logging in…" : "Log in"}
                    </Button>
                </form>
                <p className="mt-6 text-sm text-center text-muted-foreground">
                    Newly intaken? <Link to="/apply" className="text-primary font-semibold hover:underline" data-testid="login-apply-link">Apply for access</Link>
                </p>
            </div>
        </div>
    );
}
