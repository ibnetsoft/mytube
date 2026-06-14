import "./globals.css";

export const metadata = {
  title: "PICADILLY STUDIO SaaS",
  description: "Next-Generation AI Video Production Platform",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
