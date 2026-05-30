import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";
import { Nav } from "./components/Nav";

/*
 * Fonts (ink-cobalt-paper v2.0):
 *   serif display headlines -> Fraunces, weight 300, sentence-case
 *   mono labels/dates       -> IBM Plex Mono (400, 500), UPPERCASE in CSS
 *   body sans               -> Inter (400, 500), left-aligned
 * Multi-word Google fonts use an underscore import name.
 */
const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["300"],
  display: "swap",
  variable: "--font-fraunces",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-mono-plex",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "First Issue · Knowledge Graph",
  description:
    "Knowledge-graph explorer for the Costa Rica 1863 First Issue — Mena 2018 catalog, Scott equivalents, and grounded literature evidence.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${fraunces.variable} ${ibmPlexMono.variable}`}
    >
      <body>
        <Nav />
        {children}
      </body>
    </html>
  );
}
