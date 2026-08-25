import { Suspense, type ComponentType } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BrandedSpinner } from '@/components/common/BrandedSpinner';

export interface GroupTab {
  id: string;
  label: string;
  Component: ComponentType;
}

/**
 * Renders several admin pages as tabs of one page. The active tab lives in
 * `?tab=`, so old deep links can redirect straight to a tab.
 */
export function GroupedPage({ tabs }: { tabs: GroupTab[] }) {
  const [params, setParams] = useSearchParams();
  const active = tabs.find((t) => t.id === params.get('tab')) ?? tabs[0];
  const Active = active.Component;

  return (
    <div className="space-y-6">
      <Tabs
        value={active.id}
        onValueChange={(id) => setParams(id === tabs[0].id ? {} : { tab: id }, { replace: true })}
      >
        <TabsList className="flex-wrap h-auto">
          {tabs.map((t) => (
            <TabsTrigger key={t.id} value={t.id} className="min-h-[36px]">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <Suspense fallback={<BrandedSpinner />}>
        <Active />
      </Suspense>
    </div>
  );
}

export default GroupedPage;
