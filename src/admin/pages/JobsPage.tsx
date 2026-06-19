import { useQuery } from '@tanstack/react-query';
import { listQueueJobs, type QueueJob } from '@/admin/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { EmptyState } from '@/admin/components/EmptyState';

const STATUS_COLORS: Record<string, string> = {
  queued: 'bg-amber-500/10 text-amber-600 border-amber-200',
  processing: 'bg-blue-500/10 text-blue-600 border-blue-200',
  completed: 'bg-green-500/10 text-green-600 border-green-200',
  failed: 'bg-red-500/10 text-red-600 border-red-200',
  cancelled: 'bg-gray-500/10 text-gray-600 border-gray-200',
};

function useQueueJobs() {
  return useQuery({
    queryKey: ['admin', 'queue'],
    queryFn: () => listQueueJobs(100),
    refetchInterval: 5000,
  });
}

export default function JobsPage() {
  const { data, isLoading, isError } = useQueueJobs();
  const jobs = data?.jobs ?? [];

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }

  if (isError) {
    return <div className="p-6 text-sm text-red-500">Failed to load queue data</div>;
  }

  const counts: Record<string, number> = { queued: 0, processing: 0, completed: 0, failed: 0, cancelled: 0 };
  for (const j of jobs) {
    counts[j.status] = (counts[j.status] || 0) + 1;
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Job Queue</h1>

      {!data?.queue_enabled && (
        <p className="text-sm text-muted-foreground">
          Queue is currently disabled. Set <code>queue_enabled=true</code> in backend config to activate.
        </p>
      )}

      {data?.queue_enabled && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Queued</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-bold">{counts.queued}</p></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Processing</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-bold">{counts.processing}</p></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Completed</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-bold">{counts.completed}</p></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Failed</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-bold">{counts.failed}</p></CardContent>
            </Card>
          </div>

          {jobs.length === 0 ? (
            <EmptyState title="No jobs in the queue" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Position</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job: QueueJob) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-mono text-xs">{job.job_id}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={STATUS_COLORS[job.status]}>{job.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{job.queue_position ?? '—'}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{job.user_id?.slice(0, 12)}…</TableCell>
                    <TableCell className="text-xs">{job.is_stream ? 'Stream' : 'Sync'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(job.created_at * 1000).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}
