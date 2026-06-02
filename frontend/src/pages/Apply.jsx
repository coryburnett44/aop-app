import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

export default function Apply() {
    const [form, setForm] = useState({
        first_name: "", last_name: "", email: "",
        password: "", confirm_password: "",
        line_name: "", intake_line: "", intake_completed_at: "",
        address: "", city: "", state: "", zip_code: "", country: "USA",
    });
    const [submitting, setSubmitting] = useState(false);
    const [done, setDone] = useState(false);

    function set(field, v) { setForm({ ...form, [field]: v }); }

    async function onSubmit(e) {
        e.preventDefault();
        if (form.password.length < 6) { toast.error("Password must be at least 6 characters"); return; }
        if (form.password !== form.confirm_password) { toast.error("Passwords don't match"); return; }
        setSubmitting(true);
        try {
            // Defensive trim to defeat Safari autofill leaks
            const { confirm_password: _, ...rest } = form;
            const payload = {
                ...rest,
                first_name: (rest.first_name || "").trim(),
                last_name: (rest.last_name || "").trim(),
                email: (rest.email || "").trim().toLowerCase(),
                password: (rest.password || "").trim(),
            };
            await api.post("/auth/apply", payload);
            setDone(true);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Could not submit application");
        }
        setSubmitting(false);
    }

    if (done) {
        return (
            <div className="max-w-md mx-auto px-6 py-16" data-testid="apply-done">
                <div className="bg-card rounded-3xl p-10 shadow-warm border border-border text-center">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold text-primary mb-3">Application received</div>
                    <h1 className="font-heading text-3xl font-bold mb-3">Thank you, {form.first_name}.</h1>
                    <p className="text-muted-foreground leading-relaxed">An Alpha Omega Phi admin will review your application. Once approved, you'll receive an email — then you can sign in with the email and password you just chose.</p>
                    <Link to="/login" className="inline-block mt-6 text-primary font-semibold hover:underline">Back to login</Link>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto px-6 py-12">
            <div className="bg-card rounded-3xl p-8 sm:p-10 shadow-warm border border-border">
                <div className="text-xs uppercase tracking-[0.25em] font-bold text-primary">Apply for access</div>
                <h1 className="font-heading text-3xl sm:text-4xl font-bold mt-1">Membership application</h1>
                <p className="text-sm text-muted-foreground mt-2">Tell us about your intake and choose a password. An admin reviews each application personally — once approved, you can sign in with the email + password you set below.</p>
                <form onSubmit={onSubmit} className="mt-8 space-y-4" data-testid="apply-form">
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div><Label>First name *</Label><Input required value={form.first_name} onChange={(e) => set("first_name", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-first-name" /></div>
                        <div><Label>Last name *</Label><Input required value={form.last_name} onChange={(e) => set("last_name", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-last-name" /></div>
                    </div>
                    <div>
                        <Label>Email *</Label>
                        <Input required type="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck="false" inputMode="email" value={form.email} onChange={(e) => set("email", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-email" />
                    </div>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div><Label>Choose a password *</Label><Input required type="password" minLength={6} value={form.password} onChange={(e) => set("password", e.target.value)} className="rounded-xl mt-1.5" placeholder="At least 6 characters" data-testid="apply-password" /></div>
                        <div><Label>Confirm password *</Label><Input required type="password" minLength={6} value={form.confirm_password} onChange={(e) => set("confirm_password", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-confirm-password" /></div>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div><Label>Line name</Label><Input value={form.line_name} onChange={(e) => set("line_name", e.target.value)} className="rounded-xl mt-1.5" placeholder="ex. Thunder" data-testid="apply-line-name" /></div>
                        <div><Label>Intake line</Label><Input value={form.intake_line} onChange={(e) => set("intake_line", e.target.value)} className="rounded-xl mt-1.5" placeholder="ex. Spring '24 — A1" data-testid="apply-intake-line" /></div>
                    </div>
                    <div>
                        <Label>Intake completion date (Month &amp; Year) *</Label>
                        <Input required type="month" value={form.intake_completed_at} onChange={(e) => set("intake_completed_at", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-intake-completed-at" />
                    </div>
                    <div className="border-t border-border/40 pt-4">
                        <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-3">Mailing address</div>
                        <div className="space-y-4">
                            <div><Label>Street address *</Label><Input required value={form.address} onChange={(e) => set("address", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-address" /></div>
                            <div className="grid sm:grid-cols-3 gap-4">
                                <div><Label>City *</Label><Input required value={form.city} onChange={(e) => set("city", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-city" /></div>
                                <div><Label>State *</Label><Input required value={form.state} onChange={(e) => set("state", e.target.value)} className="rounded-xl mt-1.5" placeholder="TX" data-testid="apply-state" /></div>
                                <div><Label>Zip code *</Label><Input required value={form.zip_code} onChange={(e) => set("zip_code", e.target.value)} className="rounded-xl mt-1.5" placeholder="77001" data-testid="apply-zip" /></div>
                            </div>
                            <div><Label>Country *</Label><Input required value={form.country} onChange={(e) => set("country", e.target.value)} className="rounded-xl mt-1.5" data-testid="apply-country" /></div>
                        </div>
                    </div>
                    <Button type="submit" disabled={submitting} className="w-full rounded-full bg-primary hover:bg-primary/90 shadow-warm py-6" data-testid="apply-submit-btn">
                        {submitting ? "Submitting…" : "Submit application"}
                    </Button>
                    <p className="text-xs text-center text-muted-foreground">
                        Already approved? <Link to="/login" className="text-primary font-semibold hover:underline">Log in</Link>
                    </p>
                </form>
            </div>
        </div>
    );
}
