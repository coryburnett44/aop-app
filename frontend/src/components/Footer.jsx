import { Link } from "react-router-dom";
import { useSiteSettings } from "../context/SiteSettingsContext";

export default function Footer() {
    const { settings } = useSiteSettings();
    const customText = settings?.footer_text;
    const customLinks = settings?.footer_links;
    return (
        <footer className="mt-24 text-white" style={{ backgroundColor: "#0A2463" }} data-testid="footer">
            {/* Patriotic top stripe */}
            <div className="h-1 flex">
                <div className="flex-1" style={{ backgroundColor: "#C8102E" }} />
                <div className="flex-1 bg-white" />
                <div className="flex-1" style={{ backgroundColor: "#0A2463" }} />
            </div>

            <div className="max-w-7xl mx-auto px-6 lg:px-10 py-14 grid md:grid-cols-4 gap-10">
                <div className="md:col-span-2">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-11 h-11 rounded-2xl grid place-items-center font-heading font-black text-lg" style={{ backgroundColor: "#C8102E" }}>
                            A
                        </div>
                        <div>
                            <div className="font-heading font-bold text-xl leading-tight">Alpha Omega Phi</div>
                            <div className="text-xs opacity-75">Military Fraternity &amp; Sorority, Inc.</div>
                        </div>
                    </div>
                    <p className="text-sm opacity-80 leading-relaxed max-w-md">
                        A 501(c)(3) nonprofit. United across branches, dedicated to fellowship, service, and supporting
                        our nation's veterans and the communities they call home.
                    </p>
                </div>
                <div>
                    <h4 className="font-heading font-bold mb-3 text-sm uppercase tracking-wider opacity-90">Members</h4>
                    <ul className="space-y-2 text-sm opacity-80">
                        <li><Link to="/events" className="hover:text-white hover:opacity-100">Events</Link></li>
                        <li><Link to="/directory" className="hover:text-white hover:opacity-100">Member directory</Link></li>
                        <li><Link to="/chapters" className="hover:text-white hover:opacity-100">Chapters</Link></li>
                        <li><Link to="/awards" className="hover:text-white hover:opacity-100">Awards</Link></li>
                        <li><Link to="/hours" className="hover:text-white hover:opacity-100">Volunteer hours</Link></li>
                    </ul>
                </div>
                <div>
                    <h4 className="font-heading font-bold mb-3 text-sm uppercase tracking-wider opacity-90">Resources</h4>
                    <ul className="space-y-2 text-sm opacity-80">
                        <li><Link to="/photos" className="hover:text-white hover:opacity-100">Photo gallery</Link></li>
                        <li><Link to="/documents" className="hover:text-white hover:opacity-100">Documents</Link></li>
                        <li><Link to="/news" className="hover:text-white hover:opacity-100">News &amp; stories</Link></li>
                        <li><Link to="/page/about" className="hover:text-white hover:opacity-100">About</Link></li>
                        <li><Link to="/page/contact" className="hover:text-white hover:opacity-100">Contact</Link></li>
                    </ul>
                </div>
            </div>
            <div className="border-t border-white/20">
                <div className="max-w-7xl mx-auto px-6 lg:px-10 py-4 flex flex-wrap items-center justify-between gap-3 text-xs opacity-80">
                    <span data-testid="footer-text">{customText || `© ${new Date().getFullYear()} Alpha Omega Phi Military Fraternity & Sorority, Inc. All rights reserved.`}</span>
                    {customLinks && customLinks.length > 0 && (
                        <span className="flex flex-wrap gap-x-3 gap-y-1" data-testid="footer-links">
                            {customLinks.map((l, i) => (
                                <a key={i} href={l.href} className="hover:text-white hover:opacity-100">{l.label}</a>
                            ))}
                        </span>
                    )}
                    <span className="uppercase tracking-widest font-bold">Trendsetters</span>
                </div>
            </div>
        </footer>
    );
}
