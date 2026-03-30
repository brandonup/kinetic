"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";

/**
 * Kinetic login page — Google OAuth only (no passwords, no magic link).
 *
 * Auth pattern (KIN-252, KIN-363):
 *   Google OAuth → Supabase OAuth flow → redirects to /auth/callback
 *
 * Auth callback route handles session exchange: app/auth/callback/route.ts
 */
export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const { toast } = useToast();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);

  // Thread `redirectTo` through the auth callback so middleware redirects
  // land users back at the page they originally requested.
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const redirectTo = searchParams.get("redirectTo") ?? "/projects";
  const callbackUrl = `${origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}`;

  const handleGoogleOAuth = async () => {
    setLoading(true);

    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: callbackUrl,
        },
      });

      if (error) {
        toast({
          variant: "destructive",
          title: "Error",
          description: error.message,
        });
        setLoading(false);
      }
      // On success, browser navigates — no state update needed.
    } catch {
      toast({
        variant: "destructive",
        title: "Error",
        description: "An unexpected error occurred. Please try again.",
      });
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <Card className="w-[400px]">
        <CardHeader>
          <CardTitle>Sign in to Kinetic</CardTitle>
          <CardDescription>
            Continue with your Google account to get started.
          </CardDescription>
        </CardHeader>

        <CardFooter>
          <Button
            className="w-full"
            disabled={loading}
            onClick={handleGoogleOAuth}
          >
            {loading ? "Signing in..." : "Continue with Google"}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
