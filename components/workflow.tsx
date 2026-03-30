import { Upload, Settings, Play, Download } from "lucide-react";

const steps = [
  {
    icon: Upload,
    step: "01",
    title: "데이터 업로드",
    description: "CSV, Excel, JSON 등 다양한 형식의 데이터를 드래그 앤 드롭으로 업로드하세요.",
  },
  {
    icon: Settings,
    step: "02",
    title: "전처리 설정",
    description: "결측치 처리, 이상치 제거, 데이터 변환 등 원하는 전처리 옵션을 선택하세요.",
  },
  {
    icon: Play,
    step: "03",
    title: "실행 및 미리보기",
    description: "설정한 파이프라인을 실행하고 실시간으로 결과를 확인하세요.",
  },
  {
    icon: Download,
    step: "04",
    title: "결과 다운로드",
    description: "정제된 데이터를 원하는 형식으로 내보내세요. 자동 리포트도 생성됩니다.",
  },
];

export function Workflow() {
  return (
    <section id="workflow" className="py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            간단한 워크플로우
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            4단계로 데이터 전처리를 완료하세요
          </p>
        </div>

        {/* Steps */}
        <div className="relative mt-16">
          {/* Connection Line */}
          <div className="absolute left-1/2 top-0 hidden h-full w-px -translate-x-1/2 bg-border lg:block" />
          
          <div className="grid gap-8 lg:grid-cols-4">
            {steps.map((step, index) => (
              <div key={step.step} className="relative">
                {/* Step Card */}
                <div className="flex flex-col items-center text-center">
                  {/* Icon Container */}
                  <div className="relative z-10 mb-6 flex h-16 w-16 items-center justify-center rounded-full border-2 border-primary bg-background">
                    <step.icon className="h-7 w-7 text-primary" />
                  </div>
                  
                  {/* Step Number */}
                  <div className="mb-2 text-sm font-medium text-primary">{step.step}</div>
                  
                  {/* Title */}
                  <h3 className="mb-2 text-lg font-semibold text-foreground">{step.title}</h3>
                  
                  {/* Description */}
                  <p className="text-sm leading-relaxed text-muted-foreground">{step.description}</p>
                </div>

                {/* Arrow (visible on mobile) */}
                {index < steps.length - 1 && (
                  <div className="my-4 flex justify-center lg:hidden">
                    <div className="h-8 w-px bg-border" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
