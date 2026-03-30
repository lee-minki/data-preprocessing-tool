import { Zap, Shield, BarChart3, Layers, RefreshCw, Code2 } from "lucide-react";

const features = [
  {
    icon: Zap,
    title: "빠른 처리 속도",
    description: "대용량 데이터도 빠르게 처리합니다. 병렬 처리 기술로 기존 대비 5배 빠른 속도를 경험하세요.",
  },
  {
    icon: Shield,
    title: "데이터 품질 보장",
    description: "AI 기반 이상치 탐지와 자동 수정으로 데이터 품질을 보장합니다. 정확도 98% 이상.",
  },
  {
    icon: BarChart3,
    title: "시각화 대시보드",
    description: "처리 중인 데이터를 실시간으로 확인하세요. 직관적인 차트와 그래프로 인사이트를 얻으세요.",
  },
  {
    icon: Layers,
    title: "다양한 포맷 지원",
    description: "CSV, Excel, JSON, Parquet 등 다양한 데이터 포맷을 지원합니다. 손쉬운 변환이 가능합니다.",
  },
  {
    icon: RefreshCw,
    title: "자동화 파이프라인",
    description: "반복적인 작업을 자동화하세요. 스케줄링 기능으로 정기적인 데이터 처리를 설정할 수 있습니다.",
  },
  {
    icon: Code2,
    title: "노코드 인터페이스",
    description: "코딩 없이 드래그 앤 드롭으로 복잡한 데이터 파이프라인을 구축할 수 있습니다.",
  },
];

export function Features() {
  return (
    <section id="features" className="border-t border-border bg-secondary/30 py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            강력한 기능
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            데이터 전처리에 필요한 모든 기능을 제공합니다
          </p>
        </div>

        {/* Features Grid */}
        <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="group rounded-xl border border-border bg-card p-6 transition-all hover:border-primary/50 hover:shadow-lg"
            >
              <div className="mb-4 inline-flex rounded-lg bg-primary/10 p-3">
                <feature.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-2 text-lg font-semibold text-foreground">{feature.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
