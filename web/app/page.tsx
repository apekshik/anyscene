import { Suspense } from "react";
import Shell from "@/components/Shell";

export default function Page() {
  return (
    <Suspense>
      <Shell />
    </Suspense>
  );
}
