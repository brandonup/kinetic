"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";

const NAV_ITEMS = [
  { label: "Users", href: "/admin/users", activePrefix: "/admin/users" },
  { label: "LLM Models", href: "/admin/models", activePrefix: "/admin/models" },
  { label: "RAG Debug", href: "/admin/rag-debug", activePrefix: "/admin/rag-debug" },
  { label: "Request Trace", href: "/admin/request-trace", activePrefix: "/admin/request-trace" },
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

        // Use RPC to check admin status — avoids RLS restrictions on the users table.
        const { data: isAdminResult, error } = await supabase.rpc("is_admin");
        if (mounted) {
          if (isAdminResult === true) {
            setIsAdmin(true);
          } else {
            router.push("/projects");
          }
        }
      } catch (err) {
        console.error("[admin-layout] checkAdminAccess error:", err);
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
  }, [router]); // removed `loading` — including it caused the effect to double-fire

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
