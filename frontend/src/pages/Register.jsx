import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function Register() {
    const { register } = useAuth();
    const navigate = useNavigate();
    const [form, setForm] = useState({ name: "", email: "", password: "", city: "", interests: "" });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function onSubmit(e) {
        e.preventDefault();
        setLoading(true);
        setError("");
        const res = await register({
            name: form.name,
            email: form.email,
            password: form.password,
            city: form.city,
            interests: form.interests
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
        });
        setLoading(false);
        if (res.ok) {
            toast.success("Welcome to the club!");
            navigate("/");
        } else {
            setError(res.error);
        }
    }

    return (
        <div className="max-w-md mx-auto px-6 py-16">
            <div className="bg-card rounded-3xl p-8 shadow-warm border border-border">
                <h1 className="font-heading text-3xl font-bold tracking-tight">Join the club</h1>
                <p className="text-muted-foreground mt-2">It takes 30 seconds. Bring a friend.</p>
                <form onSubmit={onSubmit} className="mt-8 space-y-4" data-testid="register-form">
                    <div>
                        <Label htmlFor="name">Full name</Label>
                        <Input id="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-xl mt-1.5" data-testid="register-name-input" />
                    </div>
                    <div>
                        <Label htmlFor="email">Email</Label>
                        <Input id="email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded-xl mt-1.5" data-testid="register-email-input" />
                    </div>
                    <div>
                        <Label htmlFor="password">Password</Label>
                        <Input id="password" type="password" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="rounded-xl mt-1.5" data-testid="register-password-input" />
                    </div>
                    <div>
                        <Label htmlFor="city">City</Label>
                        <Input id="city" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-xl mt-1.5" data-testid="register-city-input" />
                    </div>
                    <div>
                        <Label htmlFor="interests">Interests (comma separated)</Label>
                        <Input id="interests" placeholder="hiking, baking, chess" value={form.interests} onChange={(e) => setForm({ ...form, interests: e.target.value })} className="rounded-xl mt-1.5" data-testid="register-interests-input" />
                    </div>
                    {error && (
                        <div className="text-sm text-destructive bg-destructive/10 rounded-xl px-4 py-2" data-testid="register-error">
                            {error}
                        </div>
                    )}
                    <Button type="submit" className="w-full rounded-full bg-primary hover:bg-primary/90 shadow-warm py-6" disabled={loading} data-testid="register-submit-btn">
                        {loading ? "Creating account…" : "Create my account"}
                    </Button>
                </form>
                <p className="mt-6 text-sm text-center text-muted-foreground">
                    Already a member?{" "}
                    <Link to="/login" className="text-primary font-medium hover:underline">
                        Log in
                    </Link>
                </p>
            </div>
        </div>
    );
}
