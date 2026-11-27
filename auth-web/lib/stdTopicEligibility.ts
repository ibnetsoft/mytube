export function isAvailablePendingTopic(topic: any, requesterEmail = ''): boolean {
    const assignee = String(topic?.assigned_employee_email || '').trim().toLowerCase()
    const requester = String(requesterEmail || '').trim().toLowerCase()
    const assignedAt = topic?.assigned_at
    const hasAssignedAt = assignedAt !== null && assignedAt !== undefined && String(assignedAt).trim().length > 0
    return String(topic?.status || '') === 'pending' && !hasAssignedAt && (!assignee || Boolean(requester && assignee === requester))
}

export function mergeAvailableTopics(reserved: any[], recommendations: any[], limit: number): any[] {
    const unique = new Map<string, any>()
    for (const topic of [...reserved, ...recommendations]) {
        if (!unique.has(String(topic.id))) unique.set(String(topic.id), topic)
    }
    return [...unique.values()].slice(0, limit)
}
