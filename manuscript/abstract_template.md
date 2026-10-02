<!-- Rendered by: python src/manuscript_tables.py --abstract
     Every {field} comes from results/; nothing here is typed by hand.
     Restructured (Phase 4) around the corrected numbers: utilisation gain ->
     ToU (with CI) -> household penalty (by year) -> viability, now with the
     costed operating subsidy as the recommendation. -->

Electric cooking is usually framed as a burden on solar mini-grids: a large
evening load that forces battery oversizing. We couple a stochastic household
demand model built from national Multi-Tier Framework microdata with an hourly
dispatch, least-cost sizing and financial model for two islanded lake
communities, Nkombo (Rwanda) and Ringiti (Kenya).

Cooking load raises asset utilisation: levelised cost falls by
{lcoe_reduction_pct_rwanda:.0f}% in Rwanda and {lcoe_reduction_pct_kenya:.0f}%
in Kenya from zero to full adoption. Where half of evening cooking moves into
the afternoon under a daytime discount, storage falls by
{ens_avoided_battery_pct_rwanda:.0f}% (95% CI {ens_avoided_battery_pct_rwanda_lo:.0f}–{ens_avoided_battery_pct_rwanda_hi:.0f})
in Rwanda and {ens_avoided_battery_pct_kenya:.0f}% ({ens_avoided_battery_pct_kenya_lo:.0f}–{ens_avoided_battery_pct_kenya_hi:.0f})
in Kenya across {ens_n_seeds} demand realisations, but the coincident cooking peak rises.

Neither gain reaches the operator. At regulated tariffs revenue does not
cover operating cost, so no capital grant achieves a commercial return; the
cost-reflective tariff is {multiple_base_rwanda:.1f} times the regulated rate
in Rwanda and {multiple_base_kenya:.1f} in Kenya. Closing the gap with an
operating subsidy costs about US${opsub_rwanda:.0f} per connection per year in
Rwanda and US${opsub_kenya:.0f} in Kenya. Households are penalised too: under
Rwanda's telescopic bands the blended rate rises
{band_factor_year1_rwanda:.1f}-fold on adoption, growing to
{band_factor_final_rwanda:.1f}-fold as consumption grows, against
{band_factor_year1_kenya:.1f}-fold in Kenya.

Clean-cooking and tariff policy work against each other, and capital
subsidy, the sector's dominant instrument, cannot reconcile them.
