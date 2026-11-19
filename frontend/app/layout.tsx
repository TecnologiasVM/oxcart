import type { Metadata } from "next";
import { Newsreader, JetBrains_Mono, Inter } from "next/font/google";
import "./globals.css";
import AppHeader from "./components/AppHeader";
import AppFooter from "./components/AppFooter";

/*
 * Fonts:
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
  title: "Oxcart · Costa Rica philately knowledge graph",
  description:
    "Research demo: ask about any Costa Rican stamp issue and read the evidence, from the catalogue graph and the philatelic literature. Retrieval only, no generated answers.",
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
        <AppHeader />
        {children}
        <AppFooter />
      </body>
    </html>
  );
}
