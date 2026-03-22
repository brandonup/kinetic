"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";
import { API_BASE_URL } from "@/lib/api";

const NAV_ITEMS = [
  { label: "Users", href: "/admin/users", activePrefix: "/admin/users" },
  { label: "LLM Models", href: "/admin/models", activePrefix: "/admin/models" },
  { label: "Back to App", href: "/projects", activePrefix: null },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let mounted = true;

    const safetyTimeout = setTimeout(() => {
      if (mounted && loading) {
        router.push("/projects");
      }
    }, 8000);

    const checkAdminAccess = async () => {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();

        if (!mounted) return;
        if (!session) {
          router.push("/login");
          return;
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const response = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        if (!mounted) return;

        if (response.status === 403) {
          router.push("/projects");
          return;
        }

        if (response.ok) {
          setIsAdmin(true);
        } else {
          router.push("/projects");
        }
      } catch {
        if (!mounted) return;
        router.push("/projects");
      } finally {
        if (mounted) {
          setLoading(false);
          clearTimeout(safetyTimeout);
        }
      }
    };

    checkAdminAccess();

    return () => {
      mounted = false;
      clearTimeout(safetyTimeout);
    };
  }, [router, loading]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-muted-foreground text-sm">Checking admin access…</p>
      </div>
    );
  }

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-border">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-foreground">Admin</h1>
          <div className="flex gap-2">
            {NAV_ITEMS.map((item) => {
              const isActive = item.activePrefix
                ? pathname?.startsWith(item.activePrefix)
                : false;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>
      <main className="w-full">{children}</main>
    </div>
  );
}
