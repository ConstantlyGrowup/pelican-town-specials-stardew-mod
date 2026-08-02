import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

export const apiClient = createClient<paths>({
  baseUrl: "",
});
