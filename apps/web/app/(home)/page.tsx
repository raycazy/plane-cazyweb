/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

"use client";

import React, { useState } from "react";
// components
import { AuthBase } from "@/components/auth-screens/auth-base";
// helpers
import { EAuthModes, EPageTypes } from "@/helpers/authentication.helper";
// layouts
import DefaultLayout from "@/layouts/default-layout";
// wrappers
import { AuthenticationWrapper } from "@/lib/wrappers/authentication-wrapper";

// cazyweb SSO page — shown to unauthenticated users visiting pm.cazyweb.com.
// Append ?fallback=1 to the URL to reveal the standard Plane sign-in form
// (email/password + OTP) in case the cazyweb SSO flow needs to be bypassed.

const CAZYWEB = "https://dashboard.cazyweb.com";

function CazywebSignIn() {
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [stage, setStage] = useState<"email" | "otp">("email");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${CAZYWEB}/api/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        credentials: "include",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error || "Could not send code. Please try again.");
        return;
      }
      setStage("otp");
    } catch {
      setError("Network error. Please check your connection.");
    } finally {
      setLoading(false);
    }
  };

  const verifyAndSso = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const verifyRes = await fetch(`${CAZYWEB}/api/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
        credentials: "include",
      });
      if (!verifyRes.ok) {
        const body = await verifyRes.json().catch(() => ({}));
        setError(body.error || "Invalid or expired code.");
        return;
      }
      const { accessToken } = await verifyRes.json();

      const ssoRes = await fetch(`${CAZYWEB}/api/plane/sso`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      });
      if (!ssoRes.ok) {
        setError("SSO failed. Please try again.");
        return;
      }
      const { redirect_url } = await ssoRes.json();
      window.location.href = redirect_url;
    } catch {
      setError("Network error. Please check your connection.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
      <div className="w-full max-w-sm space-y-6 p-6">
        <div className="text-center">
          <img
            src="/plane-logo.svg"
            alt="cazyweb"
            className="h-10 mx-auto"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
          <h1 className="mt-4 text-xl font-bold">cazyweb PM</h1>
          <p className="mt-2 text-sm text-zinc-400">
            Sign in with your cazyweb account
          </p>
        </div>

        {stage === "email" ? (
          <form onSubmit={requestOtp} className="space-y-3">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@yourcompany.com"
              required
              autoFocus
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={loading || !email}
              className="w-full px-4 py-2 bg-white text-black rounded-lg font-semibold disabled:opacity-60"
            >
              {loading ? "Sending…" : "Send code"}
            </button>
          </form>
        ) : (
          <form onSubmit={verifyAndSso} className="space-y-3">
            <p className="text-xs text-zinc-400">
              Code sent to <span className="text-white">{email}</span>
            </p>
            <input
              type="text"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="6-digit code"
              required
              autoFocus
              inputMode="numeric"
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white tracking-widest text-center focus:border-blue-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={loading || !otp}
              className="w-full px-4 py-2 bg-white text-black rounded-lg font-semibold disabled:opacity-60"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
            <button
              type="button"
              onClick={() => {
                setStage("email");
                setOtp("");
                setError(null);
              }}
              className="w-full text-xs text-zinc-400 hover:text-white"
            >
              Use a different email
            </button>
          </form>
        )}

        {error && (
          <p className="text-xs text-red-400 text-center">{error}</p>
        )}

        <p className="text-center text-xs text-zinc-500">
          <a href="/?fallback=1" className="hover:text-zinc-300">
            Sign in with magic link instead
          </a>
        </p>
      </div>
    </div>
  );
}

function HomePage() {
  // ?fallback=1 reveals the original Plane auth form for emergency/admin use
  const showFallback =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("fallback") === "1";

  if (!showFallback) {
    return <CazywebSignIn />;
  }

  return (
    <DefaultLayout>
      <AuthenticationWrapper pageType={EPageTypes.NON_AUTHENTICATED}>
        <AuthBase authType={EAuthModes.SIGN_IN} />
      </AuthenticationWrapper>
    </DefaultLayout>
  );
}

export default HomePage;
