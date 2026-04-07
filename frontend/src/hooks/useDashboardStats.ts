import { dashboard } from "@/lib/api";
import { useApi } from "./useApi";

export function useDashboardStats() {
  return useApi(() => dashboard.stats(), []);
}

export function useActivity() {
  return useApi(() => dashboard.activity(), []);
}
