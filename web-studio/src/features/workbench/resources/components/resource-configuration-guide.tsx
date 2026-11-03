import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'

type ResourceConfigurationGuideProps = {
  children: ReactNode
  title: string
}

export function ResourceConfigurationGuide({
  children,
  title,
}: ResourceConfigurationGuideProps) {
  return (
    <details className="group rounded-md border border-border/50 bg-background/30 px-3 py-2">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs font-medium text-foreground marker:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
        {title}
      </summary>
      <div className="mt-2 space-y-2 border-t border-border/40 pt-2 text-xs text-muted-foreground">
        {children}
      </div>
    </details>
  )
}
