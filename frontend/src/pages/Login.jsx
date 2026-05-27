import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function onSubmit(e) {
        e.preventDefault();
        setLoading(true);
        setError("");
        const res = await login(email, password);
        setLoading(false);
        if (res.ok) {
            toast.success("Welcome back!");
            navigate("/");
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
                        <Label htmlFor="email">Email</Label>
                        <Input
                            id="email"
                            type="email"
                            autoComplete="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
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
                    Membership is invitation-only. Contact your chapter admin if you need access.
                </p>
            </div>
        </div>
    );
}
