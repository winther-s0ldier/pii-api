"use client";

import { OrganizationProfile, OrganizationSwitcher, useAuth } from "@clerk/nextjs";
import { Shield, Upload, CheckCircle, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

interface BulkInviteResult {
  sent: string[];
  failed: string[];
  total: number;
}

function BulkInviteSection() {
  const { getToken } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<BulkInviteResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("loading");
    setResult(null);
    setErrorMsg("");
    try {
      const token = await getToken();
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/admin/invite/bulk`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail || res.statusText);
      }
      setResult(await res.json());
      setStatus("done");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Upload failed");
      setStatus("error");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="w-full max-w-4xl bg-white border border-[#E0D9C8] rounded-xl p-6 mb-6">
      <h2 className="text-lg font-semibold mb-1">Bulk Invite via CSV</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Upload a CSV with one email per row. Invitations will be sent automatically.
      </p>

      <label
        className={`flex items-center gap-3 cursor-pointer border-2 border-dashed rounded-lg px-5 py-4 transition-colors ${
          status === "loading"
            ? "border-[#C8BBA8] bg-[#F5F2EC] cursor-not-allowed"
            : "border-[#C8BBA8] hover:border-[#8B6F4E] hover:bg-[#FAF9F5]"
        }`}
      >
        <Upload size={20} className="text-[#8B6F4E] shrink-0" />
        <span className="text-sm font-medium text-[#5C4A3A]">
          {status === "loading" ? "Sending invitations…" : "Click to upload CSV"}
        </span>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          disabled={status === "loading"}
          onChange={handleFile}
        />
      </label>

      {status === "done" && result && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center gap-2 text-sm text-green-700">
            <CheckCircle size={16} />
            <span>{result.sent.length} invitation{result.sent.length !== 1 ? "s" : ""} sent</span>
          </div>
          {result.failed.length > 0 && (
            <div className="flex items-start gap-2 text-sm text-red-600">
              <XCircle size={16} className="mt-0.5 shrink-0" />
              <span>
                {result.failed.length} failed:{" "}
                <span className="font-mono">{result.failed.join(", ")}</span>
              </span>
            </div>
          )}
        </div>
      )}

      {status === "error" && (
        <div className="mt-4 flex items-center gap-2 text-sm text-red-600">
          <XCircle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}
    </div>
  );
}

export default function AdminOrganizationPage() {
  const { isLoaded, orgId } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded && !orgId) {
      router.replace('/admin');
    }
  }, [isLoaded, orgId, router]);

  if (!isLoaded || !orgId) {
    return (
      <div className="min-h-screen bg-[#FAF9F5] p-8 flex flex-col items-center justify-center font-sans text-[#2A1F1A]">
        <div className="text-lg font-medium">Redirecting to Admin...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAF9F5] p-8 flex flex-col items-center font-sans text-[#2A1F1A]">
      <div className="max-w-4xl w-full mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Shield className="text-primary" size={32} />
            Organization Management
          </h1>
          <p className="text-muted-foreground mt-2">
            Invite employees, manage admin roles, and configure organization settings.
          </p>
        </div>
        <div>
          <OrganizationSwitcher
            hidePersonal={true}
            appearance={{
              elements: {
                organizationSwitcherTrigger: "py-2 px-4 bg-white border border-[#E0D9C8] rounded-lg shadow-sm"
              }
            }}
          />
        </div>
      </div>

      <BulkInviteSection />

      <div className="w-full max-w-4xl flex justify-center">
        <OrganizationProfile
          routing="hash"
          appearance={{
            elements: {
              rootBox: "w-full max-w-none flex justify-center",
            }
          }}
        />
      </div>
    </div>
  );
}
