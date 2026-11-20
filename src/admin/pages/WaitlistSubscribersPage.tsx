import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AdminPageError } from '@/admin/components/AdminPageStates';
import { EmptyState } from '@/admin/components/EmptyState';
import { useWaitlistSubscribers } from '@/admin/hooks/useAdminData';
import { fmtDateTime } from '@/admin/lib/formatters';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';

/**
 * Owner view of consented launch-update subscribers.
 *
 * Read-only on purpose: addresses are stored now, but no email sending or
 * owner notification is configured. Do not add a "send" control here until a
 * verified sender, destination and unsubscribe flow exist.
 */
export default function WaitlistSubscribersPage() {
  const { data, isLoading, isError, error, refetch } = useWaitlistSubscribers();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <AdminPageError
        title="Subscribers unavailable"
        message={error instanceof Error ? error.message : 'Could not load launch subscribers.'}
        onRetry={() => void refetch()}
      />
    );
  }

  const rows = data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Launch subscribers</h1>
          <p className="text-sm text-muted-foreground">
            Consented launch-update opt-ins, newest first. Owner-only; no public read path exists.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Refresh
        </Button>
      </div>

      <div className="rounded-lg border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
        Email sending is not configured. These addresses are collected only; no update or owner
        notification is being sent.
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {rows.length === 0 ? 'No subscribers yet' : `${rows.length} subscriber${rows.length === 1 ? '' : 's'}`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <EmptyState
              title="No subscribers yet"
              hint="Signups from the public guides appear here after they are stored."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Consented launch-update subscribers, newest first</caption>
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th scope="col" className="py-2 pr-4 font-medium">Email</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Source</th>
                    <th scope="col" className="py-2 font-medium">Consented</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b border-border/60 last:border-0">
                      <td className="py-2 pr-4 break-all">{row.email}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{row.source ?? 'unknown'}</td>
                      <td className="py-2 whitespace-nowrap text-muted-foreground">
                        {fmtDateTime(row.consented_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
