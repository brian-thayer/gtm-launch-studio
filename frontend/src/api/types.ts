/**
 * Short names for the generated schema types. These are aliases, not hand-written shapes: when the API
 * changes, `npm run gen:api` changes them, and the compiler points at every place that has to follow.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type ActivityEvent = Schemas["ActivityEvent"];
export type ActivityPage = Schemas["ActivityPage"];
export type AuthOptions = Schemas["AuthOptions"];
export type DevUserOption = Schemas["DevUserOption"];
export type Me = Schemas["Me"];
export type Permission = Schemas["Permission"];
