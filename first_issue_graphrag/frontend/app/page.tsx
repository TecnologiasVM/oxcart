import { redirect } from "next/navigation";

/*
 * The demo is the Research section (Overview, Explore, Query, Mena Catalogue).
 * The site root sends visitors there.
 */
export default function Page() {
  redirect("/research");
}
