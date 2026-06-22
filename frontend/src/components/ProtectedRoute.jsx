import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, adminOnly = false, allowInactive = false }) {
    const { user, loading } = useAuth();
    if (loading || user === null) {
        return (
            <div className="min-h-[50vh] grid place-items-center" data-testid="auth-loading">
                <div className="animate-pulse text-muted-foreground">Loading…</div>
            </div>
        );
    }
    if (!user) return <Navigate to="/login" replace />;
    if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
    // Inactive members are restricted to Home + Profile + the auth pages — they
    // can re-activate by contacting an officer (dues payment from dashboard is
    // explicitly NOT offered per the product decision). Admins bypass the gate
    // so they can still administer their chapter while their own status is
    // anything but active (edge case but harmless).
    if (!allowInactive && user.role !== "admin" && user.status_override === "inactive") {
        return <Navigate to="/" replace />;
    }
    return children;
}
