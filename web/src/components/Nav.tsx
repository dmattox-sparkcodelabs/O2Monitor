"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/history", label: "History" },
  { href: "/alerts", label: "Alerts" },
  { href: "/settings", label: "Settings" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-4">
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
  );
}
