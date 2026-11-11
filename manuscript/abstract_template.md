<!-- Rendered by: python src/manuscript_tables.py --abstract
     Every {field} comes from results/; nothing here is typed by hand.
     Rewritten for the review revision: tariffs are scenarios, the burden of
     cooking is measured by the extra operating subsidy per cooking household
     (not by the levelised cost), and the range across input assumptions is
     reported next to the base case. -->

Electric cooking is often seen as a burden on solar mini-grids because it adds
a large evening load that needs batteries. We test this for model villages of
300 households on Nkombo Island, Rwanda, and Ringiti Island, Kenya, combining
household demand from national surveys, hourly solar and battery operation,
least-cost sizing in two stages and project finance. Tariffs are scenarios: the
uniform national tariff, as charged on Kenya's public mini-grids, and
site-specific tariffs of the kind private mini-grids charge. Adoption does not
respond to price.

Full adoption lowers the levelised cost of electricity by
{lcoe_reduction_pct_rwanda:.0f}% in Rwanda and {lcoe_reduction_pct_kenya:.0f}%
in Kenya, mostly because per-connection costs are divided by
{cvp_energy_ratio_kenya:.1f} to {cvp_energy_ratio_rwanda:.1f} times as much
energy. At the national tariff it also enlarges the operator's loss, by
{burden_loss_increase_pct_rwanda:.0f}% and {burden_loss_increase_pct_kenya:.0f}%,
because cooking energy costs about US${burden_cooking_cost_per_kwh_100_kenya:.2f}
to {burden_cooking_cost_per_kwh_100_rwanda:.2f}/kWh to supply and sells for
about US${cooking_price_paid_rwanda:.2f}.

The operating subsidy needed rises from US${burden_opsub_0_rwanda:.0f} to
{burden_opsub_100_rwanda:.0f} per connection per year in Rwanda and from
US${burden_opsub_0_kenya:.0f} to {burden_opsub_100_kenya:.0f} in Kenya:
US${burden_incremental_100_rwanda:.0f} and {burden_incremental_100_kenya:.0f}
for each cooking household, or US${carbon_usd_min_all:.0f} to
{carbon_usd_max_all:,.0f} per tonne of CO2 avoided, far above carbon credit
prices. This increment ranges from US${sens_incremental_all_low_kenya:.0f} to
{sens_incremental_all_high_rwanda:.0f} across input assumptions and turns
negative at tariffs above about US$0.50/kWh, where few households could afford
to cook.

Rwanda's block tariff raises a cooking household's average price
{band_factor_year1_rwanda:.1f}-fold. A daytime discount that moved half of
supper cooking would cut battery capacity by
{ens_avoided_battery_pct_phi50_rwanda:.0f} to
{ens_avoided_battery_pct_phi50_kenya:.0f}% but raise the cooking peak by
{ens_peak_cooking_increase_pct_phi50_rwanda:.0f}%.
