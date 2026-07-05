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
import { Plus, Send, Paperclip, X, Search, Users as UsersIcon, Trash2, LogOut, Settings, FileText, Image as ImageIcon, Download, ArrowLeft, Upload, Camera, Reply, Smile, Timer, AlarmClock, Video, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isToday, isYesterday } from "date-fns";

const NAVY = "#0A2463";
const RED = "#C8102E";

const EMOJI_CATEGORIES = {
    "Smileys": ["😀", "😁", "😂", "🤣", "😃", "😄", "😅", "😆", "😉", "😊", "😋", "😎", "😍", "🥰", "😘", "🥺", "🤔", "🤨", "😐", "😑"],
    "Gestures": ["👍", "👎", "👌", "🤞", "✌️", "🤟", "🤘", "👏", "🙌", "🙏", "💪", "✊", "🤝", "🫡", "🫶"],
    "Hearts": ["❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "💔", "❣️", "💕", "💖", "💗", "💘", "💝"],
    "Celebration": ["🎉", "🎊", "🥳", "🎂", "🎁", "🎈", "🍾", "🥂", "✨", "🌟", "⭐", "🔥", "💯"],
    "Symbols": ["✅", "❌", "⚠️", "💯", "💢", "💥", "💫", "💦", "💨", "🔴", "🟢", "🔵", "🟡"],
};

const TTL_OPTIONS = [
    { value: "off", label: "Off", icon: "—" },
    { value: "1h", label: "1 hour", icon: "1h" },
    { value: "24h", label: "24 hours", icon: "24h" },
    { value: "7d", label: "7 days", icon: "7d" },
];

function ttlLabel(v) {
    return TTL_OPTIONS.find((o) => o.value === v)?.label || "Off";
}

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
            <VideoMeetingModal />
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
            data-testid={`conversation-row-${conv.id}`}
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
    const [replyTo, setReplyTo] = useState(null);
    const scrollerRef = useRef(null);

    useEffect(() => {
        api.get(`/conversations/${conversation.id}/messages?limit=50`).then(({ data }) => {
            setMessages(data);
            setHasMore(data.length === 50);
            setTimeout(() => scrollToBottom("instant"), 50);
        }).catch(() => {});
        api.post(`/conversations/${conversation.id}/read`).catch(() => {});
        setReplyTo(null);
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
                <StartVideoMeetingButton conversation={conversation} />
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
                    <MessageBubble
                        key={g.msg.id}
                        message={g.msg}
                        mine={g.msg.sender_id === user.id}
                        showSender={conversation.type === "group" && g.msg.sender_id !== user.id}
                        allMessages={messages}
                        onReply={() => setReplyTo(g.msg)}
                    />
                ))}
            </div>

            <MessageComposer conversation={conversation} onSent={onSent} replyTo={replyTo} clearReply={() => setReplyTo(null)} />
        </>
    );
}

function MessageBubble({ message, mine, showSender, allMessages, onReply }) {
    const isDeleted = !!message.deleted_at;
    // Video meeting messages get a full-width actionable card instead of the
    // usual chat bubble. Renders whether the current user started it or not.
    if (!isDeleted && message.kind === "video_meeting" && message.meeting?.url) {
        return <VideoMeetingCard message={message} mine={mine} />;
    }
    const repliedTo = message.reply_to ? (allMessages || []).find((m) => m.id === message.reply_to) : null;
    const ttl = parseInt(message.ttl_seconds || 0, 10);
    return (
        <div className={`group flex gap-2 my-1.5 ${mine ? "justify-end" : "justify-start"}`} data-testid={`msg-${message.id}`}>
            {!mine && (
                <Avatar className="h-7 w-7 shrink-0 mt-1">
                    {message.sender_avatar && <AvatarImage src={message.sender_avatar} />}
                    <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">
                        {(message.sender_name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}
                    </AvatarFallback>
                </Avatar>
            )}
            <div className="flex items-center gap-1">
                {mine && !isDeleted && (
                    <button onClick={onReply} className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-primary p-1" title="Reply" data-testid={`reply-${message.id}`}>
                        <Reply className="h-3.5 w-3.5" />
                    </button>
                )}
                <div className={`max-w-[78%] sm:max-w-[65%] rounded-2xl px-3.5 py-2 ${mine ? "text-white rounded-br-sm" : "bg-white border border-slate-200 rounded-bl-sm"}`} style={mine ? { backgroundColor: NAVY } : {}}>
                    {showSender && <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: RED }}>{message.sender_name}</div>}
                    {repliedTo && (
                        <div className={`text-[11px] mb-1.5 border-l-2 pl-2 py-0.5 rounded-sm ${mine ? "border-white/40 bg-white/10" : "border-primary/40 bg-primary/5"}`}>
                            <div className={`font-bold ${mine ? "text-white/80" : "text-primary"}`}>{repliedTo.sender_name}</div>
                            <div className={`truncate ${mine ? "text-white/70" : "text-slate-500"}`}>
                                {repliedTo.body || (repliedTo.attachments?.length ? `📎 ${repliedTo.attachments[0].filename || "attachment"}` : "—")}
                            </div>
                        </div>
                    )}
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
                    <div className={`text-[10px] mt-1 flex items-center gap-1.5 ${mine ? "text-white/60" : "text-slate-400"}`}>
                        {format(parseISO(message.created_at), "h:mm a")}
                        {ttl > 0 && (
                            <span className="inline-flex items-center gap-0.5" title={`Disappears ${ttl/3600 >= 24 ? `${Math.round(ttl/86400)}d` : `${Math.round(ttl/3600)}h`} after first read`}>
                                <Timer className="h-2.5 w-2.5" />
                                {ttl >= 86400 ? `${Math.round(ttl/86400)}d` : `${Math.round(ttl/3600)}h`}
                            </span>
                        )}
                    </div>
                </div>
                {!mine && !isDeleted && (
                    <button onClick={onReply} className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-primary p-1" title="Reply" data-testid={`reply-${message.id}`}>
                        <Reply className="h-3.5 w-3.5" />
                    </button>
                )}
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

function MessageComposer({ conversation, onSent, replyTo, clearReply }) {
    const [text, setText] = useState("");
    const [attachments, setAttachments] = useState([]);
    const [busy, setBusy] = useState(false);
    const [uploading, setUploading] = useState(0);
    const [showEmoji, setShowEmoji] = useState(false);
    const [showTtl, setShowTtl] = useState(false);
    const [ttl, setTtl] = useState(null); // null = use conversation default
    const fileInputRef = useRef(null);
    const textareaRef = useRef(null);
    const emojiRef = useRef(null);
    const ttlRef = useRef(null);

    const effectiveTtl = ttl !== null ? ttl : (conversation.ttl || "off");

    useEffect(() => { setTtl(null); }, [conversation.id]);
    useEffect(() => {
        function onDown(e) {
            if (emojiRef.current && !emojiRef.current.contains(e.target)) setShowEmoji(false);
            if (ttlRef.current && !ttlRef.current.contains(e.target)) setShowTtl(false);
        }
        window.addEventListener("mousedown", onDown);
        return () => window.removeEventListener("mousedown", onDown);
    }, []);

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
            const payload = { body, attachments };
            if (replyTo) payload.reply_to = replyTo.id;
            if (ttl !== null) payload.ttl = ttl;  // explicit per-message override
            const { data } = await api.post(`/conversations/${conversation.id}/messages`, payload);
            onSent(data);
            setText(""); setAttachments([]); setTtl(null);
            clearReply?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Send failed");
        }
        setBusy(false);
    }

    function insertEmoji(e) {
        const ta = textareaRef.current;
        if (!ta) { setText((t) => t + e); return; }
        const start = ta.selectionStart ?? text.length;
        const end = ta.selectionEnd ?? text.length;
        const next = text.slice(0, start) + e + text.slice(end);
        setText(next);
        setTimeout(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = start + e.length; }, 0);
    }

    return (
        <div className="border-t bg-white p-3" data-testid="composer">
            {replyTo && (
                <div className="flex items-center gap-2 mb-2 bg-primary/5 border-l-4 border-primary rounded-r-xl pl-3 pr-2 py-2" data-testid="reply-preview">
                    <Reply className="h-4 w-4 text-primary shrink-0" />
                    <div className="flex-1 min-w-0 text-xs">
                        <div className="font-bold text-primary">Replying to {replyTo.sender_name}</div>
                        <div className="text-slate-500 truncate">{replyTo.body || (replyTo.attachments?.length ? `📎 ${replyTo.attachments[0].filename || "attachment"}` : "—")}</div>
                    </div>
                    <button onClick={clearReply} className="text-slate-400 hover:text-destructive p-1" data-testid="clear-reply-btn"><X className="h-3.5 w-3.5" /></button>
                </div>
            )}
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
            <div className="flex items-end gap-1.5">
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) => { upload(Array.from(e.target.files || [])); e.target.value = ""; }}
                    data-testid="file-input"
                />
                <Button variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()} disabled={busy || uploading > 0} className="shrink-0 rounded-full h-9 w-9" data-testid="attach-btn">
                    <Paperclip className="h-5 w-5" />
                </Button>
                {/* Emoji */}
                <div className="relative shrink-0" ref={emojiRef}>
                    <Button variant="ghost" size="icon" onClick={() => { setShowEmoji((s) => !s); setShowTtl(false); }} className="rounded-full h-9 w-9" data-testid="emoji-btn">
                        <Smile className="h-5 w-5" />
                    </Button>
                    {showEmoji && (
                        <div
                            className="fixed bottom-[5.5rem] left-1/2 -translate-x-1/2 w-[min(320px,calc(100vw-1.5rem))] max-h-[min(280px,45vh)] bg-white border border-slate-200 rounded-2xl shadow-warm-lg p-3 overflow-y-auto z-[60]"
                            data-testid="emoji-picker"
                        >
                            {Object.entries(EMOJI_CATEGORIES).map(([cat, list]) => (
                                <div key={cat} className="mb-2">
                                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 mb-1">{cat}</div>
                                    <div className="flex flex-wrap gap-1">
                                        {list.map((e) => (
                                            <button key={e} onClick={() => { insertEmoji(e); }} className="text-xl hover:bg-slate-100 rounded p-1 transition-colors" data-testid={`emoji-${e}`}>{e}</button>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                {/* TTL */}
                <div className="relative shrink-0" ref={ttlRef}>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => { setShowTtl((s) => !s); setShowEmoji(false); }}
                        className={`rounded-full h-9 w-9 ${effectiveTtl !== "off" ? "text-amber-500" : ""}`}
                        data-testid="ttl-btn"
                        title={effectiveTtl === "off" ? "Disappearing messages off" : `Disappears ${ttlLabel(effectiveTtl)} after seen`}
                    >
                        <AlarmClock className="h-5 w-5" />
                    </Button>
                    {showTtl && (
                        <div
                            className="fixed bottom-[5.5rem] left-1/2 -translate-x-1/2 w-[min(280px,calc(100vw-1.5rem))] bg-white border border-slate-200 rounded-2xl shadow-warm-lg p-2 z-[60]"
                            data-testid="ttl-picker"
                        >
                            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 px-2 pt-1 pb-1.5">Disappear after seen</div>
                            <div className="text-xs text-slate-400 px-2 pb-2 leading-snug">Conversation default: <span className="font-bold text-slate-600">{ttlLabel(conversation.ttl || "off")}</span></div>
                            {TTL_OPTIONS.map((o) => (
                                <button
                                    key={o.value}
                                    onClick={() => { setTtl(o.value); setShowTtl(false); }}
                                    className={`flex items-center gap-2 w-full px-3 py-1.5 rounded-lg text-sm hover:bg-slate-100 ${effectiveTtl === o.value ? "bg-primary/10 text-primary font-semibold" : ""}`}
                                    data-testid={`ttl-option-${o.value}`}
                                >
                                    <span className="w-8 text-[11px] font-bold text-slate-400">{o.icon}</span>
                                    {o.label}
                                </button>
                            ))}
                            {ttl !== null && (
                                <button onClick={() => { setTtl(null); setShowTtl(false); }} className="text-xs text-slate-500 hover:text-primary px-3 py-1 mt-1" data-testid="ttl-reset">Use conversation default</button>
                            )}
                        </div>
                    )}
                </div>
                <textarea
                    ref={textareaRef}
                    rows={1}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                    placeholder={uploading > 0 ? "Uploading…" : (replyTo ? `Reply to ${replyTo.sender_name}…` : "Type a message")}
                    className="flex-1 resize-none rounded-2xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 max-h-32"
                    data-testid="message-input"
                />
                <Button onClick={send} disabled={busy || (!text.trim() && attachments.length === 0)} className="rounded-full text-white shrink-0 h-9 w-9" style={{ backgroundColor: NAVY }} data-testid="send-btn">
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
                                            <img src={(process.env.REACT_APP_BACKEND_URL || "") + avatarUrl} alt="Group" className="w-full h-full object-contain" />
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

/* ---------- Embedded Jitsi meeting modal ---------- */
// Global controller so any component can trigger the same modal from a
// simple hook — avoids threading state through props for every join button.
let _openMeetingModalFn = null;
function openMeetingModal(meeting) {
    if (_openMeetingModalFn) _openMeetingModalFn(meeting);
}

function VideoMeetingModal() {
    const [meeting, setMeeting] = useState(null);
    useEffect(() => {
        _openMeetingModalFn = (m) => setMeeting(m);
        return () => { _openMeetingModalFn = null; };
    }, []);
    // Constrain the Jitsi URL with query params that skip Jitsi's own
    // pre-join screen and disable the mobile-app deep-link banner.
    const src = meeting?.url ? `${meeting.url}#config.prejoinPageEnabled=false&config.disableDeepLinking=true` : "";
    return (
        <Dialog open={!!meeting} onOpenChange={(o) => !o && setMeeting(null)}>
            <DialogContent
                className="p-0 gap-0 max-w-[100vw] w-[100vw] h-[100vh] sm:max-w-5xl sm:w-[95vw] sm:h-[85vh] sm:rounded-2xl flex flex-col overflow-hidden"
                data-testid="video-meeting-modal"
            >
                <div className="flex items-center gap-3 px-4 py-3 border-b bg-white shrink-0">
                    <div className="h-8 w-8 rounded-full grid place-items-center shrink-0" style={{ backgroundColor: NAVY, color: "#fff" }}>
                        <Video className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="font-heading font-bold text-sm truncate" style={{ color: NAVY }}>Video meeting</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-400 truncate">Powered by Jitsi · {meeting?.room}</div>
                    </div>
                    <a
                        href={meeting?.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-slate-500 hover:text-slate-800 underline hidden sm:inline"
                        data-testid="video-meeting-open-tab"
                    >Open in new tab</a>
                    <Button
                        variant="outline"
                        size="sm"
                        className="rounded-full"
                        onClick={() => setMeeting(null)}
                        data-testid="video-meeting-leave-btn"
                    >
                        <X className="h-3.5 w-3.5 mr-1" /> Leave
                    </Button>
                </div>
                {meeting && (
                    <iframe
                        title="Video meeting"
                        src={src}
                        // Full A/V + screen-share permissions delegated to Jitsi.
                        allow="camera; microphone; fullscreen; display-capture; autoplay; clipboard-write"
                        className="flex-1 w-full border-0"
                        data-testid="video-meeting-iframe"
                    />
                )}
            </DialogContent>
        </Dialog>
    );
}

/* ---------- Video meeting card (rendered inline in the thread) ---------- */
function VideoMeetingCard({ message, mine }) {
    const meeting = message.meeting || {};
    const starterName = meeting.started_by_name || message.sender_name || "Someone";
    const startedAt = message.created_at ? format(parseISO(message.created_at), "MMM d, h:mm a") : "";
    return (
        <div className="my-3 flex justify-center" data-testid={`video-meeting-card-${message.id}`}>
            <div className="w-full max-w-md rounded-2xl border-2 p-4 shadow-sm bg-gradient-to-br from-indigo-50 to-white" style={{ borderColor: NAVY }}>
                <div className="flex items-center gap-3 mb-3">
                    <div className="h-10 w-10 rounded-full grid place-items-center shrink-0" style={{ backgroundColor: NAVY, color: "#fff" }}>
                        <Video className="h-5 w-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="font-heading font-bold text-sm" style={{ color: NAVY }}>Video meeting started</div>
                        <div className="text-xs text-slate-500 truncate">{mine ? "You" : starterName} · {startedAt}</div>
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => openMeetingModal(meeting)}
                    className="flex items-center justify-center gap-2 w-full rounded-full py-2.5 text-sm font-bold text-white transition-colors hover:opacity-90"
                    style={{ backgroundColor: RED }}
                    data-testid={`join-meeting-${message.id}`}
                >
                    <Video className="h-4 w-4" /> Join meeting
                </button>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 text-center mt-2">Powered by Jitsi · opens in-app</div>
            </div>
        </div>
    );
}

/* ---------- Header "Start video meeting" button ---------- */
function StartVideoMeetingButton({ conversation }) {
    const [busy, setBusy] = useState(false);
    async function start() {
        if (busy) return;
        setBusy(true);
        try {
            const { data } = await api.post(`/conversations/${conversation.id}/video-meeting`);
            toast.success("Video meeting started — link posted in the chat");
            // Land the initiator directly into the embedded modal.
            if (data?.meeting) openMeetingModal(data.meeting);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Couldn't start meeting");
        } finally {
            setBusy(false);
        }
    }
    return (
        <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            onClick={start}
            disabled={busy}
            title="Start video meeting"
            data-testid="start-video-meeting-btn"
        >
            <Video className="h-4 w-4" />
        </Button>
    );
}

/* ---------- Add-members dialog (from ConversationSettings) ---------- */
function AddMembersDialog({ conversation, onAdded }) {
    const [open, setOpen] = useState(false);
    const [q, setQ] = useState("");
    const [candidates, setCandidates] = useState([]);
    const [selected, setSelected] = useState(new Set());
    const [busy, setBusy] = useState(false);
    const isDm = conversation.type === "dm";

    useEffect(() => {
        if (!open) return;
        api.get("/members").then(({ data }) => setCandidates(data)).catch(() => setCandidates([]));
        setSelected(new Set());
        setQ("");
    }, [open]);

    const existingIds = new Set(conversation.member_ids || conversation.members?.map((m) => m.id) || []);
    const filtered = candidates
        .filter((m) => !existingIds.has(m.id))
        .filter((m) => {
            const query = q.trim().toLowerCase();
            if (!query) return true;
            return (m.name || "").toLowerCase().includes(query) || (m.email || "").toLowerCase().includes(query);
        })
        .slice(0, 100);

    function toggle(id) {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }

    async function submit() {
        if (selected.size === 0) return;
        setBusy(true);
        try {
            await api.put(`/conversations/${conversation.id}`, { add_member_ids: [...selected] });
            toast.success(isDm && selected.size > 0
                ? `Added ${selected.size} member${selected.size > 1 ? "s" : ""} — chat converted to group`
                : `Added ${selected.size} member${selected.size > 1 ? "s" : ""}`);
            setOpen(false);
            onAdded?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed to add members");
        } finally {
            setBusy(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="rounded-full w-full" data-testid="add-members-btn">
                    <UserPlus className="h-4 w-4 mr-1.5" /> Add members
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md" data-testid="add-members-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl" style={{ color: NAVY }}>Add members</DialogTitle>
                </DialogHeader>
                {isDm && (
                    <div className="text-xs bg-amber-50 border border-amber-200 rounded-xl p-3 text-amber-800" data-testid="dm-convert-notice">
                        Adding people will convert this DM into a group chat. Message history is preserved.
                    </div>
                )}
                <div className="relative mt-2">
                    <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder="Search members…"
                        className="pl-9 rounded-xl"
                        data-testid="add-members-search"
                    />
                </div>
                <div className="max-h-72 overflow-y-auto space-y-1 mt-2">
                    {filtered.length === 0 && (
                        <div className="text-center text-xs text-slate-500 py-6">
                            {q.trim() ? "No matches." : "Everyone else is already in this chat."}
                        </div>
                    )}
                    {filtered.map((m) => {
                        const on = selected.has(m.id);
                        return (
                            <button
                                key={m.id}
                                type="button"
                                onClick={() => toggle(m.id)}
                                className={`w-full text-left flex items-center gap-3 p-2 rounded-xl border-2 transition-colors ${on ? "border-primary bg-primary/5" : "border-transparent hover:bg-slate-50"}`}
                                data-testid={`add-member-row-${m.id}`}
                            >
                                <Avatar className="h-8 w-8">
                                    {m.avatar_url && <AvatarImage src={m.avatar_url} />}
                                    <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">
                                        {(m.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}
                                    </AvatarFallback>
                                </Avatar>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-semibold truncate">{m.name}</div>
                                    <div className="text-xs text-slate-500 truncate">{m.email}</div>
                                </div>
                                {on && <div className="text-primary text-xs font-bold">Selected</div>}
                            </button>
                        );
                    })}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full" data-testid="add-members-cancel">Cancel</Button>
                    <Button
                        onClick={submit}
                        disabled={busy || selected.size === 0}
                        className="rounded-full text-white"
                        style={{ backgroundColor: NAVY }}
                        data-testid="add-members-submit"
                    >
                        {busy ? "Adding…" : `Add ${selected.size || ""}`.trim()}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}



/* ---------- One row in the settings members list ---------- */
function MemberRow({ member, conversation, viewerId, canModerate, isCreator, onChanged }) {
    const [busy, setBusy] = useState(false);
    const isSelf = member.id === viewerId;
    const isTheCreator = member.id === conversation.created_by;
    const isGroupAdmin = (conversation.admin_ids || []).includes(member.id);
    const isGroup = conversation.type === "group";

    async function toggleAdmin() {
        if (busy) return;
        setBusy(true);
        try {
            const key = isGroupAdmin ? "demote_ids" : "promote_ids";
            await api.put(`/conversations/${conversation.id}`, { [key]: [member.id] });
            toast.success(isGroupAdmin ? `${member.name} is no longer an admin` : `${member.name} is now a group admin`);
            onChanged();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        } finally { setBusy(false); }
    }

    async function removeFromGroup() {
        if (busy) return;
        if (!confirm(`Remove ${member.name} from this group?`)) return;
        setBusy(true);
        try {
            await api.put(`/conversations/${conversation.id}`, { remove_member_ids: [member.id] });
            toast.success(`${member.name} removed`);
            onChanged();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Failed");
        } finally { setBusy(false); }
    }

    return (
        <div className="flex items-center gap-3 p-2 bg-slate-50 rounded-xl" data-testid={`chat-member-row-${member.id}`}>
            <Avatar className="h-8 w-8">
                {member.avatar_url && <AvatarImage src={member.avatar_url} />}
                <AvatarFallback className="bg-primary/15 text-primary text-xs font-bold">
                    {member.name?.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase()}
                </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold truncate">{member.name}{isSelf && <span className="ml-1.5 text-[10px] text-slate-400">(you)</span>}</div>
                <div className="flex flex-wrap gap-1 mt-0.5">
                    {isTheCreator && <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-full text-white" style={{ backgroundColor: RED }} data-testid={`chat-member-creator-${member.id}`}>Creator</span>}
                    {!isTheCreator && isGroupAdmin && <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800" data-testid={`chat-member-admin-${member.id}`}>Admin</span>}
                </div>
            </div>
            {isGroup && !isSelf && !isTheCreator && (
                <div className="flex items-center gap-1 shrink-0">
                    {isCreator && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="rounded-full h-7 px-2 text-xs"
                            onClick={toggleAdmin}
                            disabled={busy}
                            data-testid={`chat-member-toggle-admin-${member.id}`}
                            title={isGroupAdmin ? "Remove admin role" : "Make group admin"}
                        >
                            {isGroupAdmin ? "Remove admin" : "Make admin"}
                        </Button>
                    )}
                    {canModerate && (
                        <button
                            type="button"
                            onClick={removeFromGroup}
                            disabled={busy}
                            className="text-slate-400 hover:text-destructive p-1 rounded"
                            title="Remove from group"
                            data-testid={`chat-member-remove-${member.id}`}
                        >
                            <X className="h-3.5 w-3.5" />
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

function ConversationSettings({ conversation, onChanged }) {    const { user } = useAuth();
    const [open, setOpen] = useState(false);
    const [name, setName] = useState(conversation.raw_name || "");
    const isGroup = conversation.type === "group";
    const isDm = conversation.type === "dm";
    // "Creator" here is the effective role — org-level admins moderate every chat.
    const isCreator = conversation.created_by === user.id || user.role === "admin";
    const isAdmin = user.role === "admin";
    const groupAdminIds = conversation.admin_ids || [];
    const isGroupAdmin = isCreator || groupAdminIds.includes(user.id);
    // Who can moderate the roster (add/remove).
    const canModerate = isGroupAdmin;
    const policy = conversation.member_add_policy || "admins_only";
    // Who sees the "Add members" button in the sheet.
    const canAdd = isDm || isGroupAdmin || (isGroup && policy === "anyone");

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
                        <Label className="text-xs">Disappearing messages</Label>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 mt-1.5" data-testid="ttl-conv-grid">
                            {TTL_OPTIONS.map((o) => (
                                <button
                                    key={o.value}
                                    onClick={async () => {
                                        try {
                                            await api.put(`/conversations/${conversation.id}`, { ttl: o.value });
                                            toast.success(o.value === "off" ? "Disappearing off" : `Set to ${o.label} after seen`);
                                            onChanged();
                                        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
                                    }}
                                    className={`text-xs rounded-xl py-2 font-semibold border-2 transition-all ${conversation.ttl === o.value ? "border-primary bg-primary text-white" : "border-slate-200 bg-white text-slate-600 hover:border-primary/40"}`}
                                    data-testid={`ttl-conv-${o.value}`}
                                >
                                    {o.label}
                                </button>
                            ))}
                        </div>
                        <p className="text-xs text-slate-500 mt-1.5">Timer starts after the first recipient reads the message. You can still override this per-message from the composer.</p>
                    </div>
                    <div>
                        <Label className="text-xs">Members ({conversation.members?.length || 0})</Label>
                        <div className="mt-2 space-y-1.5 max-h-72 overflow-y-auto" data-testid="chat-members-list">
                            {conversation.members?.map((m) => (
                                <MemberRow
                                    key={m.id}
                                    member={m}
                                    conversation={conversation}
                                    viewerId={user.id}
                                    canModerate={canModerate}
                                    isCreator={isCreator}
                                    onChanged={onChanged}
                                />
                            ))}
                        </div>
                        {isGroup && isCreator && (
                            <div className="mt-3 flex items-center justify-between gap-3 bg-slate-50 rounded-xl p-3" data-testid="member-add-policy">
                                <div className="text-xs flex-1">
                                    <div className="font-semibold text-slate-700">Who can add members?</div>
                                    <div className="text-slate-500 mt-0.5">Creator and admins can always add. Turn this on to let everyone in the group invite too.</div>
                                </div>
                                <button
                                    type="button"
                                    onClick={async () => {
                                        const next = policy === "anyone" ? "admins_only" : "anyone";
                                        try {
                                            await api.put(`/conversations/${conversation.id}`, { member_add_policy: next });
                                            toast.success(next === "anyone" ? "Anyone can add members now" : "Only admins can add members");
                                            onChanged();
                                        } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
                                    }}
                                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${policy === "anyone" ? "bg-primary" : "bg-slate-300"}`}
                                    data-testid="member-add-policy-toggle"
                                    aria-checked={policy === "anyone"}
                                    role="switch"
                                >
                                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${policy === "anyone" ? "translate-x-6" : "translate-x-1"}`} />
                                </button>
                            </div>
                        )}
                        {canAdd && (
                            <div className="mt-2">
                                <AddMembersDialog conversation={conversation} onAdded={() => { setOpen(false); onChanged(); }} />
                            </div>
                        )}
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
