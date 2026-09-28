import Dashboard from "../components/dashboard";
import { getDashboardPayload } from "../lib/dashboard-data";

export const dynamic = "force-dynamic";

export default async function Page() {
  const payload = await getDashboardPayload();
  return <Dashboard initialData={payload} />;
}
