import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import AppHeader from "./components/AppHeader";
import AppFooter from "./components/AppFooter";
import { linkPicture, SITE, SITE_DESCRIPTION, SITE_TITLE } from "./link-picture";

/*
 * Fonts, served from files in this repository (app/fonts, see its README):
 *   serif display headlines -> Newsreader (300, 400; normal + italic)
 *   mono labels/dates       -> JetBrains Mono (400, 500, 600)
 *   body sans               -> Inter (400, 500)
 * A build fetches nothing from a font service.
 * CSS variable names below are referenced by globals.css.
 */
const newsreader = localFont({
  src: [
    { path: "./fonts/newsreader-latin-300-normal.woff2", weight: "300", style: "normal" },
    { path: "./fonts/newsreader-latin-300-italic.woff2", weight: "300", style: "italic" },
    { path: "./fonts/newsreader-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/newsreader-latin-400-italic.woff2", weight: "400", style: "italic" },
  ],
  display: "swap",
  variable: "--font-newsreader",
  adjustFontFallback: "Times New Roman",
});

const jetbrainsMono = localFont({
  src: [
    { path: "./fonts/jetbrains-mono-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/jetbrains-mono-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "./fonts/jetbrains-mono-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  variable: "--font-jetbrains-mono",
  adjustFontFallback: false,
});

const inter = localFont({
  src: [
    { path: "./fonts/inter-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/inter-latin-500-normal.woff2", weight: "500", style: "normal" },
  ],
  display: "swap",
  variable: "--font-inter",
  adjustFontFallback: "Arial",
});


// the tab's icon is app/icon.svg (Next's file convention); the picture a link shows, app/link-picture.ts
export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  ...linkPicture(SITE_TITLE, SITE_DESCRIPTION, "/"),
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
