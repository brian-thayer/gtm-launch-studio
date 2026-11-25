import { useState } from "react";
import { ActivityFeed } from "@/components/ActivityFeed";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ActivityScope } from "@/hooks/useActivity";
import { can, useMe } from "@/hooks/useMe";

/**
 * Everyone's activity needs `audit:read`; "My activity" is open to any signed-in user. Without the
 * permission the first tab isn't offered. If the permission is withdrawn later, the server answers 403 and
 * the feed shows the forbidden page.
 */
export function ActivityPage() {
  const { data: me } = useMe();
  const canReadAll = can(me, "audit:read");
  const [tab, setTab] = useState<ActivityScope>(canReadAll ? "all" : "me");
  const activeTab = canReadAll ? tab : "me";

  return (
    <section className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Activity</h1>
      <Tabs value={activeTab} onValueChange={(value) => setTab(value as ActivityScope)}>
        <TabsList>
          {canReadAll && <TabsTrigger value="all">All activity</TabsTrigger>}
          <TabsTrigger value="me">My activity</TabsTrigger>
        </TabsList>
        {canReadAll && (
          <TabsContent value="all" className="pt-4">
            <ActivityFeed scope="all" />
          </TabsContent>
        )}
        <TabsContent value="me" className="pt-4">
          <ActivityFeed scope="me" />
        </TabsContent>
      </Tabs>
    </section>
  );
}
