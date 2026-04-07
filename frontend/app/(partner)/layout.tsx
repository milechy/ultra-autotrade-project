// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { PartnerProviders } from '@/components/providers/PartnerProviders'

export default function PartnerLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <PartnerProviders>{children}</PartnerProviders>
}
