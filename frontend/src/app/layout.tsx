import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const poppins = Poppins({
  variable: "--font-poppins",
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ADOPSHUN AI",
  description: "Secure enterprise AI communication platform.",
  icons: {
    icon: "/logo-t.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html
        lang="en"
        className={`${inter.variable} ${poppins.variable} h-full antialiased font-sans`}
        suppressHydrationWarning
      >
        <body className="min-h-full flex flex-col font-sans" suppressHydrationWarning>{children}</body>
      </html>
    </ClerkProvider>
  );
}
