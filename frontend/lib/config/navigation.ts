import { getPrimaryProductDomains, type ProductDomain } from "@/lib/config/product-navigation";

export type NavigationItem = ProductDomain;

export const SIDEBAR_NAV_ITEMS: NavigationItem[] = getPrimaryProductDomains();
