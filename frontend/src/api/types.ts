/**
 * Short names for the generated schema types. These are aliases, not hand-written shapes: when the API
 * changes, `npm run gen:api` changes them, and the compiler points at every place that has to follow.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type ActivityEvent = Schemas["ActivityEvent"];
export type ActivityPage = Schemas["ActivityPage"];
export type AssetRef = Schemas["AssetRefOut"];
export type AssetTypeResponse = Schemas["AssetTypeResponse"];
export type AuthOptions = Schemas["AuthOptions"];
export type Brand = Schemas["Brand"];
export type CatalogResponse = Schemas["CatalogResponse"];
export type DevUserOption = Schemas["DevUserOption"];
export type Issue = Schemas["Issue"];
export type MatrixResponse = Schemas["MatrixResponse"];
export type Me = Schemas["Me"];
export type Permission = Schemas["Permission"];
export type ReloadResponse = Schemas["ReloadResponse"];
export type RoleInfo = Schemas["RoleInfo"];
export type TierOut = Schemas["TierOut"];
