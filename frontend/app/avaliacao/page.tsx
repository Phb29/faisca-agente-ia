import { Suspense } from "react";
import { Avaliacao } from "@/components/avaliacao/Avaliacao";

export default function PaginaDaAvaliacao() {
  // A aba fica na URL (`useSearchParams`), e o Next 15 exige um Suspense em volta disso.
  return (
    <Suspense fallback={null}>
      <Avaliacao />
    </Suspense>
  );
}
