import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function CTA() {
  return (
    <section className="border-t border-border bg-secondary/30 py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-2xl bg-foreground px-6 py-16 text-center md:px-16 md:py-24">
          {/* Background Pattern */}
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,hsl(var(--background)/0.05)_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--background)/0.05)_1px,transparent_1px)] bg-[size:2rem_2rem]" />
          
          <div className="relative">
            <h2 className="text-balance text-3xl font-bold tracking-tight text-background sm:text-4xl md:text-5xl">
              지금 바로 시작하세요
            </h2>
            <p className="mx-auto mt-6 max-w-2xl text-pretty text-lg text-background/70">
              무료로 시작하고, 필요에 따라 확장하세요. 
              신용카드 없이 모든 기능을 체험해 보실 수 있습니다.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link
                href="/signup"
                className="group flex items-center gap-2 rounded-lg bg-primary px-8 py-4 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/90"
              >
                무료로 시작하기
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/contact"
                className="flex items-center gap-2 rounded-lg border border-background/20 px-8 py-4 text-sm font-medium text-background transition-colors hover:bg-background/10"
              >
                문의하기
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
