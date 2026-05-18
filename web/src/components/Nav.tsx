"use client";

/**
 * Nav — Desktop inline links + mobile bottom bar.
 * Styled to match the Windows viewer dark palette.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard", icon: "📊" },
  { href: "/history", label: "History", icon: "📈" },
  { href: "/alerts", label: "Alerts", icon: "🔔" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <>
      <nav className="hidden md:flex gap-4">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`text-sm font-medium transition-colors duration-200 ${
              pathname === link.href
                ? "text-[#4dabf7]"
                : "text-[#8a96a7] hover:text-[#e4e6eb]"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[#0f1419] border-t border-[#2a3a52] flex justify-around py-2 px-1 z-50">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors duration-200 min-w-[60px] ${
              pathname === link.href
                ? "text-[#4dabf7] bg-[#1a2332]"
                : "text-[#8a96a7]"
            }`}
          >
            <span className="text-lg">{link.icon}</span>
            <span>{link.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
