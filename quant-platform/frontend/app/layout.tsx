import "./globals.css";
import type { Metadata } from "next";
import Shell from "@/components/Shell";

export const metadata: Metadata = { title: "Quant Research Platform", description: "Personal investment research & portfolio intelligence" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><Shell>{children}</Shell></body></html>;
}
