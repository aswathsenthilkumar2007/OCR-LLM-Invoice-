import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({ variant = "secondary", className = "", children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; children: ReactNode }) {
  return <button className={`button button-${variant} ${className}`} {...props}>{children}</button>;
}

export function Card({ className = "", children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <section className={`surface-card ${className}`} {...props}>{children}</section>;
}

export function StatusBadge({ children, tone }: { children: ReactNode; tone: string }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}

export function IconButton({ label, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return <button className={`icon-button ${className}`} aria-label={label} title={label} {...props}>{children}</button>;
}
