import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { format, parseISO } from "date-fns";

export default function News() {
    const [items, setItems] = useState([]);
    useEffect(() => {
        api.get("/news").then(({ data }) => setItems(data)).catch(() => {});
    }, []);
    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">News & stories</h1>
            <p className="text-muted-foreground mt-2">Updates from around the club.</p>
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
                                <img src={n.cover_image} alt={n.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                            )}
                        </div>
                        <div className="p-6">
                            <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                <span>{n.created_at && format(parseISO(n.created_at), "MMM d, yyyy")}</span>
                                {n.tags?.[0] && <span className="bg-secondary/40 rounded-full px-2 py-0.5 uppercase tracking-wider text-[10px] font-semibold">{n.tags[0]}</span>}
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
