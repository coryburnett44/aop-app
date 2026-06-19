import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { CheckCircle2, AlertCircle, Loader2, Ticket, Calendar, MapPin, ArrowLeft, RefreshCw } from "lucide-react";
import { format, parseISO } from "date-fns";
import { fmtET } from "../lib/eventTime";
import { toast } from "sonner";

const NAVY = "#0A2463";
const RED = "#C8102E";

const TICKET_PRETTY = {
    vip: "VIP",
    all_access: "All Access",
    general: "General Admission",
    guest: "Guest",
    speaker: "Speaker",
    volunteer: "Volunteer",
};

/**
 * /checkin/:token — landing page reached when an admin scans a ticket QR.
 * Flow:
 *  1. Decode the token via /api/checkin/lookup/{token} (public — anyone with link can see who it's for).
 *  2. If the visitor is logged in as admin → auto-call /api/checkin/scan/{token} immediately.
 *  3. If not logged in → push them to /login?next=/checkin/{token}. After they log in they bounce back here.
 *  4. If not admin → show "Only admins can scan tickets" with a Switch account option.
 */
export default function CheckinScan() {
    const { token } = useParams();
    const { user, loading: authLoading } = useAuth();
    const navigate = useNavigate();

    const [ticket, setTicket] = useState(null);
    const [event, setEvent] = useState(null);
    const [status, setStatus] = useState("loading"); // loading | needs_login | not_admin | checking_in | success | already | error
    const [errorMsg, setErrorMsg] = useState("");
    const [checkin, setCheckin] = useState(null);

    // Step 1: lookup ticket info
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const { data } = await api.get(`/checkin/lookup/${token}`);
                if (cancelled) return;
                setTicket(data);
                setEvent(data.event);
            } catch (e) {
                if (cancelled) return;
                setErrorMsg(e.response?.data?.detail || "Could not read this ticket QR.");
                setStatus("error");
            }
        })();
        return () => { cancelled = true; };
    }, [token]);

    // Step 2/3: when auth is known + ticket loaded, dispatch
    useEffect(() => {
        if (authLoading || !ticket) return;
        if (status === "success" || status === "already" || status === "error") return;
        if (!user) { setStatus("needs_login"); return; }
        if (user.role !== "admin") { setStatus("not_admin"); return; }
        // Auto-scan
        runScan();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading, user, ticket]);

    async function runScan() {
        setStatus("checking_in");
        try {
            const { data } = await api.post(`/checkin/scan/${token}`);
            setCheckin(data.checkin);
            setEvent(data.event);
            setStatus(data.already_checked_in ? "already" : "success");
            if (!data.already_checked_in) toast.success(`Checked in ${data.checkin.user_name || data.checkin.guest_name || "attendee"}`);
        } catch (e) {
            setErrorMsg(e.response?.data?.detail || "Check-in failed.");
            setStatus("error");
        }
    }

    return (
        <div className="bg-slate-50 min-h-screen">
            <section className="border-b-2 bg-white" style={{ borderColor: NAVY }}>
                <div className="max-w-xl mx-auto px-6 py-8">
                    <Link to="/admin" className="text-sm text-slate-500 hover:text-primary inline-flex items-center gap-1 mb-3" data-testid="back-to-admin">
                        <ArrowLeft className="h-4 w-4" /> Admin console
                    </Link>
                    <div className="text-xs uppercase tracking-[0.3em] font-bold mb-2" style={{ color: RED }}>Ticket scan</div>
                    <h1 className="font-heading text-3xl sm:text-4xl font-black tracking-tighter" style={{ color: NAVY }}>
                        {event ? event.title : "Loading ticket…"}
                    </h1>
                    {event && (
                        <div className="text-sm text-slate-600 mt-2 flex flex-wrap items-center gap-4">
                            <span className="inline-flex items-center gap-1"><Calendar className="h-4 w-4" />{fmtET(event.start_at, "EEE, MMM d · h:mm a zzz")}</span>
                            {event.location && <span className="inline-flex items-center gap-1"><MapPin className="h-4 w-4" />{event.location}</span>}
                        </div>
                    )}
                </div>
            </section>

            <section className="max-w-xl mx-auto px-6 py-10">
                {status === "loading" && (
                    <div className="bg-white rounded-3xl border border-slate-200 p-10 text-center shadow-warm" data-testid="checkin-loading">
                        <Loader2 className="h-10 w-10 mx-auto animate-spin text-slate-400" />
                        <p className="mt-4 text-slate-500">Reading ticket…</p>
                    </div>
                )}

                {status === "needs_login" && ticket && (
                    <div className="bg-white rounded-3xl border-2 border-amber-300 p-8 shadow-warm text-center" data-testid="checkin-needs-login">
                        <Ticket className="h-10 w-10 mx-auto text-amber-500" />
                        <h2 className="font-heading text-2xl font-black mt-3" style={{ color: NAVY }}>Admin login required</h2>
                        <p className="text-sm text-slate-600 mt-2">Scanning tickets at the door requires an admin account.</p>
                        <TicketSummary ticket={ticket} />
                        <Button
                            onClick={() => navigate(`/login?next=${encodeURIComponent(`/checkin/${token}`)}`)}
                            className="mt-5 w-full rounded-full bg-primary hover:bg-primary/90 text-white shadow-warm py-6"
                            data-testid="checkin-go-login"
                        >
                            Log in to check this person in
                        </Button>
                    </div>
                )}

                {status === "not_admin" && ticket && (
                    <div className="bg-white rounded-3xl border-2 border-red-300 p-8 shadow-warm text-center" data-testid="checkin-not-admin">
                        <AlertCircle className="h-10 w-10 mx-auto text-red-500" />
                        <h2 className="font-heading text-2xl font-black mt-3" style={{ color: NAVY }}>Only admins can scan</h2>
                        <p className="text-sm text-slate-600 mt-2">You're signed in as a member — ask the admin manning the door to scan this QR with their phone instead.</p>
                        <TicketSummary ticket={ticket} />
                    </div>
                )}

                {status === "checking_in" && (
                    <div className="bg-white rounded-3xl border border-slate-200 p-10 text-center shadow-warm" data-testid="checkin-running">
                        <Loader2 className="h-10 w-10 mx-auto animate-spin text-primary" />
                        <p className="mt-4 text-slate-600">Checking in…</p>
                    </div>
                )}

                {(status === "success" || status === "already") && checkin && (
                    <div className={`bg-white rounded-3xl border-2 p-8 shadow-warm text-center ${status === "success" ? "border-green-300" : "border-amber-300"}`} data-testid={`checkin-${status}`}>
                        <CheckCircle2 className={`h-14 w-14 mx-auto ${status === "success" ? "text-green-500" : "text-amber-500"}`} />
                        <h2 className="font-heading text-3xl font-black mt-3" style={{ color: NAVY }}>
                            {status === "success" ? "Checked in!" : "Already checked in"}
                        </h2>
                        <div className="mt-4 bg-slate-50 rounded-2xl p-5 inline-block text-left">
                            <div className="text-xs uppercase tracking-wider font-bold mb-1" style={{ color: RED }}>
                                {TICKET_PRETTY[checkin.ticket_type] || checkin.ticket_type}
                                {checkin.guest_name ? " · GUEST" : ""}
                            </div>
                            <div className="font-heading font-black text-xl" style={{ color: NAVY }}>
                                {checkin.user_name || checkin.guest_name}
                            </div>
                            {checkin.host_user_name && (
                                <div className="text-xs text-slate-500 mt-1">Guest of {checkin.host_user_name}</div>
                            )}
                            <div className="text-xs text-slate-500 mt-2">
                                {checkin.checked_in_at && format(parseISO(checkin.checked_in_at), "MMM d · h:mm:ss a")}
                                {checkin.checked_in_by_name && ` · by ${checkin.checked_in_by_name}`}
                            </div>
                        </div>
                        <div className="mt-6 flex flex-col sm:flex-row gap-2">
                            <Button onClick={() => navigate(`/events/${event.id}`)} variant="outline" className="rounded-full flex-1" data-testid="checkin-back-event">
                                Open event check-in list
                            </Button>
                            <Button onClick={() => window.location.reload()} className="rounded-full bg-primary hover:bg-primary/90 text-white flex-1" data-testid="checkin-scan-next">
                                <RefreshCw className="h-4 w-4 mr-1.5" /> Scan another
                            </Button>
                        </div>
                    </div>
                )}

                {status === "error" && (
                    <div className="bg-white rounded-3xl border-2 border-red-300 p-8 shadow-warm text-center" data-testid="checkin-error">
                        <AlertCircle className="h-12 w-12 mx-auto text-red-500" />
                        <h2 className="font-heading text-2xl font-black mt-3" style={{ color: NAVY }}>Couldn't check in</h2>
                        <p className="text-sm text-slate-600 mt-2">{errorMsg}</p>
                        <Button onClick={() => navigate("/admin")} variant="outline" className="rounded-full mt-5" data-testid="checkin-error-back">
                            Back to Admin
                        </Button>
                    </div>
                )}
            </section>
        </div>
    );
}

function TicketSummary({ ticket }) {
    return (
        <div className="mt-5 bg-slate-50 rounded-2xl p-5 inline-block text-left max-w-full">
            <div className="text-xs uppercase tracking-wider font-bold mb-1" style={{ color: RED }}>
                {TICKET_PRETTY[ticket.ticket_type] || ticket.ticket_type}
                {ticket.kind === "guest" ? " · GUEST" : ""}
            </div>
            <div className="font-heading font-black text-xl" style={{ color: NAVY }}>{ticket.name || (ticket.kind === "guest" ? "Guest" : "Member")}</div>
            <div className="text-xs text-slate-500 mt-1">Ticket ID: {ticket.ticket_id?.slice(0, 8)}…</div>
        </div>
    );
}
