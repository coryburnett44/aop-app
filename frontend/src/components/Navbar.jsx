import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { mediaUrl } from "../lib/api";
import { Button } from "./ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import {
    DropdownMenu,
    DropdownMenuTrigger,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuLabel,
} from "./ui/dropdown-menu";
import { Sparkles, Menu } from "lucide-react";
import { useState } from "react";
import { useSiteSettings } from "../context/SiteSettingsContext";

const LINKS = [
    { to: "/calendar", slug: "calendar", label: "Calendar" },
    { to: "/events", slug: "events", label: "Events" },
    { to: "/directory", slug: "directory", label: "Members" },
    { to: "/chat", slug: "chat", label: "Chat" },
    { to: "/chapters", slug: "chapters", label: "Chapters" },
    { to: "/photos", slug: "photos", label: "Photos" },
    { to: "/documents", slug: "documents", label: "AOP Forms" },
    { to: "/awards", slug: "awards", label: "Awards" },
    { to: "/gear", slug: "gear", label: "Gear" },
    { to: "/donations", slug: "donations", label: "Donate" },
    { to: "/omega", slug: "omega", label: "Omega" },
    { to: "/news", slug: "news", label: "News" },
    { to: "/schedule-meeting", slug: "schedule-meeting", label: "Meet" },
];

export default function Navbar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const { settings } = useSiteSettings();
    const navOverrides = settings?.nav_labels || {};
    const links = LINKS.map((l) => ({ ...l, label: navOverrides[l.slug] || l.label }));

    const initials = (user?.name || user?.email || "U")
        .split(" ")
        .map((s) => s[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();

    return (
        <header
            className="sticky top-0 z-40 backdrop-blur-xl bg-[hsl(40_33%_98%_/_0.75)] border-b border-orange-900/10"
            data-testid="main-navbar"
        >
            <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center justify-between gap-4">
                <Link to="/" className="flex items-center gap-2 group shrink-0" data-testid="nav-logo">
                    <img
                        src="https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/k67x4iui_Trendsetters%20logo.png"
                        alt="Alpha Omega Phi"
                        className="h-9 w-9 rounded-2xl object-cover shadow-warm group-hover:rotate-6 transition-transform"
                    />
                    <span className="font-heading font-bold text-xl tracking-tight leading-tight whitespace-nowrap">
                        Alpha<span className="text-[#D62828]"> Omega Phi</span>
                    </span>
                </Link>

                <nav className="hidden xl:flex items-center gap-1">
                    {user && links.map((l) => (
                        <NavLink
                            key={l.to}
                            to={l.to}
                            data-testid={`nav-link-${l.label.toLowerCase()}`}
                            className={({ isActive }) =>
                                `px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                                    isActive
                                        ? "bg-primary/10 text-primary"
                                        : "text-foreground/70 hover:text-foreground hover:bg-muted"
                                }`
                            }
                        >
                            {l.label}
                        </NavLink>
                    ))}
                </nav>

                <div className="flex items-center gap-2">
                    {user && user !== false ? (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <button
                                    className="flex items-center gap-2 rounded-full pl-1 pr-3 py-1 bg-muted hover:bg-muted/70 transition-colors"
                                    data-testid="nav-user-menu"
                                >
                                    <Avatar className="h-8 w-8 border border-border">
                                        {user.avatar_url ? <AvatarImage src={mediaUrl(user.avatar_url)} alt={user.name} /> : null}
                                        <AvatarFallback className="bg-primary/15 text-primary font-semibold text-xs">
                                            {initials}
                                        </AvatarFallback>
                                    </Avatar>
                                    <span className="hidden sm:inline text-sm font-medium truncate max-w-[120px]">
                                        {user.name || user.email}
                                    </span>
                                </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56">
                                <DropdownMenuLabel className="font-heading">
                                    {user.name}
                                    <div className="text-xs font-sans text-muted-foreground font-normal">
                                        {user.email}
                                    </div>
                                </DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => navigate("/profile")} data-testid="menu-profile">
                                    My Profile
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => navigate("/profile?tab=events")} data-testid="menu-my-events">
                                    My Events
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => navigate("/hours")} data-testid="menu-hours">
                                    Volunteer hours
                                </DropdownMenuItem>
                                {user.role === "admin" && (
                                    <>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={() => navigate("/admin")} data-testid="menu-admin">
                                            <Sparkles className="h-4 w-4 mr-2 text-primary" />
                                            Admin Console
                                        </DropdownMenuItem>
                                    </>
                                )}
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                    onClick={async () => {
                                        await logout();
                                        navigate("/");
                                    }}
                                    data-testid="menu-logout"
                                >
                                    Log out
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    ) : (
                        <Button
                            className="rounded-full bg-primary hover:bg-primary/90 shadow-warm"
                            onClick={() => navigate("/login")}
                            data-testid="nav-login-btn"
                        >
                            Member login
                        </Button>
                    )}
                    <button
                        className={`xl:hidden rounded-full p-2 hover:bg-muted ${!user ? "hidden" : ""}`}
                        onClick={() => setOpen(!open)}
                        data-testid="mobile-menu-btn"
                        aria-label="Menu"
                    >
                        <Menu className="h-5 w-5" />
                    </button>
                </div>
            </div>
            {open && user && (
                <div className="xl:hidden border-t border-border bg-background/95 backdrop-blur-xl" data-testid="mobile-menu">
                    <div className="px-6 py-3 flex flex-col gap-1">
                        {links.map((l) => (
                            <NavLink
                                key={l.to}
                                to={l.to}
                                onClick={() => setOpen(false)}
                                className={({ isActive }) =>
                                    `px-4 py-2 rounded-xl text-sm font-medium ${
                                        isActive ? "bg-primary/10 text-primary" : "hover:bg-muted"
                                    }`
                                }
                            >
                                {l.label}
                            </NavLink>
                        ))}
                    </div>
                </div>
            )}
        </header>
    );
}
