"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, X, Database } from "lucide-react";

export function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2">
            <Database className="h-6 w-6 text-primary" />
            <span className="text-lg font-semibold text-foreground">DataPrep</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden items-center gap-8 md:flex">
            <Link href="#features" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              기능
            </Link>
            <Link href="#workflow" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              워크플로우
            </Link>
            <Link href="#pricing" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              가격
            </Link>
            <Link href="#docs" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              문서
            </Link>
          </nav>

          {/* CTA Buttons */}
          <div className="hidden items-center gap-3 md:flex">
            <Link
              href="/login"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              로그인
            </Link>
            <Link
              href="/signup"
              className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-foreground/90"
            >
              시작하기
            </Link>
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="md:hidden"
            aria-label="Toggle menu"
          >
            {isMenuOpen ? (
              <X className="h-6 w-6 text-foreground" />
            ) : (
              <Menu className="h-6 w-6 text-foreground" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile Navigation */}
      {isMenuOpen && (
        <div className="border-t border-border bg-background md:hidden">
          <nav className="flex flex-col gap-4 px-4 py-6">
            <Link href="#features" className="text-sm text-muted-foreground">
              기능
            </Link>
            <Link href="#workflow" className="text-sm text-muted-foreground">
              워크플로우
            </Link>
            <Link href="#pricing" className="text-sm text-muted-foreground">
              가격
            </Link>
            <Link href="#docs" className="text-sm text-muted-foreground">
              문서
            </Link>
            <div className="flex flex-col gap-3 pt-4">
              <Link href="/login" className="text-sm text-muted-foreground">
                로그인
              </Link>
              <Link
                href="/signup"
                className="rounded-lg bg-foreground px-4 py-2 text-center text-sm font-medium text-background"
              >
                시작하기
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
