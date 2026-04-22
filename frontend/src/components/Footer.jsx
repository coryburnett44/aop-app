import { Link } from "react-router-dom";

export default function Footer() {
    return (
        <footer className="mt-24 border-t border-border bg-muted/30" data-testid="footer">
            <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12 grid md:grid-cols-4 gap-10">
                <div>
                    <div className="flex items-center gap-2 mb-4">
                        <div className="w-9 h-9 rounded-2xl bg-primary text-primary-foreground grid place-items-center font-heading font-black">
                            C
                        </div>
                        <span className="font-heading font-bold text-xl">ClubHaven</span>
                    </div>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                        A warm digital home for the club — events, members, and stories, all in one place.
                    </p>
                </div>
                <div>
                    <h4 className="font-heading font-semibold mb-3">Club</h4>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                        <li><Link to="/events" className="hover:text-primary">Events</Link></li>
                        <li><Link to="/directory" className="hover:text-primary">Member directory</Link></li>
                        <li><Link to="/news" className="hover:text-primary">News</Link></li>
                    </ul>
                </div>
                <div>
                    <h4 className="font-heading font-semibold mb-3">About</h4>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                        <li><Link to="/page/about" className="hover:text-primary">About us</Link></li>
                        <li><Link to="/page/contact" className="hover:text-primary">Contact</Link></li>
                    </ul>
                </div>
                <div>
                    <h4 className="font-heading font-semibold mb-3">Join</h4>
                    <p className="text-sm text-muted-foreground leading-relaxed mb-3">
                        Become a member and get access to everything.
                    </p>
                    <Link
                        to="/register"
                        className="inline-flex items-center rounded-full bg-primary text-primary-foreground px-4 py-2 text-sm font-medium shadow-warm hover:-translate-y-0.5 transition-transform"
                        data-testid="footer-join-btn"
                    >
                        Join today
                    </Link>
                </div>
            </div>
            <div className="border-t border-border">
                <div className="max-w-7xl mx-auto px-6 lg:px-10 py-4 text-xs text-muted-foreground">
                    © {new Date().getFullYear()} ClubHaven. Built with warmth.
                </div>
            </div>
        </footer>
    );
}
