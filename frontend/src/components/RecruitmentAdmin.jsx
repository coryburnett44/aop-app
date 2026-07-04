import { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../lib/api";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Plus, Pencil, Trash2, Upload, Download, FileText, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { formatCalendarDay } from "../lib/dateUtil";

/**
 * Admin → Recruitment tab.
 * Table of recruitment records with add/edit/delete + CSV import/export
 * + per-recruit search. Mirrors HoursAdmin's rhythm so admins have muscle
 * memory across the console.
 */
export default function RecruitmentAdmin() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [members, setMembers] = useState([]);
    const [editing, setEditing] = useState(null); // null | {} (new) | record (edit)
    const [csvOpen, setCsvOpen] = useState(false);

    async function load() {
        setLoading(true);
        try {
            const { data } = await api.get("/recruitments");
            setItems(data);
        } catch (e) {
            toast.error(formatApiError(e.response?.data?.detail) || "Failed to load recruitments");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        load();
        api.get("/members").then(({ data }) => setMembers(data)).catch(() => setMembers([]));
    }, []);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return items;
        return items.filter((r) =>
            (r.recruiter_name || "").toLowerCase().includes(q) ||
            (r.recruiter_email || "").toLowerCase().includes(q) ||
            (r.recruit_name || "").toLowerCase().includes(q) ||
            (r.recruit_email || "").toLowerCase().includes(q) ||
            (r.notes || "").toLowerCase().includes(q),
        );
    }, [items, search]);

    async function del(r) {
        if (!confirm(`Delete recruitment: ${r.recruiter_name} → ${r.recruit_name}?`)) return;
        try {
            await api.delete(`/recruitments/${r.id}`);
            toast.success("Recruitment deleted");
            load();
        } catch (e) {
            toast.error(formatApiError(e.response?.data?.detail) || "Delete failed");
        }
    }

    function exportCSV() {
        const url = `${api.defaults.baseURL}/recruitments/csv/export`;
        // Auth cookies are attached because axios uses withCredentials.
        // Use a plain anchor click so the browser handles the download.
        const a = document.createElement("a");
        a.href = url;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    return (
        <div data-testid="admin-recruitment">
            <div className="flex flex-wrap items-center gap-2 mb-4">
                <Button onClick={() => setEditing({})} className="rounded-full bg-primary hover:bg-primary/90" data-testid="admin-recruitment-add">
                    <Plus className="h-4 w-4 mr-1.5" /> New recruitment
                </Button>
                <Button variant="outline" className="rounded-full" onClick={() => setCsvOpen(true)} data-testid="admin-recruitment-csv-open">
                    <Upload className="h-4 w-4 mr-1.5" /> Import CSV
                </Button>
                <Button variant="outline" className="rounded-full" onClick={exportCSV} data-testid="admin-recruitment-csv-export">
                    <Download className="h-4 w-4 mr-1.5" /> Export CSV
                </Button>
                <div className="ml-auto flex items-center gap-2 min-w-[260px]">
                    <Input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search recruiter, recruit, or notes…"
                        className="rounded-full h-9 text-sm"
                        data-testid="admin-recruitment-search"
                    />
                    {search && (
                        <button
                            type="button"
                            onClick={() => setSearch("")}
                            className="text-xs text-muted-foreground hover:text-foreground whitespace-nowrap"
                            data-testid="admin-recruitment-search-clear"
                        >Clear</button>
                    )}
                </div>
            </div>

            {search.trim() && (
                <div className="text-xs text-muted-foreground mb-2">
                    {filtered.length} of {items.length} records match &quot;{search.trim()}&quot;
                </div>
            )}

            {loading ? (
                <div className="text-muted-foreground">Loading…</div>
            ) : filtered.length === 0 ? (
                <div className="bg-muted/40 border-2 border-dashed border-muted rounded-2xl p-10 text-center text-muted-foreground" data-testid="admin-recruitment-empty">
                    <UserPlus className="h-8 w-8 mx-auto mb-3 opacity-60" />
                    {search.trim() ? "No matches." : "No recruitment records yet. Add one or import a CSV to get started."}
                </div>
            ) : (
                <div className="bg-card rounded-2xl border overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-4 py-3">Date</th>
                                <th className="text-left px-4 py-3">Recruiter</th>
                                <th className="text-left px-4 py-3">Recruit</th>
                                <th className="text-left px-4 py-3">Chapter</th>
                                <th className="text-left px-4 py-3">Notes</th>
                                <th className="text-right px-4 py-3">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((r) => (
                                <tr key={r.id} className="border-t" data-testid={`admin-recruitment-row-${r.id}`}>
                                    <td className="px-4 py-3 whitespace-nowrap font-medium">{r.date_recruited ? formatCalendarDay(r.date_recruited, "MMM d, yyyy") : ""}</td>
                                    <td className="px-4 py-3">
                                        <div className="font-semibold">{r.recruiter_name || "—"}</div>
                                        {r.recruiter_email && <div className="text-xs text-muted-foreground">{r.recruiter_email}</div>}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="font-semibold">{r.recruit_name || "—"}</div>
                                        {r.recruit_email && <div className="text-xs text-muted-foreground">{r.recruit_email}</div>}
                                    </td>
                                    <td className="px-4 py-3">{r.chapter_name || "—"}</td>
                                    <td className="px-4 py-3 max-w-[240px] truncate" title={r.notes}>{r.notes}</td>
                                    <td className="px-4 py-3 text-right whitespace-nowrap">
                                        <Button size="sm" variant="outline" className="rounded-full mr-1.5" onClick={() => setEditing(r)} data-testid={`admin-recruitment-edit-${r.id}`}>
                                            <Pencil className="h-3.5 w-3.5" />
                                        </Button>
                                        <Button size="sm" variant="outline" className="rounded-full text-red-600" onClick={() => del(r)} data-testid={`admin-recruitment-delete-${r.id}`}>
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {editing !== null && (
                <RecruitmentEditDialog
                    record={editing}
                    members={members}
                    onClose={() => setEditing(null)}
                    onSaved={() => { setEditing(null); load(); }}
                />
            )}

            {csvOpen && (
                <RecruitmentCsvDialog
                    onClose={() => setCsvOpen(false)}
                    onImported={() => { setCsvOpen(false); load(); }}
                />
            )}
        </div>
    );
}

function RecruitmentEditDialog({ record, members, onClose, onSaved }) {
    const isNew = !record.id;
    const [recruiterId, setRecruiterId] = useState(record.recruiter_id || "");
    const [recruitId, setRecruitId] = useState(record.recruit_id || "");
    const [date, setDate] = useState(record.date_recruited ? record.date_recruited.slice(0, 10) : new Date().toISOString().slice(0, 10));
    const [notes, setNotes] = useState(record.notes || "");
    const [saving, setSaving] = useState(false);

    async function save() {
        if (!recruiterId || !recruitId || !date) {
            toast.error("Recruiter, recruit, and date are required.");
            return;
        }
        if (recruiterId === recruitId) {
            toast.error("A member cannot recruit themselves.");
            return;
        }
        setSaving(true);
        try {
            const body = { recruiter_id: recruiterId, recruit_id: recruitId, date_recruited: date, notes };
            if (isNew) {
                await api.post("/recruitments", body);
                toast.success("Recruitment recorded");
            } else {
                await api.put(`/recruitments/${record.id}`, body);
                toast.success("Recruitment updated");
            }
            onSaved();
        } catch (e) {
            toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
        } finally {
            setSaving(false);
        }
    }

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="admin-recruitment-dialog">
                <DialogHeader>
                    <DialogTitle>{isNew ? "New recruitment record" : "Edit recruitment"}</DialogTitle>
                    <DialogDescription>Credit the member who brought this recruit into Alpha Omega Phi.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                    <MemberSelect label="Recruiter (existing member)" value={recruiterId} onChange={setRecruiterId} members={members} testid="admin-recruitment-recruiter" excludeId={recruitId} />
                    <MemberSelect label="Recruit (existing member)" value={recruitId} onChange={setRecruitId} members={members} testid="admin-recruitment-recruit" excludeId={recruiterId} />
                    <div>
                        <Label className="text-xs">Date recruited</Label>
                        <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="rounded-xl mt-1.5" data-testid="admin-recruitment-date" />
                    </div>
                    <div>
                        <Label className="text-xs">Notes (optional)</Label>
                        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="rounded-xl mt-1.5" rows={3} placeholder="Where they met, event, campaign, etc." data-testid="admin-recruitment-notes" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} className="rounded-full" data-testid="admin-recruitment-cancel">Cancel</Button>
                    <Button onClick={save} disabled={saving} className="rounded-full bg-primary hover:bg-primary/90" data-testid="admin-recruitment-save">
                        {saving ? "Saving…" : (isNew ? "Add recruitment" : "Save changes")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function MemberSelect({ label, value, onChange, members, testid, excludeId }) {
    // Sort by name for stable UX
    const sorted = useMemo(() => [...members].sort((a, b) => (a.name || "").localeCompare(b.name || "")), [members]);
    const list = useMemo(() => sorted.filter((m) => m.id !== excludeId), [sorted, excludeId]);
    return (
        <div>
            <Label className="text-xs">{label}</Label>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className="rounded-xl mt-1.5" data-testid={testid}>
                    <SelectValue placeholder="Choose a member" />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                    {list.map((m) => (
                        <SelectItem key={m.id} value={m.id} data-testid={`${testid}-option-${m.id}`}>
                            {m.name}{m.email ? ` · ${m.email}` : ""}
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
}

function RecruitmentCsvDialog({ onClose, onImported }) {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [submitting, setSubmitting] = useState(false);

    async function runDryRun() {
        if (!file) return;
        setSubmitting(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/recruitments/csv?dry_run=true", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setPreview(data);
        } catch (e) {
            toast.error(formatApiError(e.response?.data?.detail) || "CSV parse failed");
        } finally {
            setSubmitting(false);
        }
    }

    async function commit() {
        if (!file) return;
        setSubmitting(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/recruitments/csv?dry_run=false", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success(`Imported ${data.created} recruitment${data.created !== 1 ? "s" : ""}${data.skipped ? ` · ${data.skipped} skipped` : ""}${data.failed ? ` · ${data.failed} failed` : ""}`);
            onImported();
        } catch (e) {
            toast.error(formatApiError(e.response?.data?.detail) || "Import failed");
        } finally {
            setSubmitting(false);
        }
    }

    function downloadTemplate() {
        const a = document.createElement("a");
        a.href = `${api.defaults.baseURL}/recruitments/csv/template`;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="admin-recruitment-csv-dialog">
                <DialogHeader>
                    <DialogTitle>Import Recruitment CSV</DialogTitle>
                    <DialogDescription>
                        Match by <strong>email</strong> (preferred) or by <strong>full name</strong>. Duplicate recruiter/recruit/date rows are skipped, not failed.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2">
                        <Button variant="outline" size="sm" className="rounded-full" onClick={downloadTemplate} data-testid="admin-recruitment-csv-template">
                            <FileText className="h-4 w-4 mr-1.5" /> Download template
                        </Button>
                    </div>
                    <div>
                        <Label className="text-xs">CSV file</Label>
                        <Input
                            type="file"
                            accept=".csv,text/csv"
                            onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); }}
                            className="rounded-xl mt-1.5"
                            data-testid="admin-recruitment-csv-file"
                        />
                    </div>

                    {preview && (
                        <div className="border rounded-xl p-3" data-testid="admin-recruitment-csv-preview">
                            <div className="text-sm font-semibold mb-2">
                                Preview · {preview.total} row{preview.total !== 1 ? "s" : ""} · {preview.total - preview.failed - preview.skipped} ready · {preview.skipped || 0} skip · {preview.failed || 0} errors
                            </div>
                            <div className="max-h-64 overflow-y-auto text-xs space-y-1">
                                {preview.rows.map((r) => (
                                    <div key={r.row} className={`px-2 py-1.5 rounded-lg ${r.status === "ERROR" ? "bg-red-50 text-red-800" : r.status === "SKIP" ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-800"}`}>
                                        <div><strong>Row {r.row}:</strong> {r.recruiter} → {r.recruit} · {r.date}</div>
                                        {r.errors?.length > 0 && <div className="text-red-700">{r.errors.join(" · ")}</div>}
                                        {r.warnings?.length > 0 && <div className="text-amber-700">{r.warnings.join(" · ")}</div>}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} className="rounded-full" data-testid="admin-recruitment-csv-cancel">Cancel</Button>
                    <Button variant="outline" onClick={runDryRun} disabled={!file || submitting} className="rounded-full" data-testid="admin-recruitment-csv-dryrun">
                        {preview ? "Re-preview" : "Preview"}
                    </Button>
                    <Button onClick={commit} disabled={!file || submitting || !preview} className="rounded-full bg-primary hover:bg-primary/90" data-testid="admin-recruitment-csv-commit">
                        {submitting ? "Importing…" : `Import ${preview ? preview.total - (preview.failed || 0) - (preview.skipped || 0) : ""}`}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
