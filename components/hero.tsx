import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-32 pb-20 md:pt-40 md:pb-32">
      {/* Background Grid */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,hsl(var(--border))_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--border))_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_110%)]" />
      
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          {/* Badge */}
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-secondary px-4 py-1.5">
            <span className="text-xs font-medium text-primary">New</span>
            <span className="text-xs text-muted-foreground">AI 기반 자동 데이터 정제 기능 출시</span>
          </div>

          {/* Main Heading */}
          <h1 className="text-balance text-4xl font-bold tracking-tight text-foreground sm:text-5xl md:text-6xl lg:text-7xl">
            데이터 전처리의
            <br />
            <span className="text-primary">새로운 기준</span>
          </h1>

          {/* Subheading */}
          <p className="mx-auto mt-6 max-w-2xl text-pretty text-lg text-muted-foreground md:text-xl">
            복잡한 데이터를 간단하게. 클릭 몇 번으로 데이터 정제, 변환, 분석을 완료하세요.
            코딩 없이도 전문가 수준의 데이터 파이프라인을 구축할 수 있습니다.
          </p>

          {/* CTA Buttons */}
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              href="/signup"
              className="group flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/90"
            >
              무료로 시작하기
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="#demo"
              className="flex items-center gap-2 rounded-lg border border-border bg-background px-6 py-3 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
            >
              데모 보기
            </Link>
          </div>

          {/* Stats */}
          <div className="mt-16 grid grid-cols-2 gap-8 md:grid-cols-4">
            {[
              { value: "10K+", label: "활성 사용자" },
              { value: "500M+", label: "처리된 데이터 행" },
              { value: "98%", label: "정확도" },
              { value: "5x", label: "작업 속도 향상" },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-2xl font-bold text-foreground md:text-3xl">{stat.value}</div>
                <div className="mt-1 text-sm text-muted-foreground">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Preview Window */}
        <div className="relative mx-auto mt-20 max-w-5xl">
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
            {/* Window Header */}
            <div className="flex items-center gap-2 border-b border-border bg-secondary/50 px-4 py-3">
              <div className="h-3 w-3 rounded-full bg-destructive/60" />
              <div className="h-3 w-3 rounded-full bg-yellow-500/60" />
              <div className="h-3 w-3 rounded-full bg-green-500/60" />
              <span className="ml-4 text-xs text-muted-foreground">data-pipeline.csv</span>
            </div>
            {/* Window Content */}
            <div className="p-6">
              <div className="grid grid-cols-4 gap-4 text-xs">
                <div className="rounded-lg bg-secondary p-4">
                  <div className="mb-2 font-medium text-foreground">데이터 입력</div>
                  <div className="space-y-1 text-muted-foreground">
                    <div>CSV, Excel, JSON</div>
                    <div>API 연동</div>
                  </div>
                </div>
                <div className="rounded-lg bg-secondary p-4">
                  <div className="mb-2 font-medium text-foreground">데이터 정제</div>
                  <div className="space-y-1 text-muted-foreground">
                    <div>결측치 처리</div>
                    <div>이상치 탐지</div>
                  </div>
                </div>
                <div className="rounded-lg bg-secondary p-4">
                  <div className="mb-2 font-medium text-foreground">데이터 변환</div>
                  <div className="space-y-1 text-muted-foreground">
                    <div>타입 변환</div>
                    <div>스케일링</div>
                  </div>
                </div>
                <div className="rounded-lg bg-secondary p-4">
                  <div className="mb-2 font-medium text-foreground">데이터 출력</div>
                  <div className="space-y-1 text-muted-foreground">
                    <div>다양한 포맷</div>
                    <div>자동 리포트</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          {/* Decorative Glow */}
          <div className="absolute -inset-x-20 -bottom-20 h-40 bg-gradient-to-t from-primary/10 to-transparent blur-3xl" />
        </div>
      </div>
    </section>
  );
}
