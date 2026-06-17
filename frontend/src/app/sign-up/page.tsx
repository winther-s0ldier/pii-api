"use client";
import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-[#FAF9F5] font-sans text-[#2A1F1A] p-4">
      <div className="mb-6">
        <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="h-12 w-auto object-contain" />
      </div>
      <SignUp 
        routing="hash" 
        signInUrl="/" 
        forceRedirectUrl="/" 
        appearance={{
          elements: {
            formButtonPrimary: "bg-[#F3694C] hover:bg-[#E05A3E] text-white",
          }
        }}
      />
    </div>
  );
}
