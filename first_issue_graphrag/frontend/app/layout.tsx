import type { Metadata } from "next";
import { Newsreader, JetBrains_Mono, Inter } from "next/font/google";
import "./globals.css";
import Masthead from "./components/Masthead";
import SiteFooter from "./components/SiteFooter";

/*
 * Fonts (SOCORICO redesign):
 *   serif display headlines -> Newsreader (300, 400; normal + italic)
 *   mono labels/dates       -> JetBrains Mono (400, 500, 600)
 *   body sans               -> Inter (400, 500)
 * Multi-word Google fonts use an underscore import name.
 * CSS variable names below are referenced by globals.css.
 */
const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["300", "400"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-newsreader",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "SOCORICO · The Society for Costa Rica Collectors",
  description:
    "The Society for Costa Rica Collectors — stamps and postal history of Costa Rica. Auctions, The Oxcart journal since 1960, exhibits, literature, and a knowledge-graph research tool for the 1863 First Issue.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${newsreader.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <Masthead />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
