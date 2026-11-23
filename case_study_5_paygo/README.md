# Case Study 5: PAYGo portfolio analysis

04-782 Energy Data Analytics. Should an investor put money into a Nigerian PAYGo solar company?

`PAYGo_Investment_Analysis.ipynb` builds on the TA's starter notebook. It uses the same cleaning, the same
payment-allocation assumption and the same checks, and it reproduces every worked number from the TA notebook and
the lecture. It then extends the analysis to the whole portfolio.

`Case_5_-_Decision_Briefing.pptx` is the 12-slide decision briefing for the investment committee, in the same
style as the Case 4 deck. It follows the course structure: recommendation, portfolio overview, risk today, repayment, losses, data quality, conditions and next steps. Its charts are native PowerPoint charts, and every slide has speaker notes.

## Running it

1. Put the two course CSVs in `data/` next to the notebook, with these names:
   - `data/261113_contracts_vfinal.csv`
   - `data/261113_payments_vfinal.csv`

   They are not in this repository, because the repository is public and the files are course material.
2. Install pandas, numpy, matplotlib and statsmodels (Python 3.10 or later).
3. Run all cells. It takes about 15 seconds. Figures are saved to `outputs/figures` and tables to `outputs/tables`.

## What the notebook covers

| Section | Content |
|---|---|
| 1 | The TA's data checks reproduced, extra checks, and the cleaning decisions |
| 2 | Original schedule rebuilt exactly from contract terms; measurement functions; TA results reproduced |
| 3 | Sales volume, product mix, deposits, channels, status |
| 4 | KPIs 1–2: portfolio PvP and PvFin, by cohort and over time |
| 5 | Vintage curves: PvP at the same share of the term, all products and Z17 only |
| 6 | KPI 3: day-90 PvP for every monthly cohort (timing bounds and midpoint) |
| 7 | KPIs 4–5: PvP and ownership at 2× term, plus 1× and 1.5×, against GOGLA benchmarks |
| 8 | Does day 90 predict later results? (contract level and cohort level) |
| 9 | Drivers: calendar-time drop, channel, region, deposit, the new large products |
| 10 | Energy access: lockouts, repossessions, ownership |
| 11 | Risk in the open book: outstanding balance, PAR and arrears buckets, lock rate; losses so far (repossessions, write-off proxy) |
| 12 | Forecast of lifetime repayment with a backtest, a stress scenario, and the time value of late payment |
| 13 | Decision and conditions |
| 14 | Final checks |

## Main results

| | Result |
|---|---|
| Portfolio PvP / PvFin at 31 Jul 2026 | 76.4% / 57.7% |
| Day-90 PvP, all 23,765 eligible contracts | 75.0–90.3% (midpoint 86.5%) |
| PvP at 2× term, 4,825 contracts | 93.4–93.7% (GOGLA: 72% overall, 77% West Africa) |
| Ownership at 2× term | 84.8% (GOGLA: 78%) |
| Z17 PvP at 90% of term | 80% for Q4 2023 sales → 60–61% for Q2–Q3 2025 sales |
| Share of monthly dues paid (mid-term contracts) | about 75% in 2024 → about 58% in 2026 |
| Active customers locked out on 10 Aug 2026 | 8,140 of 15,885 (51%) |
| Projected lifetime PvP, 2025 cohorts | about 78–80% |

**Decision:** invest a smaller first amount now, only in products sold with a deposit. Add more only if new cohorts
stop getting worse. Conditions are in Section 13.

All repayment figures are conditional estimates. They assume receipts after the deposit are applied to instalments
due, because the files have monthly cash only, not GOGLA's daily allocation ledger.
