import type { Metadata } from "next";
import HowItWorks from "../components/how/HowItWorks";

/*
 * "How it works": what the demo is, the path of a question, and how it was measured. A static page: it
 * calls nothing, so it reads the same while the service sleeps. Its language is the one the visitor chose
 * on the question page, kept in this browser.
 */
export const metadata: Metadata = {
  title: "How it works · Oxcart",
  description:
    "How Oxcart answers a question about Costa Rican stamps from a catalogue graph and the philatelic literature, and how its answers were measured.",
};

export default function Page() {
  return <HowItWorks />;
}
