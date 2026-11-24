import type { Metadata } from "next";
import Chat from "./components/Chat";
import StructuredData from "./structured-data";

/*
 * The site opens directly on the question box: ask about any Costa Rican stamp
 * issue and read the evidence. The explorer of the First Issue graph stays under
 * /research for local research use; the hosted site does not ship it.
 */
// the site's root. Next writes it as the origin with no slash ("https://oxcart.chat"), the same address as the
// sitemap's "https://oxcart.chat/": an https address with an empty path has the path "/"
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function Page() {
  return (
    <>
      <StructuredData />
      <Chat />
    </>
  );
}
