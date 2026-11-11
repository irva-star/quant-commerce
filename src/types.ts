export type Scenario = 'clean' | 'anchor' | 'carbon';
export interface Mandate {
  product_url: string; scenario: Scenario; market_mode:'synthetic'|'live'; market_query:string; max_spend: number; purchase_carbon_cap: number;
  monthly_carbon_cap: number; max_fees: number; no_subscription: boolean; detect_anchor: boolean;
  offset_opt_in: boolean; override_policy: 'strict' | 'reviewable_carbon'; override_acknowledged: boolean;
  override_reason: string; destination: string; cart: { name: string; quantity: number; unit_price: number }[];
}
export interface Offer {id: string;name: string;merchant: string;url: string;price: string;currency:string;match: string;match_reason:string;synthetic: boolean;specifications:Record<string,unknown>}
export interface Evidence {id:string;field:string;value:string;url:string;selector:string;captured_at:string;synthetic:boolean;sha256:string}
export interface Audit {
  id:string;created_at:string;mandate:Mandate;decision:'PASS'|'BLOCK'|'REVIEW';
  product:{name:string;sku:string;merchant:string;url:string;advertised:string;reference:string|null;final:string;mass_kg:number;shipment_kg:number;origin:string;destination:string;mode:string;distance_km:number;controlled:boolean;synthetic:boolean};
  fiat:{item:number;shipping:number;tax:number;fees:number;merchant_total:number;offset:number;total:number;monthly_settled:number};
  market:{original_price:number|null;currency:string;price_difference_pct:number|null;median:number|null;spread:number|null;reference_deviation_pct:number|null;suspicious_anchor:boolean;sample_size:number;alternatives:Offer[];basis:string};
  carbon:{material_kg:number|null;manufacturing_kg:number|null;embodied_kg:number|null;shipping_kg:number|null;gross_kg:number|null;monthly_used:number;monthly_remaining:number;monthly_projected:number|null;offset_amount:number;credited_kg:number;offset_requested_kg:number;offset_partner:string;offset_price_per_tonne:number;offset_mode:string;missing:string[];methodology:string;uncertainty:string;factors:{name:string;value:number|null;unit:string;source:string;boundary:string}[]};
  persona:{mode:string;clean_price:number|null;personalized_price:number|null;delta:number|null;variable:string;limitations:string};
  channel3:{mode:string;detail:string;source:string;http_status?:number|null;search_http_status?:number|null;lookup_http_status?:number|null;product_count?:number;offer_count?:number;query?:string|null;error_code?:string|null;retry_after_seconds?:number|null;fallback_note?:string;partial?:boolean};
  epistemic:{mode:string;score:number;detail:string;model:string|null;scoring:string;uncertainty:string;claims:{claim:string;verdict:string;explanation:string;source_ids:string[]}[]};
  findings:{code:string;severity:string;message:string}[]; offers:Offer[];evidence:Evidence[];
}
export interface Health {paypal_configured:boolean;channel3_configured:boolean;llm_configured:boolean;ledger:{carbon:number;fiat:number}}

export interface PayPalCheckout {
  audit_id:string;order_id:string;approval_url:string;amount:string;currency:string;mode:string;
  paypal_status:string;approval_verified:boolean;capture_completed:boolean;audit_expired:boolean;warning:string|null;
}
