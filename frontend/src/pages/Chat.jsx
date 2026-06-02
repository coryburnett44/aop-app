import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";
import { Plus, Send, Paperclip, X, Search, Users as UsersIcon, Trash2, LogOut, Settings, FileText, Image as ImageIcon, Download, ArrowLeft, Upload, Camera } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isToday, isYesterday } from "date-fns";

const NAVY = "#0A2463";
const RED = "#C8102E";

function chatWsUrl() {
    const base = process.env.REACT_APP_BACKEND_URL || "";
    return base.replace(/^http/, "ws") + "/api/ws/chat";
}

function fmtMessageDay(iso) {
    if (!iso) return "";
    const d = parseISO(iso);
    if (isToday(d)) return "Today";
    if (isYesterday(d)) return "Yesterday";
    return format(d, "MMM d, yyyy");
}

export default function Chat() {
    const { user } = useAuth();
    const { conversationId } = useParams();
    const navigate = useNavigate();
    const [conversations, setConversations] = useState([]);
    const [active, setActive] = useState(null);
    const wsRef = useRef(null);
    const reconnectTimer = useRef(null);

    const loadConversations = useCallback(async () => {
        const { data } = await api.get("/conversations");
        setConversations(data);
        return data;
    }, []);

    useEffect(() => { loadConversations().catch(() => {}); }, [loadConversations]);

    // Sync active with URL
    useEffect(() => {
        if (conversationId) {
            const found = conversations.find((c) => c.id === conversationId);
            if (found) setActive(found);
            else api.get(`/conversations/${conversationId}`).then(({ data }) => setActive(data)).catch(() => {});
        }
    }, [conversationId, conversations]);

    // WebSocket lifecycle
    useEffect(() => {
        function connect() {
            const ws = new WebSocket(chatWsUrl());
            wsRef.current = ws;
            ws.onmessage = (e) => {
                try {
                    const msg = JSON.parse(e.data);
                    handleEvent(msg);
                } catch {}
            };
            ws.onclose = () => {
                wsRef.current = null;
                if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
                reconnectTimer.current = setTimeout(connect, 3000);
            };
        }
        connect();
        return () => {
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
            if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); }
        };
    }, []); // eslint-disable-line

    function handleEvent(msg) {
        if (msg.type === "message:new") {
            // Bump conversation list with new preview
            setConversations((prev) => {
                const updated = prev.map((c) =>
                    c.id === msg.message.conversation_id
                        ? { ...c, last_message_at: msg.message.created_at, last_message_preview: msg.message.body || (msg.message.attachments?.[0]?.filename ? `📎 ${msg.message.attachments[0].filename}` : "") }
                        : c
                );
                updated.sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""));
                return updated;
            });
            // Dispatch to active thread
            window.dispatchEvent(new CustomEvent("chat:message", { detail: msg.message }));
        } else if (msg.type === "conversation:created" || msg.type === "conversation:updated") {
            loadConversations();
        } else if (msg.type === "conversation:deleted") {
            setConversations((prev) => prev.filter((c) => c.id !== msg.conversation_id));
            if (active?.id === msg.conversation_id) navigate("/chat");
        }
    }

    function openConv(c) {
        navigate(`/chat/${c.id}`);
    }

    if (!user) return null;
    return (
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-10 py-6">
            <div className="grid lg:grid-cols-[320px_1fr] gap-4 h-[calc(100vh-180px)] min-h-[600px]">
                <aside className={`bg-white rounded-3xl border-2 shadow-warm overflow-hidden flex flex-col ${active ? "hidden lg:flex" : "flex"}`} style={{ borderColor: `${NAVY}20` }} data-testid="chat-sidebar">
                    <div className="px-5 py-4 border-b flex items-center justify-between">
                        <div>
                            <div className="text-xs uppercase tracking-widest font-bold" style={{ color: RED }}>Messages</div>
                            <div className="font-heading text-xl font-black" style={{ color: NAVY }}>{conversations.length} chat{conversations.length !== 1 ? "s" : ""}</div>
                        </div>
                        <NewChatDialog onCreated={(c) => { loadConversations().then(() => navigate(`/chat/${c.id}`)); }} />
                    </div>
                    <ScrollArea className="flex-1">
                        {conversations.length === 0 ? (
                            <div className="text-center text-sm text-slate-500 p-8">
                                <UsersIcon className="h-10 w-10 mx-auto text-slate-300 mb-3" />
                                No chats yet. Start one with the + button.
                            </div>
                        ) : conversations.map((c) => (
                            <ConversationItem key={c.id} conv={c} active={active?.id === c.id} onClick={() => openConv(c)} viewerId={user.id} />
                        ))}
                    </ScrollArea>
                </aside>

                <section className={`bg-white rounded-3xl border-2 shadow-warm overflow-hidden flex flex-col ${active ? "flex" : "hidden lg:flex"}`} style={{ borderColor: `${NAVY}20` }}>
                    {active ? (
                        <ChatThread conversation={active} onRefresh={loadConversations} onBack={() => { setActive(null); navigate("/chat"); }} />
                    ) : (
                        <div className="m-auto text-center text-slate-500 max-w-xs">
                            <UsersIcon className="h-12 w-12 mx-auto text-slate-300 mb-4" />
                            <p className="font-heading text-xl mb-1" style={{ color: NAVY }}>Pick a conversation</p>
                            <p className="text-sm">Choose one from the left, or start a new chat.</p>
                        </div>
                    )}
                </section>
            </div>
        </div>
    );
}

function ConversationItem({ conv, active, onClick, viewerId }) {
    const initials = (conv.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
    const unread = conv.last_message_at && (!conv.last_read_at || conv.last_message_at > conv.last_read_at);
    return (
        <button
            onClick={onClick}
            className={`w-full text-left px-4 py-3 flex items-center gap-3 border-b border-slate-100 transition-colors ${active ? "bg-primary/10" : "hover:bg-slate-50"}`}
            data-testid={`conv-${conv.id}`}
        >
            <Avatar className="h-11 w-11 border-2 border-white shadow-sm shrink-0">
                {conv.avatar_url && <AvatarImage src={conv.avatar_url} />}
                <AvatarFallback className={`${conv.type === "group" ? "bg-amber-100 text-amber-800" : "bg-primary/15 text-primary"} font-bold`}>{initials}</AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                    <div className={`font-semibold truncate ${active ? "text-primary" : ""}`} style={!active ? { color: NAVY } : {}}>{conv.name}</div>
                    {conv.last_message_at && (
                        <div className="text-[10px] text-slate-400 shrink-0">{format(parseISO(conv.last_message_at), isToday(parseISO(conv.last_message_at)) ? "h:mm a" : "MMM d")}</div>
                    )}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                    <div className="text-xs text-slate-500 truncate flex-1">{conv.last_message_preview || (conv.type === "group" ? `${conv.members?.length || 0} members` : "Say hi")}</div>
                    {unread && <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: RED }} />}
                </div>
            </div>
        </button>
    );
}

function ChatThread({ conversation, onRefresh, onBack }) {
    const { user } = useAuth();
    const [messages, setMessages] = useState([]);
    const [hasMore, setHasMore] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const scrollerRef = useRef(null);

    useEffect(() => {
        api.get(`/conversations/${conversation.id}/messages?limit=50`).then(({ data }) => {
            setMessages(data);
            setHasMore(data.length === 50);
            setTimeout(() => scrollToBottom("instant"), 50);
        }).catch(() => {});
        api.post(`/conversations/${conversation.id}/read`).catch(() => {});
    }, [conversation.id]);

    useEffect(() => {
        function onMsg(e) {
            const m = e.detail;
            if (m.conversation_id === conversation.id) {
                setMessages((prev) => prev.find((x) => x.id === m.id) ? prev : [...prev, m]);
                api.post(`/conversations/${conversation.id}/read`).catch(() => {});
                setTimeout(() => scrollToBottom("smooth"), 50);
            }
        }
        window.addEventListener("chat:message", onMsg);
        return () => window.removeEventListener("chat:message", onMsg);
    }, [conversation.id]);

    function scrollToBottom(behavior = "smooth") {
        const el = scrollerRef.current;
        if (el) el.scrollTo({ top: el.scrollHeight, behavior });
    }

    async function loadOlder() {
        if (!messages.length || loadingMore) return;
        setLoadingMore(true);
        try {
            const before = messages[0].created_at;
            const { data } = await api.get(`/conversations/${conversation.id}/messages?before=${encodeURIComponent(before)}&limit=50`);
            const prevHeight = scrollerRef.current?.scrollHeight || 0;
            setMessages((m) => [...data, ...m]);
            setHasMore(data.length === 50);
            setTimeout(() => {
                const el = scrollerRef.current;
                if (el) el.scrollTop = el.scrollHeight - prevHeight;
            }, 50);
        } finally { setLoadingMore(false); }
    }

    function onSent(m) {
        setMessages((prev) => prev.find((x) => x.id === m.id) ? prev : [...prev, m]);
        setTimeout(() => scrollToBottom("smooth"), 30);
    }

    // Group messages by day
    const grouped = [];
    let lastDay = null;
    for (const m of messages) {
        const day = fmtMessageDay(m.created_at);
        if (day !== lastDay) { grouped.push({ kind: "day", day, id: `day-${day}-${m.id}` }); lastDay = day; }
        grouped.push({ kind: "msg", msg: m });
    }

    return (
        <>
            <header className="px-4 sm:px-5 py-3.5 border-b flex items-center gap-3" data-testid="thread-header">
                <button onClick={onBack} className="lg:hidden text-slate-500 hover:text-slate-700" data-testid="thread-back">
                    <ArrowLeft className="h-5 w-5" />
                </button>
                <Avatar className="h-10 w-10 border-2 border-white shadow-sm">
                    {conversation.avatar_url && <AvatarImage src={conversation.avatar_url} />}
                    <AvatarFallback className={`${conversation.type === "group" ? "bg-amber-100 text-amber-800" : "bg-primary/15 text-primary"} font-bold`}>
                        {(conversation.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}
                    </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                    <div className="font-heading font-bold truncate" style={{ color: NAVY }}>{conversation.name}</div>
                    <div className="text-xs text-slate-500">
                        {conversation.type === "group" ? `${conversation.members.length} members` : "Direct message"}
                    </div>
                </div>
                <ConversationSettings conversation={conversation} onChanged={onRefresh} />
            </header>

            <div ref={scrollerRef} className="flex-1 overflow-y-auto px-3 sm:px-5 py-4 bg-slate-50" data-testid="thread-scroller">
                {hasMore && (
                    <div className="text-center mb-3">
                        <button onClick={loadOlder} disabled={loadingMore} className="text-xs text-slate-500 hover:text-slate-800 underline" data-testid="load-older-btn">
                            {loadingMore ? "Loading…" : "Load older messages"}
                        </button>
                    </div>
                )}
                {grouped.length === 0 && <div className="text-center text-sm text-slate-500 py-12">No messages yet. Say hi 👋</div>}
                {grouped.map((g) => g.kind === "day" ? (
                    <div key={g.id} className="text-center my-4">
                        <span className="text-[10px] uppercase tracking-widest font-bold bg-white border border-slate-200 rounded-full px-3 py-1 text-slate-500">{g.day}</span>
                    </div>
                ) : (
                    <MessageBubble key={g.msg.id} message={g.msg} mine={g.msg.sender_id === user.id} showSender={conversation.type === "group" && g.msg.sender_id !== user.id} />
                ))}
            </div>

            <MessageComposer conversation={conversation} onSent={onSent} />
        </>
    );
}

function MessageBubble({ message, mine, showSender }) {
    const isDeleted = !!message.deleted_at;
    return (
        <div className={`flex gap-2 my-1.5 ${mine ? "justify-end" : "justify-start"}`} data-testid={`msg-${message.id}`}>
            {!mine && (
                <Avatar className="h-7 w-7 shrink-0 mt-1">
                    {message.sender_avatar && <AvatarImage src={message.sender_avatar} />}
                    <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">
                        {(message.sender_name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}
                    </AvatarFallback>
                </Avatar>
            )}
            <div className={`max-w-[78%] sm:max-w-[65%] rounded-2xl px-3.5 py-2 ${mine ? "text-white rounded-br-sm" : "bg-white border border-slate-200 rounded-bl-sm"}`} style={mine ? { backgroundColor: NAVY } : {}}>
                {showSender && <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: RED }}>{message.sender_name}</div>}
                {isDeleted ? (
                    <div className="italic text-xs opacity-60">message deleted</div>
                ) : (
                    <>
                        {message.attachments?.length > 0 && (
                            <div className={`space-y-1.5 ${message.body ? "mb-2" : ""}`}>
                                {message.attachments.map((a, i) => <Attachment key={i} att={a} mine={mine} />)}
                            </div>
                        )}
                        {message.body && <div className="whitespace-pre-wrap break-words text-sm">{message.body}</div>}
                    </>
                )}
                <div className={`text-[10px] mt-1 ${mine ? "text-white/60" : "text-slate-400"}`}>{format(parseISO(message.created_at), "h:mm a")}</div>
            </div>
        </div>
    );
}

function Attachment({ att, mine }) {
    const base = process.env.REACT_APP_BACKEND_URL || "";
    const href = att.url?.startsWith("/api") ? base + att.url : att.url;
    if (att.kind === "image") {
        return (
            <a href={href} target="_blank" rel="noreferrer" className="block">
                <img src={href} alt={att.filename} className="rounded-xl max-w-full max-h-72 object-contain bg-black/5" loading="lazy" />
            </a>
        );
    }
    if (att.kind === "video") {
        return <video src={href} controls className="rounded-xl max-w-full max-h-72" />;
    }
    if (att.kind === "audio") {
        return <audio src={href} controls className="w-full" />;
    }
    return (
        <a href={href} target="_blank" rel="noreferrer" className={`flex items-center gap-3 rounded-xl px-3 py-2 ${mine ? "bg-white/10 hover:bg-white/15" : "bg-slate-100 hover:bg-slate-200"} transition-colors`}>
            <FileText className="h-5 w-5 shrink-0" />
            <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">{att.filename}</div>
                <div className="text-[10px] opacity-70">{formatBytes(att.size)}</div>
            </div>
            <Download className="h-4 w-4 opacity-60" />
        </a>
    );
}

function formatBytes(b) {
    if (!b) return "—";
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`;
    return `${(b / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function MessageComposer({ conversation, onSent }) {
    const [text, setText] = useState("");
    const [attachments, setAttachments] = useState([]);
    const [busy, setBusy] = useState(false);
    const [uploading, setUploading] = useState(0);
    const fileInputRef = useRef(null);

    async function upload(files) {
        for (const f of files) {
            if (f.size > 100 * 1024 * 1024) {
                toast.error(`${f.name} is over 100 MB — please pick a smaller file.`);
                continue;
            }
            setUploading((u) => u + 1);
            try {
                const fd = new FormData();
                fd.append("file", f);
                const { data } = await api.post("/chat/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
                setAttachments((prev) => [...prev, data]);
            } catch (e) {
                toast.error(e.response?.data?.detail || `Upload of ${f.name} failed`);
            } finally {
                setUploading((u) => u - 1);
            }
        }
    }

    async function send() {
        const body = text.trim();
        if (!body && attachments.length === 0) return;
        setBusy(true);
        try {
            const { data } = await api.post(`/conversations/${conversation.id}/messages`, { body, attachments });
            onSent(data);
            setText(""); setAttachments([]);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Send failed");
        }
        setBusy(false);
    }

    return (
        <div className="border-t bg-white p-3" data-testid="composer">
            {attachments.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2">
                    {attachments.map((a, i) => (
                        <div key={i} className="relative bg-slate-100 rounded-xl pl-3 pr-7 py-1.5 text-xs max-w-[200px]" data-testid={`attachment-pill-${i}`}>
                            <span className="truncate inline-block max-w-[170px] align-middle">📎 {a.filename}</span>
                            <button onClick={() => setAttachments((p) => p.filter((_, idx) => idx !== i))} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-destructive">
                                <X className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    ))}
                </div>
            )}
            <div className="flex items-end gap-2">
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) => { upload(Array.from(e.target.files || [])); e.target.value = ""; }}
                    data-testid="file-input"
                />
                <Button variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()} disabled={busy || uploading > 0} className="shrink-0 rounded-full" data-testid="attach-btn">
                    <Paperclip className="h-5 w-5" />
                </Button>
                <textarea
                    rows={1}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                    placeholder={uploading > 0 ? "Uploading…" : "Type a message"}
                    className="flex-1 resize-none rounded-2xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 max-h-32"
                    data-testid="message-input"
                />
                <Button onClick={send} disabled={busy || (!text.trim() && attachments.length === 0)} className="rounded-full text-white shrink-0" style={{ backgroundColor: NAVY }} data-testid="send-btn">
                    <Send className="h-4 w-4" />
                </Button>
            </div>
            {uploading > 0 && <div className="text-xs text-slate-500 mt-1.5">Uploading {uploading} file{uploading !== 1 ? "s" : ""}…</div>}
        </div>
    );
}

function NewChatDialog({ onCreated }) {
    const [open, setOpen] = useState(false);
    const [members, setMembers] = useState([]);
    const [search, setSearch] = useState("");
    const [selected, setSelected] = useState([]);
    const [name, setName] = useState("");
    const [avatarUrl, setAvatarUrl] = useState("");
    const [uploadingPic, setUploadingPic] = useState(false);
    const [busy, setBusy] = useState(false);
    const { user } = useAuth();
    const picRef = useRef(null);

    useEffect(() => {
        if (open) {
            api.get("/members").then(({ data }) => setMembers(data.filter((m) => m.id !== user.id))).catch(() => {});
            setSearch(""); setSelected([]); setName(""); setAvatarUrl("");
        }
    }, [open, user.id]);

    const filtered = members.filter((m) => {
        if (!search) return true;
        const q = search.toLowerCase();
        return m.name?.toLowerCase().includes(q) || m.email?.toLowerCase().includes(q) || m.line_name?.toLowerCase().includes(q);
    }).slice(0, 50);

    function toggle(id) {
        setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
    }

    async function pickGroupPic(file) {
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { toast.error("Image must be under 10 MB"); return; }
        setUploadingPic(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const { data } = await api.post("/chat/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setAvatarUrl(data.url || "");
            toast.success("Group picture set");
        } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
        setUploadingPic(false);
        if (picRef.current) picRef.current.value = "";
    }

    async function create() {
        if (selected.length === 0) { toast.error("Pick at least one member"); return; }
        setBusy(true);
        try {
            const payload = { member_ids: selected, name: selected.length > 1 ? (name.trim() || null) : null };
            if (selected.length > 1 && avatarUrl) payload.avatar_url = avatarUrl;
            const { data } = await api.post("/conversations", payload);
            setOpen(false);
            onCreated(data);
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        setBusy(false);
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button className="rounded-full text-white shadow-warm" style={{ backgroundColor: RED }} size="icon" data-testid="chat-new-btn">
                    <Plus className="h-4 w-4" />
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md max-h-[90vh] overflow-hidden flex flex-col">
                <DialogHeader><DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>New chat</DialogTitle></DialogHeader>
                <div className="space-y-3 mt-2 overflow-hidden flex flex-col flex-1">
                    {selected.length > 1 && (
                        <>
                            <div>
                                <Label className="text-xs">Group name (optional)</Label>
                                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Texas Bravo squad" className="rounded-xl mt-1.5" data-testid="group-name-input" />
                            </div>
                            <div>
                                <Label className="text-xs">Group picture (optional)</Label>
                                <div className="flex items-center gap-3 mt-1.5">
                                    <div className="h-14 w-14 rounded-full overflow-hidden border-2 border-slate-200 shrink-0 grid place-items-center bg-slate-100">
                                        {avatarUrl ? (
                                            <img src={(process.env.REACT_APP_BACKEND_URL || "") + avatarUrl} alt="Group" className="w-full h-full object-cover" />
                                        ) : (
                                            <Camera className="h-5 w-5 text-slate-400" />
                                        )}
                                    </div>
                                    <input
                                        ref={picRef}
                                        type="file"
                                        accept="image/*"
                                        className="hidden"
                                        onChange={(e) => pickGroupPic(e.target.files?.[0])}
                                        data-testid="group-pic-input"
                                    />
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="rounded-full"
                                        disabled={uploadingPic}
                                        onClick={() => picRef.current?.click()}
                                        data-testid="group-pic-upload-btn"
                                    >
                                        <Upload className="h-3.5 w-3.5 mr-1" /> {uploadingPic ? "Uploading…" : avatarUrl ? "Replace" : "Upload"}
                                    </Button>
                                    {avatarUrl && (
                                        <button
                                            type="button"
                                            onClick={() => setAvatarUrl("")}
                                            className="text-xs text-slate-500 hover:text-destructive"
                                            data-testid="group-pic-clear-btn"
                                        >
                                            Remove
                                        </button>
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search members…" className="pl-9 rounded-xl" data-testid="member-search-input" />
                    </div>
                    {selected.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                            {selected.map((id) => {
                                const m = members.find((x) => x.id === id);
                                return (
                                    <span key={id} className="inline-flex items-center gap-1 bg-primary/10 text-primary rounded-full px-2.5 py-1 text-xs font-medium">
                                        {m?.name}
                                        <button onClick={() => toggle(id)}><X className="h-3 w-3" /></button>
                                    </span>
                                );
                            })}
                        </div>
                    )}
                    <div className="overflow-y-auto border border-slate-200 rounded-xl flex-1 min-h-[200px] max-h-[300px]">
                        {filtered.length === 0 ? (
                            <div className="text-center text-sm text-slate-500 p-4">No members match.</div>
                        ) : filtered.map((m) => {
                            const isSel = selected.includes(m.id);
                            const initials = (m.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                            return (
                                <button
                                    key={m.id}
                                    onClick={() => toggle(m.id)}
                                    className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors border-b last:border-0 ${isSel ? "bg-primary/10" : "hover:bg-slate-50"}`}
                                    data-testid={`pick-member-${m.id}`}
                                >
                                    <Avatar className="h-8 w-8">
                                        {m.avatar_url && <AvatarImage src={m.avatar_url} />}
                                        <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">{initials}</AvatarFallback>
                                    </Avatar>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium truncate">{m.name}</div>
                                        <div className="text-xs text-slate-500 truncate">{m.email}</div>
                                    </div>
                                    {isSel && <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] grid place-items-center">✓</span>}
                                </button>
                            );
                        })}
                    </div>
                </div>
                <DialogFooter>
                    <Button onClick={create} disabled={busy || selected.length === 0} className="rounded-full text-white" style={{ backgroundColor: NAVY }} data-testid="create-chat-btn">
                        {busy ? "Creating…" : selected.length > 1 ? `Start group (${selected.length})` : "Start chat"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ConversationSettings({ conversation, onChanged }) {
    const { user } = useAuth();
    const [open, setOpen] = useState(false);
    const [name, setName] = useState(conversation.raw_name || "");
    const isGroup = conversation.type === "group";
    const isCreator = conversation.created_by === user.id;
    const isAdmin = user.role === "admin";

    useEffect(() => { setName(conversation.raw_name || ""); }, [conversation.id, conversation.raw_name]);

    async function rename() {
        try {
            await api.put(`/conversations/${conversation.id}`, { name });
            toast.success("Renamed");
            setOpen(false);
            onChanged();
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }
    async function leave() {
        if (!confirm("Leave this conversation?")) return;
        try {
            await api.post(`/conversations/${conversation.id}/leave`);
            toast.success("Left the conversation");
            setOpen(false);
            window.location.href = "/chat";
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }
    async function deleteConv() {
        if (!confirm("Delete this conversation and all messages? This cannot be undone.")) return;
        try {
            await api.delete(`/conversations/${conversation.id}`);
            toast.success("Deleted");
            setOpen(false);
            window.location.href = "/chat";
        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="ghost" size="icon" className="shrink-0" data-testid="chat-settings-btn"><Settings className="h-4 w-4" /></Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>Chat settings</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                    {isGroup && (
                        <div>
                            <Label>Group name</Label>
                            <div className="flex gap-2 mt-1.5">
                                <Input value={name} onChange={(e) => setName(e.target.value)} className="rounded-xl flex-1" data-testid="rename-input" />
                                <Button onClick={rename} className="rounded-full text-white" style={{ backgroundColor: NAVY }} data-testid="rename-btn">Save</Button>
                            </div>
                        </div>
                    )}
                    <div>
                        <Label className="text-xs">Members ({conversation.members?.length || 0})</Label>
                        <div className="mt-2 space-y-1.5 max-h-56 overflow-y-auto">
                            {conversation.members?.map((m) => (
                                <div key={m.id} className="flex items-center gap-3 p-2 bg-slate-50 rounded-xl">
                                    <Avatar className="h-7 w-7">
                                        {m.avatar_url && <AvatarImage src={m.avatar_url} />}
                                        <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">{m.name?.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}</AvatarFallback>
                                    </Avatar>
                                    <div className="flex-1 text-sm">{m.name}{m.id === conversation.created_by && <span className="ml-2 text-[10px] uppercase tracking-wider font-bold" style={{ color: RED }}>Creator</span>}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="flex gap-2 pt-2 border-t">
                        {isGroup && (
                            <Button variant="outline" onClick={leave} className="rounded-full flex-1" data-testid="leave-btn">
                                <LogOut className="h-4 w-4 mr-1.5" /> Leave
                            </Button>
                        )}
                        {(isCreator || isAdmin) && (
                            <Button variant="outline" onClick={deleteConv} className="rounded-full flex-1 text-destructive border-destructive/30 hover:bg-destructive/10" data-testid="delete-conv-btn">
                                <Trash2 className="h-4 w-4 mr-1.5" /> Delete
                            </Button>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
