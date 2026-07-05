import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { format, parseISO } from "date-fns";
import { Search } from "lucide-react";

export default function News() {
    const [items, setItems] = useState([]);
    const [q, setQ] = useState("");
    const [loading, setLoading] = useState(false);

    // Debounce the search input so we don't hammer the API on every keystroke.
    useEffect(() => {
        const handle = setTimeout(() => {
            setLoading(true);
            const params = q.trim() ? { q: q.trim() } : {};
            api.get("/news", { params })
                .then(({ data }) => setItems(data))
                .catch(() => {})
                .finally(() => setLoading(false));
        }, 250);
        return () => clearTimeout(handle);
    }, [q]);

    const empty = !loading && items.length === 0;

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                <div>
                    <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">News & stories</h1>
                    <p className="text-muted-foreground mt-2">Updates from around the club.</p>
                </div>
                <div className="relative w-full sm:w-80">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <input
                        type="search"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder="Search articles…"
                        className="w-full rounded-full border border-border bg-card pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                        data-testid="news-search-input"
                    />
                </div>
            </div>
            {empty && (
                <div className="mt-16 text-center text-muted-foreground" data-testid="news-empty">
                    {q.trim() ? `No articles match "${q.trim()}".` : "No articles yet."}
                </div>
            )}
            <div className="mt-10 grid md:grid-cols-2 gap-8">
                {items.map((n) => (
                    <Link
                        key={n.id}
                        to={`/news/${n.id}`}
                        className="group block rounded-2xl overflow-hidden bg-card border border-border hover:-translate-y-1 hover:shadow-warm transition-all"
                        data-testid={`news-card-${n.id}`}
                    >
                        <div className="aspect-[16/10] overflow-hidden bg-muted">
                            {n.cover_image && (
                                <img src={n.cover_image} alt={n.title} className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-500" />
                            )}
                        </div>
                        <div className="p-6">
                            <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                <span>{n.created_at && format(parseISO(n.created_at), "MMM d, yyyy")}</span>
                                {n.tags?.[0] && <span className="bg-secondary/40 rounded-full px-2 py-0.5 uppercase tracking-wider text-[10px] font-semibold">{n.tags[0]}</span>}
                                {n.template && n.template !== "classic" && (
                                    <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 uppercase tracking-wider text-[10px] font-semibold">{templateLabel(n.template)}</span>
                                )}
                            </div>
                            <h3 className="font-heading text-2xl font-semibold mt-3 leading-tight">{n.title}</h3>
                            <p className="text-sm text-muted-foreground mt-3 leading-relaxed line-clamp-3">{n.summary}</p>
                        </div>
                    </Link>
                ))}
            </div>
        </div>
    );
}

function templateLabel(tpl) {
    const map = {
        two_col: "2 cols",
        three_col: "3 cols",
        image_left: "image left",
        image_right: "image right",
        gallery: "gallery",
        hero: "hero",
    };
    return map[tpl] || tpl;
}
