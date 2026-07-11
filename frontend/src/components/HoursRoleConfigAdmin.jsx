import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Switch } from "./ui/switch";
import { toast } from "sonner";
import { UsersRound, Save } from "lucide-react";

/**
 * Hours Role Config — Admin Settings panel (iter 123).
 *
 * Lets a Full Access admin decide, per admin role:
 *   • whether that role can log hours on behalf of OTHER members
 *   • what the default Log Hours dialog mode is when they open it
 *     ("for_others" auto-approves; "for_myself" queues for review)
 *
 * Stored in db.app_settings.hours_role_config. Read is public to any
 * authenticated user (the frontend uses it to decide whether to render
 * the toggle in the Log Hours dialog); write is Full-Access-only.
 *
 * Backed by:  GET/PUT /api/hours/role-config
 */
export default function HoursRoleConfigAdmin() {
    const [items, setItems] = useState(null);
    const [dirty, setDirty] = useState({}); // role → partial overrides
    const [busy, setBusy] = useState(false);
    const [newRole, setNewRole] = useState("");

    async function load() {
        try {
            const { data } = await api.get("/hours/role-config");
            setItems(data.items || []);
            setDirty({});
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to load hours role config");
        }
    }
    useEffect(() => { load(); }, []);

    function stage(role, patch) {
        setDirty((d) => ({ ...d, [role]: { ...(d[role] || {}), ...patch } }));
    }

    async function save() {
        if (!Object.keys(dirty).length) {
            toast.info("No changes to save");
            return;
        }
        setBusy(true);
        try {
            const { data } = await api.put("/hours/role-config", { roles: dirty });
            setItems(data.items || []);
            setDirty({});
            toast.success("Hours role config saved");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to save");
        }
        setBusy(false);
    }

    async function addRole() {
        const key = newRole.trim().toLowerCase().replace(/\s+/g, "_");
        if (!key) return;
        if ((items || []).some((r) => r.role === key)) {
            toast.error(`Role "${key}" already listed`);
            return;
        }
        // Send an initial default entry so the row shows up next load.
        setBusy(true);
        try {
            await api.put("/hours/role-config", {
                roles: { [key]: { can_manage_others: false, default_mode: "for_myself" } },
            });
            setNewRole("");
            await load();
            toast.success(`Added ${key}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to add role");
        }
        setBusy(false);
    }

    if (!items) return null;

    // Effective view = stored items with any pending edits layered on top.
    const rowsForRender = items.map((it) => ({
        ...it,
        ...(dirty[it.role] || {}),
    }));

    return (
        <div className="bg-card border border-border rounded-2xl p-6" data-testid="hours-role-config">
            <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
                <div>
                    <h3 className="font-heading text-xl font-bold flex items-center gap-2">
                        <UsersRound className="h-5 w-5" /> Hours by admin role
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
                        Control which admin roles can log hours on behalf of other members, and what the Log Hours dialog opens to by default. Any role marked <strong>&ldquo;Can manage others&rdquo;</strong> also gets the Review queue and CSV import; sub-roles without it are limited to logging their own hours.
                    </p>
                </div>
                <Button
                    onClick={save}
                    disabled={busy || !Object.keys(dirty).length}
                    className="rounded-full shadow-warm"
                    data-testid="hours-role-config-save-btn"
                >
                    <Save className="h-4 w-4 mr-1.5" /> Save changes {Object.keys(dirty).length > 0 && `(${Object.keys(dirty).length})`}
                </Button>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b">
                            <th className="py-2 pr-3">Role</th>
                            <th className="py-2 pr-3">Can manage others&apos; hours?</th>
                            <th className="py-2 pr-3">Default Log Hours mode</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rowsForRender.map((row) => {
                            const isEdited = !!dirty[row.role];
                            return (
                                <tr
                                    key={row.role}
                                    className={`border-b border-border/60 ${isEdited ? "bg-amber-50/60" : ""}`}
                                    data-testid={`hours-role-row-${row.role}`}
                                >
                                    <td className="py-2 pr-3">
                                        <div className="font-semibold">{row.label}</div>
                                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{row.role}</div>
                                    </td>
                                    <td className="py-2 pr-3">
                                        <div className="flex items-center gap-3">
                                            <Switch
                                                checked={!!row.can_manage_others}
                                                onCheckedChange={(v) => stage(row.role, { can_manage_others: v })}
                                                data-testid={`hours-role-manage-toggle-${row.role}`}
                                            />
                                            <span className="text-xs text-muted-foreground">
                                                {row.can_manage_others ? "Yes — sees review queue" : "Own hours only"}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="py-2 pr-3">
                                        <select
                                            value={row.default_mode}
                                            onChange={(e) => stage(row.role, { default_mode: e.target.value })}
                                            disabled={!row.can_manage_others}
                                            className="h-9 rounded-full border border-border bg-background px-3 text-sm disabled:opacity-50"
                                            data-testid={`hours-role-mode-select-${row.role}`}
                                        >
                                            <option value="for_others">Log for others (auto-approve)</option>
                                            <option value="for_myself">Log for myself (queue for review)</option>
                                        </select>
                                        {!row.can_manage_others && (
                                            <div className="text-[10px] text-muted-foreground mt-1">
                                                Default is forced to &ldquo;for myself&rdquo; while manage-others is off.
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            <div className="mt-5 pt-4 border-t border-border/60 flex flex-wrap items-center gap-2">
                <div className="text-xs text-muted-foreground mr-2">
                    Add a new admin role key (e.g. <code className="text-foreground">chapter_treasurer</code>):
                </div>
                <input
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                    placeholder="new_role_key"
                    className="h-9 rounded-full border border-border bg-background px-3 text-sm min-w-[220px]"
                    data-testid="hours-role-add-input"
                />
                <Button
                    onClick={addRole}
                    disabled={busy || !newRole.trim()}
                    variant="outline"
                    className="rounded-full"
                    data-testid="hours-role-add-btn"
                >
                    Add role
                </Button>
            </div>
        </div>
    );
}
