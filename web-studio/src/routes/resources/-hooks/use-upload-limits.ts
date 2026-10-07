import * as React from 'react'

import { LEGACY_UPLOAD_LIMITS, fetchUploadLimits } from '../-lib/upload-limits'
import type { UploadLimits } from '../-lib/upload-limits'

/** Server upload limits; the legacy limits apply until (or unless) the server answers. */
export function useUploadLimits(): UploadLimits {
  const [limits, setLimits] = React.useState<UploadLimits>(LEGACY_UPLOAD_LIMITS)

  React.useEffect(() => {
    let active = true
    void fetchUploadLimits().then((next) => {
      if (active) setLimits(next)
    })
    return () => {
      active = false
    }
  }, [])

  return limits
}
