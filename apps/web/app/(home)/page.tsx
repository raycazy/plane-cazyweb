/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
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
function CazywebSignIn() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
      <div className="text-center space-y-6">
        <img src="/plane-logo.svg" alt="cazyweb" className="h-12 mx-auto" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
        <h1 className="text-2xl font-bold">cazyweb PM</h1>
        <p className="text-zinc-400 text-sm">Sign in with your cazyweb account to continue.</p>
        <a
          href="https://dashboard.cazyweb.com/login?return_to=https://pm.cazyweb.com/"
          className="inline-block px-6 py-3 bg-white text-black rounded-xl font-semibold hover:bg-zinc-200 transition-colors"
        >
          Sign in via cazyweb
        </a>
      </div>
    </div>
  );
}

function HomePage() {
  // ?fallback=1 reveals the original Plane auth form for emergency/admin use
  const showFallback =
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("fallback") === "1";

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
