import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { toast } from "sonner";
import { MessageSquare, ShieldAlert, CheckCircle2 } from "lucide-react";

/**
 * Global SMS kill-switch panel for Admin → Settings.
 *
 * Lets an admin flip all outbound SMS on/off in one click — useful during
 * a Brevo credit outage so the chat video-meeting fan-out and the dues
 * reminder companion texts don't spam logs with failures.
 *
 * Reads / writes the `sms_config` doc in db.app_settings via:
 *   GET /api/admin/sms-config
 *   PUT /api/admin/sms-config { enabled: bool }
 */
export default function SmsSettingsAdmin() {
    const [cfg, setCfg] = useState(null);
    const [busy, setBusy] = useState(false);

    async function load() {
        try {
            const { data } = await api.get("/admin/sms-config");
            setCfg(data);
        } catch (e) {
            // Non-admins won't see the tab this lives in, so a load failure
            // is a real error — surface it once.
            const msg = e.response?.data?.detail || "Failed to load SMS config";
            toast.error(typeof msg === "string" ? msg : "Failed to load SMS config");
        }
    }
    useEffect(() => { load(); }, []);

    async function toggle() {
        if (!cfg) return;
        const next = !cfg.enabled;
        if (!next && !confirm("Disable ALL outbound SMS?\n\nThis stops chat video-meeting texts and dues-reminder texts across the whole app until you re-enable it. Emails are unaffected.")) {
            return;
        }
        setBusy(true);
        try {
            const { data } = await api.put("/admin/sms-config", { enabled: next });
            setCfg((c) => ({ ...c, enabled: !!data.enabled }));
            toast.success(next ? "Outbound SMS enabled" : "Outbound SMS disabled globally");
            // Re-fetch to pick up updated_at / updated_by.
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to update SMS config");
        }
        setBusy(false);
    }

    if (!cfg) return null;

    const on = cfg.enabled;
    const hasProvider = cfg.brevo_configured || cfg.twilio_configured;

    return (
        <div className="bg-card border border-border rounded-2xl p-6" data-testid="sms-settings-admin">
            <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                    <h3 className="font-heading text-xl font-bold flex items-center gap-2">
                        <MessageSquare className="h-5 w-5" />Outbound SMS
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1 max-w-xl">
                        Global kill-switch for every SMS the app sends — video-meeting fan-out and dues-reminder companion texts. Flip this off during a Brevo credit outage; emails are unaffected.
                    </p>
                </div>
                <div
                    className={`shrink-0 flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${on ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-slate-100 text-slate-500 border border-slate-200"}`}
                    data-testid="sms-status-badge"
                >
                    {on ? <CheckCircle2 className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
                    {on ? "Enabled" : "Disabled"}
                </div>
            </div>

            <div className="grid sm:grid-cols-3 gap-3 mb-4">
                <MetaTile label="Active provider" value={cfg.provider || "none"} />
                <MetaTile label="Brevo configured" value={cfg.brevo_configured ? "Yes" : "No"} muted={!cfg.brevo_configured} />
                <MetaTile label="Twilio configured" value={cfg.twilio_configured ? "Yes" : "No"} muted={!cfg.twilio_configured} />
            </div>

            {!hasProvider && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-800 text-xs p-3 mb-4" data-testid="sms-no-provider-warning">
                    No SMS provider is currently configured (no Brevo or Twilio credentials in the environment). This toggle will have no effect until one is set.
                </div>
            )}

            <div className="flex items-center gap-3">
                <Button
                    onClick={toggle}
                    disabled={busy}
                    className={`rounded-full ${on ? "bg-slate-800 hover:bg-slate-900 text-white" : "bg-primary hover:bg-primary/90"}`}
                    data-testid="sms-toggle-btn"
                >
                    {busy ? "Saving…" : on ? "Disable outbound SMS" : "Enable outbound SMS"}
                </Button>
                {cfg.updated_at && (
                    <span className="text-xs text-muted-foreground" data-testid="sms-updated-meta">
                        Last changed {new Date(cfg.updated_at).toLocaleString()}{cfg.updated_by ? ` by ${cfg.updated_by}` : ""}
                    </span>
                )}
            </div>
        </div>
    );
}

function MetaTile({ label, value, muted }) {
    return (
        <div className={`rounded-xl border p-3 ${muted ? "bg-slate-50 border-slate-200" : "bg-white border-border"}`}>
            <div className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground">{label}</div>
            <div className={`text-sm font-semibold mt-1 ${muted ? "text-slate-400" : "text-foreground"}`}>{value}</div>
        </div>
    );
}
