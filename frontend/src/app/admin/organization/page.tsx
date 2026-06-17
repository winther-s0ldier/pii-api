"use client";

import { OrganizationProfile, OrganizationSwitcher, useAuth } from "@clerk/nextjs";
import { Shield } from "lucide-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

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
