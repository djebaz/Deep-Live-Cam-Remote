import type { Job } from "./api";
const ACTIVE = ["queued", "running"];
/** Pick the job to monitor after connecting. A saved job that is missing or
 * already terminal must not hide a different job the backend reports active. */
export function chooseJob(
  fetchedSaved: Job | null,
  active: Job[] | undefined,
): { job: Job | null; attachedActive: boolean } {
  if (fetchedSaved && ACTIVE.includes(fetchedSaved.status))
    return { job: fetchedSaved, attachedActive: false };
  if (active?.length) return { job: active[0], attachedActive: true };
  return { job: fetchedSaved, attachedActive: false };
}
