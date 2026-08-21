"use client";

import { useActionState } from "react";
import { login } from "./actions";

export default function LoginPage() {
  const [state, formAction, pending] = useActionState(login, undefined);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form
        action={formAction}
        className="w-full max-w-sm rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6"
      >
        <h1 className="mb-1 text-lg font-bold tracking-tight">Mikayla&apos;s Weather Bot</h1>
        <p className="mb-5 text-xs text-[var(--foreground-secondary)]">
          Enter the password to view the dashboard.
        </p>
        <label htmlFor="password" className="mb-1 block text-xs font-medium text-[var(--foreground-secondary)]">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoFocus
          required
          className="mb-3 w-full rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent-forecast)]"
        />
        {state?.error && <p className="mb-3 text-xs text-[var(--negative)]">{state.error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-sm bg-[var(--accent-forecast)] py-2 text-sm font-medium text-[#0b0e12] disabled:opacity-50"
        >
          {pending ? "Checking…" : "Enter"}
        </button>
      </form>
    </div>
  );
}
