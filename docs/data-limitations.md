# Dataset limitations

- The customer population and all banking relationships are synthetic. Results must not be presented as Lloyds customer behaviour.
- UCI Online Retail II is retail invoice data, not bank merchant data. It is used only to seed description and amount variation for a subset of `OTHER` transactions.
- The London sample is a bounded slice of one official partition, not the full 5,567-household population. It seeds electricity-profile variation but is not used for population inference.
- Smart-meter readings are from 2011 to 2014 and are scaled into synthetic 2025-2026 profiles. They do not represent current tariffs or measured current consumption.
- Product take-up is simulated from plausible relationships plus noise. Reported model metrics will describe performance on synthetic labels only.
- Eligibility rules are not encoded in the labels. Propensity and eligibility remain separate.
- Missing values and conflicts are deliberately included for scenario testing.
- Age, income and region distributions are illustrative and are not calibrated to Lloyds or the UK population.
- Emissions factors are official 2026 UK factors, but the eventual carbon engine must still document formulas, system boundaries and assumptions.
- Paperless adoption is reported separately from carbon reduction unless a documented lifecycle method is later added.
