import type { Metadata } from "next";
import { SessionProvider } from "@/lib/session";
import "./globals.css";
import "./operations.css";

export const metadata: Metadata = {
  title: "RailSync AI | Integrated Maintenance Planning",
  description: "SIH 2026 PS26027 prototype maintenance block planning",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><SessionProvider>{children}</SessionProvider></body></html>;
}
