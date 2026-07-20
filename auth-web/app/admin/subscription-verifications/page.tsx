// Thin standalone-route wrapper - the actual UI lives in
// components/SubscriptionVerificationsPanel.tsx so it can also be embedded
// inline in the main dashboard (see DashboardContent.tsx).
import SubscriptionVerificationsPanel from '../../../components/SubscriptionVerificationsPanel'

export default function SubscriptionVerificationsPage() {
    return <SubscriptionVerificationsPanel />
}
