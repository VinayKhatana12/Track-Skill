"use client";

import {
  BarChart3,
  BotMessageSquare,
  CheckCheck,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/api";

export interface SidebarSection {
  id: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const ROLE_SECTIONS: Record<UserRole, SidebarSection[]> = {
  PROVIDER: [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "trainees", label: "Trainees", icon: Radar },
    { id: "followups", label: "Follow-ups", icon: Radar },
    { id: "insights", label: "Insights", icon: BarChart3 },
  ],
  TRAINEE: [
    { id: "journey", label: "My Journey", icon: LayoutDashboard },
    { id: "consent", label: "Consent", icon: ShieldCheck },
    { id: "messages", label: "Messages", icon: BotMessageSquare },
    { id: "skills", label: "Skills", icon: Radar },
  ],
  EMPLOYER: [
    { id: "verify", label: "Verify", icon: CheckCheck },
    { id: "hires", label: "Hires", icon: LayoutDashboard },
    { id: "talent", label: "Talent pool", icon: Radar },
    { id: "impact", label: "Impact", icon: BarChart3 },
  ],
  ADMIN: [
    { id: "governance", label: "Governance", icon: LayoutDashboard },
    { id: "providers", label: "Providers", icon: Radar },
    { id: "gaps", label: "Gaps", icon: BarChart3 },
    { id: "activity", label: "Activity", icon: ShieldCheck },
  ],
};

export function AppSidebar({ role }: { role: UserRole }) {
  const collapsedStored =
    typeof window !== "undefined" &&
    window.localStorage.getItem(`sidebar-collapsed-${role}`) === "1";
  const [collapsed, setCollapsed] = useState(collapsedStored);

  useEffect(() => {
    window.localStorage.setItem(
      `sidebar-collapsed-${role}`,
      collapsed ? "1" : "0",
    );
  }, [collapsed, role]);

  const sections = ROLE_SECTIONS[role];

  return (
    <aside
      data-collapsed={collapsed || undefined}
      className={cn(
        "sticky top-16 hidden h-[calc(100dvh-4rem)] shrink-0 flex-col border-r border-border/70 bg-card transition-[width] md:flex",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <nav aria-label="Dashboard sections" className="flex flex-1 flex-col gap-1 p-2">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <a
              key={section.id}
              href={`#${section.id}`}
              title={section.label}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                collapsed && "justify-center px-2",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {!collapsed && <span>{section.label}</span>}
            </a>
          );
        })}
      </nav>
      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="flex items-center justify-center gap-2 border-t border-border/60 py-3 text-muted-foreground hover:bg-accent hover:text-foreground w-full"
      >
        {collapsed ? (
          <PanelLeftOpen className="h-4 w-4" aria-hidden />
        ) : (
          <>
            <PanelLeftClose className="h-4 w-4" aria-hidden />
            <span className="text-xs">Collapse</span>
          </>
        )}
      </button>
    </aside>
  );
}

export function BottomTabs({ role }: { role: UserRole }) {
  const sections = ROLE_SECTIONS[role];
  return (
    <nav
      aria-label="Dashboard sections"
      className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-4 border-t border-border bg-background md:hidden"
    >
      {sections.map((section) => {
        const Icon = section.icon;
        return (
          <a
            key={section.id}
            href={`#${section.id}`}
            className="flex flex-col items-center gap-0.5 py-2.5 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <Icon className="h-4 w-4" aria-hidden />
            {section.label}
          </a>
        );
      })}
    </nav>
  );
}
