"use client";

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
            className={`text-sm font-medium transition-colors ${
              pathname === link.href ? "text-white" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 flex justify-around py-2 px-1 z-50">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors min-w-[60px] ${
              pathname === link.href
                ? "text-white bg-gray-800"
                : "text-gray-500"
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
