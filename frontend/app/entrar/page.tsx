import { Suspense } from "react";
import { FormularioDeLogin } from "@/components/acesso/FormularioDeLogin";

export default function PaginaDeEntrada() {
  // O `proximo` vem da URL (`useSearchParams`), e o Next 15 exige um Suspense em volta disso.
  return (
    <Suspense fallback={null}>
      <FormularioDeLogin />
    </Suspense>
  );
}
