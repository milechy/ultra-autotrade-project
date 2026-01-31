import type { AppProps } from "next/app";
import { AuthProvider } from "../lib/auth";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <AuthProvider>
      <Component {...pageProps} />
    </AuthProvider>
  );
}
