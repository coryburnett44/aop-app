import React from "react";

export const InvoiceHeader = ({ size = "default" }) => {
    const titleClass =
        size === "large"
            ? "font-heading text-6xl sm:text-7xl md:text-8xl lg:text-9xl font-black tracking-tighter uppercase text-slate-900 leading-[0.85]"
            : "font-heading text-5xl sm:text-6xl md:text-7xl font-black tracking-tighter uppercase text-slate-900 leading-[0.85]";

    return (
        <div data-testid="invoice-brand-header" className="select-none">
            <h1 className={titleClass} data-testid="invoice-title">
                CORY BURNETT
            </h1>
            <p
                className="text-base sm:text-lg font-normal tracking-normal text-slate-600 mt-3"
                data-testid="invoice-subtitle"
            >
                or Overflow Investment Legacy
            </p>
        </div>
    );
};

export default InvoiceHeader;
