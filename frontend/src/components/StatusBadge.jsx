import React from "react";

const styles = {
    draft: "bg-slate-100 text-slate-700 border-slate-200",
    sent: "bg-amber-50 text-amber-700 border-amber-200",
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
    overdue: "bg-red-50 text-red-700 border-red-200",
};

export const StatusBadge = ({ status = "draft" }) => {
    const cls = styles[status] || styles.draft;
    return (
        <span
            data-testid={`status-badge-${status}`}
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-[0.12em] border ${cls}`}
        >
            {status}
        </span>
    );
};

export default StatusBadge;
